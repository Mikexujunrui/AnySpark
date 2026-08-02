"""anyspark.store.sqlite — 会话与章节存储的真实 SQLite 测试。"""

import tempfile
from pathlib import Path

from anyspark.core.types import Message
from anyspark.store import ChapterStore, SqliteConversationStore


def _db() -> Path:
    d = tempfile.mkdtemp()
    return Path(d) / "test.db"


def test_conversation_crud() -> None:
    db = _db()
    store = SqliteConversationStore(db)
    try:
        conv = store.create()
        store.append(conv.id, Message(role="user", content="a"))
        store.append(conv.id, Message(role="assistant", content="b"))
        msgs = store.messages(conv.id)
        assert [m.content for m in msgs] == ["a", "b"]
        assert store.get(conv.id) is not None
        assert store.list_conversations()
    finally:
        store.close()


def test_chapter_upsert_and_version_history() -> None:
    db = _db()
    store = ChapterStore(db)
    try:
        c1 = store.upsert("main", "第一章", "版本一正文", 0)
        c2 = store.upsert("main", "第一章", "版本二正文（修改后）", 0)
        assert c1.id == c2.id  # 同一章覆盖
        got = store.get(c1.id)
        assert got is not None
        assert got.content == "版本二正文（修改后）"
        assert len(got.versions) == 1  # 旧版进了历史
        assert got.versions[0]["content"] == "版本一正文"
    finally:
        store.close()


def test_chapter_list_ordered() -> None:
    db = _db()
    store = ChapterStore(db)
    try:
        store.upsert("main", "第二章", "b", 1)
        store.upsert("main", "第一章", "a", 0)
        titles = [c.title for c in store.list_by_book("main")]
        assert titles == ["第一章", "第二章"]
    finally:
        store.close()
