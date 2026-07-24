"""Headless Agent Loop — run agent_loop without an HTTP/SSE connection.

This is the lightweight bridge between the persistent task engine and the
existing agent_loop. Instead of binding the loop to an SSE response, it:
  1. Creates an isolated session (headless_{source}_{timestamp})
  2. Calls run_agent_loop() and collects LoopEvents
  3. Broadcasts progress to event_bus (so online SSE can relay it)
  4. Persists the turn to json_store (same format as normal chat)
  5. Returns the final text output

Used by: TaskRunner (for task steps), Scheduler (for scheduled tasks),
         Autopilot (for chapter writing), Supervisor (for retries).
"""

import asyncio
import logging
import time
from dataclasses import dataclass

from .agent_loop import AgentConfig, run_agent_loop
from .config import config
from .event_bus import Event, EventType, bus
from .task_queue import TaskStatus

logger = logging.getLogger(__name__)


# ── Step Context Accumulator ──


class StepContextAccumulator:
    """Collects results from completed steps and provides context injection for subsequent steps.

    This enables step-to-step context passing: the output of a planning step
    can be injected into the following writing step's prompt, etc.
    """

    def __init__(self):
        self._results: dict[str, dict] = {}  # step_id → result
        self._chapter_outputs: dict[int, str] = {}  # chapter_index → text summary
        self._recent_steps: list[tuple[str, str, str]] = []  # (step_id, label, result_summary)

    def record(self, step_id: str, step, result: dict):
        """Record a completed step's result."""
        self._results[step_id] = result

        # Track recent steps (keep last 5)
        summary = self._extract_summary(result)
        label = getattr(step, "label", step_id) or step_id
        self._recent_steps.append((step_id, label, summary))
        if len(self._recent_steps) > 5:
            self._recent_steps = self._recent_steps[-5:]

        # Track chapter outputs
        cfg = getattr(step, "config", {}) or {}
        chapter_idx = cfg.get("chapter_index")
        if chapter_idx is not None:
            text = result.get("text", "")
            self._chapter_outputs[int(chapter_idx)] = text[:500] if text else ""

    def _extract_summary(self, result: dict, max_len: int = 300) -> str:
        """Extract a concise summary from a step result."""
        if not result:
            return ""
        text = result.get("text", "")
        if not text:
            return ""
        if len(text) > max_len:
            return text[:max_len] + "..."
        return text

    def build_context_injection(self, step, all_steps: list) -> str:
        """Build context text to inject into a step's prompt.

        Strategy:
        1. Check for explicit context_bindings in step config
        2. Otherwise: inject recent step summaries + related chapter outputs
        """
        if not self._recent_steps and not self._chapter_outputs:
            return ""

        cfg = getattr(step, "config", {}) or {}
        bindings = cfg.get("context_bindings", [])

        parts = []

        if bindings:
            # Explicit bindings from LLM planner
            for binding in bindings:
                source_id = binding.get("source_step_id", "")
                source_result = self._results.get(source_id, {})
                btype = binding.get("binding_type", "summary")
                template = binding.get("template", "前序步骤结果: {result}")

                if btype == "full_result":
                    content = source_result.get("text", "")[:2000]
                elif btype == "summary":
                    content = self._extract_summary(source_result, 300)
                elif btype == "quality_score":
                    q = source_result.get("quality", {})
                    content = f"评分: {q.get('score', 'N/A')}, 评语: {q.get('summary', '')[:200]}"
                    # Surface AI flavor issues if available
                    ai_issues = q.get("ai_flavor_issues", [])
                    if ai_issues:
                        issues_text = "; ".join(ai_issues[:3])
                        content += f" | AI味警告: {issues_text}"
                elif btype == "chapter_ref":
                    idx = source_result.get("chapter_index", "")
                    content = f"章节 #{idx} 已完成"
                else:
                    content = str(source_result)[:500]

                parts.append(template.replace("{result}", content))
        else:
            # Default: inject recent step summaries
            recent_summaries = []
            for _sid, label, summary in self._recent_steps[-3:]:
                if summary:
                    recent_summaries.append(f"[{label}] {summary}")
            if recent_summaries:
                parts.append("最近完成的步骤:\n" + "\n".join(recent_summaries))

        # Inject related chapter context
        chapter_idx = cfg.get("chapter_index")
        if chapter_idx is not None:
            # For writing/editing chapter N, inject chapter N-1's output
            prev_idx = int(chapter_idx) - 1
            if prev_idx in self._chapter_outputs:
                prev_text = self._chapter_outputs[prev_idx]
                if prev_text:
                    parts.append(f"前一章(第{prev_idx}章)摘要: {prev_text}")

        return "\n\n".join(parts)


