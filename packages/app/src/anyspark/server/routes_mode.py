"""
anyspark.server.routes_mode — 快速模式切换 API（S98）。

GET  /api/settings/mode → 当前模式 + 槽位 + 任务映射 + 注册表模型列表（前端配置 UI 用）
POST /api/settings/mode → 保存（mode 单字段切换 or 全量；None 字段=保留现值，
空串=清空槽位回退激活配置）

模式语义（v3 移植，见 anyspark.models.mode）：
  quality 全部任务→pro 槽 / flash 全部→flash 槽 / split 创作→pro 其余→flash /
  custom 按任务类型查 custom_map。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel


class ModeIn(BaseModel):
    """模式配置写入（None=保留现值；slot 空串=清空回退激活配置）。"""

    mode: str | None = None
    slot_pro: str | None = None
    slot_flash: str | None = None
    custom_map: dict[str, str] | None = None


def make_mode_router(deps: Any) -> APIRouter:
    router = APIRouter()

    @router.get("/api/settings/mode", response_model=dict[str, Any])
    def get_mode() -> dict[str, Any]:
        cfg = deps.mode_store.get()
        d: dict[str, Any] = cfg.to_dict()
        d["models"] = [
            {"id": m.id, "name": m.name, "model": m.model, "is_active": m.is_active}
            for m in deps.models.list()
        ]
        return d

    @router.post("/api/settings/mode", response_model=dict[str, Any])
    def set_mode(req: ModeIn) -> dict[str, Any]:
        cfg = deps.mode_store.get()
        if req.mode is not None:
            cfg.mode = req.mode
        if req.slot_pro is not None:
            cfg.slot_pro = req.slot_pro or None
        if req.slot_flash is not None:
            cfg.slot_flash = req.slot_flash or None
        if req.custom_map is not None:
            cfg.custom_map = req.custom_map
        saved = deps.mode_store.save(cfg)
        d: dict[str, Any] = saved.to_dict()
        return {"ok": True, **d}

    return router
