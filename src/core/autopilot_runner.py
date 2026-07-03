# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Autopilot Runner — task lifecycle management.

Extracted from autopilot.py to separate the execution/lifecycle concern
from the planning/intent-classification concern.

AutopilotExecutor handles: plan → start → confirm → pause → resume → cancel → status.
"""

import logging
import time

from .autopilot import AutopilotConfig, AutopilotPlanner
from .headless_loop import get_task_runner
from .task_queue import (
    PersistentTask,
    task_queue,
)

logger = logging.getLogger(__name__)


class AutopilotExecutor:
    """Manages autopilot task lifecycle — plan, start, monitor, stop."""

    def __init__(self):
        self._active_configs: dict[str, AutopilotConfig] = {}

    async def start(self, config: AutopilotConfig) -> dict:
        """Plan and optionally start an autopilot task."""
        planner = AutopilotPlanner()
        plan = await planner.plan(config)

        task_id = f"autopilot_{int(time.time() * 1000)}"
        steps = plan["steps"]

        task = PersistentTask(
            id=task_id,
            type="autopilot",
            book_id=config.book_id,
            session_id=config.session_id or config.book_id,
            label=config.instruction[:80],
            steps=steps,
            audit_mode=config.audit_mode,
            created_by="autopilot",
            metadata={
                "plan_summary": plan["plan_summary"],
                "total_chapters": plan["estimated_chapters"],
                "chapters_completed": 0,
                "tokens_used": 0,
                "token_budget": config.token_budget,
                "auto_review": config.auto_review,
                "auto_extract": config.auto_extract,
                "pause_between_chapters": config.pause_between_chapters,
                "quality_gate": config.quality_gate,
                "instruction": config.instruction,
                "intent_type": plan.get("intent_type", "write_new"),
                "replan_count": 0,
                "max_replans": config.max_replans,
                "enable_replan": config.enable_replan,
                "plan_version": 1,
            },
        )
        task_queue.create_task(task)
        self._active_configs[task_id] = config

        if not config.confirm_before_start:
            runner = get_task_runner()
            if runner:
                await runner.start_task(task_id)

        return {
            "task_id": task_id,
            "plan_summary": plan["plan_summary"],
            "chapters": plan.get("chapters", []),
            "total_steps": plan["total_steps"],
            "status": task.status,
            "needs_confirm": config.confirm_before_start,
            "intent_type": plan.get("intent_type", "write_new"),
        }

    async def confirm_start(self, task_id: str) -> bool:
        """Confirm and start an autopilot task that was waiting for confirmation."""
        task = task_queue.get_task(task_id)
        if not task or task.type != "autopilot":
            return False
        if task.status != "pending":
            return False

        runner = get_task_runner()
        if not runner:
            return False

        return await runner.start_task(task_id)

    async def pause(self, task_id: str) -> bool:
        runner = get_task_runner()
        if not runner:
            return False
        return await runner.pause_task(task_id)

    async def resume(self, task_id: str) -> bool:
        runner = get_task_runner()
        if not runner:
            return False
        return await runner.resume_task(task_id)

    async def cancel(self, task_id: str) -> bool:
        runner = get_task_runner()
        if not runner:
            return False
        self._active_configs.pop(task_id, None)
        return await runner.cancel_task(task_id)

    def get_status(self, task_id: str) -> dict:
        """Get autopilot task status with chapter-level progress."""
        task = task_queue.get_task(task_id)
        if not task:
            return {}

        progress = task_queue.get_progress(task_id)
        meta = task.metadata or {}

        # Count completed chapters
        chapters_completed = 0
        for step in task.steps:
            if (step.type == "checkpoint"
                    and step.config.get("final")
                    and step.status == "completed"):
                chapters_completed += 1

        return {
            "task_id": task_id,
            "status": task.status,
            "audit_mode": task.audit_mode,
            "label": task.label,
            "progress": progress,
            "chapters_completed": chapters_completed,
            "total_chapters": meta.get("total_chapters", 0),
            "tokens_used": meta.get("tokens_used", 0),
            "token_budget": meta.get("token_budget", 0),
            "plan_summary": meta.get("plan_summary", ""),
            "intent_type": meta.get("intent_type", "write_new"),
            "replan_count": meta.get("replan_count", 0),
            "error": task.error,
        }

    async def check_budget(self, task_id: str) -> bool:
        """Check if token budget is still available.

        Returns True if budget is sufficient or unlimited (budget <= 0).
        """
        task = task_queue.get_task(task_id)
        if not task:
            return False
        meta = task.metadata or {}
        budget = meta.get("token_budget", 500_000)
        if budget <= 0:
            return True
        used = meta.get("tokens_used", 0)
        return used < budget

    def update_tokens(self, task_id: str, additional_tokens: int):
        """Update token usage counter in task metadata (thread-safe)."""
        task = task_queue.get_task(task_id)
        if not task:
            return
        meta = task.metadata or {}
        task_queue.update_task_meta(task_id, {
            "tokens_used": meta.get("tokens_used", 0) + additional_tokens,
        })


# Module-level singleton
autopilot = AutopilotExecutor()
