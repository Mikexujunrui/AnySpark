"""Task management API — CRUD + SSE streaming for persistent tasks."""

import asyncio
import json
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from core.event_bus import Event, EventType, bus
from core.headless_loop import get_task_runner
from core.task_queue import PersistentTask, TaskStatus, TaskStep, task_queue

logger = logging.getLogger(__name__)

# ── Connection diagnostics ──
conn_logger = logging.getLogger("connection.diagnostics")

router = APIRouter(tags=["tasks"])


# ── Request Models ──


class CreateTaskRequest(BaseModel):
    type: str = "custom"
    label: str = ""
    book_id: str = ""
    session_id: str = ""
    audit_mode: str = "soft"
    steps: list[dict] = []
    metadata: dict = {}


class AutopilotRequest(BaseModel):
    instruction: str = ""
    max_chapters_per_run: int = 10
    token_budget: int = 500000
    auto_review: bool = True
    auto_extract: bool = True
    pause_between_chapters: int = 5
    confirm_before_start: bool = True
    audit_mode: str = "soft"
    quality_gate: str = "medium"


# ── Task CRUD ──


@router.get("/books/{book_id}/tasks")
def list_tasks(book_id: str, status: str = ""):
    """List all tasks for a book, optionally filtered by status."""
    tasks = task_queue.list_tasks(book_id=book_id, status=status or None)
    return [
        {
            "id": t.id,
            "type": t.type,
            "label": t.label,
            "status": t.status,
            "audit_mode": t.audit_mode,
            "progress": task_queue.get_progress(t.id),
            "created_at": t.created_at,
            "started_at": t.started_at,
            "completed_at": t.completed_at,
            "created_by": t.created_by,
            "error": t.error,
            "metadata": t.metadata,
        }
        for t in tasks
    ]


@router.post("/books/{book_id}/tasks")
def create_task(book_id: str, req: CreateTaskRequest):
    """Create a new persistent task."""
    task_id = f"task_{int(datetime.now().timestamp() * 1000)}"

    steps = []
    for i, s in enumerate(req.steps):
        steps.append(
            TaskStep(
                id=f"{task_id}_s{i}",
                type=s.get("type", "agent_loop"),
                label=s.get("label", f"步骤 {i + 1}"),
                config=s.get("config", {}),
            )
        )

    task = PersistentTask(
        id=task_id,
        type=req.type,
        book_id=book_id,
        session_id=req.session_id or book_id,
        label=req.label or f"自定义任务 {task_id[-6:]}",
        steps=steps,
        audit_mode=req.audit_mode,
        metadata=req.metadata,
    )
    task_queue.create_task(task)
    return {"id": task.id, "status": task.status, "steps": len(steps)}


@router.get("/books/{book_id}/tasks/{task_id}")
def get_task(book_id: str, task_id: str):
    """Get task details including all steps."""
    task = task_queue.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return {
        "id": task.id,
        "type": task.type,
        "label": task.label,
        "status": task.status,
        "audit_mode": task.audit_mode,
        "current_step_index": task.current_step_index,
        "progress": task_queue.get_progress(task.id),
        "steps": [
            {
                "id": s.id,
                "type": s.type,
                "label": s.label,
                "status": s.status,
                "result": s.result,
                "retry_count": s.retry_count,
                "error": s.error,
                "started_at": s.started_at,
                "completed_at": s.completed_at,
            }
            for s in task.steps
        ],
        "created_at": task.created_at,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
        "created_by": task.created_by,
        "error": task.error,
        "metadata": task.metadata,
    }


@router.delete("/books/{book_id}/tasks/{task_id}")
def delete_task(book_id: str, task_id: str):
    """Delete a task (only completed/cancelled/failed tasks can be deleted)."""
    task = task_queue.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if task.status in (TaskStatus.RUNNING, TaskStatus.PENDING):
        raise HTTPException(400, "运行中或等待中的任务不能删除，请先取消")
    if not task_queue.delete_task(task_id):
        raise HTTPException(500, "删除失败")
    return {"ok": True}


# ── Task Control ──