@dataclass
class HeadlessResult:
    success: bool = True
    text: str = ""
    session_id: str = ""
    rounds: int = 0
    error: str = ""
    metrics: dict = None

    def __post_init__(self):
        if self.metrics is None:
            self.metrics = {}


async def run_agent_loop_headless(
    book_id: str,
    instruction: str,
    agent_config: AgentConfig | None = None,
    source: str = "manual",
    parent_session_id: str = "",
    task_id: str = "",
    history_messages: list[dict] | None = None,
) -> HeadlessResult:
    """Execute agent_loop without an HTTP connection.

    Args:
        book_id: The book to operate on.
        instruction: The prompt/instruction for the agent.
        agent_config: Optional pre-built config; auto-created if None.
        source: Origin of this call — "manual", "scheduler", "autopilot", "supervisor".
        parent_session_id: The user-facing session that initiated this (for context).
        task_id: Associated PersistentTask ID (for progress broadcasting).
        history_messages: Optional conversation history to pass to the agent.

    Returns:
        HeadlessResult with success status, final text, and metrics.
    """
    session_id = f"headless_{source}_{int(time.time() * 1000)}"

    if agent_config is None:
        agent_config = AgentConfig(
            agent_type="write",
            mode="write",
            book_id=book_id,
            session_id=session_id,
        )
    else:
        # Override session_id to isolate from user's active session
        agent_config.session_id = session_id

    # Broadcast start event
    await bus.emit(
        Event(
            type=EventType.HEADLESS_LOOP_PROGRESS,
            data={
                "task_id": task_id,
                "book_id": book_id,
                "session_id": session_id,
                "source": source,
                "stage": "started",
                "instruction": instruction[:200],
            },
            source="headless_loop",
        )
    )

    final_text = ""
    turn_parts = None
    total_rounds = 0
    metrics_data = {}

    try:
        async for event in run_agent_loop(instruction, agent_config, history_messages):
            # Broadcast each event for online SSE relay
            await bus.emit(
                Event(
                    type=EventType.HEADLESS_LOOP_PROGRESS,
                    data={
                        "task_id": task_id,
                        "book_id": book_id,
                        "session_id": session_id,
                        "source": source,
                        "event_type": event.type,
                        **event.data,
                    },
                    source="headless_loop",
                )
            )

            # Collect results
            if event.type == "done":
                final_text = event.data.get("message", "")
                turn_parts = event.data.get("parts")
                total_rounds = event.data.get("rounds", 0)
                metrics_data = event.data.get("metrics", {})
            elif event.type == "text" and not final_text:
                final_text = event.data.get("content", "")
            elif event.type == "error":
                final_text = event.data.get("message", "处理出错")
                return HeadlessResult(
                    success=False,
                    text=final_text,
                    session_id=session_id,
                    rounds=total_rounds,
                    error=final_text,
                    metrics=metrics_data,
                )

    except asyncio.CancelledError:
        logger.info("Headless loop cancelled for session %s", session_id)
        return HeadlessResult(
            success=False,
            text="任务已取消",
            session_id=session_id,
            rounds=total_rounds,
            error="cancelled",
        )
    except Exception as e:
        logger.exception("Headless loop error for session %s: %s", session_id, e)
        return HeadlessResult(
            success=False,
            text="",
            session_id=session_id,
            rounds=total_rounds,
            error=str(e)[:300],
        )

    # Persist the turn so it appears in session history
    if final_text:
        _persist_headless_turn(
            book_id, session_id, instruction, final_text, mode="write", parts=turn_parts, source=source
        )

    # Broadcast completion
    await bus.emit(
        Event(
            type=EventType.HEADLESS_LOOP_PROGRESS,
            data={
                "task_id": task_id,
                "book_id": book_id,
                "session_id": session_id,
                "source": source,
                "stage": "completed",
                "text_preview": final_text[:200],
                "rounds": total_rounds,
            },
            source="headless_loop",
        )
    )

    return HeadlessResult(
        success=True,
        text=final_text,
        session_id=session_id,
        rounds=total_rounds,
        metrics=metrics_data,
    )


