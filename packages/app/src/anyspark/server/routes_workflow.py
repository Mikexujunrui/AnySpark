"""
anyspark.server.routes_workflow — 工作流路由（S80c 拆分）。

从 app.py build_app 搬移（行为零变化）：模板 CRUD + AI 生成草稿 + 任务运行/
审批（可选增强，默认关）。闭包引用 → deps.xxx。
"""

from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, HTTPException

from anyspark.server.deps import AppDeps
from anyspark.server.logging import logger
from anyspark.server.schemas import (
    WorkflowGenerateIn,
    WorkflowIn,
    WorkflowRunIn,
)
from anyspark.workflow import WorkflowDef


def make_workflow_router(deps: AppDeps) -> APIRouter:
    """工作流路由（依赖：deps.workflow_store / workflow_generator / workflow_engine）。"""
    router = APIRouter()

    workflow_engine = deps.workflow_engine
    assert workflow_engine is not None  # 组合根装配必填（S80 接线）

    @router.get("/api/workflows", response_model=list[dict[str, Any]])
    def list_workflows() -> list[dict[str, Any]]:
        return deps.workflow_store.list_templates()

    @router.post("/api/workflows", response_model=dict[str, Any])
    def create_workflow(req: WorkflowIn) -> dict[str, Any]:
        wf = WorkflowDef.from_dict(
            {
                "name": req.name,
                "description": req.description,
                "nodes": req.nodes,
                "edges": req.edges,
                "layout": req.layout,
            }
        )
        errors = wf.validate()
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})
        deps.workflow_store.add_template(wf)
        return wf.to_dict()

    workflow_generator = deps.workflow_generator
    assert workflow_generator is not None  # 组合根装配必填（S80 接线）

    @router.post("/api/workflows/generate", response_model=dict[str, Any])
    def generate_workflow(req: WorkflowGenerateIn) -> dict[str, Any]:
        """AI 生成工作流候选 → 草稿表（未生效，人工确认 promote 转正）。"""
        try:
            wf = workflow_generator.generate(req.goal)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        deps.workflow_store.add_draft(wf, hint=req.goal)
        return wf.to_dict()

    @router.get("/api/workflows/drafts", response_model=list[dict[str, Any]])
    def list_workflow_drafts() -> list[dict[str, Any]]:
        return deps.workflow_store.list_drafts()

    @router.post("/api/workflows/drafts/{draft_id}/promote", response_model=dict[str, Any])
    def promote_workflow_draft(draft_id: str) -> dict[str, Any]:
        wf = deps.workflow_store.promote_draft(draft_id)
        if wf is None:
            raise HTTPException(status_code=404, detail="草稿不存在")
        return wf.to_dict()

    @router.delete("/api/workflows/drafts/{draft_id}", response_model=dict[str, bool])
    def delete_workflow_draft(draft_id: str) -> dict[str, bool]:
        if not deps.workflow_store.delete_draft(draft_id):
            raise HTTPException(status_code=404, detail="草稿不存在")
        return {"ok": True}

    @router.get("/api/workflows/tasks", response_model=list[dict[str, Any]])
    def list_workflow_tasks() -> list[dict[str, Any]]:
        return deps.workflow_store.list_tasks()

    @router.get("/api/workflows/tasks/{task_id}", response_model=dict[str, Any])
    def get_workflow_task(task_id: str) -> dict[str, Any]:
        task = deps.workflow_store.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return task

    @router.post("/api/workflows/tasks/{task_id}/approve", response_model=dict[str, Any])
    def approve_workflow_task(task_id: str, req: dict[str, str]) -> dict[str, Any]:
        """approval 节点人工确认：{"decision": "ok"|"reject"}。"""
        try:
            return workflow_engine.approve(task_id, decision=req.get("decision", "ok"))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/workflows/{workflow_id}", response_model=dict[str, Any])
    def get_workflow(workflow_id: str) -> dict[str, Any]:
        wf = deps.workflow_store.get_template(workflow_id)
        if wf is None:
            raise HTTPException(status_code=404, detail="工作流不存在")
        return wf.to_dict()

    @router.delete("/api/workflows/{workflow_id}", response_model=dict[str, bool])
    def delete_workflow(workflow_id: str) -> dict[str, bool]:
        if not deps.workflow_store.delete_template(workflow_id):
            raise HTTPException(status_code=404, detail="工作流不存在")
        return {"ok": True}

    @router.post("/api/workflows/{workflow_id}/run", response_model=dict[str, Any])
    def run_workflow(workflow_id: str, req: WorkflowRunIn) -> dict[str, Any]:
        """运行工作流：冻结定义快照 → 后台线程执行（不阻塞请求）。"""
        wf = deps.workflow_store.get_template(workflow_id)
        if wf is None:
            raise HTTPException(status_code=404, detail="工作流不存在")
        task_id = deps.workflow_store.create_task(wf, book_id=req.book_id, template_id=workflow_id)

        def _run() -> None:
            try:
                workflow_engine.run_task(task_id)
            except Exception as exc:
                logger.warning("工作流后台执行异常 %s: %s", task_id, exc)

        threading.Thread(target=_run, daemon=True).start()
        return {"task_id": task_id, "status": "queued"}

    return router
