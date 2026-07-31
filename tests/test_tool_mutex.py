"""Behavioral tests for agent_loop's write-mutex protection and the
permission-confirmation fuse (consecutive cancels must stop the agent from
blindly retrying the same write).

M2.2 / M2.3 of .pi/plan.md — core-loop behaviors that were historically
untested (the 10s mis-cancel bug survived 700+ tests precisely because these
behaviors had no coverage).
"""

import asyncio

import core.agent_loop as agent_loop
from core.agent_loop import AgentConfig
from core.llm_client import LLMResponse, ToolCall
from core.loop_state import LoopState
from core.session_state import RunHandle


def _cfg(book_id: str = "b1") -> AgentConfig:
    return AgentConfig(book_id=book_id, session_id="s1", agent_type="write", mode="write")


def _prepared(state: LoopState, tool_calls: list[ToolCall], monkeypatch, perm="allow", ack="confirmed"):
    """Run _prepare_tool_calls once and return (prepared, messages)."""
    agent_loop.permission_manager.check = lambda name: perm  # type: ignore[assignment]
    if perm == "ask":
        agent_loop._await_answer = _FakeAwait(ack)  # type: ignore[assignment]
    response = LLMResponse(tool_calls=tool_calls)
    messages: list[dict] = []
    prepared: list[dict] = []
    cfg = _cfg()

    async def _run():
        async for _ in agent_loop._prepare_tool_calls(response, messages, cfg, RunHandle("s1"), state, prepared):
            pass

    asyncio.run(_run())
    return prepared, messages


class _FakeAwait:
    """Returns the same answer for every call — deterministic fuse testing."""

    def __init__(self, answer: str):
        self._answer = answer
        self.calls = 0

    async def __call__(self, qid: str, timeout: float = 300) -> str:
        self.calls += 1
        return self._answer


def test_write_mutex_only_first_full_write_tool_executes(monkeypatch):
    """Two full-chapter write tools in one response → only the first runs."""
    state = LoopState()
    prepared, messages = _prepared(
        state,
        [
            ToolCall(id="t1", name="edit_chapter", arguments='{"chapter_id": "#1", "content": "新内容"}'),
            ToolCall(id="t2", name="write_chapter", arguments='{"chapter_id": "#1", "instruction": "写一段"}'),
        ],
        monkeypatch,
    )
    assert len(prepared) == 1
    assert prepared[0]["tc"].id == "t1"
    assert any("写作互斥保护" in m.get("content", "") for m in messages)


def test_write_mutex_allows_second_after_first_round(monkeypatch):
    """A later round with a single write tool is not blocked by the previous round."""
    state = LoopState()
    prepared1, _ = _prepared(
        state,
        [ToolCall(id="t1", name="edit_chapter", arguments='{"chapter_id": "#1", "content": "新内容"}')],
        monkeypatch,
    )
    prepared2, _ = _prepared(
        state,
        [ToolCall(id="t2", name="write_chapter", arguments='{"chapter_id": "#1", "instruction": "写一段"}')],
        monkeypatch,
    )
    assert len(prepared1) == 1
    assert len(prepared2) == 1


def test_confirm_cancel_fuse_increments_and_warns(monkeypatch):
    """Two consecutive cancels → counter reaches 2 and the tool message warns the agent."""
    state = LoopState()
    fake = _FakeAwait("cancelled")
    agent_loop.permission_manager.check = lambda name: "ask"  # type: ignore[assignment]
    agent_loop._await_answer = fake  # type: ignore[assignment]

    tool = ToolCall(id="t1", name="edit_chapter", arguments='{"chapter_id": "#1", "content": "新内容"}')
    response = LLMResponse(tool_calls=[tool])
    messages: list[dict] = []
    prepared: list[dict] = []

    async def _run():
        async for _ in agent_loop._prepare_tool_calls(
            response, messages, _cfg(), RunHandle("s1"), state, prepared
        ):
            pass

    asyncio.run(_run())  # first cancel
    assert state.consecutive_confirm_cancels == 1
    assert len(prepared) == 0
    assert messages[-1]["content"] == "用户取消了 edit_chapter。"

    asyncio.run(_run())  # second cancel → fuse trips
    assert state.consecutive_confirm_cancels == 2
    assert "已连续 2 次确认被取消/超时" in messages[-1]["content"]
    assert "停止反复尝试" in messages[-1]["content"]


def test_confirm_cancel_fuse_resets_on_confirm(monkeypatch):
    """A confirmed answer resets the fuse counter."""
    state = LoopState()
    state.consecutive_confirm_cancels = 2  # simulate prior cancels
    fake = _FakeAwait("confirmed")
    agent_loop.permission_manager.check = lambda name: "ask"  # type: ignore[assignment]
    agent_loop._await_answer = fake  # type: ignore[assignment]

    tool = ToolCall(id="t1", name="edit_chapter", arguments='{"chapter_id": "#1", "content": "新内容"}')
    response = LLMResponse(tool_calls=[tool])
    messages: list[dict] = []
    prepared: list[dict] = []

    async def _run():
        async for _ in agent_loop._prepare_tool_calls(
            response, messages, _cfg(), RunHandle("s1"), state, prepared
        ):
            pass

    asyncio.run(_run())
    assert state.consecutive_confirm_cancels == 0
    assert len(prepared) == 1


def test_confirm_timeout_is_distinguished_from_cancel(monkeypatch):
    """Timeout produces an explicit 'not a cancel' message so the agent doesn't
    misread a slow user as a dissatisfied one (the original bug class)."""
    state = LoopState()
    fake = _FakeAwait("timeout")
    agent_loop.permission_manager.check = lambda name: "ask"  # type: ignore[assignment]
    agent_loop._await_answer = fake  # type: ignore[assignment]

    tool = ToolCall(id="t1", name="edit_chapter", arguments='{"chapter_id": "#1", "content": "新内容"}')
    response = LLMResponse(tool_calls=[tool])
    messages: list[dict] = []
    prepared: list[dict] = []

    async def _run():
        async for _ in agent_loop._prepare_tool_calls(
            response, messages, _cfg(), RunHandle("s1"), state, prepared
        ):
            pass

    asyncio.run(_run())
    assert len(prepared) == 0
    assert "这不是用户取消" in messages[-1]["content"]
    assert "确认超时" in messages[-1]["content"]
