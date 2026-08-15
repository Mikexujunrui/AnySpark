"""
anyspark.align.plan — 剧情计划（S46：计划→执行系统化，场景 1 核心缺口）。

背景：AI 能产出规划（S34 实测 16 章规划），但规划是 chat 输出、没有固化机制——
"写这一章时 AI 不知道接下来计划是什么"。本模块把规划固化为**章节级计划**：

- story_plan 表：每章一条（chapter_order/title/content/status: planned|done）
- 写作注入：当前章计划 + 后续 2 章（AI 知道接下来写什么）
- 推进：写完一章标记 done（API 或 AI 自主标记）
- 与伏笔（plot_points）区分：伏笔=已埋线索的状态；计划=待写章节的安排

哲学：机制硬编码（表/注入/推进状态机）、内容自然语言（计划内容是文本）。
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anyspark.core.db import connect as sqlite_connect

PLAN_STATUSES = ("planned", "done")


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ChapterPlan:
    """一章的写作计划。"""

    chapter_order: int
    title: str = ""
    content: str = ""  # 该章计划（事件/要点/悬念，自然语言）
    status: str = "planned"  # planned | done
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "chapter_order": self.chapter_order,
            "title": self.title,
            "content": self.content,
            "status": self.status,
            "created_at": self.created_at,
        }


class StoryPlanStore:
    """剧情计划存储（SQLite，项目级 book）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        # S79：连接配置收敛到 anyspark.core.db.connect
        self._conn = sqlite_connect(self._db)
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS story_plan (
                    id TEXT PRIMARY KEY,
                    book_id TEXT NOT NULL DEFAULT 'main',
                    chapter_order INTEGER NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'planned',
                    created_at TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def list(self, book_id: str = "main") -> list[ChapterPlan]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM story_plan WHERE book_id=? ORDER BY chapter_order, rowid",
                (book_id,),
            ).fetchall()
        return [_from_row(r) for r in rows]

    def add(
        self,
        chapter_order: int,
        title: str = "",
        content: str = "",
        book_id: str = "main",
    ) -> ChapterPlan:
        p = ChapterPlan(chapter_order=chapter_order, title=title, content=content)
        with self._lock:
            self._conn.execute(
                "INSERT INTO story_plan (id, book_id, chapter_order, title, content, "
                "status, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (p.id, book_id, p.chapter_order, p.title, p.content, p.status, p.created_at),
            )
            self._conn.commit()
        return p

    def update(
        self,
        plan_id: str,
        title: str | None = None,
        content: str | None = None,
        status: str | None = None,
    ) -> ChapterPlan | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM story_plan WHERE id=?", (plan_id,)).fetchone()
            if row is None:
                return None
            sets: list[str] = []
            params: list[Any] = []
            if title is not None:
                sets.append("title=?")
                params.append(title)
            if content is not None:
                sets.append("content=?")
                params.append(content)
            if status is not None and status in PLAN_STATUSES:
                sets.append("status=?")
                params.append(status)
            if sets:
                params.append(plan_id)
                self._conn.execute(f"UPDATE story_plan SET {', '.join(sets)} WHERE id=?", params)
                self._conn.commit()
        return self.get(plan_id)

    def get(self, plan_id: str) -> ChapterPlan | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM story_plan WHERE id=?", (plan_id,)).fetchone()
        return _from_row(row) if row else None

    def delete(self, plan_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM story_plan WHERE id=?", (plan_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()


def _from_row(row: sqlite3.Row) -> ChapterPlan:
    return ChapterPlan(
        id=row["id"],
        chapter_order=int(row["chapter_order"]),
        title=row["title"],
        content=row["content"],
        status=row["status"],
        created_at=row["created_at"],
    )


def render_plan(entries: list[ChapterPlan], horizon: int = 3) -> str:
    """渲染当前写作计划（注入用）：下一章（planned 最小 order）+ 后续 horizon-1 章。

    只注入 planned（未写）；done 的不再提示（已推进）。"""
    planned = sorted([p for p in entries if p.status == "planned"], key=lambda p: p.chapter_order)
    if not planned:
        return ""
    current = planned[0]
    lines = [f"# 剧情计划（当前进度：第{current.chapter_order}章）"]
    t_next = f"「{current.title}」" if current.title else ""
    lines.append(f"→ 下一章（第{current.chapter_order}章{t_next}）：{current.content}")
    for p in planned[1:horizon]:
        title = f"「{p.title}」" if p.title else ""
        lines.append(f"  后续：第{p.chapter_order}章{title}：{p.content}")
    lines.append("写完当前章后，用 PATCH /api/plan/{id} 标记 status=done 推进。")
    return "\n".join(lines)
