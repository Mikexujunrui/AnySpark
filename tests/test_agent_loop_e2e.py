"""Minimal end-to-end tests of the agent loop driven by a fake LLM.

M2.4 of .pi/plan.md. These exercise the real ``_loop_inner`` state machine
(permission → execute → continue → terminate) without any network call:
``chat_with_tools_stream_async`` is replaced by a deterministic fake.

Historical gap: 700+ tests covered LoopState logic but not the loop itself,
which is exactly where the 10s mis-cancel bug lived.
"""

import pytest

import core.agent_loop as agent_loop
from core.llm_client import StreamEvent
from core.session_state import RunHandle
from data.json_store import json_store


@pytest.fixture
def book(tmp_data_dir):
    """Create a real book record so _loop_inner's context load succeeds."""
    return json_store.create_book("测试书", "")


def _cfg(book_id: str = "b1") -> agent_loop.AgentConfig:
    return agent_loop.AgentConfig(
        book_id=book_id,
        session_id="s1",
        agent_type="write",
        mode="write",
        max_rounds=5,
    )


@pytest.mark.asyncio
async def test_loop_terminates_immediately_without_tools(monkeypatch, book):
    """LLM returns finish on the first call → loop ends cleanly with a done event."""
    calls: list[int] = []

    async def fake_llm(messages, tools, temp, task_label):
        calls.append(1)
        yield StreamEvent(type="finish", data={"reason": "stop"})

    monkeypatch.setattr(agent_loop, "chat_with_tools_stream_async", fake_llm)
    events = [e async for e in agent_loop._loop_inner("你好", _cfg(book["id"]), None, RunHandle("s1"))]
    types = [e.type for e in events]
    assert "done" in types
    assert len(calls) == 1  # single LLM call, no tool round-trips
    # final done event carries the agent's text
    done = next(e for e in events if e.type == "done")
    assert isinstance(done.data, dict)


@pytest.mark.asyncio
async def test_loop_handles_unknown_tool_then_terminates(monkeypatch, book):
    """One tool call to a non-existent tool → error surfaced, loop continues, then done."""
    call = {"n": 0}

    async def fake_llm(messages, tools, temp, task_label):
        call["n"] += 1
        if call["n"] == 1:
            yield StreamEvent(
                type="tool-call-end",
                data={"id": "tc1", "name": "nonexistent_tool_xyz", "arguments": "{}"},
            )
        yield StreamEvent(type="finish", data={"reason": "stop"})

    monkeypatch.setattr(agent_loop, "chat_with_tools_stream_async", fake_llm)
    events = [e async for e in agent_loop._loop_inner("写一章", _cfg(book["id"]), None, RunHandle("s1"))]
    types = [e.type for e in events]
    assert "done" in types
    assert call["n"] >= 2  # second round happened after the tool error


@pytest.mark.asyncio
async def test_loop_cancellation_yields_cancelled_event(monkeypatch, book):
    """A pre-cancelled handle aborts at the first round boundary → cancelled event."""
    handle = RunHandle("s1")
    handle.cancel()

    async def fake_llm(messages, tools, temp, task_label):
        raise AssertionError("LLM must not be called for a pre-cancelled run")

    monkeypatch.setattr(agent_loop, "chat_with_tools_stream_async", fake_llm)
    events = [e async for e in agent_loop.run_agent_loop("你好", _cfg(book["id"]), None, handle)]
    types = [e.type for e in events]
    assert "cancelled" in types
    assert "操作已取消" in next(e.data.get("message", "") for e in events if e.type == "cancelled")
