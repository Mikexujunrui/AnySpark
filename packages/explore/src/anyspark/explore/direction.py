"""
anyspark.explore.direction — 方向卡模型 + 项目档案固化。

方向卡：探索者产出的候选方向（带术语标注/三来源），用户判别选择。
项目档案：固化选中方向（探索自由但约束由设定档提供）。
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from anyspark.core.db import connect as sqlite_connect

# 方向来源（三来源混合场）
Source = Literal["template", "grow", "user"]
# 探索维度默认种子（S50 内容化：可增删改，不再硬编码锁死）
DEFAULT_DIMENSIONS: list[str] = [
    "情节驱动",
    "角色驱动",
    "氛围驱动",
    "结构实验",
    "文笔质感",
    "用户指导",
]


class DimensionStore:
    """探索维度存储（SQLite，内容层：维度=可编辑内容，非硬编码常量）。

    S50：把 DIMENSIONS 从代码常量升级为内容载体——探索该从哪些维度发散
    取决于用户与作品，应可增删改（对齐 mood 维度/skills 模式）。
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        # S79：连接配置收敛到 anyspark.core.db.connect
        self._conn = sqlite_connect(self._db)
        self._lock = threading.Lock()
        self._init_schema()
        self._seed()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS explore_dims (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    order_index INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def _seed(self) -> None:
        with self._lock:
            n = self._conn.execute("SELECT COUNT(*) AS c FROM explore_dims").fetchone()["c"]
            if n == 0:
                now = _now()
                for i, d in enumerate(DEFAULT_DIMENSIONS):
                    self._conn.execute(
                        "INSERT INTO explore_dims (id, name, enabled, order_index, created_at) "
                        "VALUES (?,?,1,?,?)",
                        (uuid.uuid4().hex, d, i, now),
                    )
                self._conn.commit()

    def list_names(self) -> list[str]:
        """启用的维度名（探索分派用）。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT name FROM explore_dims WHERE enabled=1 ORDER BY order_index, rowid"
            ).fetchall()
        return [r["name"] for r in rows]

    def list_all(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM explore_dims ORDER BY order_index, rowid"
            ).fetchall()
        return [dict(r) for r in rows]

    def add(self, name: str) -> dict[str, Any] | None:
        name = name.strip()
        if not name:
            return None
        with self._lock:
            exists = self._conn.execute(
                "SELECT 1 FROM explore_dims WHERE name=?", (name,)
            ).fetchone()
            if exists:
                return None
            max_order = self._conn.execute(
                "SELECT COALESCE(MAX(order_index), -1) AS m FROM explore_dims"
            ).fetchone()["m"]
            did = uuid.uuid4().hex
            self._conn.execute(
                "INSERT INTO explore_dims (id, name, enabled, order_index, created_at) "
                "VALUES (?,?,1,?,?)",
                (did, name, int(max_order) + 1, _now()),
            )
            self._conn.commit()
            return {"id": did, "name": name, "enabled": 1}

    def set_enabled(self, dim_id: str, enabled: bool) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM explore_dims WHERE id=?", (dim_id,)).fetchone()
            if row is None:
                return None
            self._conn.execute(
                "UPDATE explore_dims SET enabled=? WHERE id=?",
                (1 if enabled else 0, dim_id),
            )
            self._conn.commit()
        return dict(row) | {"enabled": 1 if enabled else 0}

    def delete(self, dim_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM explore_dims WHERE id=?", (dim_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()


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
        # S79：连接配置收敛到 anyspark.core.db.connect
        self._conn = sqlite_connect(self._db)
        self._lock = threading.Lock()
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

    def close(self) -> None:
        self._conn.close()
