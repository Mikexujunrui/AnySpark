"""Tests for sub-agent Plan-mode read-only guard.

Validates the hard runtime guard in ``_run_sub_agent`` that prevents
plan-mode main agents from spawning read-write sub-agents.
"""

import pytest

from core.agent_context import AgentContext
from tools.executor import _run_sub_agent


@pytest.mark.asyncio
async def test_plan_mode_blocks_write_subagent():
    """Plan-mode main agent must NOT be able to spawn write/extract/edit/general."""
    plan_ctx = AgentContext(mode="plan", agent_type="plan")
    for rw_type in ("general", "extract", "write", "edit"):
        result = await _run_sub_agent(
            args={"prompt": "do something", "agent_type": rw_type},
            book_id="book1",
            session_id="parent_session",
            context=plan_ctx,
        )
        assert "Plan 模式" in result, f"plan mode must block {rw_type}"
        assert rw_type in result, f"error message should mention the blocked type {rw_type}"
        assert "Write 模式" in result or "Write" in result


@pytest.mark.asyncio
async def test_plan_mode_allows_readonly_subagent_types(monkeypatch):
    """Plan-mode main agent SHOULD allow spawning read-only sub-agents."""
    plan_ctx = AgentContext(mode="plan", agent_type="plan")

    # Stub spawn_sub_agent to avoid real sub-agent execution
    class DummyResult:
        success = True
        output = "OK"
        session_id = "dummy_session"
        error = ""

    async def dummy_spawn(**kwargs):
        return DummyResult()

    monkeypatch.setattr("core.sub_agent.spawn_sub_agent", dummy_spawn)

    for ro_type in ("research", "plan", "consistency", "reviewer"):
        result = await _run_sub_agent(
            args={"prompt": "do something", "agent_type": ro_type},
            book_id="book1",
            session_id="parent_session",
            context=plan_ctx,
        )
        assert "Plan 模式" not in result, f"plan mode must NOT block {ro_type}"
        assert "OK" in result


@pytest.mark.asyncio
async def test_write_mode_allows_all_subagent_types(monkeypatch):
    """Write-mode main agent SHOULD be able to spawn all 8 sub-agent types."""
    write_ctx = AgentContext(mode="write", agent_type="write")

    class DummyResult:
        success = True
        output = "OK"
        session_id = "dummy_session"
        error = ""

    async def dummy_spawn(**kwargs):
        return DummyResult()

    monkeypatch.setattr("core.sub_agent.spawn_sub_agent", dummy_spawn)

    for agent_type in ("research", "plan", "consistency", "reviewer", "extract", "write", "edit", "general"):
        result = await _run_sub_agent(
            args={"prompt": "do something", "agent_type": agent_type},
            book_id="book1",
            session_id="parent_session",
            context=write_ctx,
        )
        assert "Plan 模式" not in result, f"write mode must NOT block {agent_type}"


@pytest.mark.asyncio
async def test_no_context_allows_all_subagent_types(monkeypatch):
    """Back-compat: if context is None, allow all types (legacy callers)."""

    class DummyResult:
        success = True
        output = "OK"
        session_id = "dummy_session"
        error = ""

    async def dummy_spawn(**kwargs):
        return DummyResult()

    monkeypatch.setattr("core.sub_agent.spawn_sub_agent", dummy_spawn)

    for agent_type in ("research", "plan", "consistency", "reviewer", "extract", "write", "edit", "general"):
        result = await _run_sub_agent(
            args={"prompt": "do something", "agent_type": agent_type},
            book_id="book1",
            session_id="parent_session",
            context=None,  # ← legacy fallback
        )
        assert "Plan 模式" not in result


@pytest.mark.asyncio
async def test_plan_mode_still_requires_prompt():
    plan_ctx = AgentContext(mode="plan", agent_type="plan")
    result = await _run_sub_agent(
        args={"agent_type": "research"},
        book_id="book1",
        session_id="parent_session",
        context=plan_ctx,
    )
    assert "prompt" in result
