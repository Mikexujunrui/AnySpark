"""Tests for writing.py pure helpers — the cheapest way to lift writing.py's
7% coverage (M9.3 leftover: coverage 40% target)."""

from types import SimpleNamespace

from tools.impl.writing import (
    _build_scope_report,
    _format_chapter_result,
    _guard_new_chapter_target,
    _requested_regular_chapter_index,
)

# ── _requested_regular_chapter_index ──


def test_chapter_index_from_args():
    assert _requested_regular_chapter_index({"chapter_index": 3}) == 3


def test_chapter_index_extra_returns_none():
    assert _requested_regular_chapter_index({"is_extra": True, "chapter_index": 3}) is None


def test_chapter_index_zero_or_negative_returns_none():
    assert _requested_regular_chapter_index({"chapter_index": 0}) is None
    assert _requested_regular_chapter_index({"chapter_index": -2}) is None


def test_chapter_index_invalid_type_returns_none():
    assert _requested_regular_chapter_index({"chapter_index": "abc"}) is None


def test_chapter_index_from_instruction_text():
    assert _requested_regular_chapter_index({}, "写第 12 章的内容") == 12


def test_chapter_index_from_title():
    assert _requested_regular_chapter_index({"chapter_title": "第5章 真相"}) == 5


def test_chapter_index_ignores_word_count_distraction():
    # "写一章 2500 字" must NOT be read as chapter #2500.
    assert _requested_regular_chapter_index({}, "写一章 2500 字") is None


def test_chapter_index_no_match():
    assert _requested_regular_chapter_index({}, "随便写点") is None


# ── _build_scope_report ──


def _ent(name: str, reason: str = "manual"):
    return SimpleNamespace(entity_name=name, reason=reason)


def test_scope_report_empty():
    assert _build_scope_report(SimpleNamespace(
        characters=[], locations=[], concepts=[], forbidden_characters=[],
        chapter_outline="", writing_rules="",
    )) == ""


def test_scope_report_characters_and_outline():
    report = _build_scope_report(SimpleNamespace(
        characters=[_ent("哈利"), _ent("赫敏")],
        locations=[_ent("霍格沃茨")],
        concepts=[],
        forbidden_characters=["伏地魔"],
        chapter_outline="这是一个比较长的大纲描述",
        writing_rules="规则内容",
    ))
    assert "哈利" in report and "赫敏" in report
    assert "地点(1): 霍格沃茨" in report
    assert "禁止出场: 伏地魔" in report
    assert "大纲:" in report
    assert "角色(2)" in report


def test_scope_report_truncates_long_outline():
    report = _build_scope_report(SimpleNamespace(
        characters=[], locations=[], concepts=[], forbidden_characters=[],
        chapter_outline="长" * 100, writing_rules="",
    ))
    assert "..." in report


# ── _format_chapter_result ──


def test_format_chapter_result_basic(tmp_data_dir):
    from data.json_store import json_store

    book = json_store.create_book("测试书", "")
    json_store.add_chapter(book["id"], "第一章", "内容内容")
    result = _format_chapter_result(book["id"], "ch1", "第一章", "内容内容")
    assert "✅ 章节: 第一章" in result
    assert "共1章" in result or "进度:" in result
    assert "内容预览: 内容内容" in result


def test_format_chapter_result_with_scope(tmp_data_dir):
    from data.json_store import json_store

    book = json_store.create_book("测试书2", "")
    result = _format_chapter_result(book["id"], "ch2", "第二章", "x" * 200, scope_report="📋 知识范围报告:\n  角色(1)")
    assert "📋 知识范围报告" in result
    assert "..." in result  # long content preview truncated


# ── _guard_new_chapter_target ──


def test_guard_allows_new_chapter(tmp_data_dir):
    from data.json_store import json_store

    book = json_store.create_book("测试书3", "")
    # No chapters yet → no guard hit.
    assert _guard_new_chapter_target(book["id"], {"chapter_index": 1}) is None


def test_guard_blocks_existing_chapter(tmp_data_dir):
    from data.json_store import json_store

    book = json_store.create_book("测试书4", "")
    json_store.add_chapter(book["id"], "第一章 起点", "内容")
    guard = _guard_new_chapter_target(book["id"], {"chapter_index": 1})
    assert guard is not None
    assert guard["type"] == "writing_result"
    assert "原稿保护" in guard["text"]
    assert guard["saved"] is False
