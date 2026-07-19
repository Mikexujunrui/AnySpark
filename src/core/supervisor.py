"""Supervisor — background daemon that monitors and manages persistent tasks.

Responsibilities:
  1. Monitor running tasks — detect orphans (asyncio.Task died silently)
  2. Retry failed steps — exponential backoff, max 3 retries
  3. Detect stale tasks — no progress for > 1 hour
  4. Integrate with Scheduler — convert scheduled tasks to PersistentTasks
  5. Notify frontend — via EventBus when human intervention needed

Relationship with other components:
  - Scheduler: time-driven trigger; Supervisor handles what happens after
  - TaskRunner: executes tasks; Supervisor watches over it
  - Autopilot: creates tasks; Supervisor ensures they complete
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from .event_bus import Event, EventType, bus
from .task_queue import TaskStatus, TaskStepStatus

logger = logging.getLogger(__name__)


@dataclass
class SupervisorConfig:
    check_interval: int = 30  # seconds between checks
    max_auto_retries: int = 3
    retry_backoff_base: float = 10.0  # seconds
    retry_backoff_max: float = 300.0  # 5 minutes max
    stale_task_timeout: int = 3600  # 1 hour without progress
    auto_resume_on_start: bool = True


class Supervisor:
    """Background supervision daemon for persistent tasks."""

    def __init__(self):
        self._config = SupervisorConfig()
        self._loop_task: asyncio.Task | None = None
        self._runner = None  # TaskRunner reference
        self._queue = None   # TaskQueue reference
        self._retry_tracker: dict[str, int] = {}  # "task_id:step_id" → count
        self._last_activity: dict[str, str] = {}  # task_id → last progress timestamp

    def set_runner(self, runner, queue):
        """Set the TaskRunner and TaskQueue references. Called from server.py."""
        self._runner = runner
        self._queue = queue

    def start(self):
        """Start the supervision loop as a background asyncio.Task."""
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(
                self._supervision_loop(), name="supervisor"
            )
            logger.info("Supervisor started (interval=%ds)", self._config.check_interval)

    def stop(self):
        """Stop the supervision loop."""
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            self._loop_task = None
            logger.info("Supervisor stopped")

    def get_status(self) -> dict:
        """Get supervisor status for the API."""
        running = self._loop_task is not None and not self._loop_task.done()
        return {
            "running": running,
            "check_interval": self._config.check_interval,
            "tracked_retries": len(self._retry_tracker),
            "active_tasks": len(self._runner.active_task_ids) if self._runner else 0,
        }

    # ── Main Loop ──

    async def _supervision_loop(self):
        """Periodic check loop — runs every check_interval seconds."""
        while True:
            try:
                await self._check_running_tasks()
                await self._check_stale_tasks()
                await self._check_failed_tasks()
                await self._check_scheduled_tasks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Supervisor loop error: %s", e)
            await asyncio.sleep(self._config.check_interval)

    # ── Check: Running Tasks ──

    async def _check_running_tasks(self):
        """Verify that RUNNING tasks still have active asyncio.Tasks."""
        if not self._runner or not self._queue:
            return

        running_tasks = self._queue.list_tasks(status=TaskStatus.RUNNING)
        for task in running_tasks:
            atask = self._runner._running.get(task.id)
            if atask is None or atask.done():
                # Orphan detected — task marked RUNNING but no asyncio.Task
                logger.warning(
                    "Orphan task %s: status=RUNNING but no active asyncio.Task",
                    task.id,
                )
                # Check if it actually completed
                progress = self._queue.get_progress(task.id)
                if progress.get("completed", 0) == progress.get("total", 0) > 0:
                    self._queue.update_task_status(task.id, TaskStatus.COMPLETED)
                else:
                    # Reset to PENDING so it can be restarted
                    self._queue.update_task_status(task.id, TaskStatus.PENDING)
                    # Record for retry
                    self._notify(
                        task,
                        f"任务 {task.label} 的执行进程异常中断，将自动重试",
                    )

    # ── Check: Stale Tasks ──

    async def _check_stale_tasks(self):
        """Detect tasks that haven't made progress for too long."""
        if not self._queue:
            return

        now = datetime.now()
        cutoff = now - timedelta(seconds=self._config.stale_task_timeout)

        running_tasks = self._queue.list_tasks(status=TaskStatus.RUNNING)
        for task in running_tasks:
            last_activity = self._last_activity.get(task.id)
            if not last_activity:
                # Use task's started_at as fallback
                last_activity = task.started_at or task.created_at
                self._last_activity[task.id] = last_activity

            try:
                last_dt = datetime.fromisoformat(last_activity)
                if last_dt < cutoff:
                    logger.warning("Stale task %s: no progress for %s",
                                   task.id, now - last_dt)
                    self._notify(
                        task,
                        f"任务 {task.label} 已超过1小时无进展，已标记为暂停",
                    )
                    self._queue.update_task_status(task.id, TaskStatus.PAUSED)
                    # Cancel the asyncio.Task if still running
                    if self._runner:
                        await self._runner.pause_task(task.id)
            except (ValueError, TypeError):
                pass

    # ── Check: Failed Tasks ──

    async def _check_failed_tasks(self):
        """Auto-retry failed tasks with exponential backoff."""
        if not self._runner or not self._queue:
            return

        failed_tasks = self._queue.list_tasks(status=TaskStatus.FAILED)
        for task in failed_tasks:
            # Find the failed step
            failed_step = None
            for step in task.steps:
                if step.status == TaskStepStatus.FAILED:
                    failed_step = step
                    break

            if not failed_step:
                continue

            retry_key = f"{task.id}:{failed_step.id}"
            count = self._retry_tracker.get(retry_key, 0)

            if count >= self._config.max_auto_retries:
                # Exhausted retries — notify user
                if count == self._config.max_auto_retries:
                    self._notify(
                        task,
                        f"任务 {task.label} 的步骤 '{failed_step.label}' "
                        f"已重试{count}次仍然失败，需要人工介入",
                    )
                    self._retry_tracker[retry_key] = count + 1  # Prevent re-notification
                continue

            # Calculate backoff delay
            delay = min(
                self._config.retry_backoff_base * (2 ** count),
                self._config.retry_backoff_max,
            )

            # Check if enough time has passed since the failure
            if failed_step.completed_at:
                try:
                    fail_time = datetime.fromisoformat(failed_step.completed_at)
                    elapsed = (datetime.now() - fail_time).total_seconds()
                    if elapsed < delay:
                        continue  # Not time yet
                except (ValueError, TypeError):
                    pass

            logger.info(
                "Auto-retrying task %s step %s (attempt %d/%d, delay=%.0fs)",
                task.id, failed_step.id, count + 1,
                self._config.max_auto_retries, delay,
            )
            self._retry_tracker[retry_key] = count + 1

            try:
                await self._runner.retry_step(task.id, failed_step.id)
            except Exception as e:
                logger.error("Auto-retry failed for task %s: %s", task.id, e)

    # ── Check: Scheduled Tasks ──

    async def _check_scheduled_tasks(self):
        """Bridge between Scheduler and TaskQueue.

        Scans for PENDING tasks created by the scheduler that haven't been
        started yet (e.g., if scheduler created them but TaskRunner wasn't ready,
        or if they were recovered after a restart).
        """
        if not self._runner or not self._queue:
            return

        pending_tasks = self._queue.list_tasks(status=TaskStatus.PENDING)
        for task in pending_tasks:
            if task.created_by != "scheduler":
                continue
            if task.id in self._runner._running and not self._runner._running[task.id].done():
                continue
            logger.info("Supervisor starting scheduler-created task %s", task.id)
            try:
                await self._runner.start_task(task.id)
            except Exception as e:
                logger.error("Supervisor failed to start task %s: %s", task.id, e)

    # ── Activity Tracking ──

    def record_activity(self, task_id: str):
        """Record that a task made progress (called by event listener)."""
        self._last_activity[task_id] = datetime.now().isoformat()

    # ── Notifications ──

    def _notify(self, task, message: str):
        """Send a notification to the frontend via EventBus."""
        try:
            bus.emit_sync(Event(
                type=EventType.TASK_NOTIFICATION,
                data={
                    "task_id": task.id,
                    "book_id": task.book_id,
                    "message": message,
                    "task_label": task.label,
                },
                source="supervisor",
            ))
        except Exception as e:
            logger.warning("Supervisor notification failed: %s", e)


# Module-level singleton
supervisor = Supervisor()