@router.post("/books/{book_id}/tasks/{task_id}/start")
async def start_task(book_id: str, task_id: str):
    """Start executing a task."""
    task = task_queue.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if task.status not in (TaskStatus.PENDING,):
        raise HTTPException(400, f"任务状态 {task.status} 不允许启动")

    runner = get_task_runner()
    if not runner:
        raise HTTPException(503, "TaskRunner 未初始化")

    ok = await runner.start_task(task_id)
    if not ok:
        raise HTTPException(400, "启动失败（可能已在运行）")
    return {"ok": True, "task_id": task_id}


@router.post("/books/{book_id}/tasks/{task_id}/pause")
async def pause_task(book_id: str, task_id: str):
    """Pause a running task (waits for current step to finish)."""
    runner = get_task_runner()
    if not runner:
        raise HTTPException(503, "TaskRunner 未初始化")
    ok = await runner.pause_task(task_id)
    if not ok:
        raise HTTPException(400, "暂停失败")
    return {"ok": True}


@router.post("/books/{book_id}/tasks/{task_id}/resume")
async def resume_task(book_id: str, task_id: str):
    """Resume a paused task."""
    runner = get_task_runner()
    if not runner:
        raise HTTPException(503, "TaskRunner 未初始化")
    ok = await runner.resume_task(task_id)
    if not ok:
        raise HTTPException(400, "恢复失败")
    return {"ok": True}


@router.post("/books/{book_id}/tasks/{task_id}/cancel")
async def cancel_task(book_id: str, task_id: str):
    """Cancel a running or pending task."""
    runner = get_task_runner()
    if not runner:
        raise HTTPException(503, "TaskRunner 未初始化")
    ok = await runner.cancel_task(task_id)
    if not ok:
        raise HTTPException(400, "取消失败")
    return {"ok": True}


@router.post("/books/{book_id}/tasks/{task_id}/retry")
async def retry_task_step(book_id: str, task_id: str):
    """Retry the current failed step."""
    task = task_queue.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if task.status != TaskStatus.FAILED:
        raise HTTPException(400, "只有失败状态的任务可以重试")

    step = task_queue.get_current_step(task_id)
    if not step:
        raise HTTPException(400, "没有可重试的步骤")

    runner = get_task_runner()
    if not runner:
        raise HTTPException(503, "TaskRunner 未初始化")

    ok = await runner.retry_step(task_id, step.id)
    return {"ok": ok}


# ── SSE Stream ──


