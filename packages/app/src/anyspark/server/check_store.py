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

# S246：内置检测规则包（内容数据，非机制）——学术文本七项。
# 为什么放这里而不硬编码进 check 包骨架：骨架=小说体裁的第一性原理默认值，
# 学术项属于"领域拓展包"性质的内容；借 S195 用户骨架通道入库（可查/可删/可恢复），
# 与预置 workflow 模板的 builtin 形态同型。自举守卫：已在添加项或已被用户删除的
# 类别不重加（尊重用户删除，不复活）。
BUILTIN_ACADEMIC_CHECKS: list[tuple[str, str]] = [
    (
        "术语一致性",
        "同一概念在全文中的称谓是否统一：术语、译名、缩写不得随意变换；首次出现应有定义。",
    ),
    (
        "论断证据",
        "每个论断是否有数据/文献/推导支撑：无出处的断言、以'显然''众所周知'搪塞的要标出。",
    ),
    (
        "结构完备",
        "结构要素是否完整且各司其职：引言是否交代问题与贡献、方法是否可复现、结论是否回应引言。",
    ),
    (
        "逻辑链条",
        "推理步骤是否衔接：有无逻辑跳跃、循环论证、前提与结论错位。",
    ),
    (
        "语言规范",
        "是否存在口语化表达、绝对化断言（'证明了'应为'结果表明'）、无意义修饰与冗余。",
    ),
    (
        "数据一致",
        "数字/单位/统计指标在摘要、正文、图表描述之间是否一致；前后引用同一数据是否同值。",
    ),
    (
        "诚信自查",
        "是否有疑似空泛套话、无出处的引文、语焉不详的关键表述——提示作者逐条核实（诚信护栏：辅助自查，不代替作者判断）。",
    ),
]


_BUILTIN_PACK_CATEGORIES = frozenset(c for c, _ in BUILTIN_ACADEMIC_CHECKS)


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
        self._seed_builtin_packs()

    def _seed_builtin_packs(self) -> None:
        """S246：内置规则包自举（幂等）——添加项/删除项中已存在的类别不重加。"""
        import uuid

        with self._lock:
            have = {
                r["category"]
                for r in self._conn.execute(
                    "SELECT category FROM user_skeleton_additions"
                ).fetchall()
            }
            have |= {
                r["category"]
                for r in self._conn.execute(
                    "SELECT category FROM user_skeleton_deletions"
                ).fetchall()
            }
            for category, description in BUILTIN_ACADEMIC_CHECKS:
                if category in have:
                    continue
                self._conn.execute(
                    "INSERT INTO user_skeleton_additions (id, category, description) "
                    "VALUES (?, ?, ?)",
                    (str(uuid.uuid4()), category, description),
                )
            self._conn.commit()

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
        """按 category 删除用户添加项（前端只传 category 时用）。

        内置规则包项（S246）删除时额外标记 deletions——否则重启后自举种子会
        复活它，违背用户删除意图；语义对齐默认骨架的"标记删除（可恢复）"。"""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM user_skeleton_additions WHERE category = ?", (category,)
            )
            if cur.rowcount > 0 and category in _BUILTIN_PACK_CATEGORIES:
                self._conn.execute(
                    "INSERT OR IGNORE INTO user_skeleton_deletions (category) VALUES (?)",
                    (category,),
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
        """恢复一个被删除的默认检测项。

        内置规则包项（S246）另需重新物化物理行——自举种子只在启动时跑，
        此处幂等补种（守卫：已在添加项/删除项的不动）。"""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM user_skeleton_deletions WHERE category = ?", (category,)
            )
            self._conn.commit()
        restored = cur.rowcount > 0
        if category in _BUILTIN_PACK_CATEGORIES:
            self._seed_builtin_packs()
        return restored

    def merged_checks(self, defaults: list[SkeletonCheckItem]) -> list[SkeletonCheckItem]:
        """合并默认骨架 + 用户添加项 - 用户删除项。"""
        deletions = set(self.list_deletions())
        result = [item for item in defaults if item.category not in deletions]
        result.extend(self.list_additions())
        return result

    def close(self) -> None:
        with self._lock:
            self._conn.close()
