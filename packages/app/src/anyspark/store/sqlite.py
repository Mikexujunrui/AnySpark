"""
anyspark.store.sqlite — SQLite 持久化存储：会话 + 章节（真实落盘）。

实现 core 的 ConversationStore 接口（实现可换），并额外提供章节/版本存储。
数据库文件默认放 data/anyspark.db（data/ 已 gitignore，绝不入库）。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anyspark.core.storage import Conversation, ConversationStore
from anyspark.core.types import Message


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _conversation_from_row(row: tuple[Any, ...]) -> Conversation:
    cid, created_at = row
    return Conversation(id=cid, created_at=created_at)


class SqliteConversationStore(ConversationStore):
    """SQLite 实现的会话存储（会话 + 消息）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        parent = Path(self._db).parent
        parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False：嵌入式 SQLite 供 FastAPI 多线程 endpoint 共用
        self._conn = sqlite3.connect(self._db, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL REFERENCES conversations(id),
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}',
                seq INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, seq);
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def create(self, conversation_id: str | None = None) -> Conversation:
        cid = conversation_id or uuid.uuid4().hex
        now = _now()
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO conversations (id, created_at) VALUES (?, ?)",
                (cid, now),
            )
        return Conversation(id=cid, created_at=now)

    def get(self, conversation_id: str) -> Conversation | None:
        row = self._conn.execute(
            "SELECT id, created_at FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        return _conversation_from_row(row) if row else None

    def list_conversations(self) -> list[Conversation]:
        rows = self._conn.execute(
            "SELECT id, created_at FROM conversations ORDER BY created_at"
        ).fetchall()
        return [_conversation_from_row(row) for row in rows]

    def append(self, conversation_id: str, message: Message) -> None:
        # 确保会话存在
        self.get(conversation_id) or self.create(conversation_id)
        seq = self._conn.execute(
            "SELECT COALESCE(MAX(seq), -1) + 1 AS n FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()["n"]
        with self._conn:
            self._conn.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata, seq, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    conversation_id,
                    message.role,
                    message.content,
                    json.dumps(message.metadata, ensure_ascii=False),
                    seq,
                    _now(),
                ),
            )

    def messages(self, conversation_id: str) -> list[Message]:
        rows = self._conn.execute(
            "SELECT role, content, metadata FROM messages WHERE conversation_id = ? ORDER BY seq",
            (conversation_id,),
        ).fetchall()
        return [
            Message(
                role=row["role"],
                content=row["content"],
                metadata=json.loads(row["metadata"] or "{}"),
            )
            for row in rows
        ]


# ---------------------------------------------------------------------------
# 章节存储（写作产出：text 正文 + 版本历史，支持修改）
# ---------------------------------------------------------------------------
@dataclass
class Chapter:
    """一本书的一章（含版本历史）。"""

    id: str
    book_id: str
    title: str
    content: str
    order_index: int
    created_at: str
    updated_at: str
    versions: list[dict[str, Any]]  # 旧版本快照 [{content, saved_at, note}]


class ChapterStore:
    """SQLite 章节存储：正文 + 版本历史（修改可追溯）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.row_factory = sqlite3.Row
        # 复用同一 db 时与会话表共存
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chapters (
                id TEXT PRIMARY KEY,
                book_id TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                order_index INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chapter_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_id TEXT NOT NULL REFERENCES chapters(id),
                content TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                saved_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chapters_book ON chapters(book_id, order_index);
            """
        )
        self._conn.commit()

    def upsert(self, book_id: str, title: str, content: str, order_index: int = 0) -> Chapter:
        """新建或覆盖一章；覆盖前把旧版存进版本历史。"""
        now = _now()
        existing = self._conn.execute(
            "SELECT id FROM chapters WHERE book_id = ? AND title = ?", (book_id, title)
        ).fetchone()
        if existing:
            cid = existing["id"]
            old = self._conn.execute("SELECT content FROM chapters WHERE id = ?", (cid,)).fetchone()
            with self._conn:
                self._conn.execute(
                    "INSERT INTO chapter_versions (chapter_id, content, note, saved_at) "
                    "VALUES (?, ?, '修改前', ?)",
                    (cid, old["content"], now),
                )
                self._conn.execute(
                    "UPDATE chapters SET content = ?, title = ?, order_index = ?, updated_at = ? "
                    "WHERE id = ?",
                    (content, title, order_index, now, cid),
                )
        else:
            cid = uuid.uuid4().hex
            with self._conn:
                self._conn.execute(
                    "INSERT INTO chapters (id, book_id, title, content, order_index, "
                    "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (cid, book_id, title, content, order_index, now, now),
                )
        return self.get(cid)  # type: ignore[return-value]

    def get(self, chapter_id: str) -> Chapter | None:
        row = self._conn.execute("SELECT * FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
        if not row:
            return None
        ver_rows = self._conn.execute(
            "SELECT content, note, saved_at FROM chapter_versions "
            "WHERE chapter_id = ? ORDER BY saved_at DESC",
            (chapter_id,),
        ).fetchall()
        versions = [
            {"content": v["content"], "note": v["note"], "saved_at": v["saved_at"]}
            for v in ver_rows
        ]
        return Chapter(
            id=row["id"],
            book_id=row["book_id"],
            title=row["title"],
            content=row["content"],
            order_index=row["order_index"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            versions=versions,
        )

    def list_by_book(self, book_id: str) -> list[Chapter]:
        rows = self._conn.execute(
            "SELECT id, title, content, order_index FROM chapters "
            "WHERE book_id = ? ORDER BY order_index",
            (book_id,),
        ).fetchall()
        return [
            Chapter(
                id=r["id"],
                book_id=book_id,
                title=r["title"],
                content=r["content"],
                order_index=r["order_index"],
                created_at="",
                updated_at="",
                versions=[],
            )
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()
