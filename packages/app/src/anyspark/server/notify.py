"""anyspark.server.notify — 工作流任务完成通知（S158c：补齐"完成后的汇报"）。

任务 done/failed 后写一条系统通知（manual_notices，action="system"）：
- agent 下次会话装配时未读通知自动注入（agent_factory 渲染"系统通知"），
  agent 直接知道任务完成，不用重新查 workflow_status
- 前端 /api/manual/notices 也可展示（已读态统一管理）

调用点：routes_workflow（HTTP/前端启动 + 断点续跑）与 tools_workflow（agent 启动）
三个后台线程在 run_task 返回后调用本函数。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def notify_workflow_completion(workflow_store: Any, manual: Any, task_id: str) -> None:
    """任务终态（done/failed）→ 系统通知；非终态/异常静默。"""
    try:
        task = workflow_store.get_task(task_id)
        if task is None:
            return
        status = str(task.get("status") or "")
        if status not in ("done", "failed"):
            return
        name = str(task.get("name") or task_id)
        book = str(task.get("book_id") or "main")
        if status == "done":
            content = (
                f"工作流「{name}」已完成（task={task_id}），可在会话中询问结果或查看任务详情。"
            )
        else:
            err = str(task.get("error") or "")[:200]
            content = f"工作流「{name}」失败：{err or '未知原因'}（task={task_id}）"
        manual.add_system_notice(book, content)
    except Exception:
        logger.warning("工作流完成通知失败: task=%s", task_id, exc_info=True)
