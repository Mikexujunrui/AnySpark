"""
anyspark.align.skills — 写作技巧（S43：写作纪律内容化，参考 pi skills 形态）。

背景（主人"智能体驱动哲学"审计）：S33 粒度感知、S42 认知边界等"写作技巧"被
硬塞进 DEFAULT_SYSTEM（行为规则堆叠 → 规则驱动的倾向，违背"相信模型/少加规则"）。

修正：写作技巧从系统提示抽出，做成 **skill 式内容载体**（参考 pi 的 skills）：
- 每条技巧 = { name, description（一行，索引用）, content（完整指令）, enabled }
- DEFAULT_SYSTEM 回归极简（只留"智能体行为底线"：写出来并落盘/别乱调工具）
- 技巧作为**内容**注入（可增删改/开关/按需），不是"守则"
- 渐进式披露（对齐 pi）：技巧多了之后索引常驻、完整正文按需注入；当前技巧少（<5 条）先全量注入内容

哲学边界：DEFAULT_SYSTEM = A 类过程控制底线（硬编码）；写作技巧 = 内容（自然语言，可编辑）。
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# 默认写作技巧（种子；内容自然语言，可增删改）
DEFAULT_SKILLS: list[dict[str, str]] = [
    {
        "name": "粒度感知",
        "description": "脉络越细越严格遵循；脉络越粗=需要自主设计场景/细节/节奏。",
        "content": (
            "剧情脉络按颗粒度处理：脉络越细（逐场景/要点全），越要严格遵循、不得遗漏；"
            "脉络越粗（只有主干或种子），意味着场景推进、细节、节奏需要你自主设计——"
            "动笔前先在心中构思本章场景序列与要点（不必输出），正文要体现自主设计的层次"
            "（原创细节、节奏变化、氛围经营），不要只把主干复述一遍。"
        ),
    },
    {
        "name": "角色认知边界",
        "description": "角色只知道亲历/亲见/合理推断的信息——叙事可全知，角色不可。",
        "content": (
            "角色的认知受限于其经历：每个角色只知道他们亲眼所见、亲身经历、"
            "或能合理推断的信息。叙事者可以全知，但角色不知道的信息不能让角色说出来"
            "（防止全知全能越界）。"
        ),
    },
    {
        "name": "氛围克制",
        "description": "恐惧/情绪通过感官细节与动作呈现，不直说感受、不形容词堆砌。",
        "content": (
            "氛围通过感官细节（视觉/听觉/嗅觉/触觉）与动作呈现，避免直接概括情绪"
            "（如'他很恐惧'）与形容词堆砌；让读者从细节中感受，而非被告知。"
        ),
    },
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class WritingSkill:
    """一条写作技巧（skill 式：描述常驻索引、正文按需注入）。"""

    name: str
    description: str
    content: str
    enabled: bool = True
    order: int = 0
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "content": self.content,
            "enabled": self.enabled,
            "order": self.order,
            "created_at": self.created_at,
        }


class WritingSkillStore:
    """写作技巧存储（SQLite）。"""

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
                CREATE TABLE IF NOT EXISTS writing_skills (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    order_index INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def _seed(self) -> None:
        with self._lock:
            n = self._conn.execute("SELECT COUNT(*) AS c FROM writing_skills").fetchone()["c"]
            if n == 0:
                now = _now()
                for i, s in enumerate(DEFAULT_SKILLS):
                    self._conn.execute(
                        "INSERT INTO writing_skills "
                        "(id, name, description, content, enabled, order_index, created_at) "
                        "VALUES (?,?,?,?,1,?,?)",
                        (uuid.uuid4().hex, s["name"], s["description"], s["content"], i, now),
                    )
                self._conn.commit()

    def list_skills(self) -> list[WritingSkill]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM writing_skills ORDER BY order_index, rowid"
            ).fetchall()
        return [_from_row(r) for r in rows]

    def enabled(self) -> list[WritingSkill]:
        return [s for s in self.list_skills() if s.enabled]

    def add(self, name: str, description: str, content: str) -> WritingSkill:
        with self._lock:
            max_order = self._conn.execute(
                "SELECT COALESCE(MAX(order_index), -1) AS m FROM writing_skills"
            ).fetchone()["m"]
            s = WritingSkill(
                name=name, description=description, content=content, order=int(max_order) + 1
            )
            self._conn.execute(
                "INSERT INTO writing_skills "
                "(id, name, description, content, enabled, order_index, created_at) "
                "VALUES (?,?,?,?,1,?,?)",
                (s.id, s.name, s.description, s.content, s.order, s.created_at),
            )
            self._conn.commit()
        return s

    def update(
        self,
        skill_id: str,
        name: str | None = None,
        description: str | None = None,
        content: str | None = None,
        enabled: bool | None = None,
    ) -> WritingSkill | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM writing_skills WHERE id=?", (skill_id,)
            ).fetchone()
            if row is None:
                return None
            sets: list[str] = []
            params: list[Any] = []
            if name is not None:
                sets.append("name=?")
                params.append(name)
            if description is not None:
                sets.append("description=?")
                params.append(description)
            if content is not None:
                sets.append("content=?")
                params.append(content)
            if enabled is not None:
                sets.append("enabled=?")
                params.append(1 if enabled else 0)
            if sets:
                params.append(skill_id)
                self._conn.execute(
                    f"UPDATE writing_skills SET {', '.join(sets)} WHERE id=?", params
                )
                self._conn.commit()
        return self.get(skill_id)

    def get(self, skill_id: str) -> WritingSkill | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM writing_skills WHERE id=?", (skill_id,)
            ).fetchone()
        return _from_row(row) if row else None

    def delete(self, skill_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM writing_skills WHERE id=?", (skill_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()


def _from_row(row: sqlite3.Row) -> WritingSkill:
    return WritingSkill(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        content=row["content"],
        enabled=bool(row["enabled"]),
        order=int(row["order_index"]),
        created_at=row["created_at"],
    )


def render_skill_index(skills: list[WritingSkill]) -> str:
    """渲染技巧索引（对齐 pi skills：描述常驻，正文按需）。"""
    if not skills:
        return ""
    lines = ["# 写作技巧（可用：按需选用）"]
    for s in skills:
        lines.append(f"- {s.name}：{s.description}")
    return "\n".join(lines)


def render_skills_content(skills: list[WritingSkill]) -> str:
    """渲染启用的技巧完整内容（注入写作上下文）。"""
    enabled = [s for s in skills if s.enabled]
    if not enabled:
        return ""
    lines = ["# 写作技巧（内容）"]
    for s in enabled:
        lines.append(f"【{s.name}】{s.content}")
    return "\n".join(lines)
