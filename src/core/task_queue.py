"""Persistent Task Queue — enables long-running tasks with checkpoint/resume.

Core data structures:
- TaskStep: one unit of work inside a task (agent_loop, checkpoint, user_confirm, etc.)
- PersistentTask: an ordered list of steps with status tracking, persisted to JSON.

The queue is the single source of truth for task state. TaskRunner reads from it,
updates it after each step, and recovers from it on restart.
"""

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from .config import DATA_DIR

logger = logging.getLogger(__name__)


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TaskStep:
    id: str
    type: str  # "agent_loop" | "workflow_step" | "checkpoint" | "user_confirm"
    label: str = ""
    config: dict = field(default_factory=dict)
    status: str = TaskStepStatus.PENDING
    result: dict | None = None
    retry_count: int = 0
    max_retries: int = 2
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None


@dataclass
class PersistentTask:
    id: str
    type: str  # "autopilot" | "batch_write" | "workflow" | "custom" | "scheduled"
    book_id: str
    session_id: str
    label: str = ""
    status: str = TaskStatus.PENDING
    steps: list[TaskStep] = field(default_factory=list)
    current_step_index: int = 0
    created_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    created_by: str = "user"  # "user" | "autopilot" | "scheduler" | "supervisor"
    metadata: dict = field(default_factory=dict)
    parent_task_id: str | None = None
    error: str | None = None
    audit_mode: str = "soft"  # "hard" | "soft" | "autonomous"

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        # Ensure steps are serialized
        d["steps"] = [asdict(s) if isinstance(s, TaskStep) else s for s in self.steps]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PersistentTask":
        steps = []
        for s in data.get("steps", []):
            if isinstance(s, dict):
                steps.append(TaskStep(**s))
            else:
                steps.append(s)
        data["steps"] = steps
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class TaskQueue:
    """Thread-safe persistent task queue backed by a JSON file."""

    def __init__(self, data_dir: Path | None = None):
        self._dir = data_dir or DATA_DIR
        self._file = self._dir / "task_queue.json"
        self._tasks: dict[str, PersistentTask] = {}
        self._lock = threading.Lock()
        self._load()

    # ── Persistence ──

    def _load(self):
        if not self._file.exists():
            return
        try:
            data = json.loads(self._file.read_text(encoding="utf-8-sig"))
            for item in data:
                task = PersistentTask.from_dict(item)
                self._tasks[task.id] = task
        except (json.JSONDecodeError, OSError, TypeError, KeyError) as e:
            logger.warning("Failed to load task queue: %s", e)
            self._tasks = {}

    def _save(self):
        data = [t.to_dict() for t in self._tasks.values()]
        tmp = self._file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._file)

    # ── CRUD ──

    def update_task_meta(self, task_id: str, meta_updates: dict):
        """Thread-safe update of task metadata. Acquires the write lock."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.metadata = {**(task.metadata or {}), **meta_updates}
                self._save()

    def create_task(self, task: PersistentTask) -> PersistentTask:
        with self._lock:
            self._tasks[task.id] = task
            self._save()
            return task

    def get_task(self, task_id: str) -> PersistentTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(
        self,
        book_id: str = "",
        status: str | None = None,
        created_by: str | None = None,
    ) -> list[PersistentTask]:
        with self._lock:
            tasks = list(self._tasks.values())
        if book_id:
            tasks = [t for t in tasks if t.book_id == book_id]
        if status:
            tasks = [t for t in tasks if t.status == status]
        if created_by:
            tasks = [t for t in tasks if t.created_by == created_by]
        return tasks

    def delete_task(self, task_id: str) -> bool:
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                self._save()
                return True
            return False

    # ── Status Transitions ──

    def update_task_status(
        self, task_id: str, status: str, error: str | None = None
    ) -> PersistentTask | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            task.status = status
            if error:
                task.error = error
            now = datetime.now().isoformat()
            if status == TaskStatus.RUNNING and not task.started_at:
                task.started_at = now
            if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                task.completed_at = now
            self._save()
            return task

    # ── Step Management ──

    def get_current_step(self, task_id: str) -> TaskStep | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.current_step_index >= len(task.steps):
                return None
            return task.steps[task.current_step_index]

    def mark_step_running(self, task_id: str, step_id: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            for s in task.steps:
                if s.id == step_id:
                    s.status = TaskStepStatus.RUNNING
                    s.started_at = datetime.now().isoformat()
                    break
            self._save()

    def mark_step_completed(
        self, task_id: str, step_id: str, result: dict | None = None
    ) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            for s in task.steps:
                if s.id == step_id:
                    s.status = TaskStepStatus.COMPLETED
                    s.completed_at = datetime.now().isoformat()
                    s.result = result
                    break
            self._save()

    def mark_step_failed(self, task_id: str, step_id: str, error: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            for s in task.steps:
                if s.id == step_id:
                    s.status = TaskStepStatus.FAILED
                    s.error = error
                    s.retry_count += 1
                    break
            self._save()

    def advance_step(
        self, task_id: str, result: dict | None = None
    ) -> TaskStep | None:
        """Mark current step as completed, advance to next. Returns next step or None."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            idx = task.current_step_index
            if idx < len(task.steps):
                task.steps[idx].status = TaskStepStatus.COMPLETED
                task.steps[idx].completed_at = datetime.now().isoformat()
                if result is not None:
                    task.steps[idx].result = result
            task.current_step_index += 1
            if task.current_step_index >= len(task.steps):
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now().isoformat()
                self._save()
                return None
            next_step = task.steps[task.current_step_index]
            self._save()
            return next_step

    def reset_step_for_retry(self, task_id: str, step_id: str) -> None:
        """Reset a failed step back to pending for retry."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            for i, s in enumerate(task.steps):
                if s.id == step_id:
                    s.status = TaskStepStatus.PENDING
                    s.error = None
                    # Reset current_step_index to this step
                    task.current_step_index = i
                    break
            if task.status == TaskStatus.FAILED:
                task.status = TaskStatus.PENDING
                task.error = None
            self._save()

    def replace_remaining_steps(self, task_id: str, new_steps: list[TaskStep]) -> bool:
        """Replace all steps from current_step_index onwards with new_steps.

        Used by replan to dynamically adjust the remaining plan.
        Already-completed steps (before current_step_index) are preserved.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            idx = task.current_step_index
            # Keep completed steps, replace the rest
            task.steps = task.steps[:idx] + new_steps
            if task.status == TaskStatus.FAILED:
                task.status = TaskStatus.PENDING
                task.error = None
            self._save()
            return True

    # ── Pause / Resume / Cancel ──

    def pause_task(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.status != TaskStatus.RUNNING:
                return False
            task.status = TaskStatus.PAUSED
            self._save()
            return True

    def resume_task(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.status != TaskStatus.PAUSED:
                return False
            task.status = TaskStatus.PENDING
            self._save()
            return True

    def cancel_task(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.status in (
                TaskStatus.COMPLETED,
                TaskStatus.CANCELLED,
            ):
                return False
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now().isoformat()
            self._save()
            return True

    # ── Progress ──

    def get_progress(self, task_id: str) -> dict:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return {}
            total = len(task.steps)
            completed = sum(
                1 for s in task.steps if s.status == TaskStepStatus.COMPLETED
            )
            failed = sum(1 for s in task.steps if s.status == TaskStepStatus.FAILED)
            running = sum(1 for s in task.steps if s.status == TaskStepStatus.RUNNING)
            return {
                "task_id": task_id,
                "status": task.status,
                "total": total,
                "completed": completed,
                "failed": failed,
                "running": running,
                "current_index": task.current_step_index,
                "current_label": (
                    task.steps[task.current_step_index].label
                    if task.current_step_index < len(task.steps)
                    else ""
                ),
            }

    # ── Audit Mode (per-book config) ──

    def get_audit_mode(self, task_id: str) -> str:
        task = self.get_task(task_id)
        return task.audit_mode if task else "soft"

    def set_audit_mode(self, task_id: str, mode: str) -> bool:
        if mode not in ("hard", "soft", "autonomous"):
            return False
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            task.audit_mode = mode
            self._save()
            return True

    # ── Cleanup ──

    def archive_completed(self, older_than_days: int = 7) -> int:
        """Move old completed/cancelled tasks to archive file."""
        cutoff = datetime.now().timestamp() - older_than_days * 86400
        archived = []
        with self._lock:
            to_remove = []
            for tid, task in self._tasks.items():
                if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
                    if task.completed_at:
                        try:
                            ts = datetime.fromisoformat(task.completed_at).timestamp()
                            if ts < cutoff:
                                archived.append(task.to_dict())
                                to_remove.append(tid)
                        except (ValueError, TypeError):
                            pass
            for tid in to_remove:
                del self._tasks[tid]
            if archived:
                archive_file = self._dir / "task_queue_archive.json"
                existing = []
                if archive_file.exists():
                    try:
                        existing = json.loads(
                            archive_file.read_text(encoding="utf-8-sig")
                        )
                    except (json.JSONDecodeError, OSError):
                        pass
                existing.extend(archived)
                archive_file.write_text(
                    json.dumps(existing, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                self._save()
        return len(archived)


# Module-level singleton
task_queue = TaskQueue()
