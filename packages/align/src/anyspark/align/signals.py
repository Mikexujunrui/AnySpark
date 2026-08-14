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

from anyspark.core.db import connect as sqlite_connect

# 信号类型：用户操作语义
SignalKind = Literal[
    "accepted",  # 接受 AI 产出（未修改）
    "modified",  # 修改了 AI 产出（幅度小/大由 delta 表示）
    "deleted",  # 删除了 AI 产出/建议
    "rejected",  # 明确拒绝（"再来一批" / 否定）
    "custom",  # 用户自定规则/偏好陈述
    "locked",  # 用户锁定条目
    "negative",  # S53c 实时负例：用户明确否定/撤回（"不要破折号"）——即时捕获防稀释
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
        # S79：连接配置收敛到 anyspark.core.db.connect
        self._conn = sqlite_connect(self._db)
        self._lock = threading.Lock()
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                context TEXT NOT NULL DEFAULT '',
                delta REAL NOT NULL DEFAULT 0,
                book_id TEXT NOT NULL DEFAULT 'main',
                created_at TEXT NOT NULL,
                processed INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # 兼容旧库：已有 signals 表缺 processed 列时补列（增量游标，DESIGN §12.18 长会话标准重定）
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(signals)")}
        if "processed" not in cols:
            self._conn.execute(
                "ALTER TABLE signals ADD COLUMN processed INTEGER NOT NULL DEFAULT 0"
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

    def unprocessed(self, limit: int = 20, book_id: str = "main") -> list[Signal]:
        """取未提炼信号（增量游标：按 rowid 升序=时间序，最早未提炼先处理）。

        S7x 长会话标准重定（DESIGN §12.18）：不再用 recent() 滑动窗口——
        长会话早期信号会被挤掉导致早期偏好丢失；改为 processed 标记推进，
        与模型上下文窗口解耦（64K 还是 1M 都成立）。
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM signals WHERE book_id=? AND processed=0 "
                "ORDER BY rowid ASC LIMIT ?",
                (book_id, limit),
            ).fetchall()
        return [_signal_from_row(r) for r in rows]

    def mark_processed(self, ids: list[str]) -> None:
        """批量标记已提炼（游标推进）。不存在的 id 静默忽略（幂等）。"""
        if not ids:
            return
        with self._lock:
            self._conn.executemany(
                "UPDATE signals SET processed=1 WHERE id=?", [(i,) for i in ids]
            )
            self._conn.commit()

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

    def negative(self, statement: str, context: str = "") -> Signal:
        """S53c 实时负例：用户明确否定/撤回（如"不要破折号""我说了不用这个词"）。

        即时捕获（不等轮末提炼），防隐式否定被上下文稀释丢失。
        内容 = 用户原话（自然语言），后续由 NegativeCapture 落雷区条目。
        """
        return self._store.record(
            Signal(kind="negative", content=statement[:200], context=context, book_id=self._book_id)
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
