"""
anyspark.server.routes_mind — 心智/说明书/简介/信号路由（S80c 拆分）。

从 app.py build_app 搬移（行为零变化）：manual 条目 CRUD/衰减/通知 + brief 读写/生成 +
信号采集 + 心智对账/档位建议。闭包引用 → deps.xxx。
"""

from __future__ import annotations

from typing import Any, Literal, cast

from fastapi import APIRouter, HTTPException

from anyspark.align import (
    ManualEntry,
    build_agency_suggest_prompt,
    build_reconcile_prompt,
    parse_agency_suggest_result,
    parse_reconcile_result,
)
from anyspark.core import Message
from anyspark.server.deps import AppDeps, BgTask
from anyspark.server.logging import logger
from anyspark.server.schemas import (
    BriefGenerateIn,
    BriefIn,
    ManualDecayIn,
    ManualEntryIn,
    ManualEntryPatch,
    ReconcileIn,
    SignalIn,
)


def make_mind_router(deps: AppDeps) -> APIRouter:
    """心智/说明书/简介/信号路由（依赖：deps.manual/signals/workspace/model 等）。"""
    router = APIRouter()

    @router.get("/api/manual", response_model=list[dict[str, Any]])
    def list_manual(scope: str = "project") -> list[dict[str, Any]]:
        """说明书条目（scope=project|global）。"""
        entries = deps.manual.list(scope, "main")  # type: ignore[arg-type]
        return [e.to_dict() for e in entries]

    @router.get("/api/manual/notices", response_model=list[dict[str, Any]])
    def list_manual_notices(limit: int = 20) -> list[dict[str, Any]]:
        """心智变更通知（S74c：供前端展示——用户知情：谁在何时改了哪条偏好）。

        前端展示建议：通知列表（action=add/update/delete，old→new 变更内容、时间、
        已读态）；未读高亮；可跳转到对应条目操作（保留/改回）。
        """
        return deps.manual.list_notices(book_id="main", limit=limit)

    @router.post("/api/manual", response_model=dict[str, Any])
    def add_manual(req: ManualEntryIn) -> dict[str, Any]:
        """新增说明书条目（用户手写）。"""
        scope = cast(Literal["project", "global"], req.scope)
        entry = ManualEntry(
            content=req.content,
            source="user",
            confidence=req.confidence,
            scope=scope,
            book_id="main",
            category=cast(
                Literal["collab", "style", "habit"],
                req.category if req.category in ("collab", "style", "habit") else "style",
            ),
        )
        deps.manual.add(entry)
        # S54-B：新增 style 偏好 → 后台生成对应 skill 候选草稿（人工确认生效）
        if entry.category == "style":
            deps.bg_queue.put(BgTask(kind="skill_drafts"))
        return entry.to_dict()

    @router.patch("/api/manual/{entry_id}", response_model=dict[str, Any])
    def update_manual(entry_id: str, req: ManualEntryPatch) -> dict[str, Any]:
        """修改条目内容（锁定条目拒绝，用户主权）。"""
        entry = deps.manual.update(entry_id, content=req.content, category=req.category)
        if entry is None:
            raise HTTPException(status_code=404, detail="条目不存在")
        if req.locked is not None:
            entry = deps.manual.set_locked(entry_id, req.locked) or entry
        return entry.to_dict()

    @router.delete("/api/manual/{entry_id}")
    def delete_manual(entry_id: str) -> dict[str, bool]:
        deps.manual.delete(entry_id)
        return {"ok": True}

    @router.post("/api/manual/decay", response_model=dict[str, object])
    def manual_decay(req: ManualDecayIn) -> dict[str, object]:
        """S61：活跃度衰减（DESIGN §12.18 元数据收敛：冷条沉没）。

        长时间未触达的未锁定条目自动降级（high→medium→low）；list() 已惰性执行，
        本端点提供显式触发与阈值覆盖。只降活跃度、不删内容（用户主权）。
        """
        n = deps.manual.decay_stale(req.days_high, req.days_medium)
        entries = deps.manual.list("project")
        low = [e.to_dict() for e in entries if e.activity == "low" and not e.locked]
        return {"decayed": n, "cold_entries": low, "note": "冷条目未自动删除，可手动删除"}

    # S58 项目智能体简介（给 AI 和用户看的项目总览，非读者简介）
    @router.get("/api/brief", response_model=dict[str, Any])
    def get_brief(book_id: str = "main") -> dict[str, Any]:
        """读项目简介（md 权威；未建档返回空 + 提示）。"""
        content = deps.workspace.read_brief(book_id)
        return {"book_id": book_id, "content": content, "exists": bool(content)}

    @router.post("/api/brief", response_model=dict[str, Any])
    def save_brief(req: BriefIn) -> dict[str, Any]:
        """写项目简介（用户/前端可编辑，权威在 md 文件）。"""
        deps.workspace.write_brief(req.book_id, req.content)
        return {"book_id": req.book_id, "content": req.content.strip(), "exists": True}

    @router.post("/api/brief/generate", response_model=dict[str, Any])
    def generate_brief(req: BriefGenerateIn) -> dict[str, Any]:
        """从现有项目数据自动生成简介草案（人工确认后写回）。

        素材：已固化设定约束 + 已选方向 + 设定档 + 当前进展（章节数/场景记忆）。
        真实 LLM 提炼成总览；失败返回空提示。
        """
        try:
            archive = deps.archive  # 原 ProjectArchive(real_db)——deps.archive 同 db 等价
            # 约束 = 设定档"世界观规则"类别（全书固定规则，直接注入不匹配）
            constraints = [
                e.content
                for e in deps.settings.list(req.book_id)
                if e.category == "世界观规则" and (e.content or "").strip()
            ]
            directions = archive.directions(req.book_id)[:5]
            settings_items = deps.settings.list(req.book_id)
            ch_count = len(deps.chapters.list_by_book(req.book_id))
            last_scene = deps.memory_store.latest(req.book_id)
            parts = [
                "已固化设定约束：" + ("；".join(constraints) if constraints else "（无）"),
                "已选方向："
                + (
                    "; ".join(
                        f"{d.get('title', '')}: {d.get('summary', '')[:80]}" for d in directions
                    )
                    if directions
                    else "（无）"
                ),
                "设定档条目："
                + (
                    "; ".join(f"{s.name}" for s in settings_items[:10])
                    if settings_items
                    else "（无）"
                ),
                f"当前进展：已写 {ch_count} 章"
                + (f"；最近：{last_scene.content[:120]}" if last_scene else ""),
            ]
            prompt = (
                "你是小说项目简介生成器。根据下面的项目现状素材，生成一份『项目智能体简介』\n"
                "（给 AI 和用户看的协作总览，不是读者简介）。\n"
                "包含：一句话世界观 / 主线方向 / 主要角色 / 叙事基调 / "
                "已固化设定 / 当前进展 / 写作注意事项。\n"
                "用明确无歧义的自然语言，总长 300 字以内。\n\n素材：\n" + "\n".join(parts)
            )
            output = deps.model.respond([Message(role="system", content=prompt)], [])
            draft = (output.text or "").strip()
            if not draft:
                return {"draft": "", "note": "生成失败（空输出）"}
            return {"draft": draft, "note": ""}
        except Exception as exc:
            return {"draft": "", "note": f"生成失败: {exc}"}

    @router.post("/api/signals")
    def record_signal(req: SignalIn) -> dict[str, Any]:
        """采集用户操作信号（接受/修改/删除/自定义等）；同时驱动能动性反馈调节。"""
        if req.kind == "accepted":
            sig = deps.signal_collector.accepted(req.content, req.context)
            deps.agency.adjust(+1)  # 接受=升级（档位上限 4）
        elif req.kind == "deleted":
            sig = deps.signal_collector.deleted(req.content, req.context)
            deps.agency.adjust(-1)  # 删除=降级（档位下限 0）
        elif req.kind == "rejected":
            sig = deps.signal_collector.rejected(req.content, req.context)
            deps.agency.adjust(-1)  # 拒绝=降级
        elif req.kind == "negative":
            # S53c ⑤ 实时负例：负例信号原文进 signals 表（不丢）——"是否构成雷区、
            # 雷区是什么"是内容判断，交给轮末提炼器 LLM（S62：删除正则机械落条目）
            sig = deps.signal_collector.negative(req.content, req.context)
        elif req.kind == "custom":
            sig = deps.signal_collector.custom(req.content, req.context)
        else:  # modified
            sig = deps.signal_collector.modified(req.content, req.new_content or "", req.context)
        # S28：信号 → 后台提炼 → 说明书（异步，不阻塞操作；修复对齐闭环缺口）
        deps.bg_queue.put(BgTask(kind="refine"))
        # S54-C：信号驱动 → skill 候选草稿（后台，人工确认生效）
        deps.bg_queue.put(BgTask(kind="skill_drafts"))
        return sig.to_dict()

    @router.post("/api/mind/reconcile", response_model=dict[str, Any])
    def mind_reconcile(req: ReconcileIn) -> dict[str, Any]:
        """S53c ⑥ 跨会话对账：已沉淀条目 vs 最近行为信号 → 冲突/需更新提示（真实 LLM）。"""
        entries = deps.manual.list("project", req.book_id)
        recent_signals = deps.signals.recent(limit=30, book_id=req.book_id)
        if not entries:
            return {"results": [], "note": "无条目可对账"}
        prompt = build_reconcile_prompt(entries, recent_signals)
        try:
            output = deps.model.respond([Message(role="system", content=prompt)], [])
            results = parse_reconcile_result(output.text)
            return {"results": results, "note": ""}
        except Exception as exc:  # 对账失败不影响主链路
            logger.warning("心智对账失败: %s", exc)
            return {"results": [], "note": f"对账失败: {exc}"}

    @router.post("/api/mind/agency-suggest", response_model=dict[str, object])
    def mind_agency_suggest(req: ReconcileIn) -> dict[str, object]:
        """S61 L2：AI 看心智（collab 条目）后建议档位（真实 LLM，语义判断）。

        与 MindPlanner 关键词启发式互补：启发式处理无 LLM/失败场景，L2 理解
        复杂协作偏好（如"你看着办但大事先问我"）。建议不自动应用（用户主权），
        采纳后走 POST /api/agency。
        """
        assert deps.model is not None
        entries = deps.manual.list("project", req.book_id)
        collab = [e for e in entries if e.category == "collab"]
        levels = deps.agency.list_levels()
        # 启发式对照（始终返回，供前端展示规则推断）
        plan = deps.mind_planner.plan(
            req.book_id, base_agency=deps.agency.get_current(req.book_id).order
        )
        if not collab:
            return {
                "suggested_level": None,
                "reason": "暂无协作偏好条目（collab），先用规则推断",
                "note": "",
                "heuristic_agency": plan.agency_level,
                "heuristic_reason": plan.reason,
                "levels": [x.to_dict() for x in levels],
            }
        prompt = build_agency_suggest_prompt(collab, levels)
        try:
            output = deps.model.respond([Message(role="system", content=prompt)], [])
            res = parse_agency_suggest_result(output.text)
            valid = next((lv for lv in levels if lv.id == res.get("level_id", "")), None)
            return {
                "suggested_level": valid.to_dict() if valid else None,
                "reason": res.get("reason", ""),
                "note": res.get("note", ""),
                "heuristic_agency": plan.agency_level,
                "heuristic_reason": plan.reason,
                "levels": [x.to_dict() for x in levels],
            }
        except Exception as exc:  # 建议失败不影响主链路
            logger.warning("档位建议失败: %s", exc)
            return {
                "suggested_level": None,
                "reason": f"建议失败: {exc}",
                "note": "",
                "heuristic_agency": plan.agency_level,
                "heuristic_reason": plan.reason,
                "levels": [x.to_dict() for x in levels],
            }

    @router.get("/api/mind/agency-suggest", response_model=dict[str, object])
    def mind_agency_heuristic() -> dict[str, object]:
        """S61 L2 只读通道：当前规则推断（不调 LLM，前端打开面板即可展示）。"""
        plan = deps.mind_planner.plan("main", base_agency=deps.agency.get_current("main").order)
        return {
            "heuristic_agency": plan.agency_level,
            "heuristic_reason": plan.reason,
            "collab_notes": plan.collab_notes,
        }

    return router
