"""anyspark.core.storage 测试。"""

import pytest

from anyspark.core.storage import InMemoryConversationStore
from anyspark.core.types import Message


def test_create_and_get() -> None:
    store = InMemoryConversationStore()
    conv = store.create("c1")
    assert store.get("c1") is conv


def test_create_duplicate_raises() -> None:
    store = InMemoryConversationStore()
    store.create("c1")
    with pytest.raises(ValueError):
        store.create("c1")


def test_append_and_messages_ordered() -> None:
    store = InMemoryConversationStore()
    store.create("c1")
    store.append("c1", Message(role="user", content="a"))
    store.append("c1", Message(role="assistant", content="b"))
    msgs = store.messages("c1")
    assert [m.content for m in msgs] == ["a", "b"]
    assert [m.role for m in msgs] == ["user", "assistant"]


def test_create_autogenerates_id() -> None:
    store = InMemoryConversationStore()
    conv = store.create()
    assert conv.id


def test_missing_conversation_returns_empty() -> None:
    store = InMemoryConversationStore()
    assert store.messages("nonexistent") == []
    assert store.get("nonexistent") is None


def test_fork_inherits_chain_and_messages() -> None:
    """S58c 继承派生：新会话 parent_id 指向源 + 复制消息（参考 pi forkFrom）。"""
    store = InMemoryConversationStore()
    src = store.create()
    store.append(src.id, Message(role="user", content="第一轮"))
    store.append(src.id, Message(role="assistant", content="好的"))
    # fork
    child = store.fork(src.id, fork_point="第1轮对话后")
    assert child is not None
    assert child.parent_id == src.id  # 链条指针
    assert child.fork_point == "第1轮对话后"
    assert len(child.messages) == 2  # 继承全部消息
    assert child.messages[0].content == "第一轮"
    # 源会话不受影响
    assert len(store.messages(src.id)) == 2
    # fork 不继承消息的变体
    empty = store.fork(src.id, inherit_messages=False)
    assert empty is not None and empty.messages == []
    # 源不存在
    assert store.fork("nonexistent") is None
