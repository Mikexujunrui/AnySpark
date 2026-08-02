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
