"""anyspark.review — 拟人化评审团测试（纯机制层，fake model，不依赖真实 LLM）。"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from anyspark.core import Message, ModelOutput
from anyspark.review import (
    ReviewerDef,
    ReviewPanel,
    ReviewReport,
    ScoreDim,
)
from anyspark.review.panel import _parse_review, run_review
from anyspark.review.parse import _to_str_list, extract_json, extract_scores, parse_review_json


# ──────────────────────────────────────────────────────────────
# 评审员 YAML 加载
# ──────────────────────────────────────────────────────────────
def test_default_reviewers_loaded() -> None:
    panel = ReviewPanel()
    reviewers = panel.list_reviewers()
    ids = {r["id"] for r in reviewers}
    assert {
        "screenwriter",
        "literary_editor",
        "logic_auditor",
        "thriller_reader",
        "nitpicker",
    } <= ids
    assert "foreshadow_auditor" in ids


def test_reviewer_fields_parsed() -> None:
    panel = ReviewPanel()
    sw = panel.get_reviewer("screenwriter")
    assert sw is not None
    assert sw.name == "编剧"
    assert sw.avatar == "🎬"
    assert sw.category == "professional"
    assert sw.active is True
    assert "资深影视编剧" in sw.persona
    assert len(sw.scoring_dimensions) == 5
    weights = sum(d.weight for d in sw.scoring_dimensions)
    assert weights == pytest.approx(1.0)


def test_context_keys_parsed() -> None:
    panel = ReviewPanel()
    logic = panel.get_reviewer("logic_auditor")
    assert logic is not None
    assert logic.context_keys == ["check_report"]
    fa = panel.get_reviewer("foreshadow_auditor")
    assert fa is not None
    assert fa.context_keys == ["foreshadow"]
    assert fa.active is False  # 续写专项默认关


def test_user_dir_overrides_system(tmp_path: Path) -> None:
    panel = ReviewPanel()
    custom = tmp_path / "reviewers"
    custom.mkdir()
    (custom / "screenwriter.yaml").write_text(
        """
- id: screenwriter
  name: 改剧本的
  persona: 我改了人设
  avatar: 🎭
""".lstrip(),
        encoding="utf-8",
    )
    panel.add_dir(custom)
    sw = panel.get_reviewer("screenwriter")
    assert sw is not None
    assert sw.name == "改剧本的"  # 用户覆盖系统
    assert sw.custom is True


def test_broken_yaml_does_not_crash(tmp_path: Path) -> None:
    panel = ReviewPanel()
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "broken.yaml").write_text(": : : 不是合法yaml", encoding="utf-8")
    (bad / "no_id.yaml").write_text("- name: 没id的\n  persona: x", encoding="utf-8")
    panel.add_dir(bad)  # 不抛异常
    assert panel.list_reviewers()  # 系统评审员仍在


# ──────────────────────────────────────────────────────────────
# 加权平均
# ──────────────────────────────────────────────────────────────
def test_weighted_overall() -> None:
    r = ReviewerDef(
        id="x",
        name="X",
        persona="p",
        scoring_dimensions=[
            ScoreDim(name="a", weight=0.5),
            ScoreDim(name="b", weight=0.5),
        ],
    )
    assert r.weighted_overall({"a": 8, "b": 6}) == 7.0
    assert r.weighted_overall({"a": 8}) is None  # 维度不齐 → None
    assert r.weighted_overall({}) is None


# ──────────────────────────────────────────────────────────────
# 宽容 JSON 解析
# ──────────────────────────────────────────────────────────────
def test_extract_json_direct() -> None:
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json("[1, 2]") == [1, 2]


def test_extract_json_fence() -> None:
    data = extract_json('```json\n{"a": 1}\n```')
    assert data == {"a": 1}


def test_extract_json_noise() -> None:
    data = extract_json('评审结果如下：\n{"a": 1, "b": [1, 2]} 完毕')
    assert data == {"a": 1, "b": [1, 2]}


def test_extract_json_nested_balanced() -> None:
    raw = '前缀 {"scores": {"结构": 8, "张力": "7"}, "list": [1, {"x": "}"}]} 后缀'
    data = extract_json(raw)
    assert data is not None
    assert data["scores"]["结构"] == 8
    assert data["list"][1]["x"] == "}"


def test_extract_json_invalid() -> None:
    assert extract_json("什么都没有") is None
    assert extract_json("") is None


def test_extract_scores_clamps_range() -> None:
    scores = extract_scores({"scores": {"a": 8, "b": 15, "c": -3, "d": "7.5", "e": None}})
    assert scores == {"a": 8, "d": 7.5}  # 越界/非数值被丢弃


def test_to_str_list_handles_text() -> None:
    assert _to_str_list("1. 第一\n2. 第二") == ["第一", "第二"]
    assert _to_str_list([1, " x ", ""]) == ["1", "x"]


# ──────────────────────────────────────────────────────────────
# fake model + 评审流程
# ──────────────────────────────────────────────────────────────
@dataclass
class FakeModel:
    """按 system 提示中的 persona 特征返回预定 JSON 的 fake model。

    reviewer_responses 的 key = persona 特征子串（出现在 system 提示里则命中）。
    """

    reviewer_responses: dict[str, str] = field(default_factory=dict)  # persona 特征 -> JSON
    default_response: str = ""
    summarize_response: str = ""
    seen_system_prompts: list[str] = field(default_factory=list)
    seen_user_prompts: list[str] = field(default_factory=list)
    seen_system_messages: list[str] = field(default_factory=list)
    fail_with: Exception | None = None

    def respond(self, messages: list[Message], tools: list[Any]) -> ModelOutput:
        if self.fail_with is not None:
            raise self.fail_with
        system = messages[0].content
        user = messages[1].content
        self.seen_system_messages.append(system)
        if "评审团主席" in system:
            self.seen_system_prompts.append(system)
            self.seen_user_prompts.append(user)
            return ModelOutput(text=self.summarize_response)
        self.seen_system_prompts.append(system)
        self.seen_user_prompts.append(user)
        text = self.default_response
        for key, resp in self.reviewer_responses.items():
            if key in system:
                text = resp
                break
        return ModelOutput(text=text)


def _sample_reviewer_json() -> str:
    return json.dumps(
        {
            "scores": {"结构完整性": 8, "戏剧张力": 7},
            "overall_score": 7.5,
            "highlights": ["开头抓人"],
            "issues": ["中段节奏拖"],
            "suggestions": ["砍掉第3段"],
            "comment": "这章能立住，但中段要收。",
        },
        ensure_ascii=False,
    )


def _panel_with(tmp_path: Path, yaml_text: str) -> ReviewPanel:
    d = tmp_path / "rv"
    d.mkdir()
    (d / "one.yaml").write_text(yaml_text, encoding="utf-8")
    panel = ReviewPanel(system_dir=d)
    return panel


SIMPLE_YAML = """
- id: t1
  name: 测试员
  avatar: 🧪
  persona: 我是测试评审员
  scoring_dimensions:
    - { name: 结构, weight: 0.5, desc: 结构 }
    - { name: 文笔, weight: 0.5, desc: 文笔 }
