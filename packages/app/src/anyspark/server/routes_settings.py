"""
anyspark.server.routes_settings — 设定档/破限模式路由（S80c 拆分）。

从 app.py build_app 搬移（行为零变化）：设定档类别 CRUD + 条目 CRUD + 破限开关 +
图谱提炼设定草案。闭包引用 → deps.xxx。
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from anyspark.core import Message
from anyspark.server.deps import AppDeps
from anyspark.server.schemas import (
    SettingCategoryIn,
    SettingCategoryPatch,
    UncensorIn,
    WorldSettingExtractIn,
    WorldSettingIn,
    WorldSettingPatch,
)


def make_settings_router(deps: AppDeps) -> APIRouter:
    """设定档/破限路由（依赖：deps.settings/workspace/model/graph）。"""
    router = APIRouter()

    # ------------------------------------------------------------------
    # S41 设定档（作者正典：人物卡/能力体系/世界观规则）
    # ------------------------------------------------------------------
    @router.get("/api/settings/categories", response_model=list[dict[str, Any]])
    def list_setting_categories() -> list[dict[str, Any]]:
        """设定档类别（S50 内容化：可增删改/开关）。"""
        return deps.settings.list_categories()

    @router.post("/api/settings/categories", response_model=dict[str, Any])
    def add_setting_category(req: SettingCategoryIn) -> dict[str, Any]:
        c = deps.settings.add_category(req.name)
        if c is None:
            raise HTTPException(status_code=409, detail=f"类别已存在: {req.name}")
        return c

    @router.patch("/api/settings/categories/{cat_id}", response_model=dict[str, Any])
    def patch_setting_category(cat_id: str, req: SettingCategoryPatch) -> dict[str, Any]:
        c = deps.settings.set_category_enabled(cat_id, req.enabled)
        if c is None:
            raise HTTPException(status_code=404, detail="类别不存在")
        return c

    @router.delete("/api/settings/categories/{cat_id}", response_model=dict[str, bool])
    def delete_setting_category(cat_id: str) -> dict[str, bool]:
        ok = deps.settings.delete_category(cat_id)
        if not ok:
            raise HTTPException(status_code=404, detail="类别不存在")
        return {"ok": True}

    @router.get("/api/settings", response_model=list[dict[str, Any]])
    def list_settings(book_id: str = "main") -> list[dict[str, Any]]:
        """设定档全部条目（按书）。"""
        return [s.to_dict() for s in deps.settings.list(book_id)]

    @router.post("/api/settings", response_model=dict[str, Any])
    def add_setting(req: WorldSettingIn) -> dict[str, Any]:
        """新增设定条目（作者手写）；is_constraint=1 为约束条目。"""
        s = deps.settings.add(
            req.content,
            req.category,
            req.name,
            source="manual",
            book_id=req.book_id,
            is_constraint=req.is_constraint,
            entities=req.entities,
        )
        return s.to_dict()

    @router.patch("/api/settings/{setting_id}", response_model=dict[str, Any])
    def patch_setting(setting_id: str, req: WorldSettingPatch) -> dict[str, Any]:
        s = deps.settings.update(
            setting_id,
            req.content,
            req.category,
            req.name,
            is_constraint=req.is_constraint,
            entities=req.entities,
        )
        if s is None:
            raise HTTPException(status_code=404, detail="设定条目不存在")
        return s.to_dict()

    @router.delete("/api/settings/{setting_id}", response_model=dict[str, bool])
    def delete_setting(setting_id: str) -> dict[str, bool]:
        ok = deps.settings.delete(setting_id)
        if not ok:
            raise HTTPException(status_code=404, detail="设定条目不存在")
        return {"ok": True}

    # S70：破限模式开关（书籍级）——GET 查 / POST 设；文件标志在每书工作区
    @router.get("/api/uncensored", response_model=dict[str, object])
    def get_uncensored(book_id: str = "main") -> dict[str, object]:
        return {"book_id": book_id, "enabled": deps.workspace.is_uncensored(book_id)}

    @router.post("/api/uncensored", response_model=dict[str, object])
    def set_uncensored(req: UncensorIn) -> dict[str, object]:
        enabled = deps.workspace.set_uncensored(req.book_id, req.enabled)
        return {"book_id": req.book_id, "enabled": enabled}

    @router.post("/api/settings/extract", response_model=dict[str, object])
    def extract_settings(req: WorldSettingExtractIn) -> dict[str, object]:
        """S42：从图谱提炼设定草案（只含已揭示信息，LLM 生成，作者确认后入库）。

        提炼边界（防止"角色认知越界/未来设定泄露"）：只基于图谱已有实体/事件——
        图谱覆盖=已写章节=角色与叙事者都可能知道的信息；未来设定需作者手写补充。
        """
        assert deps.model is not None
        es = deps.graph.list_entities(req.book_id, limit=10000)
        core = [e for e in es if e.weight >= 3]
        evs = sorted(
            deps.graph.list_events(req.book_id, limit=10000), key=lambda x: x.chapter_order
        )
        ent_txt = "\n".join(
            f"- {e.name}（{e.entity_type}，出场{e.weight}章）"
            f"{('：' + (e.state or e.description)[:60]) if (e.state or e.description) else ''}"
            for e in sorted(core, key=lambda x: -x.weight)[:60]
        )
        ev_txt = "\n".join(
            f"[{ev.chapter_ref}] {ev.label}：{ev.description[:60]}" for ev in evs[:80]
        )
        prompt = (
            "根据以下小说知识图谱数据（实体/事件），提炼【设定档草案】——"
            "只包含图谱中已出现的信息（不编造未来设定）。按类别输出：\n"
            "人物卡（主要角色：身份/性格/当前状态）/ 能力体系（已出现的职业能力）/ "
            "世界观规则 / 势力 / 地点 / 物品。\n"
            '输出 JSON：{"settings": [{"category": "人物卡", '
            '"name": "顾欣桐", "content": "..."}]}\n'
            f"【实体】\n{ent_txt}\n【事件】\n{ev_txt}"
        )
        out = deps.model.respond(
            [
                Message(
                    role="system",
                    content="你是设定考据者。严格基于图谱数据提炼设定草案，不编造。",
                ),
                Message(role="user", content=prompt),
            ],
            [],
        )
        import re as _re

        m = _re.search(r"\{.*\}", out.text, _re.DOTALL)
        if not m:
            return {"draft": [], "raw": out.text[:500]}
        try:
            data = json.loads(m.group(0))
            draft = [
                s for s in data.get("settings", []) if isinstance(s, dict) and s.get("content")
            ]
        except Exception:
            return {"draft": [], "raw": out.text[:500]}
        return {"draft": draft, "raw": ""}

    return router
