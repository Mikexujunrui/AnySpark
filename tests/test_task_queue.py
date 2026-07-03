"""Tests for the persistent task queue (task_queue.py)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.task_queue import (
    PersistentTask,
    TaskQueue,
    TaskStatus,
    TaskStep,
    TaskStepStatus,
)


@pytest.fixture
def tq(tmp_data_dir):
    """Create an isolated TaskQueue with a temp data directory."""
    return TaskQueue(data_dir=tmp_data_dir)


def _make_task(task_id="t1", steps_count=3, book_id="book1", **kwargs) -> PersistentTask:
    steps = [
        TaskStep(id=f"{task_id}_s{i}", type="agent_loop",
                 label=f"步骤{i}", config={"prompt": f"do step {i}"})
        for i in range(steps_count)
    ]
    return PersistentTask(
        id=task_id,
        type="custom",
        book_id=book_id,
        session_id="sess1",
        label="测试任务",
        steps=steps,
        **kwargs,
    )


# ── CRUD ──

class TestTaskCRUD:
    def test_create_and_get(self, tq):
        task = _make_task()
        tq.create_task(task)
        retrieved = tq.get_task("t1")
        assert retrieved is not None
        assert retrieved.id == "t1"
        assert retrieved.label == "测试任务"
        assert len(retrieved.steps) == 3

    def test_list_tasks(self, tq):
        tq.create_task(_make_task("t1"))
        tq.create_task(_make_task("t2"))
        tq.create_task(_make_task("t3", book_id="book2"))

        all_tasks = tq.list_tasks()
        assert len(all_tasks) == 3

        book1_tasks = tq.list_tasks(book_id="book1")
        assert len(book1_tasks) == 2

    def test_list_by_status(self, tq):
        t1 = _make_task("t1")
        t2 = _make_task("t2")
        tq.create_task(t1)
        tq.create_task(t2)
        tq.update_task_status("t1", TaskStatus.RUNNING)

        running = tq.list_tasks(status=TaskStatus.RUNNING)
        assert len(running) == 1
        assert running[0].id == "t1"

    def test_delete_task(self, tq):
        tq.create_task(_make_task("t1"))
        assert tq.delete_task("t1") is True
        assert tq.get_task("t1") is None
        assert tq.delete_task("t1") is False

    def test_list_by_created_by(self, tq):
        t1 = _make_task("t1", created_by="autopilot")
        t2 = _make_task("t2", created_by="user")
        tq.create_task(t1)
        tq.create_task(t2)

        auto = tq.list_tasks(created_by="autopilot")
        assert len(auto) == 1
        assert auto[0].id == "t1"


# ── Status Transitions ──

class TestStatusTransitions:
    def test_update_status(self, tq):
        tq.create_task(_make_task())
        tq.update_task_status("t1", TaskStatus.RUNNING)
        task = tq.get_task("t1")
        assert task.status == TaskStatus.RUNNING
        assert task.started_at is not None

    def test_update_with_error(self, tq):
        tq.create_task(_make_task())
        tq.update_task_status("t1", TaskStatus.FAILED, error="something broke")
        task = tq.get_task("t1")
        assert task.status == TaskStatus.FAILED
        assert task.error == "something broke"
        assert task.completed_at is not None

    def test_pause_resume(self, tq):
        tq.create_task(_make_task())
        tq.update_task_status("t1", TaskStatus.RUNNING)

        assert tq.pause_task("t1") is True
        assert tq.get_task("t1").status == TaskStatus.PAUSED

        assert tq.resume_task("t1") is True
        assert tq.get_task("t1").status == TaskStatus.PENDING

    def test_pause_not_running_fails(self, tq):
        tq.create_task(_make_task())
        assert tq.pause_task("t1") is False  # PENDING, not RUNNING

    def test_cancel(self, tq):
        tq.create_task(_make_task())
        tq.update_task_status("t1", TaskStatus.RUNNING)
        assert tq.cancel_task("t1") is True
        assert tq.get_task("t1").status == TaskStatus.CANCELLED

    def test_cancel_completed_fails(self, tq):
        tq.create_task(_make_task())
        tq.update_task_status("t1", TaskStatus.COMPLETED)
        assert tq.cancel_task("t1") is False


# ── Step Management ──

class TestStepManagement:
    def test_get_current_step(self, tq):
        tq.create_task(_make_task(steps_count=3))
        step = tq.get_current_step("t1")
        assert step is not None
        assert step.id == "t1_s0"

    def test_advance_step(self, tq):
        tq.create_task(_make_task(steps_count=3))
        tq.update_task_status("t1", TaskStatus.RUNNING)

        # Advance step 0 → 1
        next_step = tq.advance_step("t1", {"result": "ok"})
        assert next_step is not None
        assert next_step.id == "t1_s1"

        task = tq.get_task("t1")
        assert task.current_step_index == 1
        assert task.steps[0].status == TaskStepStatus.COMPLETED

    def test_advance_last_step_completes_task(self, tq):
        tq.create_task(_make_task(steps_count=2))
        tq.update_task_status("t1", TaskStatus.RUNNING)

        tq.advance_step("t1")  # step 0 → 1
        next_step = tq.advance_step("t1")  # step 1 → end
        assert next_step is None

        task = tq.get_task("t1")
        assert task.status == TaskStatus.COMPLETED

    def test_mark_step_running_and_completed(self, tq):
        tq.create_task(_make_task())
        tq.mark_step_running("t1", "t1_s0")
        step = tq.get_current_step("t1")
        assert step.status == TaskStepStatus.RUNNING

        tq.mark_step_completed("t1", "t1_s0", {"score": 8.5})
        # Read from the task directly
        task = tq.get_task("t1")
        assert task.steps[0].status == TaskStepStatus.COMPLETED
        assert task.steps[0].result == {"score": 8.5}

    def test_mark_step_failed(self, tq):
        tq.create_task(_make_task())
        tq.mark_step_failed("t1", "t1_s0", "LLM error")
        task = tq.get_task("t1")
        assert task.steps[0].status == TaskStepStatus.FAILED
        assert task.steps[0].error == "LLM error"
        assert task.steps[0].retry_count == 1

    def test_reset_step_for_retry(self, tq):
        tq.create_task(_make_task())
        tq.mark_step_failed("t1", "t1_s0", "error")
        tq.update_task_status("t1", TaskStatus.FAILED)

        tq.reset_step_for_retry("t1", "t1_s0")
        task = tq.get_task("t1")
        assert task.steps[0].status == TaskStepStatus.PENDING
        assert task.current_step_index == 0
        assert task.status == TaskStatus.PENDING


# ── Progress ──

class TestProgress:
    def test_progress_basic(self, tq):
        tq.create_task(_make_task(steps_count=3))
        tq.update_task_status("t1", TaskStatus.RUNNING)

        progress = tq.get_progress("t1")
        assert progress["total"] == 3
        assert progress["completed"] == 0
        assert progress["current_index"] == 0

        tq.advance_step("t1")
        progress = tq.get_progress("t1")
        assert progress["completed"] == 1
        assert progress["current_index"] == 1

    def test_progress_nonexistent_task(self, tq):
        assert tq.get_progress("nope") == {}


# ── Audit Mode ──

class TestAuditMode:
    def test_set_and_get_audit_mode(self, tq):
        tq.create_task(_make_task())
        assert tq.get_audit_mode("t1") == "soft"  # default

        assert tq.set_audit_mode("t1", "hard") is True
        assert tq.get_audit_mode("t1") == "hard"

        assert tq.set_audit_mode("t1", "invalid") is False
        assert tq.get_audit_mode("t1") == "hard"  # unchanged


# ── Persistence ──

class TestPersistence:
    def test_persistence_across_reload(self, tmp_data_dir):
        tq1 = TaskQueue(data_dir=tmp_data_dir)
        tq1.create_task(_make_task("t1"))
        tq1.update_task_status("t1", TaskStatus.RUNNING)
        tq1.advance_step("t1")

        # Create new TaskQueue instance (simulates server restart)
        tq2 = TaskQueue(data_dir=tmp_data_dir)
        task = tq2.get_task("t1")
        assert task is not None
        assert task.status == TaskStatus.RUNNING
        assert task.current_step_index == 1


# ── Archive ──

class TestArchive:
    def test_archive_completed(self, tq):
        from datetime import datetime, timedelta

        tq.create_task(_make_task("t1"))
        tq.update_task_status("t1", TaskStatus.COMPLETED)
        # Manually set completed_at to old date
        task = tq.get_task("t1")
        old_date = (datetime.now() - timedelta(days=10)).isoformat()
        task.completed_at = old_date
        tq._save()

        count = tq.archive_completed(older_than_days=7)
        assert count == 1
        assert tq.get_task("t1") is None
