"""
anyspark.server.routes_explore — 探索 + 检测网路由（S80c 拆分）。

从 app.py build_app 搬移（行为零变化）：意图理解/方向卡/路径探索/维度 CRUD/
探索归档 + 检测网（check/check-rule）。闭包引用 → deps.xxx。
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException

from anyspark.align.worldsettings import constraint_texts
from anyspark.check import compile_rule, compile_with_model, run_review
from anyspark.explore import DirectionCard, IntentUnderstander, run_exploration
from anyspark.server.deps import AppDeps
from anyspark.server.logging import logger
from anyspark.server.schemas import (
    CheckRequest,
    ExploreArchiveIn,
    ExploreCardsIn,
    ExploreDimIn,
    ExploreDimPatch,
    ExploreIntentIn,
    PathExploreIn,
    RuleRequest,
)


def make_explore_router(deps: AppDeps) -> APIRouter:
    """探索 + 检测网路由（依赖：deps.model / archive / templates_external /
    dim_store / story_tree / graph_verifier）。"""
    router = APIRouter()

    @router.post("/api/explore/intent", response_model=dict[str, object])
    def explore_intent(req: ExploreIntentIn) -> dict[str, object]:
        """种子 → 概念卡 + 关键歧义点（意图理解）。"""
        understander = IntentUnderstander(deps.model)
        return understander.understand(req.seed)

    @router.post("/api/explore/cards", response_model=list[dict[str, object]])
    def explore_cards(req: ExploreCardsIn) -> list[dict[str, object]]:
        """确认后的意图 → 方向卡 ×4（并行探索，三来源混合）。"""
        # S83：约束来自设定档（全局约束；情景实体子集留给 path 级探索按描述提取）
        constraints = constraint_texts(deps.settings.list_constraints("main"))
        # S68：探索注入真实模板库（L2+L3 合并；template 来源探索者消费，死库接线）
        templates = [f"{t.name}：{t.description}" for t in deps.templates_external.all()[:12]]
        cards = run_exploration(
            deps.model,
            req.seed,
            req.intent_confirmed,
            constraints,
            n_explorers=4,
            dimensions=deps.dim_store.list_names(),  # S50：维度来自内容载体（可增删改）
            templates=templates,
        )
        return [c.to_dict() for c in cards]

    @router.post("/api/explore/path", response_model=dict[str, object])
    def explore_path_route(req: PathExploreIn) -> dict[str, object]:
        """路径探索（S67）：起点 A → 终点 B 的 N 条串联路径候选（叙事树节点之间）。

        三层探索粒度的中间层：大方向 explore → 桥梁 path → 场景内 play。
        输出作为参考（不直接写正文）；archive_index 显式传才落叙事树。
        """
        from anyspark.explore import explore_path

        from_desc, to_desc = req.from_desc, req.to_desc
        if req.from_node_id:
            node = deps.story_tree.get(req.from_node_id)
            if node is None:
                raise HTTPException(status_code=404, detail=f"起点节点不存在：{req.from_node_id}")
            from_desc = node.content
        if not from_desc.strip():
            raise HTTPException(status_code=400, detail="需要 from_desc 或 from_node_id")
        if req.to_node_id:
            node = deps.story_tree.get(req.to_node_id)
            if node is None:
                raise HTTPException(status_code=404, detail=f"终点节点不存在：{req.to_node_id}")
            to_desc = node.content
        # S83：约束 = 全局 + 当前情景（from/to 描述提及的实体）相关 + 请求临时
        ctx_entities: set[str] = set()
        for _t in (from_desc, to_desc):
            for _e in deps.settings.list_constraints(req.book_id):
                for _ent in (_e.entities or "").split(","):
                    if _ent.strip() and _ent.strip() in (_t or ""):
                        ctx_entities.add(_ent.strip())
        constraints = (
            constraint_texts(deps.settings.list_constraints(req.book_id), ctx_entities)
            + req.constraints
        )
        result = explore_path(deps.model, from_desc, to_desc, constraints, n=req.n)
        if not result.paths:
            raise HTTPException(status_code=502, detail="路径探索失败（无有效候选）")
        paths = result.to_dict()["paths"]
        archived: dict[str, object] | None = None
        if req.archive_index is not None:
            idx = req.archive_index - 1
            if not (0 <= idx < len(paths)):
                raise HTTPException(status_code=400, detail=f"archive_index 越界（1-{len(paths)}）")
            if not req.from_node_id:
                raise HTTPException(
                    status_code=400, detail="落树需要 from_node_id（起点必须是叙事树节点）"
                )
            chosen = paths[idx]
            node_ids: list[str] = []
            cur_parent: str | None = req.from_node_id
            for ev in chosen["events"]:
                node = deps.story_tree.add_node(
                    content=ev, book_id=req.book_id, parent_id=cur_parent, kind="candidate"
                )
                node_ids.append(node.id)
                cur_parent = node.id
            archived = {"node_ids": node_ids, "path": chosen}
        logger.info(
            "路径探索: %s → %s × %d 条%s",
            from_desc[:20],
            to_desc[:20],
            len(paths),
            "（已落树）" if archived else "",
        )
        return {"paths": paths, "archived": archived}

    @router.get("/api/explore/dims", response_model=list[dict[str, object]])
    def list_explore_dims() -> list[dict[str, object]]:
        """探索维度（内容化：可增删改/开关）。"""
        return deps.dim_store.list_all()

    @router.post("/api/explore/dims", response_model=dict[str, object])
    def add_explore_dim(req: ExploreDimIn) -> dict[str, object]:
        d = deps.dim_store.add(req.name)
        if d is None:
            raise HTTPException(status_code=409, detail=f"维度已存在: {req.name}")
        return d

    @router.patch("/api/explore/dims/{dim_id}", response_model=dict[str, object])
    def patch_explore_dim(dim_id: str, req: ExploreDimPatch) -> dict[str, object]:
        d = deps.dim_store.set_enabled(dim_id, req.enabled)
        if d is None:
            raise HTTPException(status_code=404, detail="维度不存在")
        return d

    @router.delete("/api/explore/dims/{dim_id}", response_model=dict[str, bool])
    def delete_explore_dim(dim_id: str) -> dict[str, bool]:
        ok = deps.dim_store.delete(dim_id)
        if not ok:
            raise HTTPException(status_code=404, detail="维度不存在")
        return {"ok": True}

    @router.post("/api/explore/archive", response_model=dict[str, object])
    def explore_archive(req: ExploreArchiveIn) -> dict[str, object]:
        """固化选中方向进项目档案 + 叙事树（S59：探索 = 树的生长器）。

        选中方向卡 → 存档 + 写入叙事树为当前主线节点（chosen），
        探索产生的分叉在树上留痕（其余候选由前端按需加为 candidate）。
        """
        c = req.card
        src: Literal["template", "grow", "user"]
        if c.get("source") == "grow":
            src = "grow"
        elif c.get("source") == "user":
            src = "user"
        else:
            src = "template"
        card = DirectionCard(
            title=str(c.get("title", "未命名方向")),
            summary=str(c.get("summary", "")),
            dimension=str(c.get("dimension", "情节驱动")),
            source=src,
            term=str(c.get("term", "")),
        )
        archived = deps.archive.archive_direction(card)
        # S59：写入叙事树为主线节点（探索 = 树的生长）
        parent_id = req.parent_node_id or None
        node = deps.story_tree.add_node(
            content=f"{card.title}：{card.summary[:60]}",
            book_id="main",
            parent_id=parent_id,
            kind="main",
            chosen=True,
        )
        archived["story_node_id"] = node.id
        return archived

    @router.get("/api/explore/archive", response_model=list[dict[str, object]])
    def explore_archive_list() -> list[dict[str, object]]:
        return deps.archive.directions()

    @router.post("/api/check", response_model=dict[str, object])
    def check_text_route(req: CheckRequest) -> dict[str, object]:
        """多检测者审读正文（骨架检测项，并行）+ 图谱事实证据 + 时序校验（确定性规则）。"""
        report = run_review(deps.model, req.target, req.text)
        # S7：图谱事实证据——文本涉及的已知实体/关系（检测网/用户比对设定冲突）
        evidence = deps.graph_verifier.render_evidence("main", req.text)
        # S13：时序校验——截止当前章节时空点，提及未来才首现的实体=时空倒置
        # S29：按叙事线比较（跨线首现不误报，多线并行时间差正常）
        temporal = (
            deps.graph_verifier.check_temporal("main", req.text, req.chapter_order, req.line)
            if req.chapter_order is not None
            else []
        )
        return {
            "target": report.target,
            "hard_count": report.hard_count,
            "graph_evidence": evidence,
            "temporal_warnings": temporal,
            "findings": [
                {
                    "category": f.category,
                    "severity": f.severity,
                    "message": f.message,
                    "evidence": f.evidence,
                    "suggestion": f.suggestion,
                    "source": f.source,
                }
                for f in report.findings
            ],
        }

    @router.post("/api/check/rule", response_model=dict[str, object])
    def check_rule_route(req: RuleRequest) -> dict[str, object]:
        """规则编译：用户自然语言规则 → 检测命中（内容判断交给模型，模板 fallback）。

        哲学（DESIGN §1）：用户规则"是什么意思"是内容判断 → LLM 编译；
        检测"怎么做"是过程 → 确定性执行器硬编码。模型/模板都识别不了时
        明确告知（不再静默丢弃）。
        """
        assert deps.model is not None
        # LLM 编译（内容判断）→ 失败回退轻量模板（无 LLM 场景）
        compiled = compile_with_model(req.rule, deps.model) or compile_rule(req.rule)
        if compiled is None:
            return {
                "ok": False,
                "description": "未能识别的规则：请用更具体的字面/结构描述（如'不要用破折号'）",
                "hits": [],
            }
        hits = compiled.checker(req.text)
        return {"ok": True, "description": compiled.description, "hits": hits}

    return router