"""


def test_run_review_happy_path(tmp_path: Path) -> None:
    panel = _panel_with(tmp_path, SIMPLE_YAML)
    model = FakeModel(
        reviewer_responses={"测试评审员": _sample_reviewer_json()},
        summarize_response=json.dumps(
            {
                "summary": "总体不错",
                "consensus": ["中段拖"],
                "divergences": [],
                "top_suggestions": ["砍段"],
            },
            ensure_ascii=False,
        ),
    )
    report = asyncio.run(panel.run_review(model, "正文", chapter_ref="第一章"))
    assert report.overall_score > 0
    assert report.summary == "总体不错"
    assert report.consensus == ["中段拖"]
    assert report.top_suggestions == ["砍段"]
    assert report.valid_count == 1
    detail = report.individual_reviews[0]
    assert detail["reviewer_name"] == "测试员"
    assert detail["comment"] == "这章能立住，但中段要收。"


def test_run_review_weighted_overall_wins(tmp_path: Path) -> None:
    """维度齐时综合分用确定性加权平均（防 LLM 乱打总分）。"""
    panel = _panel_with(tmp_path, SIMPLE_YAML)
    model = FakeModel(
        reviewer_responses={
            "测试评审员": json.dumps({"scores": {"结构": 8, "文笔": 4}, "overall_score": 10})
        },
        summarize_response='{"summary": ""}',
    )
    report = asyncio.run(panel.run_review(model, "正文"))
    # (8*0.5 + 4*0.5) = 6.0，而不是 LLM 的 10
    assert report.overall_score == 6.0


def test_run_review_no_active_reviewers(tmp_path: Path) -> None:
    panel = _panel_with(
        tmp_path,
        """
- id: off1
  name: 关掉的
  persona: x
  active: false
