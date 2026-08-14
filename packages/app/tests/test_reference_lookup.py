"""参考书分级检索测试：低级（书库=原文）vs 高级（项目=原文+图谱+设定）。

设计定案：书库的书=低级参考书（只检索原文文本）；项目=高级参考书
（额外可检索图谱实体卡片 + 设定档条目，只读、不注入、按需检索）。
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from anyspark.align.worldsettings import WorldSettingStore
from anyspark.core.types import ToolResult
from anyspark.graph import GraphStore
from anyspark.library import LibraryStore
from anyspark.server.tools_domain import make_reference_lookup_implementer


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "t.db"


def _call(impl: Any, name: str = "reference_lookup", **kwargs: Any) -> ToolResult:
    from anyspark.core.protocol import ToolSpec

    spec = ToolSpec(name=name, description="t", params=[])
    result = impl(spec, kwargs)
    assert isinstance(result, ToolResult)
    return result


def _setup() -> tuple[LibraryStore, GraphStore, WorldSettingStore, Any]:
    """建书库 + 图谱 + 设定档 + 装配好高级参考书检索工具。

    - 书库「雾城风云」作为低级参考书（原文检索）。
    - 项目「雾城旧作」作为高级参考书（章节文本 + 图谱 + 设定档）。
    """
    d = Path(tempfile.mkdtemp())
    lib = LibraryStore(d / "lib.db", library_root=d / "library")
    lib.add_book("雾城风云")
    lib.import_chapter("雾城风云", "第一章", "雨夜，陈渡推开钟表铺的门，老周正擦拭怀表。")

    # 高级参考书：项目「雾城旧作」的图谱 + 设定档（book_id=雾城旧作）
    graph = GraphStore(d / "graph.db")
    graph.upsert_entity(
        "雾城旧作",
        "陈渡",
        "角色",
        aliases=["陈侦探"],
        description="雾城旧作侦探，隐退后经营钟表铺",
        state_delta="已破解钟表铺悬案，回归平静",
    )
    graph.upsert_entity("雾城旧作", "老周", "角色", description="钟表铺老匠人")
    settings = WorldSettingStore(d / "settings.db")
    settings.add(
        "陈渡的世界观：雾城多雾、钟表文化兴盛",
        category="世界观",
        name="雾城",
        book_id="雾城旧作",
    )
    settings.add(
        "钟表铺的规矩：入夜后不接客",
        category="规则",
        name="钟表铺规矩",
        book_id="雾城旧作",
    )

    # 项目章节文本（高级参考书也走原文检索）
    lib.set_references(
        "main",
        [
            {"type": "library", "id": "雾城风云"},
            {"type": "project", "id": "雾城旧作"},
        ],
    )

    class _Chapter:
        def __init__(self, title: str, content: str) -> None:
            self.title = title
            self.content = content

    class _Chapters:
        def __init__(self) -> None:
            self._store: dict[str, list[Any]] = {
                "雾城旧作": [_Chapter("第一章 钟表铺", "陈渡坐在柜台后，听见雨声敲打旧钟。")]
            }

        def list_by_book(self, book_id: str) -> list[Any]:
            return self._store.get(book_id, [])

    _, impl = make_reference_lookup_implementer(
        lib,
        _Chapters(),
        book_id="main",
        graph=graph,
        settings=settings,
    )
    return lib, graph, settings, impl


def test_low_level_reference_text_only() -> None:
    """低级参考书（书库的书）：只有原文片段，无图谱/设定层。"""
    lib, _graph, _settings, impl = _setup()
    try:
        r = _call(impl, keyword="怀表")
        assert r.ok is True
        assert "雾城风云" in r.content
        assert "怀表" in r.content
        # 低级参考书不输出知识层标记
        assert "（知识层）" not in r.content
    finally:
        lib.close()


def test_high_level_reference_graph_hit() -> None:
    """高级参考书（项目）：关键词命中图谱实体卡片（含状态/类型）。"""
    lib, _, _, impl = _setup()
    try:
        r = _call(impl, keyword="陈渡")
        assert r.ok is True
        assert "知识层" in r.content
        assert "实体[角色] 陈渡" in r.content
        assert "雾城旧作" in r.content
    finally:
        lib.close()


def test_high_level_reference_settings_hit() -> None:
    """高级参考书（项目）：关键词命中设定档条目（含分类）。"""
    lib, _, _, impl = _setup()
    try:
        r = _call(impl, keyword="钟表铺")
        assert r.ok is True
        assert "设定[规则]" in r.content
        assert "入夜后不接客" in r.content
    finally:
        lib.close()


def test_no_hit_anywhere() -> None:
    """文本/图谱/设定全未命中 → ok=False，提示含知识层。"""
    lib, _, _, impl = _setup()
    try:
        r = _call(impl, keyword="不存在的词xyz")
        assert r.ok is False
        assert "未命中" in r.content
    finally:
        lib.close()


def test_reference_lookup_without_knowledge_sources() -> None:
    """不传 graph/settings 时（旧装配）：退回纯原文检索，不报错。"""
    d = Path(tempfile.mkdtemp())
    lib = LibraryStore(d / "lib.db", library_root=d / "library")
    try:
        lib.add_book("雾城风云")
        lib.import_chapter("雾城风云", "第一章", "雨夜，陈渡推开钟表铺的门。")
        lib.set_references("main", [{"type": "library", "id": "雾城风云"}])

        _, impl = make_reference_lookup_implementer(lib, None, book_id="main")
        r = _call(impl, keyword="陈渡")
        assert r.ok is True
        assert "雾城风云" in r.content
    finally:
        lib.close()


def test_knowledge_retrieval_is_read_only() -> None:
    """高级参考书检索只读：检索后参考书项目的图谱/设定档数据不变（隔离验证）。"""
    lib, graph, settings, impl = _setup()
    try:
        # 检索前快照
        before_ents = [e.to_dict() for e in graph.list_entities("雾城旧作")]
        before_settings = [s.to_dict() for s in settings.list("雾城旧作")]

        # 多次检索（图谱命中 + 设定命中 + 未命中）
        _call(impl, keyword="陈渡")
        _call(impl, keyword="钟表铺")
        _call(impl, keyword="不存在的词xyz")

        # 检索后快照：完全一致 = 零写入
        after_ents = [e.to_dict() for e in graph.list_entities("雾城旧作")]
        after_settings = [s.to_dict() for s in settings.list("雾城旧作")]
        assert after_ents == before_ents
        assert after_settings == before_settings
    finally:
        lib.close()


def test_reference_lookup_registered_in_production_toolkit() -> None:
    """S145（第三方评审 P0-1）：reference_lookup 必须出现在生产装配工具集中。

    回归：agent_factory 曾漏传 library → ctx.library 恒 None → 该工具因
    `if ctx.library is not None` 永不注册（S86 声称"检索走 agent 工具"落空，
    仅 workflow query_reference script 可用）。原子查询应开放给 agent。
    """
    from anyspark.core.protocol import ToolRegistry
    from anyspark.server.toolkit import ToolContext, build_toolkit
    from anyspark.server.tools_extensions import ExtensionToolStore

    registry = build_toolkit(
        ToolRegistry(),
        ToolContext(
            chapters=None,
            workspace=None,
            model=None,
            graph=None,
            plots=None,
            plans=None,
            settings=None,
            materials=None,
            ext_tools=ExtensionToolStore(_db()),
            book_id="main",
            library=LibraryStore(_db()),  # 非 None → reference_lookup 注册
        ),
    )
    names = {s.name for s in registry.specs()}
    assert "reference_lookup" in names, (
        "reference_lookup 未注册——agent_factory 装配漏传 library 会导致"
        "S86 参考书检索能力对 agent 不可用"
    )


def test_reference_lookup_absent_without_library() -> None:
    """对照：library 为 None 时（未装配书库）该工具确实不注册（条件语义保持）。"""
    from anyspark.core.protocol import ToolRegistry
    from anyspark.server.toolkit import ToolContext, build_toolkit
    from anyspark.server.tools_extensions import ExtensionToolStore

    registry = build_toolkit(
        ToolRegistry(),
        ToolContext(
            chapters=None,
            workspace=None,
            model=None,
            graph=None,
            plots=None,
            plans=None,
            settings=None,
            materials=None,
            ext_tools=ExtensionToolStore(_db()),
            book_id="main",
            # library 缺省 None
        ),
    )
    names = {s.name for s in registry.specs()}
    assert "reference_lookup" not in names
