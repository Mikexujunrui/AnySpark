"""Regression tests for the 3.2.1 stability fixes."""

import pytest


@pytest.mark.asyncio
async def test_busy_session_queue_is_actually_drainable():
    from core.session_state import SessionStateMachine

    state = SessionStateMachine()
    handle = await state.start_or_queue("session", "first")
    assert handle is not None
    assert await state.start_or_queue("session", "用新方向继续", "write") is None

    queued = await state.drain_queued("session")

    assert [(item.text, item.mode) for item in queued] == [("用新方向继续", "write")]
    assert not state.has_queued_input("session")


def test_queued_inputs_are_injected_as_ordered_user_corrections():
    from core.agent_loop import _inject_queued_inputs
    from core.session_state import QueuedInput

    messages = []
    _inject_queued_inputs(
        messages,
        [QueuedInput("先别写结局"), QueuedInput("改为第一人称", mode="plan")],
    )

    assert [message["role"] for message in messages] == ["user", "user"]
    assert "先别写结局" in messages[0]["content"]
    assert "改为第一人称" in messages[1]["content"]


@pytest.mark.asyncio
async def test_failed_writing_result_always_closes_preview():
    from core.agent_loop import AgentConfig, _process_tool_result
    from core.llm_client import ToolCall
    from core.loop_state import LoopState

    events = []
    async for event in _process_tool_result(
        ToolCall(id="call", name="write_chapter", arguments="{}"),
        {"type": "writing_result", "saved": False, "text": "read operation timed out"},
        AgentConfig(book_id="book", session_id="session"),
        LoopState(max_rounds=5, base_temperature=0.2),
        [],
    ):
        events.append(event)

    terminal = next(event for event in events if event.type == "writing_end")
    assert terminal.data["saved"] is False
    assert "timed out" in terminal.data["error"]


@pytest.mark.asyncio
async def test_headless_round_limit_is_failure(monkeypatch):
    import core.headless_loop as headless
    from core.agent_loop import LoopEvent

    async def fake_loop(*_args, **_kwargs):
        yield LoopEvent(
            type="done",
            data={
                "message": "我在聊天里写了一段正文",
                "rounds": 1,
                "metrics": {"finish_reason": "round_limit_reached"},
            },
        )

    monkeypatch.setattr(headless, "run_agent_loop", fake_loop)
    monkeypatch.setattr(headless, "_persist_headless_turn", lambda *_args, **_kwargs: None)

    result = await headless.run_agent_loop_headless("book", "写第三章")

    assert result.success is False
    assert "round_limit_reached" in result.error


def test_chinese_chapter_target_and_write_plus_review_are_write_intent():
    from core.autopilot.planner import _classify_intent, _parse_chapter_indices

    assert _parse_chapter_indices("写第三章后检查一致性") == [3]
    intent = _classify_intent("写第三章，完成后再检查一致性", {})
    assert intent.intent_type == "write_new"
    assert intent.chapter_indices == [3]


def test_plain_timeout_text_is_retryable():
    from core.retry import is_retryable

    assert is_retryable(TimeoutError("The read operation timed out"))


def test_character_phase_uses_supported_snapshot_parameter(monkeypatch):
    import core.graph_store as graph_store
    from core.knowledge import Entity
    from tools.impl.handlers import _handle_knowledge_edit

    calls = []

    class FakeStore:
        def __init__(self, _book_id):
            pass

        def init_schema(self):
            pass

        def get_entity(self, _character_id):
            return Entity(id="char-1", type="character", name="阿火")

        def get_entity_by_name(self, _name):
            return None

        def list_snapshots(self, character_id=None):
            calls.append(character_id)
            return []

        def add_snapshot(self, _snapshot):
            pass

    monkeypatch.setattr(graph_store, "GraphStore", FakeStore)

    result = _handle_knowledge_edit(
        "set_character_phase",
        {"character_id": "char-1", "phase": "觉醒后"},
        "book",
    )

    assert "已为角色" in result
    assert calls == ["char-1", "char-1", "char-1"]
