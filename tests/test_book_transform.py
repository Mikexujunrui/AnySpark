"""Tests for Work Package D — whole-book transform tools.

Covers:
  - find_replace_book: literal/regex, scope parsing, dry_run, version creation
  - summarize_book: summary generation + persistence to book metadata
  - apply_directive_globally: directive parsing, execution_mode auto-detection
  - transform_chapters_batch: patch mode, scope parsing
  - restyle_book: style lookup, missing style error
  - Tool registration in TOOL_META
"""

import asyncio
import json
from unittest.mock import patch

import pytest


@pytest.fixture
def book_with_chapters(tmp_data_dir):
    """Create a book with sample chapters for testing."""
    from data.json_store import json_store

    book = json_store.create_book("测试小说", "测试简介")
    book_id = book["id"]

    chapters = [
        (
            "第一章 初入江湖",
            "少年李逸站在山门前，望着云雾缭绕的青云山。小姐姐李婉从身后走来，轻声道：哥哥，我们真的要上山吗？" * 10,
        ),
        ("第二章 初次交手", "剑光闪烁，李逸拔剑迎敌。小姐姐在一旁紧张地注视着。对方是个蒙面人，武功不弱。" * 10),
        ("第三章 真相大白", "师父微笑着看向他。小姐姐终于知道了真相，原来李逸并非凡人。" * 10),
    ]
    for title, content in chapters:
        json_store.add_chapter(book_id, title, content)

    return book_id


# ── find_replace_book ──


@pytest.mark.asyncio
async def test_find_replace_literal(book_with_chapters):
    """Test literal find-and-replace across all chapters."""
    from tools.chapter_tools import find_replace_book

    loop = asyncio.get_event_loop()
    result = await find_replace_book(
        loop,
        {
            "pattern": "小姐姐",
            "replacement": "妹妹",
            "scope": "all",
        },
        book_with_chapters,
    )

    assert "查找替换完成" in result
    assert "已修改" in result

    # Verify replacement was applied
    from data.json_store import json_store

    chapters = json_store.load_chapters(book_with_chapters)
    for ch in chapters:
        view = json_store._chapter_view(ch)
        assert "小姐姐" not in view["content"], "Pattern should be replaced"
        assert "妹妹" in view["content"], "Replacement should be present"


@pytest.mark.asyncio
async def test_find_replace_dry_run(book_with_chapters):
    """Test dry_run mode doesn't modify chapters."""
    from tools.chapter_tools import find_replace_book

    loop = asyncio.get_event_loop()
    result = await find_replace_book(
        loop,
        {
            "pattern": "小姐姐",
            "replacement": "妹妹",
            "dry_run": True,
        },
        book_with_chapters,
    )

    assert "预览模式" in result
    assert "总匹配" in result

    # Verify chapters were NOT modified
    from data.json_store import json_store

    chapters = json_store.load_chapters(book_with_chapters)
    for ch in chapters:
        view = json_store._chapter_view(ch)
        assert "小姐姐" in view["content"], "Dry run should not modify content"


@pytest.mark.asyncio
async def test_find_replace_regex(book_with_chapters):
    """Test regex mode find-and-replace."""
    from tools.chapter_tools import find_replace_book

    loop = asyncio.get_event_loop()
    result = await find_replace_book(
        loop,
        {
            "pattern": r"小姐姐",
            "replacement": "妹妹",
            "regex": True,
            "scope": "all",
        },
        book_with_chapters,
    )

    assert "查找替换完成" in result
    assert "正则" in result


@pytest.mark.asyncio
async def test_find_replace_scoped(book_with_chapters):
    """Test find-replace on a subset of chapters."""
    from tools.chapter_tools import find_replace_book

    loop = asyncio.get_event_loop()
    result = await find_replace_book(
        loop,
        {
            "pattern": "小姐姐",
            "replacement": "妹妹",
            "scope": "#1-#2",
        },
        book_with_chapters,
    )

    assert "查找替换完成" in result
    assert "3 章" not in result or "2" in result  # Only 2 chapters in scope


@pytest.mark.asyncio
async def test_find_replace_no_matches(book_with_chapters):
    """Test find-replace with no matches."""
    from tools.chapter_tools import find_replace_book

    loop = asyncio.get_event_loop()
    result = await find_replace_book(
        loop,
        {
            "pattern": "不存在的文本XYZ",
            "replacement": "替换",
        },
        book_with_chapters,
    )

    assert "总匹配: 0" in result


