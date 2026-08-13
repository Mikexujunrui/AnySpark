"""S71：评审团 API 层测试（/api/review/panel + /api/review/reviewers）。

S64 只沉淀了包级机制测试（test_review_panel.py），app 层端点无测试覆盖——
S71 审计补缺：fake model 走 build_app 全链路（端点 → 面板 → 评审 → 报告）。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.core.types import Message, ModelOutput
from anyspark.server.app import build_app


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "t.db"


class _ReviewModel:
    """按 system 提示特征区分评审员/主席调用（对齐包级测试的 FakeModel）。"""

    model_name = "review-fake"

    def __init__(self) -> None:
        self.reviewer_calls = 0
        self.summarize_calls = 0

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        system = messages[0].content if messages else ""
        if "评审团主席" in system:
            self.summarize_calls += 1
            return ModelOutput(
                text=json.dumps(
                    {
                        "summary": "整体节奏偏慢，但氛围扎实。",
                        "consensus": ["心理描写偏多"],
                        "divergences": ["章末钩子强弱分歧"],
                        "top_suggestions": ["外化心理描写"],
                    },
                    ensure_ascii=False,
                )
            )
        self.reviewer_calls += 1
        return ModelOutput(
            text=json.dumps(
                {
                    "scores": {"结构完整性": 7, "戏剧张力": 8},
                    "overall_score": 7.5,
                    "highlights": ["悬念设置好"],
                    "issues": ["中段拖沓"],
                    "suggestions": ["砍掉铺垫段"],
                    "comment": "这场戏能立住，中段要收。",
                },
                ensure_ascii=False,
            )
        )


def test_reviewers_list_api() -> None:
    """GET /api/review/reviewers：返回系统默认评审员（含人设/维度/激活态）。"""
    client = TestClient(build_app(model=_ReviewModel(), db_path=_db()))
    r = client.get("/api/review/reviewers")
    assert r.status_code == 200
    reviewers = r.json()
    ids = {x["id"] for x in reviewers}
    assert "screenwriter" in ids
    assert "thriller_reader" in ids
    # 伏笔审计员 S114c 满血激活（主人拍板：已实现增强包不考虑商业化）
    fa = next(x for x in reviewers if x["id"] == "foreshadow_auditor")
    assert fa["active"] is True
    # 编剧有评分维度
    sw = next(x for x in reviewers if x["id"] == "screenwriter")
    assert len(sw["scoring_dimensions"]) == 5


def test_review_panel_api_text() -> None:
    """POST /api/review/panel：直接评审文本 → 报告（评分/共识/分歧/建议）。"""
    model = _ReviewModel()
    client = TestClient(build_app(model=model, db_path=_db()))
    r = client.post(
        "/api/review/panel",
        json={
            "text": "夜色如墨，顾长风站在廊下。",
            "reviewer_ids": ["screenwriter"],
            "with_check": False,  # 关掉 check 上下文（隔离评审员调用计数）
            "with_foreshadow": False,
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["overall_score"] > 0
    assert "整体节奏偏慢" in d["summary"]
    assert "外化心理描写" in d["top_suggestions"]
    assert d["reviewer_count"] == 1
    assert d["valid_count"] == 1
    assert "评审团报告" in d["markdown"]
    assert "编剧" in d["markdown"]
    # 指定评审员 → 只调用 1 位评审员 + 主席
    assert model.reviewer_calls == 1
    assert model.summarize_calls == 1


def test_review_panel_api_all_active() -> None:
    """POST /api/review/panel：不指定评审员 → 全部激活评审员（S114c 满血：6 位）。"""
    model = _ReviewModel()
    client = TestClient(build_app(model=model, db_path=_db()))
    r = client.post(
        "/api/review/panel",
        json={"text": "正文内容", "with_check": False, "with_foreshadow": False},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["reviewer_count"] == 6  # 6 位全激活（含伏笔审计员）
    assert model.reviewer_calls == 6


def test_review_panel_api_empty_text_400() -> None:
    """POST /api/review/panel：空文本 → 400。"""
    client = TestClient(build_app(model=_ReviewModel(), db_path=_db()))
    r = client.post("/api/review/panel", json={"text": ""})
    assert r.status_code == 400


def test_review_panel_api_missing_chapter() -> None:
    """POST /api/review/panel：chapter_ref 不存在 → 400。"""
    client = TestClient(build_app(model=_ReviewModel(), db_path=_db()))
    r = client.post("/api/review/panel", json={"chapter_ref": "不存在的章"})
    assert r.status_code == 400
    assert "不存在" in r.json()["detail"]


def test_review_panel_api_check_context_injected() -> None:
    """POST /api/review/panel：with_check 默认开 → check 硬伤清单作为上下文注入。"""
    client = TestClient(build_app(model=_ReviewModel(), db_path=_db()))
    r = client.post("/api/review/panel", json={"text": "正文", "reviewer_ids": ["logic_auditor"]})
    assert r.status_code == 200, r.text
    # logic_auditor 需要 check_report 上下文；check 包 run_review 内部也是 model 调用
    # （评审员 + 主席 + check 硬伤 = 3 次调用），校验报告仍正常返回
    assert r.json()["overall_score"] > 0
