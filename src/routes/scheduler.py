"""Scheduler API Routes."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.scheduler import TASK_TEMPLATES, ScheduledTask
from core.scheduler import engine as sched_engine

router = APIRouter(prefix="/books/{book_id}/scheduler", tags=["scheduler"])


class TaskCreate(BaseModel):
    name: str
    template: str = "custom"
    schedule_type: str = "manual"
    schedule_value: str = ""
    steps: list[dict] = []


class TaskUpdate(BaseModel):
    name: str | None = None
    template: str | None = None
    schedule_type: str | None = None
    schedule_value: str | None = None
    steps: list[dict] | None = None
    enabled: bool | None = None


@router.get("/templates")
def list_templates():
    return {
        "templates": [
            {"id": k, "name": v["name"], "description": v["description"], "steps": v["steps"]}
            for k, v in TASK_TEMPLATES.items()
        ]
    }


@router.get("/tasks")
def list_tasks(book_id: str):
    tasks = sched_engine.list_tasks(book_id)
    if not tasks:
        return {"tasks": [], "message": "暂无定时任务"}
    return {"tasks": tasks}


@router.post("/tasks")
def create_task(book_id: str, data: TaskCreate):
    now = datetime.now().isoformat()
    task_id = f"sched_{int(datetime.now().timestamp() * 1000)}"

    steps = data.steps
    if not steps and data.template in TASK_TEMPLATES:
        steps = TASK_TEMPLATES[data.template]["steps"]

    task = ScheduledTask(
        id=task_id,
        name=data.name,
        template=data.template,
        book_id=book_id,
        schedule_type=data.schedule_type,
        schedule_value=data.schedule_value,
        steps=steps,
        created_at=now,
        updated_at=now,
    )
    sched_engine.add_task(task)
    return {"id": task_id, "task": task.__dict__}


@router.get("/tasks/{task_id}")
def get_task(book_id: str, task_id: str):
    task = sched_engine.get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return {"task": task}


@router.put("/tasks/{task_id}")
def update_task(book_id: str, task_id: str, data: TaskUpdate):
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    task = sched_engine.update_task(task_id, updates)
    if not task:
        raise HTTPException(404, "任务不存在")
    return {"task": task}


@router.delete("/tasks/{task_id}")
def delete_task(book_id: str, task_id: str):
    ok = sched_engine.delete_task(task_id)
    if not ok:
        raise HTTPException(404, "任务不存在")
    return {"ok": True}


@router.post("/tasks/{task_id}/run")
async def run_task_now(book_id: str, task_id: str):
    result = await sched_engine.run_task_now(task_id)
    if not result:
        raise HTTPException(404, "任务不存在")
    return {"message": result}


@router.get("/runs")
def get_run_history(book_id: str, task_id: str = Query(""), limit: int = Query(50)):
    runs = sched_engine.get_run_history(task_id, limit)
    return {"runs": runs}
