"""
anyspark.explore.direction — 方向卡模型 + 项目档案固化。

方向卡：探索者产出的候选方向（带术语标注/三来源），用户判别选择。
项目档案：固化选中方向与已固化设定约束（探索自由但不得撞墙）。
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

# 方向来源（三来源混合场）
Source = Literal["template", "grow", "user"]
# 探索维度（默认）
DIMENSIONS = ["情节驱动", "角色驱动", "氛围驱动", "结构实验", "文笔质感", "用户指导"]


@dataclass
class DirectionCard:
    """一张方向卡：候选方向（带术语标注），用户判别。"""

    title: str
    summary: str  # 方向说明（自然语言）
    dimension: str  # 探索维度
    source: Source  # 来源
    term: str = ""  # 流派术语标注（如"废柴流开局·反差铺垫"）
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "dimension": self.dimension,
            "source": self.source,
            "term": self.term,
        }


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ProjectArchive:
    """项目档案：固化已选方向 + 已固化设定约束（跨会话记忆）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS archived_directions (
                id TEXT PRIMARY KEY,
                book_id TEXT NOT NULL DEFAULT 'main',
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                dimension TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'user',
                term TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS setting_constraints (
                id TEXT PRIMARY KEY,
                book_id TEXT NOT NULL DEFAULT 'main',
                content TEXT NOT NULL,  -- 一句级设定约束（如：女主=医者）
                created_at TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    # -- 方向固化 --
    def archive_direction(self, card: DirectionCard, book_id: str = "main") -> dict[str, Any]:
        with self._lock:
            self._conn.execute(
                "INSERT INTO archived_directions "
                "(id, book_id, title, summary, dimension, source, term, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    card.id,
                    book_id,
                    card.title,
                    card.summary,
                    card.dimension,
                    card.source,
                    card.term,
                    _now(),
                ),
            )
            self._conn.commit()
        return card.to_dict()

    def directions(self, book_id: str = "main") -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM archived_directions WHERE book_id=? ORDER BY rowid DESC",
                (book_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- 设定约束固化 --
    def add_constraint(self, content: str, book_id: str = "main") -> dict[str, Any]:
        cid = uuid.uuid4().hex
        with self._lock:
            self._conn.execute(
                "INSERT INTO setting_constraints (id, book_id, content, created_at) "
                "VALUES (?,?,?,?)",
                (cid, book_id, content, _now()),
            )
            self._conn.commit()
        return {"id": cid, "content": content, "book_id": book_id}

    def constraints(self, book_id: str = "main") -> list[str]:
        """已固化设定约束（一句级），探索者必须避开这些墙。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT content FROM setting_constraints WHERE book_id=? ORDER BY rowid",
                (book_id,),
            ).fetchall()
        return [r["content"] for r in rows]

    def close(self) -> None:
        self._conn.close()
