"""
anyspark.align.summarize — 摘要器（对话 → 场景记忆 → 项目档案）。

设计（DESIGN 第 6 节）：双轨提炼之一。摘要器把会话摘要成"场景记忆"
（发生了什么/进行到哪/做过哪些决定），写入项目档案，承担跨会话延续性。
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anyspark.core import Message

SUMMARIZE_PROMPT = """你是小说写作协作系统的会话摘要器。把下面这段对话摘要成**场景记忆**，
供下一轮会话续接使用。要求：
1. 覆盖：发生了什么 / 写作进行到哪 / 做过哪些决定（方向、设定、偏好确认）。
2. 用明确无歧义的自然语言，一段话以内。
3. 只写事实与决定，不写空话。

对话：
"""


@dataclass
class SceneMemory:
    """一次会话结束后的场景记忆（项目档案的延续性载体）。"""

    content: str
    book_id: str = "main"
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=lambda: _now())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "book_id": self.book_id,
            "created_at": self.created_at,
        }


def _now() -> str:
    return datetime.now(UTC).isoformat()


class MemoryStore:
    """场景记忆存储（SQLite）：项目档案的延续性层。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scene_memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                book_id TEXT NOT NULL DEFAULT 'main',
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def save(self, memory: SceneMemory) -> SceneMemory:
        with self._lock:
            self._conn.execute(
                "INSERT INTO scene_memories (id, content, book_id, created_at) VALUES (?,?,?,?)",
                (memory.id, memory.content, memory.book_id, memory.created_at),
            )
            self._conn.commit()
        return memory

    def latest(self, book_id: str = "main") -> SceneMemory | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM scene_memories WHERE book_id=? ORDER BY created_at DESC LIMIT 1",
                (book_id,),
            ).fetchone()
        if not row:
            return None
        return SceneMemory(
            id=row["id"],
            content=row["content"],
            book_id=row["book_id"],
            created_at=row["created_at"],
        )

    def list(self, book_id: str = "main", limit: int = 10) -> list[SceneMemory]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM scene_memories WHERE book_id=? ORDER BY created_at DESC LIMIT ?",
                (book_id, limit),
            ).fetchall()
        return [
            SceneMemory(
                id=r["id"], content=r["content"], book_id=r["book_id"], created_at=r["created_at"]
            )
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()


class SessionSummarizer:
    """会话摘要器：真实 LLM 把对话压成场景记忆并入库。"""

    def __init__(self, model: object, store: MemoryStore) -> None:
        self._model = model
        self._store = store

    def summarize(self, messages: list[Message], book_id: str = "main") -> SceneMemory:
        dialogue = "\n".join(f"{m.role}: {m.content[:300]}" for m in messages[-30:]) or "（空会话）"
        prompt = SUMMARIZE_PROMPT + dialogue
        output = self._model.respond(  # type: ignore[attr-defined]
            [Message(role="system", content=prompt)],
            [],
        )
        content = output.text.strip()
        if not content:
            content = "（本次会话无可摘要内容）"
        memory = SceneMemory(content=content, book_id=book_id)
        return self._store.save(memory)
