"""
anyspark.server.routes_story — 影响分析 + 剧情计划 + 叙事树/线进度路由（S80c 拆分）。

从 app.py build_app 搬移（行为零变化）：影响分析 impact + 剧情计划 CRUD +
叙事树节点/树视图/布局 + 线进度。闭包引用 → deps.xxx。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from anyspark.server.deps import AppDeps
from anyspark.server.schemas import (
    ChapterPlanIn,
    ChapterPlanPatch,
    ImpactIn,
    StoryLayoutIn,
    StoryNodeIn,
    StoryThreadIn,
    StoryThreadPatch,
)


def make_story_router(deps: AppDeps) -> APIRouter:
    """叙事路由（依赖：deps.graph / deps.plans / deps.story_tree / deps.story_threads）。"""
    router = APIRouter()

    @router.post("/api/impact", response_model=dict[str, object])
    def impact_route(req: ImpactIn) -> dict[str, object]:
        """S45：影响分析——改第 N 章（涉及实体）→ 后续受影响章节（连锁修改依据）。"""
        hits = deps.graph.impact_chapters("main", req.chapter_order, req.entities)
        return {"changed_order": req.chapter_order, "impacted": hits, "count": len(hits)}

    # ------------------------------------------------------------------
    # S46 剧情计划（计划→执行：固化章节计划，写作注入，推进标记）
    # ------------------------------------------------------------------
    @router.get("/api/plan", response_model=list[dict[str, Any]])
    def list_plan() -> list[dict[str, Any]]:
        """全部章节计划（按 chapter_order）。"""
        return [p.to_dict() for p in deps.plans.list()]

    @router.post("/api/plan", response_model=dict[str, Any])
    def add_plan(req: ChapterPlanIn) -> dict[str, Any]:
        p = deps.plans.add(req.chapter_order, req.title, req.content)
        return p.to_dict()

    @router.patch("/api/plan/{plan_id}", response_model=dict[str, Any])
    def patch_plan(plan_id: str, req: ChapterPlanPatch) -> dict[str, Any]:
        p = deps.plans.update(plan_id, req.title, req.content, req.status)
        if p is None:
            raise HTTPException(status_code=404, detail="计划不存在")
        return p.to_dict()

    @router.delete("/api/plan/{plan_id}", response_model=dict[str, bool])
    def delete_plan(plan_id: str) -> dict[str, bool]:
        ok = deps.plans.delete(plan_id)
        if not ok:
            raise HTTPException(status_code=404, detail="计划不存在")
        return {"ok": True}

    # ------------------------------------------------------------------
    # S59 叙事树（分叉路径模型）+ 线进度（映射锚）
    # ------------------------------------------------------------------
    @router.get("/api/story/nodes", response_model=list[dict[str, Any]])
    def list_story_nodes(book_id: str = "main") -> list[dict[str, Any]]:
        """全部叙事树节点。"""
        return [n.to_dict() for n in deps.story_tree.list_nodes(book_id)]

    @router.post("/api/story/nodes", response_model=dict[str, Any])
    def add_story_node(req: StoryNodeIn) -> dict[str, Any]:
        """加叙事节点（默认=探索可能性 candidate；kind 可指定 root/main/anchor/subplot）。"""
        n = deps.story_tree.add_node(
            content=req.content,
            book_id=req.book_id,
            parent_id=req.parent_id,
            kind=req.kind,
            chosen=req.chosen,
        )
        return n.to_dict()

    @router.post("/api/story/nodes/{node_id}/choose", response_model=dict[str, Any])
    def choose_story_node(node_id: str) -> dict[str, Any]:
        """选为当前主线（chosen，其他让位）。"""
        n = deps.story_tree.choose(node_id)
        if n is None:
            raise HTTPException(status_code=404, detail="节点不存在")
        return n.to_dict()

    @router.post("/api/story/nodes/{node_id}/anchor", response_model=dict[str, Any])
    def anchor_story_node(node_id: str) -> dict[str, Any]:
        """标记为必经锚点。"""
        n = deps.story_tree.mark_anchor(node_id)
        if n is None:
            raise HTTPException(status_code=404, detail="节点不存在")
        return n.to_dict()

    @router.delete("/api/story/nodes/{node_id}", response_model=dict[str, Any])
    def delete_story_node(node_id: str) -> dict[str, Any]:
        """删除叙事节点（含所有后代）。"""
        ok = deps.story_tree.delete_node(node_id)
        if not ok:
            raise HTTPException(status_code=404, detail="节点不存在")
        return {"ok": True, "id": node_id}

    @router.get("/api/story/tree", response_model=dict[str, Any])
    def story_tree_view(book_id: str = "main") -> dict[str, Any]:
        """树 + 线进度的注入视图（预览/调试）。"""
        return {
            "nodes": [n.to_dict() for n in deps.story_tree.list_nodes(book_id)],
            "threads": [t.to_dict() for t in deps.story_threads.list_threads(book_id)],
            "render": deps.story_tree.render_tree(book_id),
            "thread_render": deps.story_threads.render_threads(book_id),
        }

    @router.put("/api/story/layout", response_model=dict[str, int])
    def save_story_layout(req: StoryLayoutIn) -> dict[str, int]:
        """S76：批量保存叙事树节点手动坐标（DESIGN §12.37）。"""
        updated = deps.story_tree.set_positions(
            req.book_id, [(p.node_id, p.x, p.y) for p in req.positions]
        )
        return {"updated": updated}

    @router.post("/api/story/threads", response_model=dict[str, Any])
    def add_story_thread(req: StoryThreadIn) -> dict[str, Any]:
        """声明/升级一条线（预定义或涌现后手动确认）。"""
        t = deps.story_threads.add(
            name=req.name,
            book_id=req.book_id,
            content=req.content,
            progress=req.progress,
            role=req.role,
            node_id=req.node_id,
        )
        return t.to_dict()

    @router.get("/api/story/threads", response_model=list[dict[str, Any]])
    def list_story_threads(book_id: str = "main") -> list[dict[str, Any]]:
        return [t.to_dict() for t in deps.story_threads.list_threads(book_id)]

    @router.patch("/api/story/threads/{thread_id}", response_model=dict[str, Any])
    def patch_story_thread(thread_id: str, req: StoryThreadPatch) -> dict[str, Any]:
        """更新线进度（映射锚）/ 完成。"""
        t = deps.story_threads.get(thread_id)
        if t is None:
            raise HTTPException(status_code=404, detail="线不存在")
        if req.progress is not None:
            t = deps.story_threads.update_progress(thread_id, req.progress)
        if req.status == "done":
            t = deps.story_threads.mark_done(thread_id)
        return (t or deps.story_threads.get(thread_id)).to_dict()  # type: ignore[union-attr]

    return router
