"""
anyspark.server.routes_check — 检测网路由（S85 拆分，从 routes_explore 归位）。

check / check-rule：多检测者审读 + 图谱证据 + 时序校验；用户规则编译。
独立 router（原误挂 routes_explore，命名与职责不对应——S80 分组产物）。
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from anyspark.check import SKELETON_CHECKS, compile_rule, compile_with_model, run_review
from anyspark.server.agent_factory import model_for_task
from anyspark.server.deps import AppDeps
from anyspark.server.schemas import CheckRequest, RuleRequest


def _build_book_context(deps: AppDeps, book_id: str) -> str:
    """S194：组装作品上下文摘要（供 AI 动态生成检测项用）。

    图谱实体 Top N + 设定档 + 伏笔状态 → 文本块。轻量（防 token 爆炸）。
    """
    parts: list[str] = []
    # 图谱实体（按出场频率 Top 10）
    try:
        ents = deps.graph.list_entities(book_id, limit=10)
        if ents:
            ent_lines = []
            for e in ents:
                state = (e.state or e.description or "").strip()[:80]
                ent_lines.append(f"  {e.name}（{e.entity_type}）{state}")
            parts.append("主要角色/实体：\n" + "\n".join(ent_lines))
    except Exception:
        pass
    # 伏笔状态（open 的 must 钩子 Top 5）
    try:
        plots = [p for p in deps.plots.list_points(book_id) if p.status == "open"]
        must_plots = [p for p in plots if p.priority == "must"][:5]
        if must_plots:
            plot_lines = [
                f"  ★{p.content[:30]}（{p.category}，第{p.planted_order}章起）" for p in must_plots
            ]
            parts.append("未回收伏笔（必须回收）：\n" + "\n".join(plot_lines))
    except Exception:
        pass
    return "\n\n".join(parts)


def make_check_router(deps: AppDeps) -> APIRouter:
    """检测网路由（依赖：deps.model / deps.graph_verifier）。"""
    router = APIRouter()

    @router.post("/api/check", response_model=dict[str, object])
    def check_text_route(req: CheckRequest) -> dict[str, object]:
        """多检测者审读正文（骨架+AI动态检测项，并行）+ 图谱事实证据 + 时序校验。"""
        # S194：AI 动态生成检测项——从图谱/伏笔提取作品专属检测重点
        book_ctx = _build_book_context(deps, req.book_id)
        # S195：合并默认骨架 + 用户添加项 - 用户删除项
        all_checks = deps.user_skeleton.merged_checks(SKELETON_CHECKS)
        report = run_review(
            model_for_task(deps, "editing"),
            req.target,
            req.text,
            checks=all_checks,
            book_context=book_ctx,
        )
        # S7：图谱事实证据——文本涉及的已知实体/关系（检测网/用户比对设定冲突）
        evidence = deps.graph_verifier.render_evidence(req.book_id, req.text)
        # S13：时序校验——截止当前章节时空点，提及未来才首现的实体=时空倒置
        # S29：按叙事线比较（跨线首现不误报，多线并行时间差正常）
        temporal = (
            deps.graph_verifier.check_temporal(req.book_id, req.text, req.chapter_order, req.line)
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
        compiled = compile_with_model(req.rule, model_for_task(deps, "general")) or compile_rule(
            req.rule
        )
        if compiled is None:
            return {
                "ok": False,
                "description": "未能识别的规则：请用更具体的字面/结构描述（如'不要用破折号'）",
                "hits": [],
            }
        hits = compiled.checker(req.text)
        return {"ok": True, "description": compiled.description, "hits": hits}

    # S195：用户自定义骨架检测项 CRUD（DESIGN 机制 9 第③层持久化）
    class SkeletonAddIn(BaseModel):
        category: str
        description: str

    @router.get("/api/check/skeleton", response_model=list[dict[str, object]])
    def list_skeleton() -> list[dict[str, object]]:
        """列出全部检测项：默认骨架（标记 builtin）+ 用户添加项（标记 user）。"""
        deletions = set(deps.user_skeleton.list_deletions())
        items: list[dict[str, object]] = []
        for c in SKELETON_CHECKS:
            items.append(
                {
                    "category": c.category,
                    "description": c.description,
                    "source": "builtin",
                    "deleted": c.category in deletions,
                }
            )
        for c in deps.user_skeleton.list_additions():
            items.append(
                {
                    "category": c.category,
                    "description": c.description,
                    "source": "user",
                    "deleted": False,
                }
            )
        return items

    @router.post("/api/check/skeleton", response_model=dict[str, object])
    def add_skeleton(req: SkeletonAddIn) -> dict[str, object]:
        """添加用户自定义检测项。"""
        item_id = deps.user_skeleton.add(req.category.strip(), req.description.strip())
        return {"ok": True, "id": item_id}

    @router.delete("/api/check/skeleton/{category}", response_model=dict[str, object])
    def delete_skeleton(category: str) -> dict[str, object]:
        """删除检测项：默认骨架标记为删除（可恢复），用户添加项直接删除。"""
        # 先查是否是用户添加项
        additions = deps.user_skeleton.list_additions()
        user_item = next((a for a in additions if a.category == category), None)
        if user_item is not None:
            # 用户添加项：直接删除记录
            # 注意：list_additions 返回 SkeletonCheckItem 无 id，需额外查
            # 这里用 category 匹配删除（简单可靠）
            deps.user_skeleton.delete_addition_by_category(category)
            return {"ok": True, "action": "deleted"}
        # 默认骨架：标记删除
        deps.user_skeleton.add_deletion(category)
        return {"ok": True, "action": "hidden"}

    @router.post("/api/check/skeleton/{category}/restore", response_model=dict[str, object])
    def restore_skeleton(category: str) -> dict[str, object]:
        """恢复被删除的默认检测项。"""
        deps.user_skeleton.remove_deletion(category)
        return {"ok": True}

    # S195：跨层升级——发现跨书重复偏好 → 建议升级全局 → 用户确认
    @router.get("/api/manual/cross-book-candidates")
    def list_cross_book_candidates() -> list[dict[str, object]]:
        """发现多本书中出现的相似偏好条目（建议升级为全局）。"""
        return list(deps.manual.find_cross_book_candidates())

    @router.post("/api/manual/{entry_id}/promote-global", response_model=dict[str, object])
    def promote_entry_global(entry_id: str) -> dict[str, object]:
        """把项目级条目升级为全局级（跨层升级→默认锁定）。"""
        result = deps.manual.promote_to_global(entry_id)
        if result is None:
            return {"ok": False, "error": "条目不存在"}
        return {"ok": True, "entry": result.to_dict()}

    return router
