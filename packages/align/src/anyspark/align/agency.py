"""
anyspark.align.agency — 能动性协议（机制 2，AI 做多少）。

五级协议（默认档位，自然语言描述，用户可加可改）：
  0 只听写 / 1 执行+填肉 / 2 补全标注 / 3 建议扩展 / 4 自主发挥
- AI 每轮可声明级别（输出标注），用户一键点选修正
- 反馈自动调节：接受=升级，删除/拒绝=降级（信号来自操作，零打字）
- 长期：能动性是心智模型的输出而非独立旋钮，显式声明随默契退场
模型参数映射：档位低 → 温度低（精确执行）；档位高 → 温度略高（探索交给多路）
半硬编码：档位结构/温度映射/注入块硬编码，档位描述自然语言（用户可改）。
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

# 默认五级档位（自然语言，用户可增改）
AGENCY_LEVELS: list[dict[str, Any]] = [
    {"level": 0, "name": "只听写", "description": "严格按用户原文/原意输出，不添加不改动。"},
    {"level": 1, "name": "执行+填肉", "description": "按用户骨架填充，不改变结构。"},
    {"level": 2, "name": "补全标注", "description": "补全细节，但标注哪些是 AI 加的。"},
    {"level": 3, "name": "建议扩展", "description": "提出新方向供用户选。"},
    {"level": 4, "name": "自主发挥", "description": "自行探索写作，用户验收。"},
]

# 档位 → 温度映射（可调默认；档位低=精确执行温度低）
_TEMP_MAP = {0: 0.2, 1: 0.4, 2: 0.6, 3: 0.8, 4: 1.0}


def temperature_for(level: int, default: float = 0.7) -> float:
    """档位 → 温度（档位越高温度略高，探索交给多路而非单次发热）。"""
    return _TEMP_MAP.get(level, default)


def build_agency_block(level: int) -> str:
    """档位 → 自然语言系统提示块（模型无关）。"""
    for lv in AGENCY_LEVELS:
        if lv["level"] == level:
            return (
                f"# 能动级别 {level}（{lv['name']}）\n"
                f"本轮写作请按此档执行：{lv['description']}\n"
                "若你认为需要更高/更低档位（例如任务更适合自主发挥），"
                "在输出末尾附一行【能动级别: N】（0-4），供用户一键确认。"
            )
    return ""


class AgencyStore:
    """当前能动档位持久化（book 级，SQLite）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS agency_state (
                book_id TEXT PRIMARY KEY,
                level INTEGER NOT NULL DEFAULT 2,
                updated_at TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def get_level(self, book_id: str = "main") -> int:
        row = self._conn.execute(
            "SELECT level FROM agency_state WHERE book_id=?", (book_id,)
        ).fetchone()
        if row is None:
            return 2  # 默认档位：补全标注
        return int(row["level"])

    def set_level(self, level: int, book_id: str = "main") -> int:
        level = max(0, min(4, int(level)))
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO agency_state (book_id, level, updated_at) VALUES (?,?,?)",
                (book_id, level, now),
            )
            self._conn.commit()
        return level

    def adjust(self, delta: int, book_id: str = "main") -> int:
        """反馈自动调节：accepted→+1（上限4），deleted/rejected→-1（下限0）。"""
        return self.set_level(self.get_level(book_id) + delta, book_id)


def parse_agency_declaration(text: str) -> int | None:
    """解析 AI 输出中的档位声明（如【能动级别: 3】）；无声明返回 None。"""
    import re

    m = re.search(r"【能动级别\s*[:：]\s*([0-4])】", text)
    if m:
        return int(m.group(1))
    return None
