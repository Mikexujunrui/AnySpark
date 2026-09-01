"""
anyspark.server.check_store — 用户自定义骨架检测项存储（S195）。

DESIGN 机制 9 第③层：用户可增删骨架检测项的持久化。
check 包不引入 sqlite（core 单向依赖约束），持久化在 app 层做。
存储形态：用户添加项 + 用户删除的默认项 category 标记。
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from anyspark.check import SkeletonCheckItem

_CONN_TIMEOUT = 30  # 与 core/db.py 对齐


class UserSkeletonStore:
    """用户自定义骨架检测项存储。

    两种记录：
    - additions：用户添加的检测项（id/category/description）
    - deletions：用户删除的默认检测项 category 标记
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._db, check_same_thread=False, timeout=_CONN_TIMEOUT)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS user_skeleton_additions (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS user_skeleton_deletions (
                    category TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                """
            )
            self._conn.commit()

    def list_additions(self) -> list[SkeletonCheckItem]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT category, description FROM user_skeleton_additions ORDER BY created_at"
            ).fetchall()
        return [
            SkeletonCheckItem(category=r["category"], description=r["description"]) for r in rows
        ]

    def add(self, category: str, description: str) -> str:
        import uuid

        item_id = str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                "INSERT INTO user_skeleton_additions (id, category, description) VALUES (?, ?, ?)",
                (item_id, category, description),
            )
            self._conn.commit()
        return item_id

    def delete_addition(self, item_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM user_skeleton_additions WHERE id = ?", (item_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def delete_addition_by_category(self, category: str) -> bool:
        """按 category 删除用户添加项（前端只传 category 时用）。"""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM user_skeleton_additions WHERE category = ?", (category,)
            )
            self._conn.commit()
        return cur.rowcount > 0

    def list_deletions(self) -> list[str]:
        """用户删除的默认检测项 category 列表。"""
        with self._lock:
            rows = self._conn.execute("SELECT category FROM user_skeleton_deletions").fetchall()
        return [r["category"] for r in rows]

    def add_deletion(self, category: str) -> bool:
        """标记一个默认检测项为删除。"""
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO user_skeleton_deletions (category) VALUES (?)",
                (category,),
            )
            self._conn.commit()
        return True

    def remove_deletion(self, category: str) -> bool:
        """恢复一个被删除的默认检测项。"""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM user_skeleton_deletions WHERE category = ?", (category,)
            )
            self._conn.commit()
        return cur.rowcount > 0

    def merged_checks(self, defaults: list[SkeletonCheckItem]) -> list[SkeletonCheckItem]:
        """合并默认骨架 + 用户添加项 - 用户删除项。"""
        deletions = set(self.list_deletions())
        result = [item for item in defaults if item.category not in deletions]
        result.extend(self.list_additions())
        return result

    def close(self) -> None:
        with self._lock:
            self._conn.close()
