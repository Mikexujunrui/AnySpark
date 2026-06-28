"""Automation Scheduler — periodic task execution integrated with Workflow Engine."""

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .config import DATA_DIR

logger = logging.getLogger(__name__)

TASK_TEMPLATES = {
    "consolidate_memory": {
        "name": "记忆合并",
        "description": "定期整理知识库，合并重复实体，清理过期状态",
        "steps": [
            {"type": "extract", "label": "知识提取", "config": {"text": ""}},
            {"type": "validate", "label": "一致性校验", "config": {}},
        ],
    },
    "review": {
        "name": "回顾分析",
        "description": "分析近期章节的大纲、时间线、世界观完整性",
        "steps": [
            {"type": "plan", "label": "分析大纲", "config": {"message": "分析知识库完整性"}},
        ],
    },
    "continue_writing": {
        "name": "自动续写",
        "description": "根据大纲和知识库自动生成下一章草稿",
        "steps": [
            {"type": "plan", "label": "规划内容", "config": {"message": "根据大纲决定续写方向"}},
            {"type": "write", "label": "AI写作", "config": {"instruction": "续写下一章"}},
        ],
    },
    "custom": {
        "name": "自定义",
        "description": "用户自定义工作流步骤",
        "steps": [],
    },
}


@dataclass
class ScheduledTask:
    id: str
    name: str
    template: str
    book_id: str
    schedule_type: str  # manual, daily, weekly, monthly, every_n_hours
    schedule_value: str = ""  # e.g. "24" for every_n_hours, "0 9 * * *" for future cron
    steps: list[dict] = field(default_factory=list)
    enabled: bool = True
    last_run: str | None = None
    next_run: str | None = None
    created_at: str = ""
    updated_at: str = ""
    run_count: int = 0


