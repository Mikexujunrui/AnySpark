"""
anyspark.server.routes_graph — 图谱 + 影响分析 + 手动抽取路由（S80c 拆分）。

从 app.py build_app 搬移（行为零变化）：图谱类型/实体/关系/事件 CRUD +
上下文预览 + 影响分析 + 手动抽取。闭包引用 → deps.xxx。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from anyspark.server.deps import AppDeps
from anyspark.server.schemas import (
    GraphEntityIn,
    GraphEntityPatch,
    GraphEventIn,
    GraphEventPatch,
    GraphExtractIn,
    GraphRelationIn,
    GraphRelationPatch,
    GraphTypeIn,
    GraphTypePatch,
    ImpactIn,
)


def make_graph_router(deps: AppDeps) -> APIRouter:
    """图谱路由（依赖：deps.graph / graph_injector / graph_extractor / chapters）。"""
    router = APIRouter()

    @router.get("/api/graph/types", response_model=list[dict[str, Any]])
    def list_graph_types(book_id: str = "main") -> list[dict[str, Any]]:
        """实体类型集（S50 内容化：可增删改/开关；S82 按项目）。"""
        return deps.graph.list_types(book_id)

    @router.post("/api/graph/types", response_model=dict[str, Any])
    def add_graph_type(req: GraphTypeIn) -> dict[str, Any]:
        t = deps.graph.add_type(req.name)
        if t is None:
            raise HTTPException(status_code=409, detail=f"类型已存在: {req.name}")
        return t

    @router.patch("/api/graph/types/{type_id}", response_model=dict[str, Any])
    def patch_graph_type(type_id: str, req: GraphTypePatch) -> dict[str, Any]:
        t = deps.graph.set_type_enabled(type_id, req.enabled)
        if t is None:
            raise HTTPException(status_code=404, detail="类型不存在")
        return t

    @router.delete("/api/graph/types/{type_id}", response_model=dict[str, bool])
    def delete_graph_type(type_id: str) -> dict[str, bool]:
        ok = deps.graph.delete_type(type_id)
        if not ok:
            raise HTTPException(status_code=404, detail="类型不存在")
        return {"ok": True}

    @router.get("/api/graph/entities", response_model=list[dict[str, Any]])
    def list_graph_entities(
        q: str = "", entity_type: str = "", book_id: str = "main"
    ) -> list[dict[str, Any]]:
        """图谱实体（可 q 模糊 / entity_type 过滤；S82 按项目）。"""
        items = deps.graph.list_entities(book_id, q=q or None, entity_type=entity_type or None)
        return [e.to_dict() for e in items]

    @router.get("/api/graph/relations", response_model=list[dict[str, Any]])
    def list_graph_relations(book_id: str = "main") -> list[dict[str, Any]]:
        return [r.to_dict() for r in deps.graph.list_relations(book_id)]

    @router.get("/api/graph/events", response_model=list[dict[str, Any]])
    def list_graph_events(book_id: str = "main") -> list[dict[str, Any]]:
        return [e.to_dict() for e in deps.graph.list_events(book_id)]

    @router.get("/api/graph/context", response_model=dict[str, str])
    def graph_context(book_id: str = "main") -> dict[str, str]:
        """当前时空点已知事实注入块（预览；S82 按项目）。"""
        return {"block": deps.graph_injector.build_block(book_id)}

    # ── S72：图谱条目手动管理（实体/关系/事件 增改删）──
    @router.post("/api/graph/entities", response_model=dict[str, Any])
    def add_graph_entity(req: GraphEntityIn) -> dict[str, Any]:
        """S72：手动登记实体（同名=覆盖字段；不改自动统计/权重/出场记录）。"""
        if not req.name.strip():
            raise HTTPException(status_code=400, detail="name 不能为空")
        ent = deps.graph.get_entity(req.book_id, req.name)
        if ent is None:
            ent = deps.graph.upsert_entity(
                req.book_id,
                req.name,
                req.entity_type,
                req.aliases,
                req.description,
                state_delta=req.state,
            )
        else:
            ent = deps.graph.update_entity_fields(
                req.book_id,
                req.name,
                aliases=req.aliases or None,
                description=req.description or None,
                state=req.state or None,
                entity_type=req.entity_type or None,
            )
        assert ent is not None
        return ent.to_dict()

    @router.patch("/api/graph/entities/{name_or_id}", response_model=dict[str, Any])
    def patch_graph_entity(
        name_or_id: str, req: GraphEntityPatch, book_id: str = "main"
    ) -> dict[str, Any]:
        """S72：局部编辑实体字段（name 限定书 / id 回退——兼容前端传内部 id）。"""
        ent = deps.graph.get_entity(book_id, name_or_id)
        if ent is None:
            ent = deps.graph._entity_by_id(name_or_id)  # 前端按 id 操作时回退
        if ent is None:
            raise HTTPException(status_code=404, detail=f"实体不存在: {name_or_id}")
        data = req.model_dump(exclude_none=True)
        data.pop("name", None)  # S72 语义：实体主键为 name，改名请删建
        ent = deps.graph.update_entity_fields(ent.book_id, ent.name, **data)
        assert ent is not None
        return ent.to_dict()

    @router.delete("/api/graph/entities/{name_or_id}", response_model=dict[str, bool])
    def delete_graph_entity(name_or_id: str, book_id: str = "main") -> dict[str, bool]:
        """S72：删除实体及其关联关系（name 限定书 / id 回退）。"""
        ent = deps.graph.get_entity(book_id, name_or_id)
        if ent is None:
            ent = deps.graph._entity_by_id(name_or_id)  # 前端按 id 操作时回退
        if ent is None:
            raise HTTPException(status_code=404, detail=f"实体不存在: {name_or_id}")
        if not deps.graph.delete_entity(ent.book_id, ent.name):
            raise HTTPException(status_code=404, detail=f"实体不存在: {name_or_id}")
        return {"ok": True}

    @router.post("/api/graph/relations", response_model=dict[str, Any])
    def add_graph_relation(req: GraphRelationIn) -> dict[str, Any]:
        """S72：手动登记关系（两端实体须存在；同三元组去重覆盖）。"""
        rel = deps.graph.upsert_relation(
            req.book_id, req.from_name, req.to_name, req.rel_type, req.description
        )
        if rel is None:
            raise HTTPException(
                status_code=400,
                detail=f"关系端点实体不存在（{req.from_name} 或 {req.to_name}），请先登记实体",
            )
        return rel.to_dict()

    @router.patch("/api/graph/relations/{rid}", response_model=dict[str, Any])
    def patch_graph_relation(rid: str, req: GraphRelationPatch) -> dict[str, Any]:
        """S72：编辑关系字段。"""
        rel = deps.graph.update_relation_fields(rid, **req.model_dump(exclude_none=True))
        if rel is None:
            raise HTTPException(status_code=404, detail="关系不存在")
        return rel.to_dict()

    @router.delete("/api/graph/relations/{rid}", response_model=dict[str, bool])
    def delete_graph_relation(rid: str) -> dict[str, bool]:
        """S72：删除关系。"""
        if not deps.graph.delete_relation(rid):
            raise HTTPException(status_code=404, detail="关系不存在")
        return {"ok": True}

    @router.post("/api/graph/events", response_model=dict[str, Any])
    def add_graph_event(req: GraphEventIn) -> dict[str, Any]:
        """S72：手动登记事件（同章同名去重覆盖）。"""
        ev = deps.graph.upsert_event(
            req.book_id,
            req.chapter_ref,
            req.chapter_order,
            req.time_point,
            req.label,
            req.description,
            req.involved,
        )
        return ev.to_dict()

    @router.patch("/api/graph/events/{eid}", response_model=dict[str, Any])
    def patch_graph_event(eid: str, req: GraphEventPatch) -> dict[str, Any]:
        """S72：编辑事件字段。"""
        ev = deps.graph.update_event_fields(eid, **req.model_dump(exclude_none=True))
        if ev is None:
            raise HTTPException(status_code=404, detail="事件不存在")
        return ev.to_dict()

    @router.delete("/api/graph/events/{eid}", response_model=dict[str, bool])
    def delete_graph_event(eid: str) -> dict[str, bool]:
        """S72：删除事件。"""
        if not deps.graph.delete_event(eid):
            raise HTTPException(status_code=404, detail="事件不存在")
        return {"ok": True}

    @router.post("/api/impact", response_model=dict[str, object])
    def impact_route(req: ImpactIn) -> dict[str, object]:
        """S45：影响分析——改第 N 章（涉及实体）→ 后续受影响章节（连锁修改依据）。"""
        hits = deps.graph.impact_chapters(req.book_id, req.chapter_order, req.entities)
        return {"changed_order": req.chapter_order, "impacted": hits, "count": len(hits)}

    @router.post("/api/graph/extract", response_model=dict[str, int])
    def graph_extract_route(req: GraphExtractIn) -> dict[str, int]:
        """手动抽取一章入库（真实 LLM；write_chapter 后已自动，此为补抽/重抽）。"""
        existing = [e.to_dict() for e in deps.graph.list_entities(req.book_id)]
        ext = deps.graph_extractor.extract(req.chapter_ref, req.text, existing)
        chs = deps.chapters.list_by_book(req.book_id)
        order = next((c.order_index for c in chs if c.title == req.chapter_ref), len(chs))
        deps.graph.ingest_chapter(req.book_id, req.chapter_ref, order, ext)
        return {
            "entities": len(ext.entities),
            "relations": len(ext.relations),
            "events": len(ext.events),
        }

    return router