@router.get("/books/{book_id}/tasks/{task_id}/stream")
async def task_stream(book_id: str, task_id: str):
    """SSE stream for real-time task progress updates."""
    task = task_queue.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")

    conn_logger.info(
        "[SSE-START] task_stream | task=%s | book=%s",
        task_id,
        book_id,
    )

    async def event_generator():
        # Send initial state
        yield {
            "event": "task_status",
            "data": json.dumps(
                {
                    "task_id": task_id,
                    "status": task.status,
                    "progress": task_queue.get_progress(task_id),
                },
                ensure_ascii=False,
            ),
        }

        # Listen for task events via event_bus
        event_queue = asyncio.Queue()

        async def _listener(event: Event):
            data = event.data
            if data.get("task_id") == task_id or data.get("book_id") == book_id:
                await event_queue.put(event)

        bus.on(EventType.TASK_STEP_COMPLETED, _listener)
        bus.on(EventType.TASK_STEP_FAILED, _listener)
        bus.on(EventType.TASK_COMPLETED, _listener)
        bus.on(EventType.TASK_FAILED, _listener)
        bus.on(EventType.TASK_NOTIFICATION, _listener)
        bus.on(EventType.HEADLESS_LOOP_PROGRESS, _listener)

        heartbeat_timeouts = 0

        try:
            while True:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=30)
                    heartbeat_timeouts = 0
                except TimeoutError:
                    heartbeat_timeouts += 1
                    if heartbeat_timeouts >= 3:
                        conn_logger.warning(
                            "[SSE-STALL] task_stream | task=%s | %d consecutive timeouts",
                            task_id,
                            heartbeat_timeouts,
                        )
                    # Heartbeat
                    yield {
                        "event": "heartbeat",
                        "data": json.dumps(
                            {"task_id": task_id, "time": datetime.now().isoformat()}, ensure_ascii=False
                        ),
                    }
                    # Check if task is done
                    current = task_queue.get_task(task_id)
                    if current and current.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                        yield {
                            "event": "task_completed" if current.status == TaskStatus.COMPLETED else "task_error",
                            "data": json.dumps(
                                {
                                    "task_id": task_id,
                                    "status": current.status,
                                    "progress": task_queue.get_progress(task_id),
                                    "error": current.error,
                                },
                                ensure_ascii=False,
                            ),
                        }
                        conn_logger.info(
                            "[SSE-END] task_stream | task=%s | status=%s (heartbeat detection)",
                            task_id,
                            current.status,
                        )
                        return
                    continue

                etype = event.type
                data = event.data

                if etype == EventType.TASK_STEP_COMPLETED:
                    yield {
                        "event": "step_done",
                        "data": json.dumps(
                            {
                                "task_id": task_id,
                                "step_id": data.get("step_id"),
                                "step_label": data.get("step_label"),
                                "result": data.get("result", {}),
                                "progress": task_queue.get_progress(task_id),
                            },
                            ensure_ascii=False,
                        ),
                    }
                elif etype == EventType.TASK_STEP_FAILED:
                    yield {
                        "event": "step_error",
                        "data": json.dumps(
                            {
                                "task_id": task_id,
                                "step_id": data.get("step_id"),
                                "step_label": data.get("step_label"),
                                "error": data.get("error"),
                            },
                            ensure_ascii=False,
                        ),
                    }
                elif etype == EventType.TASK_COMPLETED:
                    yield {
                        "event": "task_completed",
                        "data": json.dumps(
                            {
                                "task_id": task_id,
                                "progress": data.get("progress", {}),
                            },
                            ensure_ascii=False,
                        ),
                    }
                    conn_logger.info(
                        "[SSE-END] task_stream | task=%s | event=TASK_COMPLETED",
                        task_id,
                    )
                    return
                elif etype == EventType.TASK_FAILED:
                    yield {
                        "event": "task_error",
                        "data": json.dumps(
                            {
                                "task_id": task_id,
                                "error": data.get("error"),
                            },
                            ensure_ascii=False,
                        ),
                    }
                    conn_logger.info(
                        "[SSE-END] task_stream | task=%s | event=TASK_FAILED",
                        task_id,
                    )
                    return
                elif etype == EventType.TASK_NOTIFICATION:
                    yield {
                        "event": "notification",
                        "data": json.dumps(
                            {
                                "task_id": task_id,
                                "message": data.get("message"),
                                "action_required": data.get("action_required", False),
                            },
                            ensure_ascii=False,
                        ),
                    }
                elif etype == EventType.HEADLESS_LOOP_PROGRESS:
                    stage = data.get("stage", "")
                    event_type = data.get("event_type", "")
                    if event_type == "chunk":
                        yield {
                            "event": "chunk",
                            "data": data.get("text", ""),
                        }
                    elif event_type in ("tool-start", "tool-end", "progress"):
                        yield {
                            "event": "progress",
                            "data": json.dumps(
                                {
                                    "task_id": task_id,
                                    "stage": stage or event_type,
                                    "detail": data.get("tool", data.get("text", ""))[:100],
                                },
                                ensure_ascii=False,
                            ),
                        }

        finally:
            bus.off(EventType.TASK_STEP_COMPLETED, _listener)
            bus.off(EventType.TASK_STEP_FAILED, _listener)
            bus.off(EventType.TASK_COMPLETED, _listener)
            bus.off(EventType.TASK_FAILED, _listener)
            bus.off(EventType.TASK_NOTIFICATION, _listener)
            bus.off(EventType.HEADLESS_LOOP_PROGRESS, _listener)
            conn_logger.info(
                "[SSE-CLEANUP] task_stream | task=%s | listeners removed",
                task_id,
            )

    return EventSourceResponse(event_generator())


# ── Audit Mode ──