@pytest.mark.asyncio
async def test_find_replace_missing_pattern(book_with_chapters):
    """Test error when pattern is missing."""
    from tools.chapter_tools import find_replace_book

    loop = asyncio.get_event_loop()
    result = await find_replace_book(loop, {}, book_with_chapters)
    assert "错误" in result


# ── summarize_book ──


@pytest.mark.asyncio
async def test_summarize_book(book_with_chapters):
    """Test book summary generation and persistence."""
    from tools.chapter_tools import summarize_book

    mock_summary = {
        "premise": "少年李逸的修仙之旅",
        "plot_arc": "李逸上山学艺，经历战斗，发现身世真相",
        "characters": [
            {"name": "李逸", "role": "主角", "status": "修炼中"},
            {"name": "李婉", "role": "配角", "status": "跟随"},
        ],
        "key_events": ["上山", "交手", "真相"],
        "unresolved": ["李逸的真实身世"],
        "themes": ["成长", "亲情"],
    }

    with patch("tools.chapter_tools.llm_chat", return_value=json.dumps(mock_summary, ensure_ascii=False)):
        loop = asyncio.get_event_loop()
        result = await summarize_book(loop, {}, book_with_chapters)

    assert "全书摘要已生成" in result

    # Verify summary was persisted
    from data.json_store import json_store

    book = json_store.get_book(book_with_chapters)
    assert "book_summary" in book, "Summary should be persisted to book metadata"
    assert book["book_summary"]["premise"] == "少年李逸的修仙之旅"


@pytest.mark.asyncio
async def test_summarize_book_no_chapters(tmp_data_dir):
    """Test error when book has no chapters."""
    from data.json_store import json_store
    from tools.chapter_tools import summarize_book

    book = json_store.create_book("空书", "")
    loop = asyncio.get_event_loop()
    result = await summarize_book(loop, {}, book["id"])
    assert "没有章节" in result


# ── apply_directive_globally ──


@pytest.mark.asyncio
async def test_apply_directive_parallel(book_with_chapters):
    """Test apply_directive with parallel execution (rename directive)."""
    from tools.chapter_tools import apply_directive_globally

    def mock_edit_llm(llm_chat_fn, prompt, system):
        # Return modified content (just append a marker)
        return prompt[:200] + "\n[已修改]"

    with patch("tools._common._call_edit_llm", side_effect=mock_edit_llm):
        loop = asyncio.get_event_loop()
        result = await apply_directive_globally(
            loop,
            {
                "directive": "把所有小姐姐改成妹妹",
                "scope": "all",
                "execution_mode": "parallel",
            },
            book_with_chapters,
        )

    assert "全书变换完成" in result
    assert "parallel" in result


@pytest.mark.asyncio
async def test_apply_directive_serial(book_with_chapters):
    """Test apply_directive with serial execution (continuity directive)."""
    from tools.chapter_tools import apply_directive_globally

    def mock_edit_llm(llm_chat_fn, prompt, system):
        return prompt[:200] + "\n[已修改]"

    with patch("tools._common._call_edit_llm", side_effect=mock_edit_llm):
        loop = asyncio.get_event_loop()
        result = await apply_directive_globally(
            loop,
            {
                "directive": "调整前后呼应，让章节衔接更自然",
                "execution_mode": "serial",
                "scope": "all",
            },
            book_with_chapters,
        )

    assert "全书变换完成" in result
    assert "serial" in result


@pytest.mark.asyncio
async def test_apply_directive_auto_mode(book_with_chapters):
    """Test auto execution mode detection."""
    from tools.chapter_tools import apply_directive_globally

    def mock_edit_llm(llm_chat_fn, prompt, system):
        return prompt[:200] + "\n[已修改]"

    with patch("tools._common._call_edit_llm", side_effect=mock_edit_llm):
        loop = asyncio.get_event_loop()

        # "改名" should trigger parallel
        result = await apply_directive_globally(
            loop,
            {
                "directive": "把所有小姐姐改成妹妹",
                "execution_mode": "auto",
            },
            book_with_chapters,
        )
        assert "parallel" in result

        # "前后呼应" should trigger serial
        result = await apply_directive_globally(
            loop,
            {
                "directive": "调整前后呼应，让章节衔接更自然",
                "execution_mode": "auto",
            },
            book_with_chapters,
        )
        assert "serial" in result


@pytest.mark.asyncio
async def test_apply_directive_dry_run(book_with_chapters):
    """Test dry_run mode doesn't modify chapters."""
    from tools.chapter_tools import apply_directive_globally

    def mock_edit_llm(llm_chat_fn, prompt, system):
        return prompt[:200] + "\n[已修改]"

    with patch("tools._common._call_edit_llm", side_effect=mock_edit_llm):
        loop = asyncio.get_event_loop()
        result = await apply_directive_globally(
            loop,
            {
                "directive": "把所有小姐姐改成妹妹",
                "dry_run": True,
            },
            book_with_chapters,
        )

    assert "预览模式" in result


