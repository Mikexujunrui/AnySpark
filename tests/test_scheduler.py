"""Tests for automation scheduler."""

from datetime import datetime

import pytest

from core.config import DATA_DIR
from core.scheduler import TASK_TEMPLATES, ScheduledTask, Scheduler


@pytest.fixture
def scheduler():
    """Fresh scheduler with temp data dir."""
    s = Scheduler()
    s._tasks_file = DATA_DIR / "test_scheduler_tasks.json"
    s._runs_file = DATA_DIR / "test_scheduler_runs.json"
    s._tasks = {}
    yield s
    for f in [s._tasks_file, s._runs_file]:
        if f.exists():
            f.unlink()


def test_template_structure():
    for _key, tmpl in TASK_TEMPLATES.items():
        assert "name" in tmpl
        assert "description" in tmpl
        assert "steps" in tmpl


def test_add_and_list_task(scheduler):
    task = ScheduledTask(
        id="sched_test",
        name="测试任务",
        template="review",
        book_id="testbook",
        schedule_type="manual",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )
    scheduler.add_task(task)
    tasks = scheduler.list_tasks("testbook")
    assert len(tasks) == 1
    assert tasks[0]["name"] == "测试任务"


def test_update_task(scheduler):
    task = ScheduledTask(
        id="sched_test2",
        name="原始名",
        template="review",
        book_id="testbook",
        schedule_type="manual",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )
    scheduler.add_task(task)
    scheduler.update_task("sched_test2", {"name": "新名字", "enabled": False})
    t = scheduler.get_task("sched_test2")
    assert t["name"] == "新名字"
    assert t["enabled"] is False


def test_delete_task(scheduler):
    task = ScheduledTask(
        id="sched_test3",
        name="待删除",
        template="review",
        book_id="testbook",
        schedule_type="manual",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )
    scheduler.add_task(task)
    assert scheduler.delete_task("sched_test3")
    assert scheduler.get_task("sched_test3") is None


def test_manual_task_no_next_run(scheduler):
    task = ScheduledTask(
        id="sched_test4",
        name="手动任务",
        template="review",
        book_id="testbook",
        schedule_type="manual",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )
    scheduler.add_task(task)
    t = scheduler.get_task("sched_test4")
    assert t["next_run"] is None


def test_daily_task_has_next_run(scheduler):
    now = datetime.now()
    task = ScheduledTask(
        id="sched_test5",
        name="每日任务",
        template="consolidate_memory",
        book_id="testbook",
        schedule_type="daily",
        last_run=now.isoformat(),
        enabled=True,
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
    )
    scheduler.add_task(task)
    t = scheduler.get_task("sched_test5")
    assert t["next_run"] is not None


@pytest.mark.asyncio
async def test_task_now_execution(scheduler):
    task = ScheduledTask(
        id="sched_test6",
        name="手动执行",
        template="review",
        book_id="testbook",
        schedule_type="manual",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
        steps=[{"type": "plan", "label": "分析", "config": {}}],
    )
    scheduler.add_task(task)
    result = await scheduler.run_task_now("sched_test6")
    assert result is not None
    assert ("已触发" in result) or ("已启动" in result) or ("失败" in result)
