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
        msgs = [
            Message(
                role=row["role"],
                content=row["content"],
                metadata=json.loads(row["metadata"] or "{}"),
            )
            for row in rows
        ]
        return self._heal_tool_pairs(msgs, conversation_id)

    def _load_recorder_tool_index(self, conversation_id: str) -> dict[str, Any] | None:
        """S158h：从 S49 recorder（data/records/<conv>/events.jsonl）建立工具配对索引。

        recorder 每轮 record 事件含完整 prompt 快照（assistant 声明 + tool 消息的
        metadata）——前端覆盖写损坏的配对信息可从此恢复，而不是直接丢弃。
        返回 {"tool_by_content": {content: tool_call_id}, "decl_by_id": {id: Message}}。
        """
        from anyspark.core import Message as CoreMessage

        rec = Path(self._db).parent / "records" / conversation_id / "events.jsonl"
        if not rec.exists():
            return None
        tool_by_content: dict[str, str] = {}
        decl_by_id: dict[str, CoreMessage] = {}
        try:
            with rec.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        e = json.loads(line)
                    except Exception:
                        continue
                    if e.get("event") != "record":
                        continue
                    for m in e.get("prompt") or []:
                        role = m.get("role")
                        md = m.get("metadata") or {}
                        content = m.get("content") or ""
                        if role == "tool" and md.get("tool_call_id"):
                            tool_by_content.setdefault(content, str(md["tool_call_id"]))
                        elif role == "assistant" and md.get("tool_calls"):
                            for tc in md["tool_calls"]:
                                if isinstance(tc, dict) and tc.get("id"):
                                    decl_by_id.setdefault(
                                        str(tc["id"]),
                                        CoreMessage(
                                            role="assistant",
                                            content="",
                                            metadata={"tool_calls": [tc]},
                                        ),
                                    )
        except Exception:
            return None
        return {"tool_by_content": tool_by_content, "decl_by_id": decl_by_id}

    def _heal_tool_pairs(self, msgs: list[Message], conversation_id: str = "") -> list[Message]:
        """S158d：加载时自愈——tool 消息缺 tool_call_id / 声明缺失时：

        ① 优先从 S49 recorder（每轮完整快照）恢复配对信息（S158h）——
        前端覆盖写损坏的 metadata/声明可找回，旧轮工具细节不丢；
        ② 恢复不了才从相邻声明补配/丢弃（防 OpenAI 协议 400）。
        幂等无副作用（不改库，每次读取修复内存返回）。
        """
        from collections import deque

        rec_index: dict[str, Any] | None = None
        decl_ids: deque[str] = deque()
        out: list[Message] = []
        for m in msgs:
            if m.role == "assistant" and m.metadata.get("tool_calls"):
                for tc in m.metadata["tool_calls"]:
                    tid = str(tc.get("id") or "") if isinstance(tc, dict) else ""
                    if tid:
                        decl_ids.append(tid)
                out.append(m)
            elif m.role == "tool":
                tid = str(m.metadata.get("tool_call_id") or "")
                if tid:
                    # 有 tool_call_id 且对应声明在 → 正常配对，从队列移除
                    if tid in decl_ids:
                        decl_ids.remove(tid)
                        out.append(m)
                        continue
                    # 有 id 但无对应声明 → 尝试从 recorder 找回声明（S158h）
                    if rec_index is None:
                        rec_index = self._load_recorder_tool_index(conversation_id)
                    decl = (rec_index or {}).get("decl_by_id", {}).get(tid)
                    if decl is not None and tid not in decl_ids:
                        decl_ids.append(tid)
                        out.append(decl)
                        decl_ids.remove(tid)
                        out.append(m)
                        continue
                    # 声明彻底丢失 → 孤儿 tool 丢弃（保留会 400）
                    continue
                # 缺 tool_call_id：优先从 recorder 恢复 id + 声明（S158h）
                if rec_index is None:
                    rec_index = self._load_recorder_tool_index(conversation_id)
                rid = (rec_index or {}).get("tool_by_content", {}).get(m.content or "")
                if rid:
                    decl = (rec_index or {}).get("decl_by_id", {}).get(rid)
                    md = dict(m.metadata)
                    md["tool_call_id"] = rid
                    recovered = Message(role=m.role, content=m.content, metadata=md)
                    if decl is not None and rid not in decl_ids:
                        decl_ids.append(rid)
                        out.append(decl)
                        decl_ids.remove(rid)
                    out.append(recovered)
                    continue
                # 从相邻未配对声明补（保持声明→tool 顺序）
                if decl_ids:
                    md2 = dict(m.metadata)
                    md2["tool_call_id"] = decl_ids.popleft()
                    out.append(Message(role=m.role, content=m.content, metadata=md2))
                else:
                    # 孤儿 tool（无配对声明）→ 丢弃（保留会触发 400；内容已在展示层）
                    continue
            else:
                out.append(m)
        # S169：裁剪悬挂声明——assistant 声明了 tool_calls 但后续无对应 tool 消息
        # （运行中取消/钩子异常/前端覆盖写中断遗留）。保留会让 OpenAI 协议报 400
        # （insufficient tool messages following tool_calls）；把未配对 id 从声明中
        # 移除（内存级修复，不改库；tool 侧已在前述逻辑配对/丢弃）。
        if decl_ids:
            dangling = set(decl_ids)
            out = [
                self._strip_dangling_decls(m, dangling) if m.role == "assistant" else m for m in out
            ]
        return out

    @staticmethod
    def _strip_dangling_decls(m: Message, dangling: set[str]) -> Message:
        """S169：从 assistant 声明的 tool_calls 中移除未配对 id（返回新 Message）。"""
        calls = m.metadata.get("tool_calls")
        if not isinstance(calls, list) or not calls:
            return m
        kept = [
            tc for tc in calls if isinstance(tc, dict) and str(tc.get("id") or "") not in dangling
        ]
        if len(kept) == len(calls):
            return m
        md = dict(m.metadata)
        if kept:
            md["tool_calls"] = kept
        else:
            md.pop("tool_calls", None)
        return Message(role=m.role, content=m.content, metadata=md)

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