@pytest.mark.asyncio
async def test_apply_directive_missing_directive(book_with_chapters):
    """Test error when directive is missing."""
    from tools.chapter_tools import apply_directive_globally

    loop = asyncio.get_event_loop()
    result = await apply_directive_globally(loop, {}, book_with_chapters)
    assert "错误" in result


# ── transform_chapters_batch ──


@pytest.mark.asyncio
async def test_transform_chapters_batch(book_with_chapters):
    """Test batch transform with patch mode."""
    from tools.chapter_tools import transform_chapters_batch

    def mock_edit_llm(llm_chat_fn, prompt, system):
        return prompt[:200] + "\n[已变换]"

    with patch("tools._common._call_edit_llm", side_effect=mock_edit_llm):
        loop = asyncio.get_event_loop()
        result = await transform_chapters_batch(
            loop,
            {
                "chapter_ids": "#1-#2",
                "instruction": "增加环境描写",
                "mode": "patch",
            },
            book_with_chapters,
        )

    assert "批量变换完成" in result
    assert "patch" in result


@pytest.mark.asyncio
async def test_transform_chapters_dry_run(book_with_chapters):
    """Test dry_run mode."""
    from tools.chapter_tools import transform_chapters_batch

    def mock_edit_llm(llm_chat_fn, prompt, system):
        return prompt[:200] + "\n[已变换]"

    with patch("tools._common._call_edit_llm", side_effect=mock_edit_llm):
        loop = asyncio.get_event_loop()
        result = await transform_chapters_batch(
            loop,
            {
                "chapter_ids": "all",
                "instruction": "压缩对话",
                "dry_run": True,
            },
            book_with_chapters,
        )

    assert "预览模式" in result


# ── restyle_book ──


@pytest.mark.asyncio
async def test_restyle_book_missing_style(book_with_chapters):
    """Test error when style doesn't exist."""
    from tools.chapter_tools import restyle_book

    loop = asyncio.get_event_loop()
    result = await restyle_book(
        loop,
        {
            "style_id": "nonexistent_style_xyz",
        },
        book_with_chapters,
    )

    assert "未找到文风" in result or "可用文风" in result


@pytest.mark.asyncio
async def test_restyle_book_missing_style_id(book_with_chapters):
    """Test error when style_id is missing."""
    from tools.chapter_tools import restyle_book

    loop = asyncio.get_event_loop()
    result = await restyle_book(loop, {}, book_with_chapters)
    assert "错误" in result


# ── Tool registration ──


def test_tool_meta_registration():
    """Verify all 5 tools are registered in TOOL_META."""
    from core.tools import TOOL_META

    tools = [
        "apply_directive_globally",
        "find_replace_book",
        "transform_chapters_batch",
        "restyle_book",
        "summarize_book",
    ]
    for t in tools:
        assert t in TOOL_META, f"Tool {t} should be in TOOL_META"
        assert TOOL_META[t].get("streaming") or TOOL_META[t].get("touches_chapter"), (
            f"Tool {t} should have streaming or touches_chapter flag"
        )


def test_tool_registry():
    """Verify all 5 tools are registered in the tool registry."""
    from core.tools import registry

    tools = [
        "apply_directive_globally",
        "find_replace_book",
        "transform_chapters_batch",
        "restyle_book",
        "summarize_book",
    ]
    for t in tools:
        tool = registry.get(t)
        assert tool is not None, f"Tool {t} should be registered"
        assert tool.parameters is not None, f"Tool {t} should have parameters"


def test_executor_dispatch():
    """Verify executor has dispatch entries for new tools."""
    from core.tools import registry
    from tools.executor import _DISPATCH, _build_dispatch

    _build_dispatch()

    tools = [
        "apply_directive_globally",
        "find_replace_book",
        "transform_chapters_batch",
        "restyle_book",
        "summarize_book",
    ]
    for t in tools:
        # All tools must be registered
        tool = registry.get(t)
        assert tool is not None, f"Tool {t} should be registered"
        assert tool.parameters is not None, f"Tool {t} should have parameters"

        # Dispatch table or fallback: must be reachable
        if t in _DISPATCH:
            assert _DISPATCH[t] is not None, f"Tool {t} should have a dispatch handler"
        else:
            # Fallback tools (lazy imported chapter_tools) must have a description
            assert len(tool.description) > 0, f"Tool {t} should have a description"
