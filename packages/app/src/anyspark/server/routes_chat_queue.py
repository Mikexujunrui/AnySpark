"""
anyspark.server.routes_chat_queue — 聊天消息队列路由（从 routes_chat 拆分，S207）。

S99 排队接力：queues 查看 / queue 入队 / queue 删 / queue→steer 转插入。
依赖：deps.queue_lock / conv_queues / active_lock / active_agents。
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body

from anyspark.server.deps import AppDeps
from anyspark.server.logging import logger
from anyspark.server.schemas import QueueIn


def make_chat_queue_router(deps: AppDeps) -> APIRouter:
    """消息队列路由（依赖：deps.queue_lock / conv_queues / active_lock / active_agents）。"""
    router = APIRouter()

    @router.get("/api/chat/queues")
    def list_queues() -> dict[str, Any]:
        """S99：队列信息面板——所有会话的排队消息 + 运行中会话列表。"""
        with deps.queue_lock:
            queues = {cid: list(items) for cid, items in deps.conv_queues.items() if items}
        with deps.active_lock:
            running = sorted(deps.active_agents.keys())
        return {"queues": queues, "running": running}

    @router.post("/api/chat/queue", response_model=dict[str, Any])
    def enqueue_queue(req: Annotated[QueueIn, Body()]) -> dict[str, Any]:
        """S99：消息入队（接力执行第二步前仅存储/展示；不要求会话正在运行）。"""
        item = {"id": uuid.uuid4().hex, "text": req.message}
        with deps.queue_lock:
            items = deps.conv_queues.setdefault(req.conversation_id, [])
            items.append(item)
            snapshot = list(items)
        logger.info("queue 入队: conv=%s 队列长度=%d", req.conversation_id, len(snapshot))
        return {"ok": True, "queue": snapshot}

    @router.delete(
        "/api/chat/queue/{conversation_id}/{queue_item_id}", response_model=dict[str, Any]
    )
    def dequeue_queue(conversation_id: str, queue_item_id: str) -> dict[str, Any]:
        """S99：删除一条排队消息（删空自动清理会话键）。"""
        with deps.queue_lock:
            items = deps.conv_queues.get(conversation_id, [])
            removed = any(i["id"] == queue_item_id for i in items)
            rest = [i for i in items if i["id"] != queue_item_id]
            if rest:
                deps.conv_queues[conversation_id] = rest
            else:
                deps.conv_queues.pop(conversation_id, None)
            snapshot = list(rest)
        return {"ok": removed, "queue": snapshot}

    @router.post(
        "/api/chat/queue/{conversation_id}/{queue_item_id}/steer", response_model=dict[str, Any]
    )
    def steer_queued(conversation_id: str, queue_item_id: str) -> dict[str, Any]:
        """S99：排队消息转插入（原子）——steer 成功才移除队列项；
        会话未运行时保留并提示（区别于删除，不丢指令）。"""
        with deps.queue_lock:
            items = deps.conv_queues.get(conversation_id, [])
            target = next((i for i in items if i["id"] == queue_item_id), None)
        if target is None:
            return {"ok": False, "reason": "排队消息不存在"}
        with deps.active_lock:
            agent = deps.active_agents.get(conversation_id)
        if agent is None:
            return {"ok": False, "reason": "会话未在运行，无法插入（可等它完成或先中止）"}
        agent.steer(target["text"])
        logger.info("queue→steer 注入: conv=%s msg=%s", conversation_id, target["text"][:40])
        with deps.queue_lock:
            items = deps.conv_queues.get(conversation_id, [])
            rest = [i for i in items if i["id"] != queue_item_id]
            if rest:
                deps.conv_queues[conversation_id] = rest
            else:
                deps.conv_queues.pop(conversation_id, None)
            snapshot = list(rest)
        return {"ok": True, "queue": snapshot}

    return router
