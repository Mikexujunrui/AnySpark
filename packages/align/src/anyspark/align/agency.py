"""
anyspark.align.agency — 能动性协议（机制 2，AI 做多少）。

S35 重构：档位从"固定五级枚举"升级为"全局档位记录集"（可增删改/恢复默认/温度入档）。
- 默认五级（只听写/执行+填肉/补全标注/建议扩展/自主发挥）作为稳定基线
- 用户可全局增删改档位（名称/描述/温度），恢复默认（不重置心智模型 manual）
- 温度进档位记录（自定义档位自带温度，不再按 level 数字查表）
- 反馈自动调节：接受=当前档位在排序中升级，删除/拒绝=降级（零打字）

职责边界（S35b 修正）：档位只描述**能动性**（主动程度/做什么）——文风喜好、
毒点、边界等个性化属于**心智模型**（独立系统，渐进式披露），不混入档位。

半硬编码（哲学：机制硬编码、内容自然语言）：
- 机制：档位结构（id/name/description/temperature/order）、注入块、声明解析、调整规则——硬编码
- 内容：档位名称/描述（自然语言，用户可增改）、心智附加（自然语言）
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 默认五级档位（稳定基线，用户可增删改）
# ---------------------------------------------------------------------------
DEFAULT_LEVELS: list[dict[str, Any]] = [
    {
        "id": "default-0",
        "name": "只听写",
        "description": "严格按用户原文/原意输出，不添加不改动。",
        "temperature": 0.2,
    },
    {
        "id": "default-1",
        "name": "执行+填肉",
        "description": "按用户骨架填充，不改变结构。",
        "temperature": 0.4,
    },
    {
        "id": "default-2",
        "name": "补全标注",
        "description": "补全细节，但标注哪些是 AI 加的。",
        "temperature": 0.6,
    },
    {
        "id": "default-3",
        "name": "建议扩展",
        "description": "提出新方向供用户选。",
        "temperature": 0.8,
    },
    {
        "id": "default-4",
        "name": "自主发挥",
        "description": "自行探索写作，用户验收。",
        "temperature": 1.0,
    },
]

DEFAULT_ID = "default-2"  # 默认当前档位：补全标注


@dataclass
class AgencyLevel:
    """一个能动性档位（记录，可增删改）。"""

    id: str
    name: str
    description: str
    temperature: float
    order: int  # 排序位置（声明数字/adjust 移动用）
    is_default: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "temperature": self.temperature,
            "order": self.order,
            "is_default": self.is_default,
            # 兼容旧前端字段：level=排序位（旧版数字语义）
            "level": self.order,
        }


def temperature_for(level: int | AgencyLevel, default: float = 0.7) -> float:
    """档位 → 温度（兼容旧调用：数字=默认档位 by order；记录=自带温度）。"""
    if isinstance(level, AgencyLevel):
        return level.temperature
    for d in DEFAULT_LEVELS:
        if d["id"] == f"default-{level}":
            return float(d["temperature"])
    return default


class AgencyStore:
    """全局档位记录集（增删改/恢复默认）+ 当前选择（book 级 level_id）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS agency_levels (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                temperature REAL NOT NULL,
                order_index INTEGER NOT NULL,
                is_default INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS agency_state (
                book_id TEXT PRIMARY KEY,
                level_id TEXT NOT NULL DEFAULT 'default-2',
                updated_at TEXT NOT NULL
            );
            """
        )
        self._conn.commit()
        self._seed_defaults()

    # -- 默认档位种子 --
    def _seed_defaults(self) -> None:
        with self._lock:
            n = self._conn.execute("SELECT COUNT(*) AS c FROM agency_levels").fetchone()["c"]
            if n == 0:
                now = datetime.now(UTC).isoformat()
                for i, d in enumerate(DEFAULT_LEVELS):
                    self._conn.execute(
                        "INSERT INTO agency_levels "
                        "(id, name, description, temperature, order_index, is_default, created_at) "
                        "VALUES (?,?,?,?,?,1,?)",
                        (d["id"], d["name"], d["description"], d["temperature"], i, now),
                    )
                self._conn.commit()

    # -- 查询 --
    def list_levels(self) -> list[AgencyLevel]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM agency_levels ORDER BY order_index").fetchall()
        return [_row_to_level(r) for r in rows]

    def get_level(self, level_id: str) -> AgencyLevel | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM agency_levels WHERE id=?", (level_id,)
            ).fetchone()
        return _row_to_level(row) if row else None

    def get_current(self, book_id: str = "main") -> AgencyLevel:
        with self._lock:
            row = self._conn.execute(
                "SELECT level_id FROM agency_state WHERE book_id=?", (book_id,)
            ).fetchone()
        level_id = row["level_id"] if row else DEFAULT_ID
        level = self.get_level(level_id)
        return level if level else self.get_level(DEFAULT_ID) or self.list_levels()[0]

    def set_current(self, level_id: str, book_id: str = "main") -> AgencyLevel | None:
        level = self.get_level(level_id)
        if level is None:
            return None
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO agency_state (book_id, level_id, updated_at) "
                "VALUES (?,?,?)",
                (book_id, level_id, now),
            )
            self._conn.commit()
        return level

    # -- 增删改 --
    def add_level(self, name: str, description: str, temperature: float = 0.7) -> AgencyLevel:
        """新增自定义档位（追加到排序末尾）。"""
        with self._lock:
            max_order = self._conn.execute(
                "SELECT COALESCE(MAX(order_index), -1) AS m FROM agency_levels"
            ).fetchone()["m"]
            now = datetime.now(UTC).isoformat()
            lid = uuid.uuid4().hex
            self._conn.execute(
                "INSERT INTO agency_levels "
                "(id, name, description, temperature, order_index, is_default, created_at) "
                "VALUES (?,?,?,?,?,0,?)",
                (lid, name, description, float(temperature), int(max_order) + 1, now),
            )
            self._conn.commit()
        level = self.get_level(lid)
        assert level is not None
        return level

    def update_level(
        self,
        level_id: str,
        name: str | None = None,
        description: str | None = None,
        temperature: float | None = None,
    ) -> AgencyLevel | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM agency_levels WHERE id=?", (level_id,)
            ).fetchone()
            if row is None:
                return None
            new_name = name if name is not None else row["name"]
            new_desc = description if description is not None else row["description"]
            new_temp = float(temperature) if temperature is not None else row["temperature"]
            self._conn.execute(
                "UPDATE agency_levels SET name=?, description=?, temperature=? WHERE id=?",
                (new_name, new_desc, new_temp, level_id),
            )
            self._conn.commit()
        return self.get_level(level_id)

    def delete_level(self, level_id: str) -> bool:
        """删除档位（至少保留一条；删除当前档位则回落到默认 default-2）。"""
        with self._lock:
            n = self._conn.execute("SELECT COUNT(*) AS c FROM agency_levels").fetchone()["c"]
            if n <= 1:
                return False
            cur = self._conn.execute(
                "SELECT book_id FROM agency_state WHERE level_id=?", (level_id,)
            ).fetchall()
            self._conn.execute("DELETE FROM agency_levels WHERE id=?", (level_id,))
            for r in cur:
                self._conn.execute(
                    "UPDATE agency_state SET level_id=?, updated_at=? WHERE book_id=?",
                    (DEFAULT_ID, datetime.now(UTC).isoformat(), r["book_id"]),
                )
            self._conn.commit()
        return True

    def reset_defaults(self) -> list[AgencyLevel]:
        """恢复默认五级档位（不重置心智模型——manual 在不同表，天然保留）。"""
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._conn.execute("DELETE FROM agency_levels")
            for i, d in enumerate(DEFAULT_LEVELS):
                self._conn.execute(
                    "INSERT INTO agency_levels "
                    "(id, name, description, temperature, order_index, is_default, created_at) "
                    "VALUES (?,?,?,?,?,1,?)",
                    (d["id"], d["name"], d["description"], d["temperature"], i, now),
                )
            self._conn.execute(
                "UPDATE agency_state SET level_id=?, updated_at=?",
                (DEFAULT_ID, now),
            )
            self._conn.commit()
        return self.list_levels()

    # -- 反馈自动调节（信号→档位）--
    def adjust(self, delta: int, book_id: str = "main") -> str:
        """accepted→升级（order+1 有界），deleted/rejected→降级（order-1 有界）。"""
        levels = self.list_levels()
        cur = self.get_current(book_id)
        idx = next((i for i, lv in enumerate(levels) if lv.id == cur.id), 0)
        target = min(max(idx + delta, 0), len(levels) - 1)
        self.set_current(levels[target].id, book_id)
        return levels[target].id

    def close(self) -> None:
        self._conn.close()


def _row_to_level(row: sqlite3.Row) -> AgencyLevel:
    return AgencyLevel(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        temperature=float(row["temperature"]),
        order=int(row["order_index"]),
        is_default=bool(row["is_default"]),
        created_at=row["created_at"],
    )


def build_agency_block(level: AgencyLevel | int | str) -> str:
    """档位 → 自然语言系统提示块（模型无关）。

    职责边界（S35b）：档位只描述**能动性**（主动程度/做什么），
    不含文风/喜好/毒点等心智内容——那些是心智模型（独立系统，渐进式披露）的职责。
    level 兼容：AgencyLevel 记录 / int（默认档位 by order）/ str（档位 id）。
    """
    lv: AgencyLevel | None = None
    if isinstance(level, AgencyLevel):
        lv = level
    elif isinstance(level, str):
        store = _STORE_HOOK(level)
        if store:
            lv = store.get_level(level)
    else:  # int：默认档位 by order（兼容旧调用）
        for d in DEFAULT_LEVELS:
            if d["id"] == f"default-{int(level)}":
                from dataclasses import replace

                lv = replace(
                    AgencyLevel(
                        id=d["id"],
                        name=d["name"],
                        description=d["description"],
                        temperature=float(d["temperature"]),
                        order=int(level),
                        is_default=True,
                    )
                )
                break
    if lv is None:
        return ""
    block = f"# 能动级别 {lv.order}（{lv.name}）\n本轮写作请按此档执行：{lv.description}\n"
    block += (
        "若你认为需要更高/更低档位（例如任务更适合自主发挥），"
        "在输出末尾附一行【能动级别: N】（N=排序位 0 起），供用户一键确认。"
    )
    return block


# build_agency_block 的 str 分支需要一个 store 钩子（避免函数签名背 store）
_STORE_HOOK: Any = lambda _: None  # noqa: E731


def bind_agency_store(store: Any) -> None:
    """app 装配时绑定 AgencyStore（build_agency_block 字符串 id 解析用）。"""
    global _STORE_HOOK
    _STORE_HOOK = lambda lid: store  # noqa: E731


def parse_agency_declaration(text: str) -> int | None:
    """解析 AI 声明【能动级别: N】（N=排序位，兼容中文冒号/空格）。"""
    import re

    m = re.search(r"【能动级别\s*[:：]\s*(\d+)】", text)
    if not m:
        return None
    return int(m.group(1))
