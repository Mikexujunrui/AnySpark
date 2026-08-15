"""S66 路径探索（叙事树节点之间串联的小方向探索）测试。"""

from __future__ import annotations

import json

from anyspark.core.types import Message, ModelOutput
from anyspark.explore.path import (
    MAX_PATHS,
    MIN_PATHS,
    PathExplorer,
    PathExploreResult,
    explore_path,
)


class _ScriptedModel:
    """固定返回两条路径候选（验证解析与结构）。"""

    model_name = "scripted"

    def __init__(self, raw: str | None = None) -> None:
        self.calls = 0
        self._raw = raw

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        self.calls += 1
        if self._raw is not None:
            return ModelOutput(text=self._raw)
        return ModelOutput(
            text=json.dumps(
                {
                    "paths": [
                        {
                            "events": ["陈渡在船票背面发现水印", "水印指向废弃仓库"],
                            "note": "快速推进，适合想尽快进入对峙",
                            "style": "直接推进",
                        },
                        {
                            "events": ["陈渡找到当年的船员", "船员失踪", "港口出现新线索"],
                            "note": "多层铺垫，拉满悬疑节奏",
                            "style": "多层铺垫",
                        },
                    ]
                },
                ensure_ascii=False,
            )
        )


def test_explore_path_two_candidates() -> None:
    """起终点 → N 条路径候选（事件链 + note + style）。"""
    model = _ScriptedModel()
    result = explore_path(model, "陈渡收到旧船票", "陈渡发现父亲没死", n=4)
    assert len(result.paths) == 2
    p1 = result.paths[0]
    assert p1.events == ["陈渡在船票背面发现水印", "水印指向废弃仓库"]
    assert "推进" in p1.note
    assert p1.style == "直接推进"
    assert model.calls == 1  # 单次调用


def test_explore_path_prompt_contains_both_ends() -> None:
    """prompt 含起点/终点/约束。"""
    from anyspark.explore.path import _build_prompt

    model = _ScriptedModel()
    PathExplorer(model, 4).explore("起点A", "终点B", constraints=["女主=医者"])
    p = _build_prompt("起点A", "终点B", ["女主=医者"], 3)
    assert "起点A" in p and "终点B" in p
    assert "女主=医者" in p


def test_explore_path_n_clamped() -> None:
    """n 收窄到 2-6。"""
    assert MIN_PATHS == 2 and MAX_PATHS == 6
    # 超上限：模型返回 8 条也只取前 6
    raw = json.dumps({"paths": [{"events": [f"事件{i}"]} for i in range(8)]})
    result = PathExplorer(_ScriptedModel(raw), n=9).explore("A", "B")
    assert len(result.paths) <= 6


def test_explore_path_tolerates_bad_json() -> None:
    """宽容解析：非 JSON → 整段作为单条说明；空事件链丢弃。"""
    # 非 JSON
    r1 = PathExplorer(_ScriptedModel("纯文本说明"), 4).explore("A", "B")
    assert len(r1.paths) == 1 and not r1.paths[0].events
    # 空 events 丢弃
    raw = json.dumps(
        {"paths": [{"events": [], "note": "空"}, {"events": ["有内容"], "note": "ok"}]}
    )
    r2 = PathExplorer(_ScriptedModel(raw), 4).explore("A", "B")
    assert len(r2.paths) == 1 and r2.paths[0].events == ["有内容"]
    # 完全空
    r3 = PathExplorer(_ScriptedModel(""), 4).explore("A", "B")
    assert r3.paths == []


def test_result_to_dict() -> None:
    r = PathExploreResult()
    r.paths = explore_path(_ScriptedModel(), "A", "B").paths
    d = r.to_dict()
    assert isinstance(d["paths"], list) and d["paths"][0]["events"]
