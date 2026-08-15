"""anyspark.server.routes_update — 版本检测 API（S164）。

GET /api/update/check → 本地版本 vs GitHub 最新 Release（前端启动时提示更新）。

只读端点：不修改任何本地状态；网络失败/无 Release 时 has_update=False 静默。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from anyspark.server.update_checker import check_for_update, get_local_version


def make_update_router(deps: Any) -> APIRouter:
    router = APIRouter(tags=["update"])

    @router.get("/api/update/check", response_model=dict[str, Any])
    def update_check() -> dict[str, Any]:
        """本地版本 vs 最新 Release（GitHub 公开 API，只读，300s 缓存）。"""
        return check_for_update()

    @router.get("/api/update/status", response_model=dict[str, Any])
    def update_status() -> dict[str, Any]:
        """本地版本号（前端展示用，不触发网络）。"""
        return {"current_version": get_local_version() or "unknown"}

    return router
