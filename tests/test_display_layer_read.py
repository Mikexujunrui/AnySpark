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
"""

import pytest

from core.sqlite_store import SQLiteStore

BOOK = "1785122825916"  # a book with populated timeline/foreshadow/location data


def test_timeline_and_foreshadow_readable_from_store():
    """Data written by accept_proposal must be readable via the view APIs."""
    kb = SQLiteStore(BOOK)
    try:
        tl = kb.get_timeline_for_view()
        assert len(tl["events"]) > 0, "时间线应能读到事件"
        fs = kb.list_foreshadows()
        assert len(fs) > 0, "伏笔应能读到"
        loc = kb.get_location_map_for_view()
        assert len(loc["nodes"]) > 0, "地点图应能读到节点"
    finally:
        kb.close()


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
        ("SELECT COUNT(*) AS c FROM entities WHERE project_id = '" + BOOK + "'", True),
        # non-SELECT must be rejected
        ("DELETE FROM entities WHERE project_id=?", False),
    ],
)
def test_execute_query_adapts_to_placeholder_count(sql, expect_ok):
    from core.graph_search import _execute_query

    store = SQLiteStore(BOOK)
    try:
        rows, err = _execute_query(store, sql, {"pid": BOOK, "name": "林远", "limit": 50})
        if expect_ok:
            assert err == "", f"查询应成功，但得到错误: {err}"
        else:
            assert err != "", "非 SELECT 查询应被拒绝"
    finally:
        store.close()


def test_generate_location_map_no_longer_crashes(monkeypatch):
    """Regression: the name-containment backfill read COUNT(*) c as 'cnt'.

    The original crash (KeyError('cnt')) happened during the backfill loop,
    before any LLM analysis. We stub the LLM synthesis path so the test only
    exercises the backfill + view code, never making a network call.
    """
    import asyncio

    # Stub the LLM helper imported into generation.py so the sparse-connection
    # analysis can't hit the network (fast, deterministic test).
    import tools.impl.generation as gen
    from core.graph_store import GraphStore

    def _fake_chat(prompt, system="", temperature=0.3, task="general"):
        return ""

    monkeypatch.setattr(gen, "llm_chat", _fake_chat)

    async def _run():
        kb = GraphStore(BOOK)
        try:
            result = await gen._generate_location_map(asyncio.get_event_loop(), {}, kb, BOOK, "")
            assert "地点图生成完成" in result, f"意外结果: {result[:100]}"
        finally:
            kb.close()

    asyncio.run(_run())
