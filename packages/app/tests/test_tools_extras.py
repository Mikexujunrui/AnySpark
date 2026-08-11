"""S32 扩展能力工具测试：explore_direction / read_material 注册与行为。

背景：审计发现探索/检测/资料只有 HTTP API（Agent 看不到），S32 把三类能力
注册为写作 Agent 工具（参照 pi：能力即工具、按需调用）。本测试验证：
1. explore_direction 无条件注册（Agent 可见性补齐）
2. read_material 匹配/未匹配/空库行为
3. S63：check_text 已退役（被 S59 workflow 的 review_chapter 取代）——不再注册
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.core.types import Message, ModelOutput
from anyspark.server.app import build_app
from anyspark.server.tools_extras import (
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
    """S32 防干扰：read_material 默认不注册（主链路轻量，防无关调用）；
    enable_extras=True 时点亮（能力即工具，按需装配）。S63：check_text 已退役。"""
    m = ProbeModel()
    client = _client(m)
    client.post("/api/chat", json={"message": "写一段"})
    names = m.tool_names[0]
    assert "read_material" not in names
    # 点亮后可见
    m2 = ProbeModel()
    db = Path(tempfile.mkdtemp()) / "test.db"
    client2 = TestClient(build_app(model=m2, db_path=db))
    client2.post("/api/chat", json={"message": "写一段", "enable_extras": True})
    names2 = m2.tool_names[0]
    assert "read_material" in names2
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

    def list(self, book_id: str = "main", kind: str | None = None) -> list[object]:
        """S79 适配：真实 MaterialStore.list 支持 book_id/kind 过滤。"""
        if kind is not None:
            return [c for c in self._cards if getattr(c, "kind", "inspiration") == kind]
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


def test_read_material_marks_purpose_and_boundary() -> None:
    """S72：输出标注用途 + 使用边界（防文风参考被当设定）。"""
    from anyspark.template.materials import MaterialCard

    style_card = MaterialCard(
        title="某作家文风",
        topic="雾城系列写法",
        key_points=["短句", "克制"],
        key_settings=["悲剧基调"],
        characters=[],
        terms=[],
        purpose="style",
    )
    fact_card = MaterialCard(
        title="世界观设定",
        topic="大陆地理",
        key_points=["三块大陆"],
        key_settings=["魔法体系"],
        characters=[],
        terms=["法力"],
        purpose="fact",
    )
    spec, impl = make_read_material_implementer(FakeMaterials([style_card, fact_card]))

    r1 = impl(spec, {"title": "文风"})
    assert "用途：文风参考" in r1.content
    assert "不得进入正文" in r1.content  # 使用边界
    r2 = impl(spec, {"title": "世界观"})
    assert "用途：设定参考" in r2.content
    assert "可直接引用" in r2.content
    # 列表也带用途标注
    r3 = impl(spec, {"title": ""})
    assert "文风参考" in r3.content and "设定参考" in r3.content


def test_read_material_empty_listing() -> None:
    store = FakeMaterials([])
    spec, impl = make_read_material_implementer(store)
    result = impl(spec, {"title": ""})
    assert result.ok is True
    assert "为空" in result.content


def test_check_text_retired() -> None:
    """S63：check_text 工具已退役（S59 workflow 的 review_chapter 取代）——
    不再从 tools_extras 导出，Agent 工具集不再含 check_text。"""
    import anyspark.server.tools_extras as te

    assert not hasattr(te, "make_check_implementer"), "check_text 应已退役"
