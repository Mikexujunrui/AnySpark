"""Tests for autopilot planner and executor."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.autopilot import AutopilotConfig, AutopilotPlanner
from core.autopilot_runner import AutopilotExecutor
from core.task_queue import PersistentTask, TaskQueue, TaskStep


@pytest.fixture
def tq(tmp_data_dir):
    return TaskQueue(data_dir=tmp_data_dir)


# ── Planner ──


class TestAutopilotPlanner:
    @pytest.mark.asyncio
    async def test_plan_without_outline(self, tmp_data_dir, monkeypatch):
        """When no outline exists, planner generates conservative chapter list."""
        from data.json_store import json_store

        monkeypatch.setattr(json_store, "load_chapters", lambda bid: [])
        monkeypatch.setattr(json_store, "load_outline", lambda bid: {})
        monkeypatch.setattr(json_store, "load_detailed_outline", lambda bid: {})

        planner = AutopilotPlanner()
        config = AutopilotConfig(
            book_id="test_book",
            instruction="写完这本书",
            max_chapters_per_run=5,
        )

        plan = await planner.plan(config)
        assert plan["estimated_chapters"] <= 5
        assert plan["total_steps"] > 0
        assert "plan_summary" in plan

    @pytest.mark.asyncio
    async def test_plan_with_outline(self, tmp_data_dir, monkeypatch):
        """When outline exists, planner uses outline chapters."""
        from data.json_store import json_store

        outline = {
            "chapters": [
                {"title": "第一章 开篇"},
                {"title": "第二章 冲突"},
                {"title": "第三章 高潮"},
            ]
        }
        monkeypatch.setattr(json_store, "load_chapters", lambda bid: [])
        monkeypatch.setattr(json_store, "load_outline", lambda bid: outline)
        monkeypatch.setattr(json_store, "load_detailed_outline", lambda bid: {})

        planner = AutopilotPlanner()
        config = AutopilotConfig(
            book_id="test_book",
            instruction="按大纲写完这本书",
            max_chapters_per_run=10,
        )

        plan = await planner.plan(config)
        assert plan["estimated_chapters"] == 3
        assert plan["chapters"][0]["title"] == "第一章 开篇"

    @pytest.mark.asyncio
    async def test_plan_skips_existing_chapters(self, tmp_data_dir, monkeypatch):
        """Planner skips chapters that already exist."""
        from data.json_store import json_store

        existing = [
            {"index": 1, "content": "已有内容"},
            {"index": 2, "content": "已有内容"},
        ]
        outline = {
            "chapters": [
                {"title": "第一章"},
                {"title": "第二章"},
                {"title": "第三章"},
                {"title": "第四章"},
            ]
        }
        monkeypatch.setattr(json_store, "load_chapters", lambda bid: existing)
        monkeypatch.setattr(json_store, "load_outline", lambda bid: outline)
        monkeypatch.setattr(json_store, "load_detailed_outline", lambda bid: {})

        planner = AutopilotPlanner()
        config = AutopilotConfig(
            book_id="test_book",
            instruction="继续写",
            max_chapters_per_run=10,
        )

        plan = await planner.plan(config)
        assert plan["estimated_chapters"] == 2
        indices = [ch["index"] for ch in plan["chapters"]]
        assert 1 not in indices
        assert 2 not in indices
        assert 3 in indices

    def test_build_chapter_steps_hard_mode(self):
        """Hard mode includes user_confirm steps."""
        planner = AutopilotPlanner()
        config = AutopilotConfig(
            book_id="b1",
            instruction="test",
            audit_mode="hard",
            auto_review=True,
            auto_extract=True,
        )

        steps = planner._build_chapter_steps("prefix", 1, "第一章", config, 0)
        step_types = [s.type for s in steps]

        assert "user_confirm" in step_types
        assert "agent_loop" in step_types
        assert "checkpoint" in step_types

    def test_build_chapter_steps_autonomous_mode(self):
        """Autonomous mode does NOT include user_confirm steps."""
        planner = AutopilotPlanner()
        config = AutopilotConfig(
            book_id="b1",
            instruction="test",
            audit_mode="autonomous",
            auto_review=False,
            auto_extract=False,
        )

        steps = planner._build_chapter_steps("prefix", 1, "第一章", config, 0)
        step_types = [s.type for s in steps]

        assert "user_confirm" not in step_types


# ── Executor ──


class TestAutopilotExecutor:
    @pytest.mark.asyncio
    async def test_start_creates_task(self, tq, tmp_data_dir, monkeypatch):
        """Autopilot start creates a PersistentTask."""
        from data.json_store import json_store

        monkeypatch.setattr(json_store, "load_chapters", lambda bid: [])
        monkeypatch.setattr(json_store, "load_outline", lambda bid: {})
        monkeypatch.setattr(json_store, "load_detailed_outline", lambda bid: {})

        # Patch the global task_queue in autopilot_runner module
        import core.autopilot_runner as apr

        monkeypatch.setattr(apr, "task_queue", tq)

        executor = AutopilotExecutor()
        config = AutopilotConfig(
            book_id="test_book",
            instruction="写完这本书",
            confirm_before_start=True,
        )

        result = await executor.start(config)
        assert "task_id" in result
        assert result["needs_confirm"] is True
        assert result["status"] == "pending"

        # Task should exist in queue
        task = tq.get_task(result["task_id"])
        assert task is not None
        assert task.type == "autopilot"

    @pytest.mark.asyncio
    async def test_get_status(self, tq, monkeypatch):
        """get_status returns correct progress info."""
        import core.autopilot_runner as apr

        monkeypatch.setattr(apr, "task_queue", tq)

        # Create a task manually
        steps = [
            TaskStep(id="s0", type="checkpoint", label="ch1完成", config={"final": True, "chapter_index": 1}),
            TaskStep(id="s1", type="checkpoint", label="ch2完成", config={"final": True, "chapter_index": 2}),
        ]
        task = PersistentTask(
            id="ap_test",
            type="autopilot",
            book_id="b1",
            session_id="s1",
            steps=steps,
            metadata={"total_chapters": 2, "token_budget": 500000},
        )
        tq.create_task(task)
        tq.mark_step_completed("ap_test", "s0", {"ok": True})
        tq.advance_step("ap_test")

        executor = AutopilotExecutor()
        status = executor.get_status("ap_test")

        assert status["chapters_completed"] == 1
        assert status["total_chapters"] == 2

    def test_update_tokens(self, tq, monkeypatch):
        """Token usage tracking in metadata."""
        import core.autopilot_runner as apr

        monkeypatch.setattr(apr, "task_queue", tq)

        task = PersistentTask(
            id="ap_t",
            type="autopilot",
            book_id="b1",
            session_id="s1",
            metadata={"tokens_used": 0, "token_budget": 1000},
        )
        tq.create_task(task)

        executor = AutopilotExecutor()
        executor.update_tokens("ap_t", 300)

        updated = tq.get_task("ap_t")
        assert updated.metadata["tokens_used"] == 300
