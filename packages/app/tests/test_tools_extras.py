"""S32 扩展能力工具测试：explore_direction / read_material / check_text 注册与行为。

背景：审计发现探索/检测/资料只有 HTTP API（Agent 看不到），S32 把三类能力
注册为写作 Agent 工具（参照 pi：能力即工具、按需调用）。本测试验证：
1. 三个工具默认注册进 Agent（Agent 可见性补齐）
2. read_material 匹配/未匹配/空库行为
3. check_text 调用检测网返回报告（模型异常时 ok=False 不炸链路）
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.core.types import Message, ModelOutput
from anyspark.server.app import build_app
from anyspark.server.tools_extras import (
    make_check_implementer,
    make_explore_implementer,
    make_read_material_implementer,
)


class ProbeModel:
    def __init__(self) -> None:
        self.model_name = "probe"
        self.tool_names: list[list[str]] = []

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        if tools:
            self.tool_names.append([t.name for t in tools])
        return ModelOutput(text="好的。")


def _client(model: ProbeModel) -> TestClient:
    db = Path(tempfile.mkdtemp()) / "test.db"
    return TestClient(build_app(model=model, db_path=db))


def test_explore_tool_always_registered() -> None:
    """S32 修复核心：explore_direction 无条件注册（方向模糊时 Agent 可自觉探索）。"""
    m = ProbeModel()
    client = _client(m)
    resp = client.post("/api/chat", json={"message": "写一段"})
    assert resp.status_code == 200
    assert m.tool_names, "Agent 应调用过 respond"
    assert "explore_direction" in m.tool_names[0]


def test_extra_tools_default_off_on_demand() -> None:
    """S32 防干扰：read_material/check_text 默认不注册（主链路轻量，防无关调用）；
    enable_extras=True 时点亮（能力即工具，按需装配）。"""
    m = ProbeModel()
    client = _client(m)
    client.post("/api/chat", json={"message": "写一段"})
    names = m.tool_names[0]
    assert "read_material" not in names
    assert "check_text" not in names
    # 点亮后可见
    m2 = ProbeModel()
    db = Path(tempfile.mkdtemp()) / "test.db"
    client2 = TestClient(build_app(model=m2, db_path=db))
    client2.post("/api/chat", json={"message": "写一段", "enable_extras": True})
    names2 = m2.tool_names[0]
    assert "read_material" in names2
    assert "check_text" in names2
    assert "explore_direction" in names2


def test_explore_implementer_returns_tool_result() -> None:
    """explore_direction：无有效模型输出时宽容降级（空方向卡），不抛异常不阻断链路。"""
    spec, impl = make_explore_implementer(ProbeModel())
    assert spec.name == "explore_direction"
    result = impl(spec, {"task": "一个雾城侦探的故事"})
    # 宽容解析：坏输出 → 空意图/空卡，但 ok=True、含可读结构（方向卡列表）
    assert result.ok is True
    assert "候选方向" in result.content
    assert isinstance(result.data.get("cards"), list)


def test_explore_missing_task() -> None:
    spec, impl = make_explore_implementer(ProbeModel())
    result = impl(spec, {})
    assert result.ok is False
    assert "task" in result.content


class FakeMaterials:
    """最小 MaterialStore 替身（只实现 list()）。"""

    def __init__(self, cards: list[object]) -> None:
        self._cards = cards

    def list(self) -> list[object]:
        return self._cards


def _card(title: str, topic: str, terms: list[str] | None = None) -> object:
    from anyspark.template.materials import MaterialCard

    return MaterialCard(
        title=title,
        topic=topic,
        key_points=[],
        key_settings=[],
        characters=[],
        terms=terms or [],
    )


def test_read_material_match_and_miss() -> None:
    store = FakeMaterials([_card("雾城设定", "雾气弥漫的侦探城", ["雾瘴", "失踪七人"])])
    spec, impl = make_read_material_implementer(store)
    hit = impl(spec, {"title": "雾瘴"})
    assert hit.ok is True
    assert "雾城设定" in hit.content
    assert "失踪七人" in hit.content
    miss = impl(spec, {"title": "不存在的东西"})
    assert miss.ok is False
    assert "未找到" in miss.content


def test_read_material_empty_listing() -> None:
    store = FakeMaterials([])
    spec, impl = make_read_material_implementer(store)
    result = impl(spec, {"title": ""})
    assert result.ok is True
    assert "为空" in result.content


def test_check_text_calls_review() -> None:
    """check_text：模型异常时 ok=False 不炸；正常时返回报告（hard_count 字段）。"""
    spec, impl = make_check_implementer(ProbeModel())
    assert spec.name == "check_text"
    result = impl(spec, {"target": "第一章", "text": "一段正文"})
    # ProbeModel 返回无效 JSON → 审读解析为空报告（无硬伤），不抛异常
    assert result.ok is True
    assert result.data is None or isinstance(result.data.get("hard_count"), int)
