"""Regression coverage for autonomous editing and manuscript refusal guards."""

import asyncio
import json

import pytest

from core.agent_loop import AgentConfig, _prepare_tool_calls
from core.content_guard import detect_model_refusal
from core.llm_client import LLMResponse, ToolCall
from core.loop_state import LoopState
from core.permissions import permission_manager
from core.session_state import RunHandle
from core.tools import registry


def test_patch_schema_rejects_empty_operation_list():
    from core.tool_registry import validate_tool_input

    validated, errors = validate_tool_input(registry.get("patch_chapter"), {"chapter_id": "#1", "patches": []})

    assert validated.get("chapter_id") == "#1"
    assert errors
    assert any("patches" in error for error in errors)


@pytest.mark.asyncio
async def test_empty_patch_is_rejected_before_permission_prompt():
    response = LLMResponse(
        tool_calls=[ToolCall(id="empty", name="patch_chapter", arguments='{"chapter_id":"#1","patches":[]}')]
    )
    messages = []
    prepared = []

    async for event in _prepare_tool_calls(
        response,
        messages,
        AgentConfig(book_id="book", session_id="session"),
        RunHandle("session"),
        LoopState(max_rounds=10),
        prepared,
    ):
        pytest.fail(f"empty patch must not yield a permission question: {event}")

    assert prepared == []
    assert any("参数校验失败" in message.get("content", "") for message in messages)


@pytest.mark.asyncio
async def test_identical_patch_retry_is_blocked_without_second_confirmation():
    config = AgentConfig(book_id="book", session_id="autonomous-session")
    scope = permission_manager.scope_key(config.book_id, config.session_id)
    permission_manager.set_autonomous(scope, True)
    state = LoopState(max_rounds=10)
    args = {"chapter_id": "#1", "patches": [{"op": "append", "text": "新段落"}]}

    try:
        first = LLMResponse(tool_calls=[ToolCall(id="first", name="patch_chapter", arguments=json.dumps(args))])
        first_prepared = []
        async for event in _prepare_tool_calls(
            first, [], config, RunHandle(config.session_id), state, first_prepared
        ):
            pytest.fail(f"autonomous recoverable edit must not ask: {event}")
        assert len(first_prepared) == 1

        second_messages = []
        second_prepared = []
        second = LLMResponse(tool_calls=[ToolCall(id="second", name="patch_chapter", arguments=json.dumps(args))])
        async for event in _prepare_tool_calls(
            second, second_messages, config, RunHandle(config.session_id), state, second_prepared
        ):
            pytest.fail(f"duplicate edit must be rejected without asking: {event}")

        assert second_prepared == []
        assert any("重复修改拦截" in message.get("content", "") for message in second_messages)
    finally:
        permission_manager.reset_session(scope)


@pytest.mark.parametrize(
    "text",
    [
        "抱歉，我无法协助生成这段内容。",
        "您的请求触发内容安全过滤，无法继续生成。",
        "This response was blocked by the content moderation policy.",
    ],
)
def test_model_refusal_detection(text):
    assert detect_model_refusal(text)


def test_normal_fictional_refusal_is_not_misclassified():
    prose = "“我不能走。”她抓紧门框。窗外的雨越下越大，巷口却传来熟悉的脚步声。" * 40
    assert detect_model_refusal(prose) == ""


@pytest.mark.asyncio
async def test_streamed_refusal_is_never_saved_as_chapter(monkeypatch, tmp_data_dir):
    from core import writer
    from data.json_store import json_store
    from tools.impl.writing import _write_chapter_streaming

    book = json_store.create_book("拒答保护测试", "")
    monkeypatch.setattr(writer, "write_stream", lambda *_args, **_kwargs: iter(["抱歉，我无法协助生成这段内容。"]))

    result = await _write_chapter_streaming(
        asyncio.get_running_loop(),
        {"instruction": "写第一章", "chapter_title": "第一章"},
        None,
        book["id"],
        "写第一章",
    )

    assert result["saved"] is False
    assert "未保存" in result["text"]
    assert json_store.load_chapters(book["id"]) == []

