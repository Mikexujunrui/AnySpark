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

from anyspark.core import Conversation, ConversationStore, Message


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _conversation_from_row(row: tuple[Any, ...]) -> Conversation:
    # 兼容旧库：可能只有 (id, created_at)，也可能是 (id, created_at, parent_id, fork_point, title)
    cid, created_at = row[0], row[1]
    parent_id = row[2] if len(row) > 2 else None
    fork_point = row[3] if len(row) > 3 else ""
    title = row[4] if len(row) > 4 else ""
    return Conversation(
        id=cid, created_at=created_at, parent_id=parent_id, fork_point=fork_point, title=title
    )


class SqliteConversationStore(ConversationStore):
    """SQLite 实现的会话存储（会话 + 消息）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        parent = Path(self._db).parent
        parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False：嵌入式 SQLite 供 FastAPI 多线程 endpoint 共用
        # S75：WAL + timeout=30（前端报告并发锁：多 store 独立连接竞争；WAL 允许读写并发，
        # busy_timeout 防 delete 未提交时其他写阻塞）
        self._conn = sqlite3.connect(self._db, check_same_thread=False, timeout=30)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                parent_id TEXT,  -- S58c 继承链条：源会话 id（继承自谁）
                fork_point TEXT NOT NULL DEFAULT '',  -- S58c 继承来源描述（自然语言）
                title TEXT NOT NULL DEFAULT ''  -- 会话标题
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
        # 旧库兼容（S58c）：补 parent_id / fork_point 列
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(conversations)")}
        if "parent_id" not in cols:
            self._conn.execute("ALTER TABLE conversations ADD COLUMN parent_id TEXT")
        if "fork_point" not in cols:
            self._conn.execute(
                "ALTER TABLE conversations ADD COLUMN fork_point TEXT NOT NULL DEFAULT ''"
            )
        if "title" not in cols:
            self._conn.execute(
                "ALTER TABLE conversations ADD COLUMN title TEXT NOT NULL DEFAULT ''"
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
        return self.get(cid) or Conversation(id=cid, created_at=now)

    def get(self, conversation_id: str) -> Conversation | None:
        row = self._conn.execute(
            "SELECT id, created_at, parent_id, fork_point, title FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        return _conversation_from_row(row) if row else None

    def list_conversations(self) -> list[Conversation]:
        rows = self._conn.execute(
            "SELECT id, created_at, parent_id, fork_point, title "
            "FROM conversations ORDER BY created_at"
        ).fetchall()
        return [_conversation_from_row(row) for row in rows]

    def save(self, conversation: Conversation) -> None:
        """更新会话元信息（title/parent_id/fork_point）。"""
        with self._conn:
            self._conn.execute(
                "UPDATE conversations SET title=?, parent_id=?, fork_point=? WHERE id=?",
                (
                    conversation.title,
                    conversation.parent_id,
                    conversation.fork_point,
                    conversation.id,
                ),
            )

    def delete(self, conversation_id: str) -> bool:
        """删除会话及其所有消息。"""
        with self._conn:
            self._conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            cur = self._conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        return cur.rowcount > 0

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

    def fork(
        self, conversation_id: str, fork_point: str = "", inherit_messages: bool = True
    ) -> Conversation | None:
        """S58c 继承派生（参考 pi forkFrom：新会话记 parent + 复制源内容）。

        创建新会话，parent_id=源会话（链条可追溯），fork_point=继承来源描述；
        inherit_messages=True 时把源会话全部消息复制为新会话起始上下文
        （新会话"接着上次聊"，参考 pi 全量复制语义）。源不存在返回 None。
        """
        src = self.get(conversation_id)
        if src is None:
            return None
        new_conv = self.create()
        with self._conn:
            self._conn.execute(
                "UPDATE conversations SET parent_id=?, fork_point=? WHERE id=?",
                (conversation_id, fork_point, new_conv.id),
            )
        if inherit_messages:
            for m in self.messages(conversation_id):
                self.append(new_conv.id, m)
        return self.get(new_conv.id)

    def replace_messages(self, conversation_id: str, messages: list[Message]) -> None:
        """S26：整体替换该会话消息（压缩回写，事务内删旧插新，seq 从 0 重排）。
        会话不存在则先创建。"""
        self.get(conversation_id) or self.create(conversation_id)
        with self._conn:
            self._conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            for seq, m in enumerate(messages):
                self._conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, metadata, seq, "
                    "created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        conversation_id,
                        m.role,
                        m.content,
                        json.dumps(m.metadata, ensure_ascii=False),
                        seq,
                        _now(),
                    ),
                )

    def recent_messages(self, limit: int = 10) -> list[Message]:
        """S28：跨会话最近消息（按全局 id 倒序）——信号提炼的对话上下文。
        返回保序（最旧在前）。"""
        rows = self._conn.execute(
            "SELECT role, content, metadata FROM messages ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            Message(
                role=row["role"],
                content=row["content"],
                metadata=json.loads(row["metadata"] or "{}"),
            )
            for row in reversed(rows)
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
    narrative_line: str = "main"  # S29 多线叙事：本章属于哪条线（时序校验按线比较）


class ChapterStore:
    """SQLite 章节存储：正文 + 版本历史（修改可追溯）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        # S75：WAL + timeout=30（同会话 store：并发锁加固）
        self._conn = sqlite3.connect(self._db, check_same_thread=False, timeout=30)
        self._conn.execute("PRAGMA journal_mode=WAL")
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
                narrative_line TEXT NOT NULL DEFAULT 'main',
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
        # S29 旧库兼容：narrative_line 列
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(chapters)")}
        if "narrative_line" not in cols:
            self._conn.execute(
                "ALTER TABLE chapters ADD COLUMN narrative_line TEXT NOT NULL DEFAULT 'main'"
            )
        self._conn.commit()

    def upsert(
        self,
        book_id: str,
        title: str,
        content: str,
        order_index: int = 0,
        narrative_line: str = "main",
    ) -> Chapter:
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
                    "UPDATE chapters SET content = ?, title = ?, order_index = ?, "
                    "narrative_line = ?, updated_at = ? WHERE id = ?",
                    (content, title, order_index, narrative_line, now, cid),
                )
        else:
            cid = uuid.uuid4().hex
            with self._conn:
                self._conn.execute(
                    "INSERT INTO chapters (id, book_id, title, content, order_index, "
                    "narrative_line, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (cid, book_id, title, content, order_index, narrative_line, now, now),
                )
        return self.get(cid)  # type: ignore[return-value]

    def get(self, chapter_id: str) -> Chapter | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM chapters WHERE id = ?", (chapter_id,)
            ).fetchone()
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
        with self._lock:
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

    def delete(self, chapter_id: str) -> bool:
        """删除章节及其版本历史（前端章节树管理用；md 文件删除由调用方负责）。

        S75：补 commit（前端报告并发锁根因——DELETE 事务不提交则锁持续持有，
        后续写请求 500 database is locked）。
        """
        with self._lock:
            cur = self._conn.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))
            self._conn.execute("DELETE FROM chapter_versions WHERE chapter_id = ?", (chapter_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()