def _persist_headless_turn(
    book_id: str,
    session_id: str,
    user_text: str,
    agent_text: str,
    mode: str = "write",
    parts: list | None = None,
    source: str = "manual",
):
    """Persist a headless turn to json_store so it appears in session history."""
    try:
        from datetime import datetime

        from data.json_store import json_store

        # Create a session record if it doesn't exist
        sessions = json_store.load_sessions(book_id)
        if not any(s.get("id") == session_id for s in sessions):
            sessions.append(
                {
                    "id": session_id,
                    "title": f"[{source}] {user_text[:30]}",
                    "createdAt": datetime.now().isoformat(),
                    "updatedAt": datetime.now().isoformat(),
                    "messageCount": 0,
                }
            )
            json_store.save_sessions(book_id, sessions)

        # Persist as a normal turn (compatible with _load_history_as_llm_messages)
        turn = {
            "session_id": session_id,
            "role": "user",
            "text": user_text,
            "mode": mode,
            "timestamp": datetime.now().isoformat(),
        }
        json_store.append_message(session_id, turn, book_id=book_id)

        response_turn = {
            "session_id": session_id,
            "role": "assistant",
            "text": agent_text,
            "mode": mode,
            "timestamp": datetime.now().isoformat(),
            "parts": parts,
            "source": source,
        }
        json_store.append_message(session_id, response_turn, book_id=book_id)

    except Exception as e:
        logger.warning("Failed to persist headless turn: %s", e)


# ── Task Runner: drives PersistentTask steps using headless loop ──


