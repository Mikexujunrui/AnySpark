"""
anyspark.core.storage — 存储接口。

设计边界（DESIGN.md 第 4 节）：
- 存储接口：会话/消息最小持久化接口（实现可换）。
- 核心不绑定任何具体存储后端（将来可换 SQLite / 文件 / 内存）。

阶段 0 只定义接口 + 一个内存实现（够跑最小循环与测试用）。
具体持久化后端在阶段 1+ 落位。
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .types import Message


@dataclass
class Conversation:
    """一个会话的元信息 + 消息。"""

    id: str
    created_at: str
    messages: list[Message] = field(default_factory=list)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ConversationStore(ABC):
    """对话存储接口：支持创建会话、追加消息、按会话读取。"""

    @abstractmethod
    def create(self, conversation_id: str | None = None) -> Conversation:
        """创建并返回一个新会话。"""

    @abstractmethod
    def get(self, conversation_id: str) -> Conversation | None:
        """按 id 取会话；不存在返回 None。"""

    @abstractmethod
    def list_conversations(self) -> list[Conversation]:
        """列出全部会话。"""

    @abstractmethod
    def append(self, conversation_id: str, message: Message) -> None:
        """给某会话追加一条消息。"""

    @abstractmethod
    def messages(self, conversation_id: str) -> list[Message]:
        """按会话取全部消息（保序）。不存在会话返回空列表。"""


class InMemoryConversationStore(ConversationStore):
    """内存实现：进程内有效，主要用于测试与最小循环演示。"""

    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}

    def create(self, conversation_id: str | None = None) -> Conversation:
        cid = conversation_id or uuid.uuid4().hex
        if cid in self._conversations:
            raise ValueError(f"会话已存在: {cid}")
        conv = Conversation(id=cid, created_at=_now())
        self._conversations[cid] = conv
        return conv

    def get(self, conversation_id: str) -> Conversation | None:
        return self._conversations.get(conversation_id)

    def list_conversations(self) -> list[Conversation]:
        return list(self._conversations.values())

    def append(self, conversation_id: str, message: Message) -> None:
        conv = self._conversations.get(conversation_id)
        if conv is None:
            raise KeyError(f"会话不存在: {conversation_id}")
        conv.messages.append(message)

    def messages(self, conversation_id: str) -> list[Message]:
        conv = self._conversations.get(conversation_id)
        return list(conv.messages) if conv else []
