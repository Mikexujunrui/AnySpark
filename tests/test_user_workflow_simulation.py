"""Offline simulation of the main desktop writing/editing lifecycle."""

import asyncio
import json

import pytest


@pytest.mark.asyncio
async def test_new_book_write_autonomous_patch_refusal_and_revert(monkeypatch, tmp_data_dir):
    from core import writer
    from core.agent_loop import AgentConfig, _prepare_tool_calls
    from core.llm_client import LLMResponse, ToolCall
    from core.loop_state import LoopState
    from core.permissions import permission_manager
    from core.session_state import RunHandle
    from data.json_store import json_store
    from tools.impl.chapters import _patch_chapter
    from tools.impl.writing import _guard_new_chapter_target, _write_chapter_streaming

    book = json_store.create_book("完整流程模拟", "不调用真实模型")
    json_store.add_chapter(
        book["id"],
        "第一章 原稿",
        "旧宅门前的雨一直没有停。" * 20,
        origin="user_supplied",
        protected=True,
    )

    # Imported manuscript remains immune to a new-chapter writer.
    guard = _guard_new_chapter_target(book["id"], {"chapter_index": 1}, "写第一章")
    assert guard and guard["saved"] is False and guard["protected"] is True

    generated = "她推开旧宅的门，先看见地板上的湿脚印。" * 30
    monkeypatch.setattr(writer, "write_stream", lambda *_args, **_kwargs: iter([generated[:200], generated[200:]]))
    written = await _write_chapter_streaming(
        asyncio.get_running_loop(),
        {"instruction": "承接第一章，只写第二章当前事件", "chapter_title": "第二章 脚印", "chapter_index": 2},
        None,
        book["id"],
        "写第二章",
    )
    assert written["saved"] is True
    assert len(json_store.load_chapters(book["id"])) == 2

    # Autonomous mode allows a recoverable patch with no confirmation event.
    session_id = "workflow-session"
    scope = permission_manager.scope_key(book["id"], session_id)
    permission_manager.set_autonomous(scope, True)
    patch_args = {
        "chapter_id": "#2",
        "patches": [{"op": "replace", "find": "湿脚印", "replace": "带泥的脚印"}],
        "message": "修正细节",
    }
    prepared = []
    try:
        response = LLMResponse(
            tool_calls=[ToolCall(id="patch", name="patch_chapter", arguments=json.dumps(patch_args))]
        )
        async for event in _prepare_tool_calls(
            response,
            [],
            AgentConfig(book_id=book["id"], session_id=session_id),
            RunHandle(session_id),
            LoopState(max_rounds=10),
            prepared,
        ):
            pytest.fail(f"recoverable autonomous patch unexpectedly asked a question: {event}")
        assert len(prepared) == 1

        patch_result = _patch_chapter(prepared[0]["args"], book["id"])
        assert patch_result["patched_count"] == 1
        edited = json_store.get_chapter(book["id"], "#2")
        assert "带泥的脚印" in edited["content"]
        assert edited["version_count"] == 2

        # A provider refusal for the following chapter is reported but never
        # occupies chapter #3 or alters either existing chapter.
        monkeypatch.setattr(writer, "write_stream", lambda *_args, **_kwargs: iter(["请求触发内容安全过滤，无法继续生成。"]))
        refused = await _write_chapter_streaming(
            asyncio.get_running_loop(),
            {"instruction": "写第三章", "chapter_title": "第三章", "chapter_index": 3},
            None,
            book["id"],
            "写第三章",
        )
        assert refused["saved"] is False
        assert len(json_store.load_chapters(book["id"])) == 2

        # Version history remains a real escape hatch for autonomous edits.
        history = json_store.chapter_history(book["id"], "#2")
        assert len(history) == 2
        original_version = history[-1]["id"]
        json_store.revert_chapter(book["id"], "#2", original_version)
        reverted = json_store.get_chapter(book["id"], "#2")
        assert "湿脚印" in reverted["content"]
        assert "带泥的脚印" not in reverted["content"]
    finally:
        permission_manager.reset_session(scope)