class TaskRunner:
    """Drives PersistentTask execution using headless agent loops.

    Each task runs in a background asyncio.Task. Steps of type "agent_loop"
    call run_agent_loop_headless(). Progress is broadcast via event_bus
    so online SSE connections can relay it to the frontend.
    """

    def __init__(self, task_queue):
        self._queue = task_queue
        self._running: dict[str, asyncio.Task] = {}  # task_id → asyncio.Task
        self._cancel_flags: dict[str, asyncio.Event] = {}  # task_id → cancel event
        self._accumulators: dict[str, StepContextAccumulator] = {}  # task_id → accumulator
        self._skip_flags: dict[str, bool] = {}  # task_id → skip current step
        self._skip_lock = asyncio.Lock()  # protects _skip_flags and _running check

    @property
    def active_task_ids(self) -> list[str]:
        return [tid for tid, t in self._running.items() if not t.done()]

    async def start_task(self, task_id: str) -> bool:
        """Start executing a task in the background."""
        task = self._queue.get_task(task_id)
        if not task:
            logger.warning("Task %s not found", task_id)
            return False

        if task_id in self._running and not self._running[task_id].done():
            logger.warning("Task %s already running", task_id)
            return False

        self._queue.update_task_status(task_id, "running")
        cancel_event = asyncio.Event()
        self._cancel_flags[task_id] = cancel_event

        # Broadcast task started
        await bus.emit(
            Event(
                type=EventType.TASK_STARTED,
                data={"task_id": task_id, "book_id": task.book_id, "label": task.label, "total_steps": len(task.steps)},
                source="task_runner",
            )
        )

        atask = asyncio.create_task(
            self._run_task(task_id, cancel_event),
            name=f"task_{task_id}",
        )
        self._running[task_id] = atask
        return True

    async def pause_task(self, task_id: str) -> bool:
        """Pause a running task (waits for current step to finish)."""
        if task_id in self._cancel_flags:
            self._cancel_flags[task_id].set()
        return self._queue.pause_task(task_id)

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        if task_id in self._cancel_flags:
            self._cancel_flags[task_id].set()
        atask = self._running.get(task_id)
        if atask and not atask.done():
            atask.cancel()
        self._running.pop(task_id, None)
        self._cancel_flags.pop(task_id, None)
        return self._queue.cancel_task(task_id)

    async def resume_task(self, task_id: str) -> bool:
        """Resume a paused task."""
        if not self._queue.resume_task(task_id):
            return False
        return await self.start_task(task_id)

    async def request_skip(self, task_id: str) -> bool:
        """Request skipping the current step (used by external intervention).
        The _run_task loop will check this flag and handle the skip atomically,
        avoiding the race condition where both the intervention handler and
        _run_task call advance_step concurrently."""
        async with self._skip_lock:
            if task_id not in self._running:
                return False
            self._skip_flags[task_id] = True
            return True

    async def retry_step(self, task_id: str, step_id: str) -> bool:
        """Retry a failed step."""
        self._queue.reset_step_for_retry(task_id, step_id)
        return await self.start_task(task_id)

    async def _interruptible_sleep(self, task_id: str, seconds: float) -> bool:
        """Sleep that can be interrupted by pause/cancel.

        Returns True if the full duration elapsed, False if interrupted
        (by a pause/cancel signal). Sleeps in 1s slices so pause/cancel
        take effect within ~1 second instead of blocking for the full duration.
        """
        if seconds <= 0:
            return True
        cancel_event = self._cancel_flags.get(task_id)
        elapsed = 0.0
        while elapsed < seconds:
            if cancel_event and cancel_event.is_set():
                return False
            chunk = min(1.0, seconds - elapsed)
            await asyncio.sleep(chunk)
            elapsed += chunk
        return True

    async def _run_task(self, task_id: str, cancel_event: asyncio.Event):
        """Main execution loop for a task — processes steps sequentially."""
        from .task_queue import TaskStatus

        # Initialize context accumulator for this task
        accumulator = StepContextAccumulator()
        self._accumulators[task_id] = accumulator

        # Safety: max loops to prevent zombie infinite execution
        MAX_LOOPS = 500
        loop_count = 0

        try:
            while loop_count < MAX_LOOPS:
                loop_count += 1
                if cancel_event.is_set():
                    return  # Paused or cancelled

                # Check if skip was requested externally (e.g. user intervention)
                async with self._skip_lock:
                    skip_requested = self._skip_flags.pop(task_id, None)
                if skip_requested:
                    step = self._queue.get_current_step(task_id)
                    if step:
                        self._queue.mark_step_completed(task_id, step.id, {"skipped": True, "reason": "用户跳过"})
                        self._queue.advance_step(task_id, {"skipped": True})
                        await bus.emit(
                            Event(
                                type=EventType.TASK_STEP_COMPLETED,
                                data={
                                    "task_id": task_id,
                                    "step_id": step.id,
                                    "step_label": step.label,
                                    "result": {"skipped": True},
                                },
                                source="task_runner",
                            )
                        )
                    continue

                step = self._queue.get_current_step(task_id)
                if step is None:
                    # All steps done
                    self._queue.update_task_status(task_id, TaskStatus.COMPLETED)
                    await bus.emit(
                        Event(
                            type=EventType.TASK_COMPLETED,
                            data={"task_id": task_id, "progress": self._queue.get_progress(task_id)},
                            source="task_runner",
                        )
                    )
                    return

                # Mark step as running
                self._queue.mark_step_running(task_id, step.id)

                result = None
                try:
                    result = await self._execute_step(task_id, step)
                    # Check if skip was requested during step execution
                    if self._skip_flags.pop(task_id, None):
                        self._queue.mark_step_completed(task_id, step.id, {"skipped": True, "reason": "用户跳过"})
                        self._queue.advance_step(task_id, {"skipped": True})
                        await bus.emit(
                            Event(
                                type=EventType.TASK_STEP_COMPLETED,
                                data={
                                    "task_id": task_id,
                                    "step_id": step.id,
                                    "step_label": step.label,
                                    "result": {"skipped": True},
                                },
                                source="task_runner",
                            )
                        )
                        continue
                    self._queue.mark_step_completed(task_id, step.id, result)

                    # Record result in context accumulator for subsequent steps
                    accumulator.record(step.id, step, result or {})

                    # Broadcast step completed
                    await bus.emit(
                        Event(
                            type=EventType.TASK_STEP_COMPLETED,
                            data={
                                "task_id": task_id,
                                "step_id": step.id,
                                "step_label": step.label,
                                "result": result or {},
                            },
                            source="task_runner",
                        )
                    )

                    # ── Token budget tracking ──
                    await self._track_token_usage(task_id, result)

                    # ── Analysis replan trigger: checkpoint step wants to replan ──
                    if step.config.get("trigger_replan"):
                        replan_msg = (
                            f"分析步骤 '{step.label}' 已完成，分析结果: {str(result.get('text', result))[:300]}"
                        )
                        if await self._maybe_replan(task_id, step, replan_msg, accumulator):
                            continue

                    # ── Budget check: pause if exceeded ──
                    if not await self._check_token_budget(task_id):
                        await bus.emit(
                            Event(
                                type=EventType.TASK_NOTIFICATION,
                                data={
                                    "task_id": task_id,
                                    "message": "Token 预算已用尽，任务已暂停",
                                },
                                source="task_runner",
                            )
                        )
                        self._queue.pause_task(task_id)
                        if task_id in self._cancel_flags:
                            self._cancel_flags[task_id].set()
                        return

                except asyncio.CancelledError:
                    self._queue.mark_step_failed(task_id, step.id, "cancelled")
                    raise
                except Exception as e:
                    error_msg = str(e)[:300]
                    self._queue.mark_step_failed(task_id, step.id, error_msg)
                    await bus.emit(
                        Event(
                            type=EventType.TASK_STEP_FAILED,
                            data={"task_id": task_id, "step_id": step.id, "step_label": step.label, "error": error_msg},
                            source="task_runner",
                        )
                    )
                    # Check if we should retry
                    current_step = self._queue.get_current_step(task_id)
                    if current_step and current_step.id == step.id:
                        if step.retry_count < step.max_retries:
                            logger.info(
                                "Retrying step %s (attempt %d/%d)", step.id, step.retry_count + 1, step.max_retries
                            )
                            self._queue.reset_step_for_retry(task_id, step.id)
                            await asyncio.sleep(2 * (step.retry_count + 1))
                            continue
                    # ── Replan check: if replan enabled, try to adjust plan ──
                    if await self._maybe_replan(task_id, step, error_msg, accumulator):
                        # Replan succeeded, continue with new steps
                        continue
                    # Mark task as failed
                    self._queue.update_task_status(task_id, TaskStatus.FAILED, error=error_msg)
                    await bus.emit(
                        Event(
                            type=EventType.TASK_FAILED,
                            data={"task_id": task_id, "step_id": step.id, "error": error_msg},
                            source="task_runner",
                        )
                    )
                    return

                # Advance to next step
                self._queue.advance_step(task_id, result)

                # ── Inter-chapter pause ──
                # After a chapter's final checkpoint, if there are more steps
                # and pause_between_chapters is configured, wait briefly before
                # proceeding to the next chapter. Interruptible by pause/cancel.
                if step.config.get("final"):
                    persistent_task = self._queue.get_task(task_id)
                    pause_seconds = (
                        (persistent_task.metadata or {}).get("pause_between_chapters", 0) if persistent_task else 0
                    )
                    if pause_seconds and pause_seconds > 0:
                        next_step = self._queue.get_current_step(task_id)
                        if next_step is not None:
                            await bus.emit(
                                Event(
                                    type=EventType.TASK_NOTIFICATION,
                                    data={
                                        "task_id": task_id,
                                        "message": f"章间暂停 {pause_seconds}s 后继续下一章…",
                                    },
                                    source="task_runner",
                                )
                            )
                            completed = await self._interruptible_sleep(task_id, pause_seconds)
                            if not completed:
                                # Interrupted by pause/cancel — let the main
                                # loop's top-of-iteration check handle it.
                                continue

            # If the loop exited normally (not via return/exception), we hit MAX_LOOPS
            if loop_count >= MAX_LOOPS:
                logger.error("Task %s exceeded max loops (%d), marking as failed", task_id, MAX_LOOPS)
                self._queue.update_task_status(
                    task_id, TaskStatus.FAILED, error=f"Exceeded maximum execution loops ({MAX_LOOPS})"
                )

        except asyncio.CancelledError:
            logger.info("Task %s cancelled", task_id)
        except Exception as e:
            logger.exception("Task %s failed unexpectedly: %s", task_id, e)
            self._queue.update_task_status(task_id, TaskStatus.FAILED, error=str(e)[:300])
        finally:
            self._running.pop(task_id, None)
            self._cancel_flags.pop(task_id, None)
            self._accumulators.pop(task_id, None)
            self._skip_flags.pop(task_id, None)

    async def _execute_step(self, task_id: str, step) -> dict:
        """Execute a single step based on its type."""
        task = self._queue.get_task(task_id)
        if not task:
            return {"error": "task not found"}

        step_type = step.type
        cfg = step.config

        if step_type == "agent_loop":
            # Build enriched prompt with context injection from previous steps
            base_prompt = cfg.get("prompt", cfg.get("instruction", ""))
            accumulator = self._accumulators.get(task_id)

            # ── Intervention queue: check for user messages during autopilot ──
            intervention_text = ""
            if accumulator:
                intervention_queue = getattr(accumulator, "_intervention_queue", [])
                if intervention_queue:
                    intervention_text = "[用户干预指令]\n" + "\n".join(intervention_queue)
                    accumulator._intervention_queue = []  # Clear after consuming

            if accumulator:
                context_text = accumulator.build_context_injection(step, task.steps)
                parts = []
                if intervention_text:
                    parts.append(intervention_text)
                if context_text:
                    parts.append(f"[前序步骤上下文]\n{context_text}")
                if parts:
                    enriched_prompt = f"{base_prompt}\n\n---\n" + "\n\n".join(parts)
                else:
                    enriched_prompt = base_prompt
            else:
                enriched_prompt = base_prompt

            result = await run_agent_loop_headless(
                book_id=task.book_id,
                instruction=enriched_prompt,
                source=task.created_by,
                parent_session_id=task.session_id,
                task_id=task_id,
                history_messages=cfg.get("history"),
                agent_config=self._build_agent_config(task, cfg),
            )

            step_result = {
                "text": result.text,
                "success": result.success,
                "rounds": result.rounds,
                "metrics": result.metrics,
                "error": result.error,
            }

            # ── Quality gate: if this step is flagged as a quality review ──
            gate_level = cfg.get("quality_gate")
            if gate_level and result.success:
                try:
                    from .quality_gate import run_quality_gate, should_pause_for_quality

                    chapter_text = cfg.get("chapter_text", "")
                    chapter_ref = cfg.get("chapter_ref", "")
                    # If chapter_text is not in config, load it from the book's chapters
                    if not chapter_text and chapter_ref:
                        try:
                            from data.json_store import json_store

                            chapter = json_store.get_chapter(task.book_id, chapter_ref)
                            if chapter:
                                current = chapter.get("current_version")
                                if current and chapter.get("versions"):
                                    for v in chapter["versions"]:
                                        if v["id"] == current:
                                            chapter_text = v.get("content", "")
                                            break
                        except Exception:
                            pass
                    if not chapter_text:
                        chapter_text = result.text  # fallback (should not happen for review steps)
                    q_result = await run_quality_gate(
                        chapter_text=chapter_text,
                        book_id=task.book_id,
                        chapter_ref=chapter_ref,
                        gate_level=gate_level,
                        audit_mode=task.audit_mode or "soft",
                        max_rewrite_attempts=cfg.get("max_rewrite_attempts", 2),
                    )
                    step_result["quality"] = {
                        "passed": q_result.passed,
                        "score": q_result.score,
                        "threshold": q_result.threshold,
                        "action": q_result.action,
                        "summary": q_result.summary,
                        "ai_flavor_score": q_result.ai_flavor_score,
                        "ai_flavor_issues": q_result.ai_flavor_issues,
                    }
                    if should_pause_for_quality(q_result, task.audit_mode or "soft"):
                        await bus.emit(
                            Event(
                                type=EventType.TASK_NOTIFICATION,
                                data={
                                    "task_id": task_id,
                                    "book_id": task.book_id,
                                    "message": (
                                        f"质量门未通过（评分 {q_result.score:.1f} < "
                                        f"阈值 {q_result.threshold:.1f}），任务已暂停"
                                    ),
                                    "quality_result": step_result["quality"],
                                },
                                source="task_runner",
                            )
                        )
                        self._queue.pause_task(task_id)
                        if task_id in self._cancel_flags:
                            self._cancel_flags[task_id].set()
                        step_result["paused_for_quality"] = True
                except Exception as qe:
                    logger.warning("Quality gate check failed for task %s: %s", task_id, qe)

            return step_result

        elif step_type == "checkpoint":
            # Simple state persistence — already handled by task_queue advance
            return {"checkpointed": True, "step_index": task.current_step_index}

        elif step_type == "user_confirm":
            # In autonomous mode: auto-confirm; in hard mode: wait for user
            audit_mode = task.audit_mode or "soft"
            if audit_mode == "autonomous":
                return {"confirmed": True, "mode": "auto"}
            # Use question_manager for interactive confirmation
            from .question import manager as question_manager

            q_req = question_manager.create_question(
                [
                    {
                        "question": cfg.get("message", "确认继续？"),
                        "header": cfg.get("header", "任务确认"),
                        "options": cfg.get(
                            "options",
                            [
                                {"label": "确认继续", "description": "继续执行下一步"},
                                {"label": "暂停", "description": "暂停任务"},
                            ],
                        ),
                        "custom": False,
                    }
                ],
                task.book_id,
            )
            await bus.emit(
                Event(
                    type=EventType.TASK_NOTIFICATION,
                    data={
                        "task_id": task_id,
                        "question_id": q_req.id,
                        "action_required": True,
                        "message": cfg.get("message", "确认继续？"),
                    },
                    source="task_runner",
                )
            )
            try:
                answers = await asyncio.wait_for(question_manager.wait_for_answer(q_req.id), timeout=600)
                confirmed = bool(answers and answers[0] and "确认" in answers[0][0])
                if not confirmed:
                    raise RuntimeError("用户拒绝继续")
                return {"confirmed": True, "answer": answers[0][0]}
            except TimeoutError:
                raise RuntimeError("用户确认超时（10分钟）")

        elif step_type == "workflow_step":
            # Execute via existing workflow engine
            from .workflow_engine import engine as wf_engine

            ctx = {"book_id": task.book_id, "source": "task_runner"}
            wf_id = f"task_{task_id}_{step.id}"
            wf_def = {"name": step.label, "steps": [cfg]}
            wf_engine.build(wf_id, wf_def)
            results = await wf_engine.execute(wf_id, ctx)
            return {"workflow_results": results}

        else:
            return {"warning": f"unknown step type: {step_type}"}

    def _build_agent_config(self, task, step_config: dict) -> AgentConfig:
        """Build AgentConfig from task metadata and step config."""
        agent_type = step_config.get("agent_type", "write")
        mode = step_config.get("mode", "write")
        temperature = step_config.get("temperature", config.agent.default_temperature)
        max_rounds = step_config.get("max_rounds", config.agent.max_rounds)

        return AgentConfig(
            agent_type=agent_type,
            mode=mode,
            book_id=task.book_id,
            session_id=f"headless_task_{task.id}",
            temperature=temperature,
            max_rounds=max_rounds,
        )

    async def _maybe_replan(self, task_id: str, step, error_msg: str, accumulator: "StepContextAccumulator") -> bool:
        """Check if replan should be triggered and apply it.

        Returns True if replan was applied (caller should continue loop),
        False if no replan (caller should mark task as failed).
        """
        task = self._queue.get_task(task_id)
        if not task:
            return False

        meta = task.metadata or {}
        if not meta.get("enable_replan", False):
            return False

        replan_count = meta.get("replan_count", 0)
        max_replans = meta.get("max_replans", 3)
        if replan_count >= max_replans:
            logger.info("Task %s: replan limit reached (%d/%d)", task_id, replan_count, max_replans)
            return False

        # Only replan for autopilot tasks
        if task.type != "autopilot":
            return False

        # Check if this step has replan_on_fail configured, or trigger_replan
        replan_strategy = step.config.get("replan_on_fail", "")
        trigger_replan = step.config.get("trigger_replan", False)
        if not replan_strategy and not trigger_replan and step.config.get("step_category") not in ("analyze",):
            # Only replan steps that explicitly opt in, have trigger_replan, or are analysis steps
            return False

        logger.info("Task %s: triggering replan (step %s failed: %s)", task_id, step.label, error_msg[:100])

        try:
            from .autopilot import AutopilotPlanner

            planner = AutopilotPlanner()
            new_steps = await planner.replan(task, f"步骤 '{step.label}' 失败: {error_msg[:200]}", accumulator)

            if not new_steps:
                logger.info("Task %s: replan returned empty steps — task is complete", task_id)
                self._queue.update_task_status(task_id, TaskStatus.COMPLETED)
                await bus.emit(
                    Event(
                        type=EventType.TASK_COMPLETED,
                        data={"task_id": task_id, "progress": self._queue.get_progress(task_id)},
                        source="task_runner",
                    )
                )
                return True  # let the loop see no steps and complete cleanly

            # Apply replan: replace remaining steps
            if self._queue.replace_remaining_steps(task_id, new_steps):
                # Update replan count in metadata (thread-safe)
                self._queue.update_task_meta(
                    task_id,
                    {
                        "replan_count": replan_count + 1,
                        "plan_version": meta.get("plan_version", 1) + 1,
                    },
                )

                await bus.emit(
                    Event(
                        type=EventType.TASK_NOTIFICATION,
                        data={
                            "task_id": task_id,
                            "message": f"计划已调整（第{replan_count + 1}次重规划），新增 {len(new_steps)} 个步骤",
                        },
                        source="task_runner",
                    )
                )
                return True

        except Exception as e:
            logger.warning("Task %s: replan failed: %s", task_id, e)

        return False

    async def _track_token_usage(self, task_id: str, step_result: dict):
        """Update token usage in task metadata based on step result metrics.

        Uses llm_calls * estimated_tokens_per_call as a rough proxy since the
        LLM client doesn't currently report actual token usage.
        """
        try:
            metrics = step_result.get("metrics") or {}
            llm_calls = metrics.get("llm_calls", 0)
            tool_calls = metrics.get("tool_calls", 0)
            # Rough estimate: ~3000 tokens per LLM call + ~500 per tool result
            estimated_tokens = llm_calls * 3000 + tool_calls * 500
            if estimated_tokens <= 0:
                return
            from .autopilot_runner import autopilot

            autopilot.update_tokens(task_id, estimated_tokens)
        except Exception as e:
            logger.debug("Token tracking skipped for %s: %s", task_id, e)

    async def _check_token_budget(self, task_id: str) -> bool:
        """Check if the task still has token budget. Returns True if OK to continue."""
        try:
            from .autopilot_runner import autopilot

            return await autopilot.check_budget(task_id)
        except Exception:
            return True  # Don't block if budget check fails

    # ── Recovery ──

    async def recover_pending_tasks(self):
        """Called on server startup to resume interrupted tasks."""
        from .task_queue import TaskStatus

        # Reset RUNNING tasks to PENDING (asyncio.Task was lost on restart)
        running_tasks = self._queue.list_tasks(status=TaskStatus.RUNNING)
        for task in running_tasks:
            logger.info("Resetting interrupted task %s to PENDING", task.id)
            self._queue.update_task_status(task.id, TaskStatus.PENDING)

        # Start all PENDING tasks
        pending_tasks = self._queue.list_tasks(status=TaskStatus.PENDING)
        for task in pending_tasks:
            if task.created_by in ("scheduler", "autopilot", "supervisor"):
                # Auto-start tasks created by the system
                await self.start_task(task.id)
                # Small delay between task starts to avoid thundering herd
                await asyncio.sleep(1)

        logger.info("Recovered %d running + %d pending tasks", len(running_tasks), len(pending_tasks))


# Module-level singleton (initialized in server.py lifespan)
runner: TaskRunner | None = None


def init_task_runner(tq) -> TaskRunner:
    global runner
    runner = TaskRunner(tq)
    return runner


def get_task_runner() -> TaskRunner | None:
    return runner
