"""
anyspark.store.sqlite — SQLite 持久化存储：会话 + 章节（真实落盘）。

实现 core 的 ConversationStore 接口（实现可换），并额外提供章节/版本存储。
数据库文件默认放 data/anyspark.db（data/ 已 gitignore，绝不入库）。
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anyspark.core import Conversation, ConversationStore, Message
from anyspark.core.db import connect as sqlite_connect


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _conversation_from_row(row: tuple[Any, ...]) -> Conversation:
    # 兼容旧库：可能 (id, created_at) / (+parent_id, fork_point, title) / (+book_id)
    cid, created_at = row[0], row[1]
    parent_id = row[2] if len(row) > 2 else None
    fork_point = row[3] if len(row) > 3 else ""
    title = row[4] if len(row) > 4 else ""
    book_id = row[5] if len(row) > 5 else "main"
    return Conversation(
        id=cid,
        created_at=created_at,
        parent_id=parent_id,
        fork_point=fork_point,
        title=title,
        book_id=book_id,
    )


class SqliteConversationStore(ConversationStore):
    """SQLite 实现的会话存储（会话 + 消息）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        # S79：连接配置收敛到 anyspark.core.db.connect（WAL/timeout/多线程一处定义）
        self._conn = sqlite_connect(self._db)
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                parent_id TEXT,  -- S58c 继承链条：源会话 id（继承自谁）
                fork_point TEXT NOT NULL DEFAULT '',  -- S58c 继承来源描述（自然语言）
                title TEXT NOT NULL DEFAULT '',  -- 会话标题
                book_id TEXT NOT NULL DEFAULT 'main'  -- S80：会话绑定项目
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
        if "book_id" not in cols:
            self._conn.execute(
                "ALTER TABLE conversations ADD COLUMN book_id TEXT NOT NULL DEFAULT 'main'"
            )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def create(self, conversation_id: str | None = None, book_id: str = "main") -> Conversation:
        cid = conversation_id or uuid.uuid4().hex
        now = _now()
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO conversations (id, created_at, book_id) VALUES (?, ?, ?)",
                (cid, now, book_id),
            )
        return self.get(cid) or Conversation(id=cid, created_at=now, book_id=book_id)

    def get(self, conversation_id: str) -> Conversation | None:
        row = self._conn.execute(
            "SELECT id, created_at, parent_id, fork_point, title, book_id "
            "FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        return _conversation_from_row(row) if row else None

    def list_conversations(self, book_id: str | None = None) -> list[Conversation]:
        """S80：会话列表；book_id=None 返回全部（兼容），传了按项目过滤。"""
        if book_id is None:
            rows = self._conn.execute(
                "SELECT id, created_at, parent_id, fork_point, title, book_id "
                "FROM conversations ORDER BY created_at"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, created_at, parent_id, fork_point, title, book_id "
                "FROM conversations WHERE book_id=? ORDER BY created_at",
                (book_id,),
            ).fetchall()
        return [_conversation_from_row(row) for row in rows]

    def save(self, conversation: Conversation) -> None:
        """更新会话元信息（title/parent_id/fork_point/book_id）。"""
        with self._conn:
            self._conn.execute(
                "UPDATE conversations SET title=?, parent_id=?, fork_point=?, book_id=? WHERE id=?",
                (
                    conversation.title,
                    conversation.parent_id,
                    conversation.fork_point,
                    conversation.book_id,
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

    def last_user_message_time(self, conversation_id: str) -> str | None:
        """S154（会话回滚）：最后一条 user 消息时间（本轮起点 t0）。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT created_at FROM messages WHERE conversation_id = ? AND role = 'user' "
                "ORDER BY seq DESC LIMIT 1",
                (conversation_id,),
            ).fetchone()
        return str(row["created_at"]) if row else None

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
        new_conv = self.create(book_id=src.book_id)  # S80：fork 继承源会话的项目归属
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
        # S79：连接配置收敛到 anyspark.core.db.connect
        self._conn = sqlite_connect(self._db)
        self._lock = threading.Lock()
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

    def next_order(self, book_id: str) -> int:
        """S152j：原子分配下一章节序号（MAX+1，锁内）——两会话并发新建不再撞序。

        此前调用方各自 `max(order)+1` / `len(all_chapters)` 非原子，并发同序。
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(order_index), -1) AS mx FROM chapters WHERE book_id = ?",
                (book_id,),
            ).fetchone()
            return int(row["mx"]) + 1

    def upsert(
        self,
        book_id: str,
        title: str,
        content: str,
        order_index: int = 0,
        narrative_line: str = "main",
        note: str = "修改前",
    ) -> Chapter:
        """新建或覆盖一章；覆盖前把旧版存进版本历史。

        note（S138 回溯安全网 B1）：版本来源标识，默认 '修改前'；批量任务/工作流
        可传来源（如 '批量改写/任务{task_id}'）供批级回滚按来源聚合定位。
        S152j：全程锁内——读-改-写原子（此前开头 SELECT 无锁，并发共享连接崩溃）；
        新建时若 order 已被其他章占用（并发取号撞序）自动顺延到空闲序号。
        """
        now = _now()
        with self._lock:
            existing = self._conn.execute(
                "SELECT id FROM chapters WHERE book_id = ? AND title = ?", (book_id, title)
            ).fetchone()
            if existing:
                cid = existing["id"]
                old = self._conn.execute(
                    "SELECT content FROM chapters WHERE id = ?", (cid,)
                ).fetchone()
                with self._conn:
                    self._conn.execute(
                        "INSERT INTO chapter_versions (chapter_id, content, note, saved_at) "
                        "VALUES (?, ?, ?, ?)",
                        (cid, old["content"], note, now),
                    )
                    self._conn.execute(
                        "UPDATE chapters SET content = ?, title = ?, order_index = ?, "
                        "narrative_line = ?, updated_at = ? WHERE id = ?",
                        (content, title, order_index, narrative_line, now, cid),
                    )
            else:
                cid = uuid.uuid4().hex
                with self._conn:
                    # 并发新建防撞序：同项目已有章节占用的 order 顺延到空闲（锁内判定）
                    occupied = {
                        r["order_index"]
                        for r in self._conn.execute(
                            "SELECT order_index FROM chapters WHERE book_id = ?",
                            (book_id,),
                        )
                    }
                    while order_index in occupied:
                        order_index += 1
                    self._conn.execute(
                        "INSERT INTO chapters (id, book_id, title, content, order_index, "
                        "narrative_line, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (cid, book_id, title, content, order_index, narrative_line, now, now),
                    )
        return self.get(cid)  # type: ignore[return-value]

    def restore_version(self, chapter_id: str, version_id: int) -> Chapter | None:
        """S138（回溯安全网 B2）：把章节恢复到指定历史版本。

        当前内容先入版本历史（note='恢复前'，可再回滚），目标版本内容写回当前。
        返回恢复后的 Chapter；版本不存在返回 None。
        """
        with self._lock:
            ver = self._conn.execute(
                "SELECT id, content FROM chapter_versions WHERE id = ? AND chapter_id = ?",
                (version_id, chapter_id),
            ).fetchone()
            if ver is None:
                return None
            cur = self._conn.execute(
                "SELECT content FROM chapters WHERE id = ?", (chapter_id,)
            ).fetchone()
            now = _now()
            with self._conn:
                if cur is not None:
                    self._conn.execute(
                        "INSERT INTO chapter_versions (chapter_id, content, note, saved_at) "
                        "VALUES (?, ?, '恢复前', ?)",
                        (chapter_id, cur["content"], now),
                    )
                self._conn.execute(
                    "UPDATE chapters SET content = ?, updated_at = ? WHERE id = ?",
                    (ver["content"], now, chapter_id),
                )
        return self.get(chapter_id)

    def find_versions_by_note(self, note_fragment: str) -> list[dict[str, Any]]:
        """S138（回溯安全网 B3）：按版本 note 来源片段查历史版本。

        批级回滚用：批量任务写回时 note 带任务标识（如 '批量改写/任务{task_id}'），
        按片段聚合可定位该任务改过的所有章节改前快照（按 saved_at 升序取最早=任务
        首次覆盖前状态）。返回 [{id, chapter_id, content, note, saved_at}]。
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, chapter_id, content, note, saved_at FROM chapter_versions "
                "WHERE note LIKE ? ORDER BY saved_at ASC",
                (f"%{note_fragment}%",),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "chapter_id": r["chapter_id"],
                "content": r["content"],
                "note": r["note"],
                "saved_at": r["saved_at"],
            }
            for r in rows
        ]

    def versions_after(self, book_id: str, t0: str) -> list[str]:
        """S154（会话回滚）：t0 之后有过版本记录的章节 id（回滚候选）。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT v.chapter_id AS cid FROM chapter_versions v "
                "JOIN chapters c ON c.id = v.chapter_id "
                "WHERE c.book_id = ? AND v.saved_at >= ?",
                (book_id, t0),
            ).fetchall()
        return [str(r["cid"]) for r in rows]

    def first_version_after(self, chapter_id: str, t0: str) -> dict[str, Any] | None:
        """S154（会话回滚）：saved_at >= t0 的第一条版本 = 本轮第一次覆盖存的旧版。

        版本表语义：每次 upsert 覆盖前把旧版存入 chapter_versions。因此
        saved >= t0 最早一条 = 本轮第一次修改前的状态（即 t0 时章节内容）——
        回滚目标。本轮新建章节（无版本记录）返回 None（保守不动）。
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT id, content FROM chapter_versions "
                "WHERE chapter_id = ? AND saved_at >= ? "
                "ORDER BY saved_at ASC, id ASC LIMIT 1",
                (chapter_id, t0),
            ).fetchone()
        if row is None:
            return None
        return {"id": row["id"], "content": row["content"]}

    def get(self, chapter_id: str) -> Chapter | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM chapters WHERE id = ?", (chapter_id,)
            ).fetchone()
            if not row:
                return None
            ver_rows = self._conn.execute(
                "SELECT id, content, note, saved_at FROM chapter_versions "
                "WHERE chapter_id = ? ORDER BY saved_at DESC",
                (chapter_id,),
            ).fetchall()
            versions = [
                {
                    "id": v["id"],
                    "content": v["content"],
                    "note": v["note"],
                    "saved_at": v["saved_at"],
                }
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
