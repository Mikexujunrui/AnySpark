"""
anyspark.align.signals — 信号采集器（操作 → 结构化信号）。

设计（DESIGN 第 6 节）：对齐信号全部来自操作（选择/修改/删除/接受/反馈），
零打字成本。每次操作产生一个带类型的信号，供提炼器消费。
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

# 信号类型：用户操作语义
SignalKind = Literal[
    "accepted",  # 接受 AI 产出（未修改）
    "modified",  # 修改了 AI 产出（幅度小/大由 delta 表示）
    "deleted",  # 删除了 AI 产出/建议
    "rejected",  # 明确拒绝（"再来一批" / 否定）
    "custom",  # 用户自定规则/偏好陈述
    "locked",  # 用户锁定条目
]


@dataclass
class Signal:
    """一条对齐信号。"""

    kind: SignalKind
    content: str  # 自然语言描述（如被修改的文本、用户的话）
    context: str = ""  # 场景（如"探索选卡" / "稿纸改写"）
    delta: float = 0.0  # 修改幅度 0-1（kind=modified 时）
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    book_id: str = "main"
    created_at: str = field(default_factory=lambda: _now())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "content": self.content,
            "context": self.context,
            "delta": self.delta,
            "book_id": self.book_id,
            "created_at": self.created_at,
        }


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SignalStore:
    """信号存储（SQLite），供提炼器消费。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                context TEXT NOT NULL DEFAULT '',
                delta REAL NOT NULL DEFAULT 0,
                book_id TEXT NOT NULL DEFAULT 'main',
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def record(self, sig: Signal) -> Signal:
        with self._lock:
            self._conn.execute(
                "INSERT INTO signals (id, kind, content, context, delta, book_id, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    sig.id,
                    sig.kind,
                    sig.content,
                    sig.context,
                    sig.delta,
                    sig.book_id,
                    sig.created_at,
                ),
            )
            self._conn.commit()
        return sig

    def recent(self, limit: int = 50, book_id: str = "main") -> list[Signal]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM signals WHERE book_id=? ORDER BY rowid DESC LIMIT ?",
                (book_id, limit),
            ).fetchall()
        return [_signal_from_row(r) for r in rows]

    def close(self) -> None:
        self._conn.close()


def _signal_from_row(row: sqlite3.Row) -> Signal:
    return Signal(
        id=row["id"],
        kind=row["kind"],
        content=row["content"],
        context=row["context"],
        delta=row["delta"],
        book_id=row["book_id"],
        created_at=row["created_at"],
    )


class SignalCollector:
    """操作式信号采集器：把用户操作转换成对齐信号并入库。"""

    def __init__(self, store: SignalStore, book_id: str = "main") -> None:
        self._store = store
        self._book_id = book_id

    def accepted(self, content: str, context: str = "") -> Signal:
        return self._store.record(
            Signal(kind="accepted", content=content, context=context, book_id=self._book_id)
        )

    def modified(self, original: str, new: str, context: str = "") -> Signal:
        delta = _delta_ratio(original, new)
        return self._store.record(
            Signal(
                kind="modified",
                content=f"原文：{original[:200]}\n改为：{new[:200]}",
                context=context,
                delta=delta,
                book_id=self._book_id,
            )
        )

    def deleted(self, content: str, context: str = "") -> Signal:
        return self._store.record(
            Signal(kind="deleted", content=content[:200], context=context, book_id=self._book_id)
        )

    def rejected(self, content: str, context: str = "") -> Signal:
        return self._store.record(
            Signal(kind="rejected", content=content[:200], context=context, book_id=self._book_id)
        )

    def custom(self, statement: str, context: str = "") -> Signal:
        return self._store.record(
            Signal(kind="custom", content=statement, context=context, book_id=self._book_id)
        )


def _delta_ratio(a: str, b: str) -> float:
    """粗略的修改幅度（0-1）：字符级差异占比。"""
    if not a and not b:
        return 0.0
    if not a or not b:
        return 1.0
    longer, shorter = max(a, b, key=len), min(a, b, key=len)
    if not shorter:
        return 1.0
    # 简单编辑距离近似：逐字符匹配率
    n = sum(1 for x, y in zip(longer, shorter, strict=False) if x == y)
    return 1.0 - (n / max(len(longer), 1))
