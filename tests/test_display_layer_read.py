# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Regression tests for display-layer read-path fixes.

User report: "extract_chapter 的写入目标与 generate_timeline 的读取来源不一致，
已入库的时间线/伏笔数据在展示层不可见"。Investigation showed the data WAS in
the graph DB; the actual breakage was two real bugs in the read/synthesis tools:

1. ``generate_location_map`` crashed with KeyError('cnt') when a location name
   contained another location's name — the SQL alias ``c`` was read as ``cnt``.
2. ``search_graph`` (graph_search._execute_query) always bound a fixed 3-tuple
   to LLM-generated SQL whose ``?`` count varies, raising sqlite3 binding errors.

Each test builds an isolated in-memory/temp graph DB so it never depends on a
local ``data/novel.db`` (which does not exist in CI).
"""

import asyncio

import pytest

from core.knowledge import Foreshadow, TimelineEvent
from core.sqlite_store import SQLiteStore


def _make_store(tmp_path: pytest.TempPathFactory) -> SQLiteStore:
    """Create a fresh graph store at a temp db path with schema initialized."""
    db_path = tmp_path / "graph.db"
    return SQLiteStore("test_book", db_path=db_path)


def _seed(store: SQLiteStore) -> None:
    """Seed timeline + foreshadow + location data through the public API."""
    store.add_timeline_event(
        TimelineEvent(id="evt_1", time_point="第1章", label="初遇", time_order=1.0, chapter_ref="#1")
    )
    store.add_timeline_event(
        TimelineEvent(id="evt_2", time_point="第2章", label="对决", time_order=2.0, chapter_ref="#2")
    )
    store.add_foreshadow(
        Foreshadow(id="fs_1", text="那把剑藏着秘密", hint="藏剑", status="planned", planned_resolve_arc="真相揭露")
    )
    store.add_foreshadow(Foreshadow(id="fs_2", text="门后的脚步声", hint="门", status="open"))
    # Locations with containment (name-in-name) to exercise the backfill path.
    from core.knowledge import Entity

    store.add_entity(Entity(id="loc_1", type="location", name="青云宗", data={}))
    store.add_entity(Entity(id="loc_2", type="location", name="青云宗大殿", data={"parent": "青云宗"}))
    store.add_entity(Entity(id="ch_1", type="character", name="林远", data={}))


def test_timeline_and_foreshadow_readable_from_store(tmp_path):
    """Data written via add_* must be readable via the view APIs."""
    store = _make_store(tmp_path)
    try:
        _seed(store)
        tl = store.get_timeline_for_view()
        assert len(tl["events"]) == 2, "时间线应能读到事件"
        fs = store.list_foreshadows()
        assert len(fs) == 2, "伏笔应能读到"
        loc = store.get_location_map_for_view()
        assert len(loc["nodes"]) >= 2, "地点图应能读到节点"
    finally:
        store.close()


@pytest.mark.parametrize(
    "sql,expect_ok",
    [
        # 1 placeholder
        ("SELECT name FROM entities WHERE entity_type='character' AND project_id=? LIMIT 5", True),
        # 2 placeholders
        ("SELECT name FROM entities WHERE name LIKE ? AND project_id=?", True),
        # 3 placeholders
        ("SELECT name FROM entities WHERE name LIKE ? AND project_id=? AND entity_type=? LIMIT 5", True),
        # 4 placeholders — exceeds known runtime values; must pad, not error
        ("SELECT name FROM entities WHERE name LIKE ? AND project_id=? AND name LIKE ? AND entity_type=? LIMIT 5", True),
        # 0 placeholders
        ("SELECT COUNT(*) AS c FROM entities", True),
        # non-SELECT must be rejected
        ("DELETE FROM entities WHERE project_id=?", False),
    ],
)
def test_execute_query_adapts_to_placeholder_count(tmp_path, sql, expect_ok):
    from core.graph_search import _execute_query

    store = _make_store(tmp_path)
    try:
        _seed(store)
        rows, err = _execute_query(store, sql, {"pid": "test_book", "name": "林远", "limit": 50})
        if expect_ok:
            assert err == "", f"查询应成功，但得到错误: {err}"
        else:
            assert err != "", "非 SELECT 查询应被拒绝"
    finally:
        store.close()


def test_generate_location_map_no_longer_crashes(tmp_path, monkeypatch):
    """Regression: the name-containment backfill read COUNT(*) c as 'cnt'.

    The original crash (KeyError('cnt')) happened during the backfill loop,
    before any LLM analysis. We stub the LLM helper so the test only exercises
    the backfill + view code, never making a network call.
    """
    import tools.impl.generation as gen

    def _fake_chat(prompt, system="", temperature=0.3, task="general"):
        return ""

    monkeypatch.setattr(gen, "llm_chat", _fake_chat)

    from core.graph_store import GraphStore

    db_path = tmp_path / "graph.db"
    kb = GraphStore("test_book", db_path=db_path)
    try:
        _seed(kb)
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(gen._generate_location_map(loop, {}, kb, "test_book", ""))
        finally:
            loop.close()
        assert "地点图生成完成" in result, f"意外结果: {result[:100]}"
    finally:
        kb.close()


def test_non_select_rejected_without_network(tmp_path):
    """Read tool must never execute writes."""
    from core.graph_search import _execute_query

    store = _make_store(tmp_path)
    try:
        rows, err = _execute_query(store, "DROP TABLE entities", {})
        assert rows == []
        assert err
    finally:
        store.close()
