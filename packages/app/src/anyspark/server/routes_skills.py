"""
anyspark.server.routes_skills — 叙事技巧/模板生成/AI 倾向路由（S80c 拆分）。

从 app.py build_app 搬移（行为零变化）：skill 候选生成/CRUD/草稿转正 + 模板生成 +
bias 倾向档案。闭包引用 → deps.xxx。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from anyspark.server.deps import AppDeps
from anyspark.server.schemas import (
    BiasIn,
    SkillGenerateIn,
    TemplateGenerateIn,
    WritingSkillIn,
    WritingSkillPatch,
)


def make_skills_router(deps: AppDeps) -> APIRouter:
    """叙事技巧/模板/AI 倾向路由（依赖：deps.skills/skill_generator/materials 等）。"""
    router = APIRouter()

    # ------------------------------------------------------------------
    # S50 叙事技巧（skill 式内容载体：镜头感/对白机锋/节奏控制等，可增删改/开关）
    # ------------------------------------------------------------------
    @router.post("/api/skills/generate", response_model=dict[str, object])
    def generate_skill(req: SkillGenerateIn) -> dict[str, object]:
        """S54/S58：从原文提炼 skill 候选（人工确认后走 /api/skills 入库）。

        mode=writing：文风/叙事技法（type=writing，写作调用用）；
        mode=main：类型/结构组织指导（type=main，主循环用）。
        S72：material_id 支持从资料库取原文（文风参考书 → skill 提炼链路），
        与 source_text 二选一。
        S127：候选带 type 键（target 语义并入）。
        """
        source_text = req.source_text.strip()
        if req.material_id:
            card = deps.materials.get(req.material_id)
            if card is None:
                raise HTTPException(status_code=404, detail=f"资料不存在：{req.material_id}")
            if not card.source_text.strip():
                raise HTTPException(status_code=400, detail=f"资料无原文（{card.title}），无法提炼")
            source_text = card.source_text.strip()
        if not source_text:
            raise HTTPException(status_code=400, detail="source_text 或 material_id 不能为空")
        mode = req.mode if req.mode in ("writing", "main") else "writing"
        candidates = deps.skill_generator.generate(source_text, req.hint, req.max_items, mode=mode)
        if not candidates:
            raise HTTPException(status_code=502, detail="提炼失败（无有效候选）")
        # 去重：与现有 skill 名比对（避免重复生成）
        existing_names = {s.name for s in deps.skills.list_skills()}
        fresh = [c for c in candidates if c["name"] not in existing_names]
        return {"candidates": fresh, "existing_skills": sorted(existing_names)}

    @router.post("/api/templates/generate", response_model=dict[str, object])
    def generate_template(req: TemplateGenerateIn) -> dict[str, object]:
        """S69：从书提炼剧情模式模板候选（人工确认后走 /api/templates/import 入库）。

        输入多章/全书片段 → 跨章结构归纳 → 模板四要素候选；
        与 /api/skills/generate 的区别：输出供探索 template 来源派生方向（S68 接线）。
        """
        if not req.source_text.strip():
            raise HTTPException(status_code=400, detail="source_text 不能为空")
        candidates = deps.skill_generator.generate(
            req.source_text, req.hint, req.max_items, mode="plot"
        )
        if not candidates:
            raise HTTPException(status_code=502, detail="提炼失败（无有效候选）")
        # 去重：与现有模板库（精选默认库+外部扩展库）名比对
        existing_names = {t.name for t in deps.templates_external.all()}
        fresh = [c for c in candidates if c["name"] not in existing_names]
        return {"candidates": fresh, "existing_templates": sorted(existing_names)}

    @router.get("/api/skills", response_model=list[dict[str, Any]])
    def list_skills() -> list[dict[str, Any]]:
        """全部写作技巧。"""
        return [s.to_dict() for s in deps.skills.list_skills()]

    @router.get("/api/skills/{skill_id}/export", response_model=None)
    def export_skill(skill_id: str) -> Any:
        """S118 提案 D：导出 skill 为标准文件（front-matter 五段式，分享用）。

        导出格式 = ingest 导入判别格式（闭环）——分享出去的 skill 文件
        对方上传区可直接识别进草稿。
        """
        from urllib.parse import quote

        from anyspark.server.skill_io import render_skill_file

        s = deps.skills.get(skill_id)
        if s is None:
            raise HTTPException(status_code=404, detail="技巧不存在")
        body = render_skill_file(
            name=s.name,
            description=s.description,
            content=s.content,
            example=s.example,
            tags=s.tags,
            type=s.type,
        )
        safe = quote(f"{s.name}.skill.md")
        from fastapi.responses import PlainTextResponse

        return PlainTextResponse(
            content=body,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": (f"attachment; filename=skill.md; filename*=UTF-8''{safe}")
            },
        )

    @router.post("/api/skills", response_model=dict[str, Any])
    def add_skill(req: WritingSkillIn) -> dict[str, Any]:
        typ = req.type or req.target or "writing"  # S127：type 优先，target 兼容
        s = deps.skills.add(
            req.name, req.description, req.content, req.example, req.tags, typ, req.ext
        )
        return s.to_dict()

    # -- S54 候选草稿（后台自动生成 → 人工确认转正/拒绝）——须在 {skill_id} 路由前 --
    @router.get("/api/skills/drafts", response_model=list[dict[str, Any]])
    def list_skill_drafts() -> list[dict[str, Any]]:
        """skill 候选草稿（B 心智联动/C 信号驱动自动生成，未生效）。"""
        return deps.skills.list_drafts()

    @router.post("/api/skills/drafts/{draft_id}/promote", response_model=dict[str, Any])
    def promote_skill_draft(draft_id: str) -> dict[str, Any]:
        """人工确认：草稿转正进 writing_skills（生效）。"""
        s = deps.skills.promote_draft(draft_id)
        if s is None:
            raise HTTPException(status_code=404, detail="草稿不存在")
        return s.to_dict()

    @router.delete("/api/skills/drafts/{draft_id}", response_model=dict[str, bool])
    def delete_skill_draft(draft_id: str) -> dict[str, bool]:
        ok = deps.skills.delete_draft_by_id(draft_id)
        if not ok:
            raise HTTPException(status_code=404, detail="草稿不存在")
        return {"ok": True}

    @router.patch("/api/skills/{skill_id}", response_model=dict[str, Any])
    def patch_skill(skill_id: str, req: WritingSkillPatch) -> dict[str, Any]:
        typ = req.type or req.target  # S127：type 优先，target 兼容；None=不变
        s = deps.skills.update(
            skill_id,
            req.name,
            req.description,
            req.content,
            req.example,
            req.tags,
            typ,
            req.ext,
            req.enabled,
        )
        if s is None:
            raise HTTPException(status_code=404, detail="技巧不存在")
        return s.to_dict()

    @router.delete("/api/skills/{skill_id}", response_model=dict[str, bool])
    def delete_skill(skill_id: str) -> dict[str, bool]:
        ok = deps.skills.delete(skill_id)
        if not ok:
            raise HTTPException(status_code=404, detail="技巧不存在")
        return {"ok": True}

    @router.get("/api/bias", response_model=list[dict[str, Any]])
    def list_bias() -> list[dict[str, Any]]:
        """AI 倾向档案（双向黑盒解法）。"""
        return deps.bias.list()

    @router.post("/api/bias", response_model=dict[str, Any])
    def add_bias(req: BiasIn) -> dict[str, Any]:
        """新增倾向自述（AI 声明或用户修正）。"""
        return deps.bias.add(req.content, req.source)

    @router.delete("/api/bias/{bias_id}")
    def delete_bias(bias_id: str) -> dict[str, bool]:
        deps.bias.delete(bias_id)
        return {"ok": True}

    @router.patch("/api/bias/{bias_id}", response_model=dict[str, Any])
    def update_bias(bias_id: str, req: BiasIn) -> dict[str, Any]:
        """S102：人类手动修改倾向条目（内容/来源）。"""
        updated = deps.bias.update(bias_id, req.content, req.source)
        if updated is None:
            raise HTTPException(status_code=404, detail="倾向条目不存在")
        return updated

    return router