""",
    )
    model = FakeModel()
    report = asyncio.run(panel.run_review(model, "正文"))
    assert "没有激活的评审员" in report.summary
    assert report.reviewer_count == 0


def test_run_review_all_failed(tmp_path: Path) -> None:
    panel = _panel_with(tmp_path, SIMPLE_YAML)
    model = FakeModel(fail_with=RuntimeError("boom"))
    report = asyncio.run(panel.run_review(model, "正文"))
    assert "所有评审员均未返回有效结果" in report.summary
    assert report.errors


def test_run_review_summarize_fallback(tmp_path: Path) -> None:
    """汇总 LLM 失败 → 启发式兜底，报告不挂死。"""
    panel = _panel_with(tmp_path, SIMPLE_YAML)
    model = FakeModel(
        reviewer_responses={"测试评审员": _sample_reviewer_json()},
        summarize_response="主席说了人话但不是JSON",
    )
    report = asyncio.run(panel.run_review(model, "正文"))
    assert "自动汇总" in report.summary
    assert report.overall_score == 7.5  # 单维度缺失 → 用 LLM 自报 overall


def test_context_injection(tmp_path: Path) -> None:
    """context_keys 声明的上下文块被注入；未声明的块不注入。"""
    panel = _panel_with(
        tmp_path,
        """
- id: needs_ctx
  name: 要上下文的
  persona: 我要上下文
  context_keys: [check_report]
""",
    )
    model = FakeModel(
        reviewer_responses={"我要上下文": _sample_reviewer_json()},
        summarize_response='{"summary": "x"}',
    )
    asyncio.run(
        panel.run_review(
            model, "正文", context={"check_report": "硬伤：设定矛盾", "foreshadow": "不该注入"}
        )
    )
    user = model.seen_user_prompts[0]
    assert "check_report" in user
    assert "硬伤：设定矛盾" in user
    assert "foreshadow" not in user  # 未声明的块不注入


def test_specific_reviewer_selection(tmp_path: Path) -> None:
    panel = _panel_with(
        tmp_path,
        SIMPLE_YAML
        + """
- id: t2
  name: 二队
  persona: 二队人设
""",
    )
    model = FakeModel(
        reviewer_responses={"测试评审员": _sample_reviewer_json()},
        summarize_response='{"summary": "x"}',
    )
    report = asyncio.run(panel.run_review(model, "正文", reviewer_ids=["t1"]))
    assert report.reviewer_count == 1
    assert len(report.individual_reviews) == 1


# ──────────────────────────────────────────────────────────────
# 解析与渲染
# ──────────────────────────────────────────────────────────────
def test_parse_review_result() -> None:
    reviewer = ReviewerDef(
        id="t1",
        name="测试员",
        persona="p",
        scoring_dimensions=[ScoreDim(name="结构", weight=0.5), ScoreDim(name="文笔", weight=0.5)],
    )
    result = _parse_review(_sample_reviewer_json(), reviewer)
    assert result.overall_score == 7.5
    assert result.highlights == ["开头抓人"]
    assert result.comment == "这章能立住，但中段要收。"


def test_parse_review_unparseable() -> None:
    reviewer = ReviewerDef(id="t1", name="测试员", persona="p")
    result = _parse_review("说人话，不给JSON", reviewer)
    assert result.error


def test_render_full_and_compact() -> None:
    report = ReviewReport(
        chapter_ref="第一章",
        overall_score=7.2,
        summary="总体不错",
        consensus=["中段拖"],
        divergences=["爽度分歧"],
        top_suggestions=["砍段"],
    )
    report.individual_reviews = [
        {
            "reviewer_id": "t1",
            "reviewer_name": "编剧",
            "avatar": "🎬",
            "overall_score": 7.5,
            "scores": {"结构": 8},
            "highlights": ["开头"],
            "issues": ["中段"],
            "suggestions": ["砍"],
            "comment": "能立住",
        },
        {"reviewer_id": "t2", "reviewer_name": "挂的", "error": "评审超时"},
    ]
    full = report.render()
    assert "评审团报告：第一章" in full
    assert "🎬 编剧" in full
    assert "共识" in full and "分歧" in full and "优先建议" in full
    assert "评审超时" in full
    compact = report.render_compact()
    assert "综合 7.2/10" in compact
    assert "砍段" in compact


def test_parse_review_json_none() -> None:
    assert parse_review_json("不是JSON") is None
    assert parse_review_json(None) is None  # type: ignore[arg-type]


# ──────────────────────────────────────────────────────────────
# 顶层便捷入口（run_review 函数）
# ──────────────────────────────────────────────────────────────
def test_module_run_review(tmp_path: Path) -> None:
    panel = _panel_with(tmp_path, SIMPLE_YAML)
    model = FakeModel(
        reviewer_responses={"测试评审员": _sample_reviewer_json()},
        summarize_response='{"summary": "ok"}',
    )
    report = asyncio.run(run_review(model, "正文", chapter_ref="第二章", panel=panel))
    assert isinstance(report, ReviewReport)
    assert report.chapter_ref == "第二章"
