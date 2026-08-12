"""
anyspark.server.routes_plot — 模式库 + 关键点 + 材料路由（S80c 拆分）。

从 app.py build_app 搬移（行为零变化）：templates CRUD/import + plot（伏笔）CRUD/
生成/回收 + materials（资料库）CRUD/消化。闭包引用 → deps.xxx。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from anyspark.server.agent_factory import model_for_task
from anyspark.server.deps import AppDeps
from anyspark.server.schemas import (
    MaterialImportIn,
    MaterialIn,
    MaterialPatchIn,
    PlotIn,
    PlotItemIn,
    PlotPatchIn,
    TemplateIn,
)
from anyspark.template import MaterialDigestor


def make_plot_router(deps: AppDeps) -> APIRouter:
    """模式库 + 关键点 + 材料路由（依赖：deps.templates_external / plot_generator /
    plots / materials / graph / model）。"""
    router = APIRouter()

    @router.get("/api/templates", response_model=list[dict[str, object]])
    def list_templates() -> list[dict[str, object]]:
        """模式库 L2+L3 合并（探索方向生成器）。"""
        return [t.to_dict() for t in deps.templates_external.all()]

    @router.post("/api/templates/import", response_model=dict[str, object])
    def import_template(req: TemplateIn) -> dict[str, object]:
        """L3 外部模式库：导入自定义模板（自然语言+四要素，合并进探索库）。"""
        t = deps.templates_external.import_template(
            req.name, req.description, req.granularity, req.position, req.function, req.params
        )
        return t.to_dict()

    @router.delete("/api/templates/{name}")
    def delete_template(name: str) -> dict[str, bool]:
        deps.templates_external.delete(name)
        return {"ok": True}

    @router.post("/api/plot", response_model=list[dict[str, object]])
    def generate_plot(req: PlotIn) -> list[dict[str, object]]:
        """关键点图谱（T2 阶段 3 可选深入）：LLM 生成草案入库（S82 按项目）。"""
        points = deps.plot_generator.generate(req.book_id, deps.plots, req.settings)
        return [p.to_dict() for p in points]

    @router.get("/api/plot", response_model=list[dict[str, object]])
    def list_plot(book_id: str = "main") -> list[dict[str, object]]:
        return [p.to_dict() for p in deps.plots.list_points(book_id)]

    @router.patch("/api/plot/{plot_id}", response_model=dict[str, object])
    def update_plot_status(plot_id: str, req: PlotPatchIn) -> dict[str, object]:
        """更新关键点：状态/关注度/优先级/回收章节——操作即对齐信号。"""
        p = deps.plots.update(
            plot_id,
            status=req.status,
            attention=req.attention,
            priority=req.priority,
            resolved_chapter=req.resolved_chapter,
        )
        if p is None:
            raise HTTPException(status_code=404, detail="关键点不存在")
        return p.to_dict()

    @router.post("/api/plot/item", response_model=dict[str, object])
    def add_plot_item(req: PlotItemIn) -> dict[str, object]:
        """S31：主动登记伏笔/关键点（作者或 AI 声明）——
        priority=must 表示这是作者对读者的主线承诺（剧情钩子，必须回收）；
        planted_order 记录登记时的章节序号（老龄化计算用）。"""
        p = deps.plots.add(
            req.book_id,
            req.category,
            req.content,
            req.chapter_ref,
            priority=req.priority,
            planted_order=req.planted_order,
        )
        return p.to_dict()

    @router.post("/api/plot/import-resolve")
    def resolve_all_plots(book_id: str = "main") -> dict[str, int]:
        """S31：完整书导入归档——所有 open 伏笔标 resolved（书已写完，线索已揭开）。
        只报告归档数量，不输出回收率（伏笔管理烂不影响作品伟大性，不做质量评分）。"""
        n = deps.plots.resolve_all(book_id)
        return {"resolved": n}

    @router.delete("/api/plot/{plot_id}")
    def delete_plot(plot_id: str) -> dict[str, bool]:
        deps.plots.delete(plot_id)
        return {"ok": True}

    @router.post("/api/materials", response_model=dict[str, object])
    def add_material(req: MaterialIn) -> dict[str, object]:
        """上传材料 → 真实 LLM 消化成摘要卡 → 图谱关联 → 入库（原文保留）。"""
        purpose: Any = req.purpose if req.purpose in ("style", "fact", "both") else "fact"
        digestor = MaterialDigestor(model_for_task(deps, "extraction"))
        card = digestor.digest(req.text, purpose=purpose)
        if req.title:
            card.title = req.title
        card.kind = req.kind if req.kind in ("inspiration", "copy") else "inspiration"
        # 图谱关联（机制 10 补齐）：摘要卡角色/设定/术语 → 图谱实体
        names = [*card.characters, *card.key_settings, *card.terms]
        linked = deps.graph.resolve_names(req.book_id, names)
        card.graph_entities = [e.id for e in linked]
        deps.materials.save(card, book_id=req.book_id)
        return card.to_dict()

    @router.post("/api/materials/import", response_model=dict[str, object])
    def import_material(req: MaterialImportIn) -> dict[str, object]:
        """S79：从别的池复制资料卡到本池（复制+溯源+标 copy 冷藏，智能体不可见）。"""
        new_card = deps.materials.import_card(req.card_id, req.from_book_id, req.to_book_id)
        if new_card is None:
            raise HTTPException(status_code=404, detail="源资料卡不存在")
        return new_card.to_dict()

    @router.get("/api/materials", response_model=list[dict[str, object]])
    def list_materials(book_id: str = "main", kind: str | None = None) -> list[dict[str, object]]:
        """S79：按池（book_id）列资料卡；kind 可过滤（inspiration/copy，None=全部）。

        前端传 kind='all' 等价 None（显示全部）；智能体工具走 inspiration（见 tools_extras）。
        """
        if kind == "all":
            kind = None
        return [m.to_dict() for m in deps.materials.list(book_id, kind=kind)]

    @router.get("/api/materials/{material_id}", response_model=dict[str, object])
    def get_material(material_id: str) -> dict[str, object]:
        card = deps.materials.get(material_id)
        if card is None:
            raise HTTPException(status_code=404, detail="材料不存在")
        return card.to_dict()

    @router.post("/api/materials/{material_id}/promote", response_model=dict[str, object])
    def promote_material(material_id: str) -> dict[str, object]:
        """S79：copy 冷藏卡 → inspiration（用户手动转可见，智能体才看得到）。"""
        card = deps.materials.promote(material_id)
        if card is None:
            raise HTTPException(status_code=404, detail="卡片不存在或不是冷藏副本")
        return card.to_dict()

    @router.patch("/api/materials/{material_id}", response_model=dict[str, object])
    def patch_material(material_id: str, req: MaterialPatchIn) -> dict[str, object]:
        """S80：局部编辑资料卡（只改传入字段；kind/source_ref 不可改）。"""
        card = deps.materials.update(material_id, req.model_dump(exclude_none=True))
        if card is None:
            raise HTTPException(status_code=404, detail="材料不存在")
        return card.to_dict()

    @router.delete("/api/materials/{material_id}", response_model=dict[str, object])
    def delete_material(material_id: str) -> dict[str, object]:
        """删除资料。"""
        ok = deps.materials.delete(material_id)
        if not ok:
            raise HTTPException(status_code=404, detail="材料不存在")
        return {"ok": True, "id": material_id}

    return router
