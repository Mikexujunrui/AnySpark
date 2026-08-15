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
        # S152：带 id = 原地更新（add_template upsert），缺省 = 新建（from_dict 生成新 id）
        wf = WorkflowDef.from_dict(
            {
                "id": req.id,
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

    @router.post("/api/workflows/tasks/{task_id}/cancel", response_model=dict[str, Any])
    def cancel_workflow_task(task_id: str) -> dict[str, Any]:
        """S152k：用户取消任务——引擎在下一检查点中断，任务置 cancelled（可 resume 续跑）。

        任务级 stop：只停指定任务，不影响并行任务（此前 stop 为引擎级全局，
        取消 A 会误停 B）。已完成任务幂等返回。
        """
        task = deps.workflow_store.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        status = str(task.get("status") or "")
        if status in ("done", "failed", "cancelled"):
            return {"task_id": task_id, "status": status, "note": "任务已结束，无需取消"}
        workflow_engine.request_stop(task_id)
        return {
            "task_id": task_id,
            "status": "cancelling",
            "note": "已请求取消，引擎将在下一检查点中断",
        }

    @router.post("/api/workflows/tasks/{task_id}/resume", response_model=dict[str, Any])
    def resume_workflow_task(task_id: str) -> dict[str, Any]:
        """S138（PLAN-SCALE-SAFETY 阶段 A）：断点续跑——服务重启/中断后拉起未完成任务。

        引擎层 run_task 幂等可恢复（done 节点跳过、loop 从记录迭代数续跑，S129）；
        本端点补应用层入口：对非 done 任务后台线程再跑 run_task。
        返回当前任务状态（调用方应轮询 GET /tasks/{id} 看续跑进度）。
        """
        task = deps.workflow_store.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        status = str(task.get("status") or "")
        if status == "done":
            return task  # 已完成，无需续跑

        def _run() -> None:
            try:
                workflow_engine.run_task(task_id)
            except Exception as exc:
                logger.warning("工作流续跑异常 %s: %s", task_id, exc)
            # S158c：任务终态 → 系统通知（agent 下次会话注入知晓）
            try:
                from anyspark.server.notify import notify_workflow_completion

                notify_workflow_completion(deps.workflow_store, deps.manual, task_id)
            except Exception as exc:
                logger.warning("工作流完成通知失败 %s: %s", task_id, exc)

        threading.Thread(target=_run, daemon=True).start()
        return deps.workflow_store.get_task(task_id) or {}

    @router.post("/api/workflows/tasks/{task_id}/rollback", response_model=dict[str, Any])
    def rollback_workflow_task(task_id: str) -> dict[str, Any]:
        """S138（回溯安全网 B3）：批级一键回滚——恢复该任务改过的所有章节改前快照。

        任务写回时版本 note 带任务标识（'批量任务/任务{task_id}'，见 write_chapter
        script），按片段聚合定位每章最早一条改前快照并逐个恢复（restore_version）。
        任务本身保留（不删记录），可再次回滚/重跑；回滚产生的 '恢复前' 版本不
        携带任务标识，不会被再次聚合（防循环回滚）。
        返回 {ok, restored: [{chapter_id, title, restored_at}]}。
        """
        task = deps.workflow_store.get_task(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        snaps = deps.chapters.find_versions_by_note(f"任务{task_id}")
        if not snaps:
            return {
                "ok": True,
                "restored": [],
                "note": "该任务无改前快照（未写回章节或无来源标识）",
            }
        # 每章取最早一条（saved_at 升序 = 任务首次覆盖前状态）
        by_chapter: dict[str, dict[str, Any]] = {}
        for s in snaps:
            by_chapter.setdefault(str(s["chapter_id"]), s)
        restored = []
        for cid, snap in by_chapter.items():
            ch = deps.chapters.get(str(cid))
            if ch is not None and ch.content == snap["content"]:
                continue  # 内容已是目标快照（幂等：上次已回滚/未改动），跳过
            ch = deps.chapters.restore_version(str(cid), int(snap["id"]))
            if ch is not None:
                restored.append(
                    {"chapter_id": str(cid), "title": ch.title, "restored_at": ch.updated_at}
                )
        return {"ok": True, "restored": restored, "total": len(restored)}

    @router.get("/api/workflows/{workflow_id}", response_model=dict[str, Any])
    def get_workflow(workflow_id: str) -> dict[str, Any]:
        wf = deps.workflow_store.get_template(workflow_id)
        if wf is None:
            raise HTTPException(status_code=404, detail="工作流不存在")
        return wf.to_dict()

    @router.delete("/api/workflows/{workflow_id}", response_model=dict[str, bool])
    def delete_workflow(workflow_id: str) -> dict[str, bool]:
        """S152：预置模板保护——系统模板（builtin）不可删（工具收编执行路径/安全网载体）。"""
        if deps.workflow_store.is_builtin(workflow_id):
            raise HTTPException(
                status_code=403,
                detail="系统预置模板不可删除（工具收编执行路径/安全网载体）；可复制后修改自定义版本",
            )
        if not deps.workflow_store.delete_template(workflow_id):
            raise HTTPException(status_code=404, detail="工作流不存在")
        return {"ok": True}

    @router.post("/api/workflows/{workflow_id}/run", response_model=dict[str, Any])
    def run_workflow(workflow_id: str, req: WorkflowRunIn) -> dict[str, Any]:
        """运行工作流：冻结定义快照 → 后台线程执行（不阻塞请求）。"""
        wf = deps.workflow_store.get_template(workflow_id)
        if wf is None:
            raise HTTPException(status_code=404, detail="工作流不存在")
        task_id = deps.workflow_store.create_task(
            wf, book_id=req.book_id, template_id=workflow_id, params=req.params
        )

        def _run() -> None:
            try:
                workflow_engine.run_task(task_id)
            except Exception as exc:
                logger.warning("工作流后台执行异常 %s: %s", task_id, exc)
            # S158c：任务终态 → 系统通知（agent 下次会话注入知晓）
            try:
                from anyspark.server.notify import notify_workflow_completion

                notify_workflow_completion(deps.workflow_store, deps.manual, task_id)
            except Exception as exc:
                logger.warning("工作流完成通知失败 %s: %s", task_id, exc)

        threading.Thread(target=_run, daemon=True).start()
        return {"task_id": task_id, "status": "queued"}

    return router
