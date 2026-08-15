"""
anyspark.server.routes_play — 互动推演 + 评审团 + 角色卡路由（S80c 拆分）。

从 app.py build_app 搬移（行为零变化）：角色卡/角色推演 + 互动推演会话 +
评审团面板。闭包引用 → deps.xxx。
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from fastapi import APIRouter, HTTPException

from anyspark.check import run_review
from anyspark.explore import load_role_card, run_roleplay
from anyspark.server.agent_factory import model_for_task
from anyspark.server.deps import AppDeps
from anyspark.server.logging import logger
from anyspark.server.schemas import (
    PlayBranchIn,
    PlayChooseIn,
    PlayCreateIn,
    ReviewPanelRequest,
    RoleCardIn,
    RolePlayIn,
)


def make_play_router(deps: AppDeps) -> APIRouter:
    """互动推演 + 评审团路由（依赖：deps.play_engine / play_store / review_panel / workspace）。"""
    router = APIRouter()

    play_engine = deps.play_engine
    assert play_engine is not None  # 组合根装配必填（S80 接线）

    @router.post("/api/role/card", response_model=dict[str, Any])
    def role_card_upsert(req: RoleCardIn) -> dict[str, Any]:
        """创建/更新角色卡（卡片/角色卡-{name}.md）。"""
        f = deps.workspace.write_card("main", "角色卡", req.name, req.content)
        return {"ok": True, "name": req.name, "file": f.name}

    @router.post("/api/role/play", response_model=dict[str, Any])
    def role_play(req: RolePlayIn) -> dict[str, Any]:
        """角色推演：角色卡 + 当前状态 + 场景 → N 路隔离推演 → 判别选优（作为参考）。"""
        # 角色卡：文件优先，缺省从图谱实体描述兜底（S63 收敛到 load_role_card 共享）
        role_card, state = load_role_card(deps.workspace, deps.graph, req.role)
        if not role_card.strip():
            raise HTTPException(
                status_code=404,
                detail=f"角色卡不存在（可先 POST /api/role/card 创建）：{req.role}",
            )
        result = run_roleplay(
            model_for_task(deps, "planning"), role_card, state=state, scenario=req.scenario, n=req.n
        )
        if not result.candidates:
            raise HTTPException(status_code=502, detail="推演失败（无有效候选）")
        logger.info(
            "角色推演: %s × %d 路 → best=%s",
            req.role,
            len(result.candidates),
            result.best.strategy if result.best else "?",
        )
        return result.to_dict()

    # -----------------------------------------------------------------------
    # S65 互动推演（独立扩展包 anyspark-play：扮演角色多轮选择推进的推演树）
    # -----------------------------------------------------------------------
    @router.post("/api/play/sessions", response_model=dict[str, Any])
    def play_create(req: PlayCreateIn) -> dict[str, Any]:
        """创建互动推演会话（seed 切入 + 扮演 role → 根节点 scene + 候选行动）。"""
        try:
            return play_engine.create(
                role=req.role,
                seed=req.seed,
                book_id=req.book_id,
                title=req.title,
                max_depth=req.max_depth,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.get("/api/play/sessions", response_model=list[dict[str, Any]])
    def play_list(book_id: str = "main") -> list[dict[str, Any]]:
        # S152：按项目过滤（此前全量跨项目混显）
        return deps.play_store.list_sessions(book_id=book_id)

    @router.get("/api/play/sessions/{session_id}", response_model=dict[str, Any])
    def play_get(session_id: str) -> dict[str, Any]:
        session = deps.play_store.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"推演会话不存在：{session_id}")
        tree = deps.play_store.session_tree(session_id)
        current_id = session["current_node_id"] or ""
        path = deps.play_store.path_to(current_id)
        return {"session": session, "tree": tree, "path": path}

    @router.post("/api/play/sessions/{session_id}/choose", response_model=dict[str, Any])
    def play_choose(session_id: str, req: PlayChooseIn) -> dict[str, Any]:
        """选择候选行动（或自定义输入）→ 结算推进到下一场景。"""
        try:
            return play_engine.choose(
                session_id, option_id=req.option_id or "", custom_text=req.custom_text or ""
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post("/api/play/sessions/{session_id}/branch", response_model=dict[str, Any])
    def play_branch(session_id: str, req: PlayBranchIn) -> dict[str, Any]:
        """回溯分叉：回到指定节点重新生成一批候选行动（原选项保留）。"""
        try:
            return play_engine.branch(session_id, req.node_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @router.post("/api/play/sessions/{session_id}/stop", response_model=dict[str, Any])
    def play_stop(session_id: str) -> dict[str, Any]:
        """终止推演会话。"""
        try:
            return play_engine.stop(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/api/play/sessions/{session_id}/export", response_model=dict[str, Any])
    def play_export(session_id: str) -> dict[str, Any]:
        """当前路径导出灵感卡 md（接写正文参考）。"""
        try:
            md = play_engine.export_markdown(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"session_id": session_id, "markdown": md}

    review_panel = deps.review_panel
    assert review_panel is not None  # 组合根装配必填（S80 接线）

    @router.get("/api/review/reviewers", response_model=list[dict[str, object]])
    def review_reviewers_route() -> list[dict[str, object]]:
        """S65：列出评审团评审员（含人设/维度/激活态）。激活改 YAML（内容资产）。"""
        return review_panel.list_reviewers()

    @router.post("/api/review/panel", response_model=dict[str, object])
    async def review_panel_route(req: ReviewPanelRequest) -> dict[str, object]:
        """S65：拟人化评审团——并发评审 + 主席汇总裁决报告。

        自动组装外部上下文：check_report（规则引擎硬伤清单）+ foreshadow（关键点图谱）。

        与 /api/check 的分工：check=确定性硬伤（客观）；review=人格化评价（体验）。
        """
        text, chapter_ref = req.text, req.chapter_ref

        if not text.strip() and chapter_ref:
            ch = next(
                (c for c in deps.chapters.list_by_book(req.book_id) if c.title == chapter_ref),
                None,
            )

            if ch is None:
                raise HTTPException(status_code=400, detail=f"章节不存在: {chapter_ref}")

            text, chapter_ref = ch.content, ch.title

        if not text.strip():
            raise HTTPException(status_code=400, detail="缺少评审文本（text 或 chapter_ref）")

        context: dict[str, str] = {}

        if req.with_check:
            check_report = await asyncio.to_thread(
                run_review, model_for_task(deps, "editing"), chapter_ref or "当前章节", text[:20000]
            )

            context["check_report"] = (
                f"规则引擎硬伤检测（{check_report.hard_count} 处硬伤，供核实）：\n"
                f"{check_report.render()}"
            )

        if req.with_foreshadow:
            with contextlib.suppress(Exception):  # 关键点图谱取不到不阻断评审
                context["foreshadow"] = deps.plots.render(
                    req.book_id,
                    current_order=len(deps.chapters.list_by_book(req.book_id)),
                )

        report = await review_panel.run_review(
            model_for_task(deps, "editing"),
            text,
            chapter_ref=chapter_ref or "当前章节",
            reviewer_ids=req.reviewer_ids or None,
            context=context,
        )

        return {
            "overall_score": report.overall_score,
            "summary": report.summary,
            "consensus": report.consensus,
            "divergences": report.divergences,
            "top_suggestions": report.top_suggestions,
            "reviewer_count": report.reviewer_count,
            "valid_count": report.valid_count,
            "errors": report.errors,
            "individual_reviews": report.individual_reviews,
            "timestamp": report.timestamp,
            "markdown": report.render(),
            "compact": report.render_compact(),
        }

    return router
