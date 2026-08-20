"""
anyspark.server.routes_check — 检测网路由（S85 拆分，从 routes_explore 归位）。

check / check-rule：多检测者审读 + 图谱证据 + 时序校验；用户规则编译。
独立 router（原误挂 routes_explore，命名与职责不对应——S80 分组产物）。
"""

from __future__ import annotations

from fastapi import APIRouter

from anyspark.check import compile_rule, compile_with_model, run_review
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
        report = run_review(
            model_for_task(deps, "editing"),
            req.target,
            req.text,
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

    return router
