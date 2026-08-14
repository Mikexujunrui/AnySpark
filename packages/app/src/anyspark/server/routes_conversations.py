"""
anyspark.server.routes_conversations — 会话 + 运行时模型路由（S80c 拆分）。

从 app.py build_app 搬移（行为零变化）：会话列表/继承 fork/重命名/消息/删除 +
模型注册表 CRUD/激活。闭包引用 → deps.xxx。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from anyspark.core import Conversation
from anyspark.models import DEFAULT_BASE_URL, validate_protocol, validate_thinking
from anyspark.models.registry import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    ModelConfig,
    slugify,
)
from anyspark.server.deps import AppDeps
from anyspark.server.logging import logger
from anyspark.server.schemas import (
    ConversationCreateIn,
    ConversationRenameIn,
    MessagesSaveIn,
    ModelIn,
)


def make_conversations_router(deps: AppDeps) -> APIRouter:
    """会话 + 模型路由（依赖：deps.store / deps.models / deps.window）。"""
    router = APIRouter()

    @router.get("/api/conversations", response_model=list[dict[str, Any]])
    def list_conversations(book_id: str = "main") -> list[dict[str, Any]]:
        """会话列表（S80：按项目过滤——会话绑定书籍，缺省 main）。"""
        convs = deps.store.list_conversations(book_id)
        return [
            {
                "id": c.id,
                "created_at": c.created_at,
                "parent_id": c.parent_id,
                "fork_point": c.fork_point,
                "title": c.title,
                "book_id": c.book_id,
                "message_count": len(deps.store.messages(c.id)),
            }
            for c in reversed(convs)  # 新的在前
        ]

    @router.post("/api/conversations", response_model=dict[str, Any])
    def create_conversation(req: ConversationCreateIn) -> dict[str, Any]:
        """S80：创建会话（绑定项目——会话归属 book_id，智能体作用域=该项目）。"""
        conv = deps.store.create(book_id=req.book_id)
        if req.title:
            conv.title = req.title
            deps.store.save(conv)
        return {
            "id": conv.id,
            "created_at": conv.created_at,
            "parent_id": conv.parent_id,
            "fork_point": conv.fork_point,
            "title": conv.title,
            "book_id": conv.book_id,
            "message_count": 0,
        }

    @router.post("/api/conversations/{conv_id}/fork", response_model=dict[str, Any])
    def fork_conversation(conv_id: str, fork_point: str = "") -> dict[str, Any]:
        """S58c 继承派生：从当前会话创建继承它的新会话（链条可追溯）。

        新会话复制源会话消息（接着上次聊）+ parent_id 指向源会话；
        前端/agent 用它实现"继承并新开会话"。源不存在 → 404。
        """
        child = deps.store.fork(conv_id, fork_point=fork_point or "从会话末尾继承")
        if child is None:
            raise HTTPException(status_code=404, detail=f"源会话不存在: {conv_id}")
        chain: list[str] = []
        cur: Conversation | None = child
        while cur is not None:
            chain.append(cur.id)
            cur = deps.store.get(cur.parent_id) if cur.parent_id else None
        return {
            "conversation_id": child.id,
            "parent_id": child.parent_id,
            "fork_point": child.fork_point,
            "chain": chain,  # [新会话, 源, 源的源...] 继承链条
        }

    @router.put("/api/conversations/{conv_id}", response_model=dict[str, bool])
    def rename_conversation(conv_id: str, req: ConversationRenameIn) -> dict[str, bool]:
        """重命名会话。"""
        conv = deps.store.get(conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        conv.title = req.title
        deps.store.save(conv)
        return {"ok": True}

    @router.get("/api/conversations/{conv_id}/messages", response_model=list[dict[str, Any]])
    def get_conversation_messages(conv_id: str) -> list[dict[str, Any]]:
        """获取会话的全部消息（F4a：会话历史恢复）。

        S145b（空气泡根治）：过滤 content 为空的 assistant 消息——工具调用轮的
        assistant 声明（content='' + metadata.tool_calls）落库是为了上下文配对
        （S23），对用户无展示价值；历史 UI 过滤掉（工具轨迹由 RunLedger 展示），
        上下文重建走 store.messages 不受影响。
        """
        conv = deps.store.get(conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        msgs = deps.store.messages(conv_id)
        out = []
        for m in msgs:
            content = m.content or ""
            if m.role == "assistant" and not content.strip():
                continue  # 工具轮空 assistant 声明不展示
            out.append({"role": m.role, "content": content})
        return out

    @router.post("/api/conversations/{conv_id}/messages", response_model=dict[str, int])
    def save_conversation_messages(conv_id: str, req: MessagesSaveIn) -> dict[str, int]:
        """S80：前端全量保存消息（编辑消息/手动整理后 auto-save 覆盖写）。

        事务内清空该会话消息后重新写入（前端持有完整消息数组，覆盖语义一致）；
        与 chat 过程中的自动落库不冲突（最终一致）。
        """
        conv = deps.store.get(conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        from anyspark.core import Message

        msgs = [Message(role=m.role, content=m.content, metadata={}) for m in req.messages]
        deps.store.replace_messages(conv_id, msgs)
        return {"saved": len(msgs)}

    @router.delete("/api/conversations/{conv_id}", response_model=dict[str, bool])
    def delete_conversation(conv_id: str) -> dict[str, bool]:
        """删除会话及其所有消息（S99：顺带清空该会话的排队消息）。"""
        conv = deps.store.get(conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        deps.store.delete(conv_id)
        with deps.queue_lock:
            deps.conv_queues.pop(conv_id, None)
        return {"ok": True}

    # -----------------------------------------------------------------------
    # S47 运行时模型配置：注册表 CRUD + 激活切换（换供应商/换模型/选思考强度）
    # -----------------------------------------------------------------------
    @router.get("/api/models", response_model=dict[str, Any])
    def list_models() -> dict[str, Any]:
        cfgs = deps.models.list()
        active_id = next((c.id for c in cfgs if c.is_active), cfgs[0].id if cfgs else None)
        return {"active_id": active_id, "models": [c.to_dict() for c in cfgs]}

    @router.post("/api/models", response_model=dict[str, Any])
    def upsert_model(req: ModelIn) -> dict[str, Any]:
        """新增或更新模型配置（同 id 覆盖；id 缺省由 name 生成 slug）。"""
        try:
            validate_thinking(req.thinking)  # 非法思考强度 → 400（尽早暴露配置错误）
            validate_protocol(req.protocol)  # S131：非法协议 → 400
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        cfg = ModelConfig(
            id=req.id or slugify(req.name),
            name=req.name,
            base_url=req.base_url or DEFAULT_BASE_URL,
            model=req.model,
            api_key=req.api_key,
            context_window=req.context_window or DEFAULT_CONTEXT_WINDOW,
            max_tokens=req.max_tokens or DEFAULT_MAX_TOKENS,
            temperature=req.temperature or DEFAULT_TEMPERATURE,
            thinking=req.thinking,
            protocol=req.protocol,
        )
        saved = deps.models.upsert(cfg)
        return {"ok": True, "model": saved.to_dict(), "active": saved.is_active}

    @router.delete("/api/models/{model_id}", response_model=dict[str, Any])
    def delete_model(model_id: str) -> dict[str, Any]:
        if not deps.models.delete(model_id):
            raise HTTPException(status_code=400, detail="无法删除：至少保留一条配置，或配置不存在")
        return {"ok": True}

    @router.post("/api/models/{model_id}/activate", response_model=dict[str, Any])
    def activate_model(model_id: str) -> dict[str, Any]:
        """切换当前激活模型——所有组件（Agent/抽取/检测/探索/后台）即时跟随。"""
        cfg = deps.models.activate(model_id)
        if cfg is None:
            raise HTTPException(status_code=404, detail=f"模型配置不存在: {model_id}")
        if cfg.context_window != deps.window:
            logger.warning(
                "模型窗口 %d != token 预算窗口 %d——重启后预算按新窗口生效（S26）",
                cfg.context_window,
                deps.window,
            )
        return {"ok": True, "active": cfg.to_dict()}

    return router
