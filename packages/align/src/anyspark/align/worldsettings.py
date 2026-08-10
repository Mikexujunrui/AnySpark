"""
anyspark.align.worldsettings — 设定档（S41：作品正典设定）。

定位（哲学：机制硬编码、内容自然语言；与图谱正交）：
- **图谱**：自动抽取的动态事实（实体状态随章节演化）——"系统读到的事实"
- **设定档**：作者维护的**正典设定**（人物本质/能力体系/世界观规则/禁忌）——
  "作者脑中的设定"，不随剧情漂移，写作时注入供 AI 遵守。

价值（超长书实战启示）：续写质量上限 = 设定覆盖深度。
图谱只覆盖已写章节的事实（如第一卷图谱不知道第二卷才揭示的【假死】能力），
设定档可以提前/独立维护"规则类设定"，让续写/同人/变换有正典可依。

来源：作者手写（CRUD）/ 从图谱提炼草案（LLM 生成，作者编辑确认）。
类别（自然语言自由填写，建议）：人物卡/能力体系/世界观/势力/地点/物品/规则/禁忌。
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SETTING_CATEGORIES = [
    "人物卡",
    "能力体系",
    "世界观",
    "势力",
    "地点",
    "物品",
    "规则",
    "禁忌",
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class WorldSetting:
    """一条正典设定。"""

    content: str
    category: str = "世界观"
    name: str = ""
    source: str = "manual"  # manual(作者手写) | ai(提炼草案)
    order: int = 0
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "name": self.name,
            "content": self.content,
            "source": self.source,
            "order": self.order,
            "created_at": self.created_at,
        }


class WorldSettingStore:
    """设定档存储（SQLite，项目级 book）。"""

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
                CREATE TABLE IF NOT EXISTS world_settings (
                    id TEXT PRIMARY KEY,
                    book_id TEXT NOT NULL DEFAULT 'main',
                    category TEXT NOT NULL DEFAULT '世界观',
                    name TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'manual',
                    order_index INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            # S74：旧库补 book_id 列（幂等）
            try:
                self._conn.execute("ALTER TABLE world_settings ADD COLUMN book_id TEXT NOT NULL DEFAULT 'main'")
                self._conn.commit()
            except sqlite3.OperationalError:
                pass  # 列已存在
            # S50：设定档类别内容化（默认种子建议，可增删改——不再写死锁死）
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS setting_categories (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    order_index INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            n_cat = self._conn.execute("SELECT COUNT(*) AS c FROM setting_categories").fetchone()[
                "c"
            ]
            if n_cat == 0:
                now = _now()
                for i, c in enumerate(SETTING_CATEGORIES):
                    self._conn.execute(
                        "INSERT INTO setting_categories "
                        "(id, name, enabled, order_index, created_at) VALUES (?,?,1,?,?)",
                        (uuid.uuid4().hex, c, i, now),
                    )
            self._conn.commit()

    # -- S50 类别内容化（可增删改；类别=内容自然语言） --
    def list_categories(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM setting_categories ORDER BY order_index, rowid"
            ).fetchall()
        return [dict(r) for r in rows]

    def add_category(self, name: str) -> dict[str, Any] | None:
        name = name.strip()
        if not name:
            return None
        with self._lock:
            exists = self._conn.execute(
                "SELECT 1 FROM setting_categories WHERE name=?", (name,)
            ).fetchone()
            if exists:
                return None
            max_order = self._conn.execute(
                "SELECT COALESCE(MAX(order_index), -1) AS m FROM setting_categories"
            ).fetchone()["m"]
            cid = uuid.uuid4().hex
            self._conn.execute(
                "INSERT INTO setting_categories (id, name, enabled, order_index, created_at) "
                "VALUES (?,?,1,?,?)",
                (cid, name, int(max_order) + 1, _now()),
            )
            self._conn.commit()
            return {"id": cid, "name": name, "enabled": 1}

    def set_category_enabled(self, cat_id: str, enabled: bool) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM setting_categories WHERE id=?", (cat_id,)
            ).fetchone()
            if row is None:
                return None
            self._conn.execute(
                "UPDATE setting_categories SET enabled=? WHERE id=?",
                (1 if enabled else 0, cat_id),
            )
            self._conn.commit()
        return dict(row) | {"enabled": 1 if enabled else 0}

    def delete_category(self, cat_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM setting_categories WHERE id=?", (cat_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def list(self, book_id: str = "main") -> list[WorldSetting]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM world_settings WHERE book_id=? ORDER BY order_index, rowid",
                (book_id,),
            ).fetchall()
        return [_from_row(r) for r in rows]

    def get(self, setting_id: str) -> WorldSetting | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM world_settings WHERE id=?", (setting_id,)
            ).fetchone()
        return _from_row(row) if row else None

    def add(
        self,
        content: str,
        category: str = "世界观",
        name: str = "",
        source: str = "manual",
        book_id: str = "main",
    ) -> WorldSetting:
        with self._lock:
            max_order = self._conn.execute(
                "SELECT COALESCE(MAX(order_index), -1) AS m FROM world_settings WHERE book_id=?",
                (book_id,),
            ).fetchone()["m"]
            s = WorldSetting(
                content=content,
                category=category or "世界观",  # S50：类别=内容，不再强制降级到白名单
                name=name,
                source=source,
                order=int(max_order) + 1,
            )
            self._conn.execute(
                "INSERT INTO world_settings "
                "(id, book_id, category, name, content, source, order_index, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (s.id, book_id, s.category, s.name, s.content, s.source, s.order, s.created_at),
            )
            self._conn.commit()
        return s

    def update(
        self,
        setting_id: str,
        content: str | None = None,
        category: str | None = None,
        name: str | None = None,
    ) -> WorldSetting | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM world_settings WHERE id=?", (setting_id,)
            ).fetchone()
            if row is None:
                return None
            new_content = content if content is not None else row["content"]
            new_cat = category if category is not None else row["category"]
            new_name = name if name is not None else row["name"]
            self._conn.execute(
                "UPDATE world_settings SET content=?, category=?, name=? WHERE id=?",
                (new_content, new_cat, new_name, setting_id),
            )
            self._conn.commit()
        return self.get(setting_id)

    def delete(self, setting_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM world_settings WHERE id=?", (setting_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()


def _from_row(row: sqlite3.Row) -> WorldSetting:
    return WorldSetting(
        id=row["id"],
        category=row["category"],
        name=row["name"],
        content=row["content"],
        source=row["source"],
        order=int(row["order_index"]),
        created_at=row["created_at"],
    )


def render_settings(entries: list[WorldSetting], title: str = "本书设定档") -> str:
    """渲染成可读自然语言块（注入用）。"""
    if not entries:
        return ""
    lines = [f"# {title}（作者正典，写作时须遵守；与自动抽取的图谱事实互补）"]
    # 按类别分组展示
    by_cat: dict[str, list[WorldSetting]] = {}
    for e in entries:
        by_cat.setdefault(e.category, []).append(e)
    for cat, items in by_cat.items():
        lines.append(f"【{cat}】")
        for e in items:
            prefix = f"{e.name}：" if e.name else ""
            lines.append(f"- {prefix}{e.content}")
    return "\n".join(lines)


# S73b：设定档渐进式披露阈值——超过则注入索引而非全量（对齐 S60 skill 索引模式）
SETTINGS_INDEX_THRESHOLD = 20


def render_settings_adaptive(
    entries: list[WorldSetting], title: str = "本书设定档"
) -> str:
    """设定档渲染（渐进式披露，S73b）：条目 ≤阈值 全量；超阈值 注入索引。

    索引 = 类别 + 条目名/一句话截断 + 提示 read_setting 按需查——正典细节
    不常驻（省 token），agent 决定需要哪条时用 read_setting 工具查全量。
    """
    if len(entries) <= SETTINGS_INDEX_THRESHOLD:
        return render_settings(entries, title)
    lines = [
        f"# {title}（共 {len(entries)} 条，只注入索引；"
        f"写作引用前用 read_setting 按需查询具体条目）"
    ]
    by_cat: dict[str, list[WorldSetting]] = {}
    for e in entries:
        by_cat.setdefault(e.category, []).append(e)
    for cat, items in by_cat.items():
        lines.append(f"【{cat}】")
        for e in items:
            prefix = f"{e.name}：" if e.name else ""
            snippet = e.content.replace("\n", " ").strip()[:40]
            lines.append(f"- {prefix}{snippet}…" if snippet else f"- {prefix}（空）")
    return "\n".join(lines)