@router.put("/books/{book_id}/tasks/{task_id}/audit-mode")
def set_audit_mode(book_id: str, task_id: str, data: dict):
    """Set audit mode for a task: hard | soft | autonomous."""
    mode = data.get("mode", "")
    if mode not in ("hard", "soft", "autonomous"):
        raise HTTPException(400, "mode must be 'hard', 'soft', or 'autonomous'")
    if not task_queue.set_audit_mode(task_id, mode):
        raise HTTPException(404, "任务不存在")
    return {"ok": True, "audit_mode": mode}


# ── Autopilot Endpoints ──


@router.post("/books/{book_id}/autopilot/start")
async def start_autopilot(book_id: str, req: AutopilotRequest):
    """Start an autopilot session — plan and optionally start writing."""
    from core.autopilot import AutopilotConfig
    from core.autopilot_runner import autopilot

    if not req.instruction:
        raise HTTPException(400, "instruction is required")

    config = AutopilotConfig(
        book_id=book_id,
        instruction=req.instruction,
        max_chapters_per_run=req.max_chapters_per_run,
        token_budget=req.token_budget,
        auto_review=req.auto_review,
        auto_extract=req.auto_extract,
        pause_between_chapters=req.pause_between_chapters,
        confirm_before_start=req.confirm_before_start,
        audit_mode=req.audit_mode,
        quality_gate=req.quality_gate,
    )

    result = await autopilot.start(config)

    # Register session for autopilot bridge
    if result.get("task_id"):
        from routes.chat import register_autopilot_session

        session_key = config.session_id or config.book_id
        register_autopilot_session(session_key, result["task_id"])

    return result


@router.post("/books/{book_id}/autopilot/{task_id}/confirm")
async def confirm_autopilot(book_id: str, task_id: str):
    """Confirm and start an autopilot task that was waiting for confirmation."""
    from core.autopilot_runner import autopilot

    ok = await autopilot.confirm_start(task_id)
    if not ok:
        raise HTTPException(400, "确认失败（任务可能已启动或不存在）")
    return {"ok": True}


@router.post("/books/{book_id}/autopilot/{task_id}/stop")
async def stop_autopilot(book_id: str, task_id: str):
    """Stop an autopilot task."""
    from core.autopilot_runner import autopilot

    ok = await autopilot.cancel(task_id)
    if not ok:
        raise HTTPException(400, "停止失败")
    return {"ok": True}


@router.get("/books/{book_id}/autopilot/status")
def autopilot_status(book_id: str):
    """Get status of all autopilot tasks for this book."""
    tasks = task_queue.list_tasks(book_id=book_id, created_by="autopilot")
    active = [t for t in tasks if t.status in (TaskStatus.RUNNING, TaskStatus.PENDING, TaskStatus.PAUSED)]
    if not active:
        return {"active": False, "tasks": []}
    from core.autopilot_runner import autopilot

    return {
        "active": True,
        "tasks": [autopilot.get_status(t.id) for t in active],
    }


@router.get("/books/{book_id}/autopilot/{task_id}/status")
def autopilot_task_status(book_id: str, task_id: str):
    """Get detailed status of a specific autopilot task."""
    from core.autopilot_runner import autopilot

    status = autopilot.get_status(task_id)
    if not status:
        raise HTTPException(404, "autopilot任务不存在")
    return status


# ── Supervisor Endpoints ──


@router.get("/supervisor/status")
def supervisor_status():
    """Get supervisor daemon status."""
    from core.supervisor import supervisor

    return supervisor.get_status()


@router.post("/supervisor/recover")
async def trigger_recovery():
    """Manually trigger task recovery (useful after server restart)."""
    runner = get_task_runner()
    if not runner:
        raise HTTPException(503, "TaskRunner 未初始化")
    await runner.recover_pending_tasks()
    return {"ok": True, "message": "任务恢复已触发"}


# ── Autopilot Chat Bridge ──


@router.get("/books/{book_id}/autopilot/{task_id}/chat-bridge")
async def autopilot_chat_bridge(book_id: str, task_id: str, request: Request):
    """SSE bridge: streams autopilot events in chat-compatible format."""
    task = task_queue.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")

    from routes.chat import _autopilot_bridge_sse

    return EventSourceResponse(_autopilot_bridge_sse(task_id, book_id, task.session_id, request))
