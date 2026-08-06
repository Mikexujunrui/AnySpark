"""
anyspark.align.mood — 氛围滑块注入块（机制 4 低摩擦交互组件之一）。

S50 修复（主人批评，DESIGN §12.17）：
1. **数值裸传** → 语义化：0-100 转程度词（无/极轻微/轻微/中等/较强/强烈），
   工程量纲不进模型（照抄 chat_rewrite 的 subtle→"尽量保留原文结构与表达"模式）
2. **4 维预设锁死** → 维度集内容化：默认 4 维种子（tension/warmth/calm/dread），
   但维度=内容（SQLite 可增删改/开关），滑块**形状**（0-100 range）机制硬编码保留
3. 每维度带语义描述（怎么写）+ 情景样例（什么时候用）——注入的是自然语言

哲学：B 类交互载体结构（滑块形状）硬编码；维度定义（内容）自然语言可编辑。
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# 默认氛围维度种子（内容自然语言，可增删改；键为前端滑块标识）
DEFAULT_MOOD_DIMS: list[dict[str, str]] = [
    {
        "key": "tension",
        "label": "紧张感",
        "description": "短促节奏、逼近的压迫、环境细节渲染紧绷（类似悬疑/恐怖片高潮段落的气氛）",
        "example": "追逃、对峙、时限将至的场面",
    },
    {
        "key": "warmth",
        "label": "温暖感",
        "description": "柔和的感官细节（光线/触感/气息）、缓慢的节奏、人物间的亲近感",
        "example": "重逢、日常、相依的场面",
    },
    {
        "key": "calm",
        "label": "舒缓感",
        "description": "从容的铺陈、留白、长句与安静意象；不着急推进",
        "example": "休整、回忆、风景过渡的场面",
    },
    {
        "key": "dread",
        "label": "压抑感",
        "description": "沉闷、不安、被窥视感；细节里藏着危险信号",
        "example": "密室、真相逼近、暴风雨前的场面",
    },
]


# 数值 → 程度语义词（机制：量纲分段，硬编码；不把 80/100 裸传模型）
def _level_text(val: int) -> str:
    if val <= 0:
        return "无"
    if val <= 20:
        return "极轻微"
    if val <= 40:
        return "轻微"
    if val <= 60:
        return "中等"
    if val <= 80:
        return "较强"
    return "强烈"


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class MoodDim:
    """一个氛围维度（内容：自然语言，可编辑）。"""

    key: str
    label: str
    description: str = ""
    example: str = ""
    enabled: bool = True
    order: int = 0
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "example": self.example,
            "enabled": self.enabled,
            "order": self.order,
            "created_at": self.created_at,
        }


class MoodDimStore:
    """氛围维度存储（SQLite，内容层可增删改）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._seed()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mood_dims (
                    id TEXT PRIMARY KEY,
                    key TEXT NOT NULL UNIQUE,
                    label TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    example TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    order_index INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def _seed(self) -> None:
        with self._lock:
            n = self._conn.execute("SELECT COUNT(*) AS c FROM mood_dims").fetchone()["c"]
            if n == 0:
                now = _now()
                for i, d in enumerate(DEFAULT_MOOD_DIMS):
                    self._conn.execute(
                        "INSERT INTO mood_dims "
                        "(id, key, label, description, example, enabled, order_index, created_at) "
                        "VALUES (?,?,?,?,?,1,?,?)",
                        (
                            uuid.uuid4().hex,
                            d["key"],
                            d["label"],
                            d["description"],
                            d["example"],
                            i,
                            now,
                        ),
                    )
                self._conn.commit()

    def list_dims(self) -> list[MoodDim]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM mood_dims ORDER BY order_index, rowid"
            ).fetchall()
        return [_from_row(r) for r in rows]

    def enabled_dims(self) -> list[MoodDim]:
        return [d for d in self.list_dims() if d.enabled]

    def get_by_key(self, key: str) -> MoodDim | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM mood_dims WHERE key=?", (key,)).fetchone()
        return _from_row(row) if row else None

    def add(
        self,
        key: str,
        label: str,
        description: str = "",
        example: str = "",
    ) -> MoodDim | None:
        with self._lock:
            exists = self._conn.execute("SELECT 1 FROM mood_dims WHERE key=?", (key,)).fetchone()
            if exists:
                return None
            max_order = self._conn.execute(
                "SELECT COALESCE(MAX(order_index), -1) AS m FROM mood_dims"
            ).fetchone()["m"]
            d = MoodDim(
                key=key,
                label=label,
                description=description,
                example=example,
                order=int(max_order) + 1,
            )
            self._conn.execute(
                "INSERT INTO mood_dims "
                "(id, key, label, description, example, enabled, order_index, created_at) "
                "VALUES (?,?,?,?,?,1,?,?)",
                (d.id, d.key, d.label, d.description, d.example, d.order, d.created_at),
            )
            self._conn.commit()
        return d

    def update(
        self,
        dim_id: str,
        label: str | None = None,
        description: str | None = None,
        example: str | None = None,
        enabled: bool | None = None,
    ) -> MoodDim | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM mood_dims WHERE id=?", (dim_id,)).fetchone()
            if row is None:
                return None
            sets: list[str] = []
            params: list[Any] = []
            if label is not None:
                sets.append("label=?")
                params.append(label)
            if description is not None:
                sets.append("description=?")
                params.append(description)
            if example is not None:
                sets.append("example=?")
                params.append(example)
            if enabled is not None:
                sets.append("enabled=?")
                params.append(1 if enabled else 0)
            if sets:
                params.append(dim_id)
                self._conn.execute(f"UPDATE mood_dims SET {', '.join(sets)} WHERE id=?", params)
                self._conn.commit()
        return self.get(dim_id)

    def get(self, dim_id: str) -> MoodDim | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM mood_dims WHERE id=?", (dim_id,)).fetchone()
        return _from_row(row) if row else None

    def delete(self, dim_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM mood_dims WHERE id=?", (dim_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()


def _from_row(row: sqlite3.Row) -> MoodDim:
    return MoodDim(
        id=row["id"],
        key=row["key"],
        label=row["label"],
        description=row["description"],
        example=row["example"],
        enabled=bool(row["enabled"]),
        order=int(row["order_index"]),
        created_at=row["created_at"],
    )


def build_mood_block(mood: dict[str, float] | None, dims: list[MoodDim] | None = None) -> str:
    """氛围字典 → 自然语言注入块（空字典返回空串，不注入）。

    S50：数值转程度词（不进模型），维度语义用内容层描述（可编辑）。
    dims：维度定义（来自 store）；缺省用默认种子（兼容旧调用）。
    """
    if not mood:
        return ""
    if dims is None:
        dims = [MoodDim(key=d["key"], label=d["label"]) for d in DEFAULT_MOOD_DIMS]
    by_key = {d.key: d for d in dims}
    parts: list[str] = []
    for k, raw_v in mood.items():
        dim = by_key.get(k)
        if dim is None or not dim.enabled:
            continue
        val = max(0, min(100, int(raw_v)))
        if val <= 0:
            continue
        level = _level_text(val)
        desc = dim.description or dim.label
        line = f"{dim.label}：{level}——{desc}"
        if dim.example:
            line += f"（适用：{dim.example}）"
        parts.append(line)
    if not parts:
        return ""
    return "# 本段氛围要求（写作时让文字承载此氛围）\n" + "\n".join(f"- {p}" for p in parts)
