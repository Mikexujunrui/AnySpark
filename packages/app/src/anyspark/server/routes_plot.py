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
    MaterialPublishIn,
    PlotIn,
    PlotItemIn,
    PlotPatchIn,
    TemplateIn,
)
from anyspark.template import MaterialDigestor


def _plot_skill_to_template(s: Any) -> dict[str, object]:
    """S128：skill 表 type=plot 条目 → 前端 TemplateItem 形状（四要素+layer 从 ext 解析）。

    ext 兼容缺省：无 ext/无四要素时回落默认（对齐 _parse_templates 枚举回落）。
    """
    import json as _json

    ext: dict[str, Any] = {}
    if s.ext:
        try:
            ext = _json.loads(s.ext) or {}
        except ValueError:
            ext = {}
    valid_gr = ("全书", "卷", "章", "场景", "段落")
    valid_pos = ("开局", "发展", "高潮", "结局")
    valid_fn = ("铺垫", "主线", "悬念", "爽点", "情感")
    gr = ext.get("granularity", "章")
    po = ext.get("position", "发展")
    fn = ext.get("function", "主线")
    return {
        "name": s.name,
        "description": s.description,
        "granularity": gr if gr in valid_gr else "章",
        "position": po if po in valid_pos else "发展",
        "function": fn if fn in valid_fn else "主线",
        "params": ext.get("params", []) or [],
        "layer": ext.get("layer", "external"),
    }


def make_plot_router(deps: AppDeps) -> APIRouter:
    """模式库 + 关键点 + 材料路由（依赖：deps.skills / plot_generator /
    plots / materials / graph / model）。"""
    router = APIRouter()

    @router.get("/api/templates", response_model=list[dict[str, object]])
    def list_templates() -> list[dict[str, object]]:
        """模式库（S128：skill 表 type=plot 类，L2 默认+L3 外部+拆书 plot 子条合并）。"""
        return [_plot_skill_to_template(s) for s in deps.skills.plot_skills()]

    @router.post("/api/templates/import", response_model=dict[str, object])
    def import_template(req: TemplateIn) -> dict[str, object]:
        """L3 外部模式库：导入自定义模板（自然语言+四要素）→ skill 表 type=plot。

        对齐原 ExternalLibrary.import_template 的 INSERT OR REPLACE 语义：同名覆盖；
        L2 默认模板（layer=default）不可被覆盖（保持默认库不可改）。
        """
        import json as _json

        ext = _json.dumps(
            {
                "granularity": req.granularity,
                "position": req.position,
                "function": req.function,
                "params": req.params,
                "layer": "external",
            },
            ensure_ascii=False,
        )
        dup = next((s for s in deps.skills.plot_skills() if s.name == req.name), None)
        if dup is not None and dup.ext and '"layer": "default"' in dup.ext:
            raise HTTPException(status_code=409, detail=f"默认模板「{req.name}」不可覆盖")
        if dup is not None:
            s = deps.skills.update(
                dup.id,
                name=req.name,
                description=req.description,
                content=f"剧情模式：{req.description}",
                tags="剧情模式",
                ext=ext,
            )
        else:
            s = deps.skills.add(
                name=req.name,
                description=req.description,
                content=f"剧情模式：{req.description}",
                tags="剧情模式",
                type="plot",
                ext=ext,
            )
        assert s is not None
        return _plot_skill_to_template(s)

    @router.delete("/api/templates/{name}")
    def delete_template(name: str) -> dict[str, bool]:
        """删除外部模板（S128：删 skill 表 type=plot 同名条目；L2 默认库不可删）。"""
        target = next((s for s in deps.skills.plot_skills() if s.name == name), None)
        if target is None:
            return {"ok": True}
        # L2 默认库（layer=default）不可删（对齐原 ExternalLibrary.delete 只删外部）
        if target.ext and '"layer": "default"' in target.ext:
            return {"ok": False}
        deps.skills.delete(target.id)
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

    @router.post("/api/materials/publish", response_model=dict[str, object])
    def publish_material(req: MaterialPublishIn) -> dict[str, object]:
        """S123：项目 → 全局池提交通道（写作者贡献回公共）。

        把项目池的 inspiration 卡发布到全局池：复制 + 标来源（source_ref=
        project:<书id>）+ 作为 inspiration（可见可检索，非 copy 冷藏）——
        这是全局池的唯一写入来源（防项目随手内容污染公共区）。
        """
        from_book = req.from_book_id.strip()
        if from_book == "global":
            raise HTTPException(status_code=400, detail="全局卡无需再发布")
        card = deps.materials.get(req.card_id)
        if card is None:
            raise HTTPException(status_code=404, detail="资料卡不存在")
        if card.kind != "inspiration":
            raise HTTPException(
                status_code=400, detail="仅 inspiration 卡可发布（copy 冷藏卡先转灵感）"
            )
        # 池归属校验在 store.publish_to_global（SQL 按 book_id+kind 查源）
        new_card = deps.materials.publish_to_global(req.card_id, from_book)
        if new_card is None:
            raise HTTPException(
                status_code=400, detail=f"卡片不在项目「{from_book}」中，或发布失败"
            )
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
