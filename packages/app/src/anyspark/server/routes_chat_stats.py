"""
anyspark.server.routes_chat_stats — 聊天统计路由（从 routes_chat 拆分，S207）。

stats / stats_writing：纯 SQL 读现有表，零新表。
依赖轻：仅 deps.db_path。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from anyspark.server.deps import AppDeps
from anyspark.server.stats import compute_stats, compute_writing_stats


def make_chat_stats_router(deps: AppDeps) -> APIRouter:
    """统计路由（依赖：deps.db_path）。"""
    router = APIRouter()

    @router.get("/api/stats")
    def stats() -> dict[str, Any]:
        """T7 验证指标（代理指标，纯 SQL 统计现有表，零新表）：修改率/提问率/完成率。"""
        return compute_stats(deps.db_path)

    @router.get("/api/stats/writing")
    def stats_writing() -> dict[str, Any]:
        """S101：作者视角写作统计（纯 SQL 读现有表）：趋势/连续写作/版本质量/大纲完成度/线进度。"""
        return compute_writing_stats(deps.db_path)

    return router
