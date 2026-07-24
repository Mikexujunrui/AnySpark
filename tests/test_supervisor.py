"""Tests for the supervisor daemon."""

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.supervisor import Supervisor, SupervisorConfig
from core.task_queue import (
    PersistentTask,
    TaskQueue,
    TaskStatus,
    TaskStep,
)


@pytest.fixture
def tq(tmp_data_dir):
    return TaskQueue(data_dir=tmp_data_dir)


@pytest.fixture
def supervisor_instance(tq):
    sup = Supervisor()
    runner = MagicMock()
    runner._running = {}
    runner.active_task_ids = []
    runner.retry_step = AsyncMock(return_value=True)
    runner.pause_task = AsyncMock(return_value=True)
    sup.set_runner(runner, tq)
    return sup


def _make_task(task_id="t1", status=TaskStatus.RUNNING, steps_count=2) -> PersistentTask:
    steps = [
        TaskStep(id=f"{task_id}_s{i}", type="agent_loop", label=f"Step {i}", config={"prompt": f"do {i}"})
        for i in range(steps_count)
    ]
    task = PersistentTask(
        id=task_id,
        type="custom",
        book_id="b1",
        session_id="s1",
        label="Test Task",
        steps=steps,
        status=status,
        started_at=datetime.now().isoformat(),
    )
    return task


class TestSupervisorStatus:
    def test_get_status(self, supervisor_instance):
        status = supervisor_instance.get_status()
        assert "running" in status
        assert status["running"] is False  # Not started yet

    @pytest.mark.asyncio
    async def test_get_status_after_start(self, supervisor_instance):
        supervisor_instance.start()
        status = supervisor_instance.get_status()
        assert status["running"] is True
        supervisor_instance.stop()


class TestOrphanDetection:
    @pytest.mark.asyncio
    async def test_detect_orphan_running_task(self, supervisor_instance, tq):
        """Task marked RUNNING but no asyncio.Task → reset to PENDING."""
        task = _make_task("orphan1")
        tq.create_task(task)
        tq.update_task_status("orphan1", TaskStatus.RUNNING)

        # No asyncio.Task in runner._running → orphan
        await supervisor_instance._check_running_tasks()

        updated = tq.get_task("orphan1")
        assert updated.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_detect_completed_orphan(self, supervisor_instance, tq):
        """Task marked RUNNING but all steps completed → mark COMPLETED."""
        task = _make_task("done1", steps_count=2)
        tq.create_task(task)
        tq.update_task_status("done1", TaskStatus.RUNNING)

        # Complete all steps manually
        tq.mark_step_completed("done1", "done1_s0", {})
        tq.advance_step("done1")
        tq.mark_step_completed("done1", "done1_s1", {})
        tq.advance_step("done1")

        await supervisor_instance._check_running_tasks()

        updated = tq.get_task("done1")
        assert updated.status == TaskStatus.COMPLETED


class TestStaleDetection:
    @pytest.mark.asyncio
    async def test_stale_task_paused(self, supervisor_instance, tq):
        """Task with no progress for >1 hour → paused."""
        task = _make_task("stale1")
        tq.create_task(task)
        tq.update_task_status("stale1", TaskStatus.RUNNING)

        # Set stale started_at (2 hours ago)
        old_time = (datetime.now() - timedelta(hours=2)).isoformat()
        task = tq.get_task("stale1")
        task.started_at = old_time
        tq._save()

        # Set the stale timeout low for testing
        supervisor_instance._config.stale_task_timeout = 60  # 1 minute

        await supervisor_instance._check_stale_tasks()

        updated = tq.get_task("stale1")
        assert updated.status == TaskStatus.PAUSED


class TestAutoRetry:
    @pytest.mark.asyncio
    async def test_retry_failed_step(self, supervisor_instance, tq):
        """Failed step triggers auto-retry with backoff."""
        task = _make_task("fail1")
        tq.create_task(task)
        tq.update_task_status("fail1", TaskStatus.FAILED)
        tq.mark_step_failed("fail1", "fail1_s0", "LLM error")

        # Set failed time to past (so backoff delay is satisfied)
        step = tq.get_task("fail1").steps[0]
        step.completed_at = (datetime.now() - timedelta(seconds=30)).isoformat()
        tq._save()

        # Set low backoff for testing
        supervisor_instance._config.retry_backoff_base = 1.0

        await supervisor_instance._check_failed_tasks()

        # Should have attempted retry
        supervisor_instance._runner.retry_step.assert_called_once()

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self, supervisor_instance, tq):
        """After max retries, no more retries are attempted."""
        task = _make_task("max_retry")
        tq.create_task(task)
        tq.update_task_status("max_retry", TaskStatus.FAILED)
        tq.mark_step_failed("max_retry", "max_retry_s0", "persistent error")

        # Mark retries as exhausted
        retry_key = "max_retry:max_retry_s0"
        supervisor_instance._retry_tracker[retry_key] = supervisor_instance._config.max_auto_retries

        await supervisor_instance._check_failed_tasks()

        # Should NOT retry
        supervisor_instance._runner.retry_step.assert_not_called()


class TestRecordActivity:
    def test_record_activity(self, supervisor_instance):
        supervisor_instance.record_activity("t1")
        assert "t1" in supervisor_instance._last_activity
        assert supervisor_instance._last_activity["t1"]  # Non-empty timestamp


class TestSupervisorConfig:
    def test_default_config(self):
        config = SupervisorConfig()
        assert config.check_interval == 30
        assert config.max_auto_retries == 3
        assert config.retry_backoff_base == 10.0
        assert config.retry_backoff_max == 300.0
        assert config.stale_task_timeout == 3600
