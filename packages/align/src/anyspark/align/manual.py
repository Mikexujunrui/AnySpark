"""
anyspark.align.manual — 说明书（对齐的载体）：数据模型 + SQLite 存储。

条目元数据（DESIGN 第 6 节）：
    内容（自然语言短句）+ 来源(自动提炼|用户手写) + 置信度(0-1) + 活跃度(高|中|低) + 锁定状态
分层：项目说明书（每本书，主体）/ 全局说明书（用户级，极小化）
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

# 条目来源 / 活跃度
Source = Literal["auto", "user"]
Activity = Literal["high", "medium", "low"]
# 条目类别（S50 心智分类：协作=怎么配合/文风=怎么写/习惯=行为习惯）
# 心智模型=会话规划器：协作类指导主循环装配，文风/习惯类不再注入写作工具
Category = Literal["collab", "style", "habit"]
# 说明书层级
Scope = Literal["project", "global"]


@dataclass
class ManualEntry:
    """说明书的一条条目。"""

    content: str
    source: Source = "auto"
    confidence: float = 0.5
    activity: Activity = "medium"
    locked: bool = False
    scope: Scope = "project"
    book_id: str = "main"  # scope=global 时忽略
    category: Category = "style"  # S50：collab(协作)/style(文风)/habit(习惯)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=lambda: _now())
    updated_at: str = field(default_factory=lambda: _now())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "source": self.source,
            "confidence": self.confidence,
            "activity": self.activity,
            "locked": self.locked,
            "scope": self.scope,
            "book_id": self.book_id,
            "category": self.category,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ManualStore:
    """说明书存储（SQLite）：项目级 + 全局级条目。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS manual_entries (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'auto',
                    confidence REAL NOT NULL DEFAULT 0.5,
                    activity TEXT NOT NULL DEFAULT 'medium',
                    locked INTEGER NOT NULL DEFAULT 0,
                    scope TEXT NOT NULL DEFAULT 'project',
                    book_id TEXT NOT NULL DEFAULT 'main',
                    category TEXT NOT NULL DEFAULT 'style',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            # S50 ALTER 兼容：旧库无 category 列则补（默认 style 文风）
            cols = {r[1] for r in self._conn.execute("PRAGMA table_info(manual_entries)")}
            if "category" not in cols:
                self._conn.execute(
                    "ALTER TABLE manual_entries ADD COLUMN category TEXT NOT NULL DEFAULT 'style'"
                )
            self._conn.commit()

    def add(self, entry: ManualEntry) -> ManualEntry:
        with self._lock:
            self._conn.execute(
                "INSERT INTO manual_entries (id, content, source, confidence, activity, "
                "locked, scope, book_id, category, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    entry.id,
                    entry.content,
                    entry.source,
                    entry.confidence,
                    entry.activity,
                    1 if entry.locked else 0,
                    entry.scope,
                    entry.book_id,
                    entry.category,
                    entry.created_at,
                    entry.updated_at,
                ),
            )
            self._conn.commit()
        return entry

    def list(self, scope: Scope, book_id: str = "main") -> list[ManualEntry]:
        with self._lock:
            if scope == "project":
                rows = self._conn.execute(
                    "SELECT * FROM manual_entries WHERE scope='project' AND book_id=? "
                    "ORDER BY confidence DESC, updated_at DESC",
                    (book_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM manual_entries WHERE scope='global' "
                    "ORDER BY confidence DESC, updated_at DESC"
                ).fetchall()
        return [_entry_from_row(r) for r in rows]

    def get(self, entry_id: str) -> ManualEntry | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM manual_entries WHERE id=?", (entry_id,)
            ).fetchone()
        return _entry_from_row(row) if row else None

    def update(
        self,
        entry_id: str,
        content: str | None = None,
        confidence: float | None = None,
        category: str | None = None,
    ) -> ManualEntry | None:
        """更新条目内容/置信度/类别（锁定条目不可改，用户主权）。"""
        entry = self.get(entry_id)
        if entry is None:
            return None
        if entry.locked:
            return entry
        with self._lock:
            sets: list[str] = []
            params: list[Any] = []
            if content is not None:
                sets.append("content=?")
                params.append(content)
            if confidence is not None:
                sets.append("confidence=?")
                params.append(confidence)
            if category is not None and category in ("collab", "style", "habit"):
                sets.append("category=?")
                params.append(category)
            sets.append("updated_at=?")
            params.append(_now())
            params.append(entry_id)
            self._conn.execute(f"UPDATE manual_entries SET {', '.join(sets)} WHERE id=?", params)
            self._conn.commit()
        return self.get(entry_id)

    def set_locked(self, entry_id: str, locked: bool) -> ManualEntry | None:
        with self._lock:
            self._conn.execute(
                "UPDATE manual_entries SET locked=?, updated_at=? WHERE id=?",
                (1 if locked else 0, _now(), entry_id),
            )
            self._conn.commit()
        return self.get(entry_id)

    def delete(self, entry_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM manual_entries WHERE id=?", (entry_id,))
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def _entry_from_row(row: sqlite3.Row) -> ManualEntry:
    return ManualEntry(
        id=row["id"],
        content=row["content"],
        source=row["source"],
        confidence=row["confidence"],
        activity=row["activity"],
        locked=bool(row["locked"]),
        scope=row["scope"],
        book_id=row["book_id"],
        category=row["category"],  # S50
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def render_manual(entries: list[ManualEntry], title: str = "写作说明书") -> str:
    """把条目渲染成可读的自然语言文档（跨模型可读，注入上下文用）。"""
    lines = [
        f"# {title}",
        "",
        "使用说明：以下为作者写作偏好/约束条目，写作时必须遵守；"
        "带 [锁定] 的条目为作者确认的硬规则，不得违反。",
    ]
    if not entries:
        lines.append("（暂无条目）")
    for e in entries:
        tag = " [锁定]" if e.locked else ""
        source_tag = "自动提炼" if e.source == "auto" else "作者手写"
        lines.append(f"- {e.content}{tag}（{source_tag}，置信度 {e.confidence:.1f}）")
    return "\n".join(lines)