class Scheduler:
    def __init__(self):
        self._tasks_file = DATA_DIR / "scheduler_tasks.json"
        self._runs_file = DATA_DIR / "scheduler_runs.json"
        self._tasks: dict[str, ScheduledTask] = {}
        self._loop_task: asyncio.Task | None = None
        self._check_interval = 60
        self._trigger_hooks: list[Callable] = []

    def on_trigger(self, hook: Callable):
        self._trigger_hooks.append(hook)

    # ── Persistence ──

    def _load_tasks(self) -> dict[str, ScheduledTask]:
        if self._tasks_file.exists():
            try:
                data = json.loads(self._tasks_file.read_text(encoding="utf-8-sig"))
                return {t["id"]: ScheduledTask(**t) for t in data}
            except Exception:
                return {}
        return {}

    def _save_tasks(self):
        data = [t.__dict__ for t in self._tasks.values()]
        self._tasks_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _load_runs(self) -> list[dict]:
        if self._runs_file.exists():
            try:
                return json.loads(self._runs_file.read_text(encoding="utf-8-sig"))
            except Exception:
                return []
        return []

    def _save_runs(self, runs: list[dict]):
        self._runs_file.write_text(
            json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ── Task CRUD ──

    def load(self):
        self._tasks = self._load_tasks()
        self._recompute_next_runs()

    def list_tasks(self, book_id: str = "") -> list[dict]:
        tasks = self._tasks.values()
        if book_id:
            tasks = [t for t in tasks if t.book_id == book_id]
        return [t.__dict__ for t in tasks]

    def get_task(self, task_id: str) -> dict | None:
        t = self._tasks.get(task_id)
        return t.__dict__ if t else None

    def add_task(self, task: ScheduledTask) -> ScheduledTask:
        task.next_run = self._compute_next_run(task)
        self._tasks[task.id] = task
        self._save_tasks()
        return task

    def update_task(self, task_id: str, updates: dict) -> dict | None:
        t = self._tasks.get(task_id)
        if not t:
            return None
        for k, v in updates.items():
            if hasattr(t, k) and k not in ("id", "created_at"):
                setattr(t, k, v)
        t.updated_at = datetime.now().isoformat()
        t.next_run = self._compute_next_run(t)
        self._save_tasks()
        return t.__dict__

    def delete_task(self, task_id: str) -> bool:
        if task_id in self._tasks:
            del self._tasks[task_id]
            self._save_tasks()
            return True
        return False

    async def run_task_now(self, task_id: str) -> str | None:
        t = self._tasks.get(task_id)
        if not t:
            return None
        return await self._execute_task(t)

    def get_run_history(self, task_id: str = "", limit: int = 50) -> list[dict]:
        runs = self._load_runs()
        if task_id:
            runs = [r for r in runs if r.get("task_id") == task_id]
        return runs[-limit:]

    # ── Scheduling Logic ──

    def _compute_next_run(self, task: ScheduledTask) -> str | None:
        if not task.enabled or task.schedule_type == "manual":
            return None
        now = datetime.now()
        if task.last_run:
            last = datetime.fromisoformat(task.last_run)
        else:
            return now.isoformat()

        if task.schedule_type == "daily":
            next_time = last + timedelta(days=1)
        elif task.schedule_type == "weekly":
            next_time = last + timedelta(weeks=1)
        elif task.schedule_type == "monthly":
            next_time = last + timedelta(days=30)
        elif task.schedule_type == "every_n_hours":
            hours = int(task.schedule_value) if task.schedule_value.isdigit() else 24
            next_time = last + timedelta(hours=hours)
        else:
            return None
        return next_time.isoformat()

    def _recompute_next_runs(self):
        for t in self._tasks.values():
            t.next_run = self._compute_next_run(t)

    def _get_due_tasks(self) -> list[ScheduledTask]:
        now = datetime.now()
        due = []
        for t in self._tasks.values():
            if not t.enabled or t.schedule_type == "manual":
                continue
            if t.next_run:
                try:
                    next_time = datetime.fromisoformat(t.next_run)
                    if next_time <= now:
                        due.append(t)
                except (ValueError, TypeError):
                    continue
        return due

    # ── Execution ──

    async def _execute_task(self, task: ScheduledTask) -> str:
        steps = task.steps or TASK_TEMPLATES.get(task.template, {}).get("steps", [])
        if not steps:
            return f"任务 {task.name} 没有可执行的步骤"

        wf_id = f"sched_{task.id}_{int(datetime.now().timestamp())}"

        run_id = wf_id
        run_record = {
            "run_id": run_id,
            "task_id": task.id,
            "task_name": task.name,
            "book_id": task.book_id,
            "started_at": datetime.now().isoformat(),
            "status": "running",
            "result": "",
        }

        runs = self._load_runs()
        runs.append(run_record)
        self._save_runs(runs)

        # ── Create PersistentTask for TaskRunner execution ──
        pt_id = wf_id
        try:
            from core.task_queue import PersistentTask, task_queue
            from core.task_queue import TaskStep as PTStep
            pt_steps = []
            for i, s in enumerate(steps):
                pt_steps.append(PTStep(
                    id=f"{wf_id}_s{i}",
                    type="workflow_step",
                    label=s.get("label", s.get("type", f"步骤{i+1}")),
                    config=s,
                ))
            pt = PersistentTask(
                id=wf_id,
                type="scheduled",
                book_id=task.book_id,
                session_id=f"sched_{task.id}",
                label=task.name,
                steps=pt_steps,
                created_by="scheduler",
            )
            task_queue.create_task(pt)
            run_record["persistent_task_id"] = wf_id
        except Exception as e:
            logger.warning("Failed to create PersistentTask: %s", e)

        for hook in self._trigger_hooks:
            try:
                hook(task, run_id)
            except Exception:
                logger.exception(f"trigger hook failed for task {task.id}")

        task.last_run = datetime.now().isoformat()
        task.next_run = self._compute_next_run(task)
        task.run_count += 1
        self._save_tasks()

        run_record["status"] = "triggered"
        run_record["result"] = f"工作流 {wf_id} 已触发"
        self._save_runs(self._load_runs())

        # ── Start the PersistentTask via TaskRunner ──
        try:
            from core.headless_loop import get_task_runner
            runner = get_task_runner()
            if runner:
                await runner.start_task(pt_id)
                run_record["status"] = "started"
                run_record["result"] = f"任务 {task.name} 已启动 (task: {pt_id})"
                self._save_runs(self._load_runs())
                return f"任务 {task.name} 已启动 (task: {pt_id})"
        except Exception as e:
            logger.error("Failed to start PersistentTask %s: %s", pt_id, e)
            run_record["status"] = "failed_to_start"
            run_record["result"] = f"任务已创建但启动失败: {e}"
            self._save_runs(self._load_runs())

        return f"任务 {task.name} 已触发 (workflow: {wf_id})"

    async def _check_loop(self):
        while True:
            try:
                due = self._get_due_tasks()
                for task in due:
                    try:
                        await self._execute_task(task)
                    except Exception as e:
                        logger.error(f"Task {task.id} execution failed: {e}")
            except Exception as e:
                logger.error(f"Scheduler check error: {e}")
            await asyncio.sleep(self._check_interval)

    def start(self):
        self.load()
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._check_loop())
            logger.info("Scheduler started")

    def stop(self):
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            self._loop_task = None
            logger.info("Scheduler stopped")


engine = Scheduler()
