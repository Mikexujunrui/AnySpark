"""
anyspark.template.plot — 关键点图谱（T2 阶段 3，作品级规划，可选深入）。

DESIGN：图谱=跨章长期记忆（主线冲突/角色弧/情感核/世界规则/情绪峰值/伏笔/节奏，
网状非大纲）；每章写作时注入其当前状态（哪些推进/哪些没收）。不强制：小白可跳过。
本模块：存储 + LLM 生成草案（半硬编码：存在机制硬编码，图谱内容模型生成）。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anyspark.core.types import Message

# 关键点类别（自然语言，模型无关）
PLOT_CATEGORIES = ("主线冲突", "角色弧", "情感核", "世界规则", "情绪峰值", "伏笔", "节奏")


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class PlotPoint:
    """一个关键点（可增删改、标注在意/不需要——操作即对齐信号）。"""

    id: str
    book_id: str
    category: str
    content: str
    chapter_ref: str = ""  # 关联章节（可空=全局）
    status: str = "open"  # open|resolved
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "book_id": self.book_id,
            "category": self.category,
            "content": self.content,
            "chapter_ref": self.chapter_ref,
            "status": self.status,
            "created_at": self.created_at,
        }


class PlotStore:
    """关键点图谱存储（SQLite）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS plot_points (
                id TEXT PRIMARY KEY,
                book_id TEXT NOT NULL,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                chapter_ref TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_plot_book ON plot_points(book_id, category);
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def add(self, book_id: str, category: str, content: str, chapter_ref: str = "") -> PlotPoint:
        pid = uuid.uuid4().hex
        cat = category if category in PLOT_CATEGORIES else "主线冲突"
        now = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO plot_points (id, book_id, category, content, chapter_ref, "
                "status, created_at) VALUES (?,?,?,?,?,?,?)",
                (pid, book_id, cat, content, chapter_ref, "open", now),
            )
            self._conn.commit()
        return PlotPoint(pid, book_id, cat, content, chapter_ref, "open", now)

    def list(self, book_id: str = "main") -> list[PlotPoint]:
        rows = self._conn.execute(
            "SELECT * FROM plot_points WHERE book_id=? ORDER BY rowid", (book_id,)
        ).fetchall()
        return [
            PlotPoint(
                id=r["id"],
                book_id=r["book_id"],
                category=r["category"],
                content=r["content"],
                chapter_ref=r["chapter_ref"],
                status=r["status"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def update_status(self, plot_id: str, status: str) -> PlotPoint | None:
        with self._lock:
            self._conn.execute("UPDATE plot_points SET status=? WHERE id=?", (status, plot_id))
            self._conn.commit()
        for p in self.list():
            if p.id == plot_id:
                return p
        return None

    def delete(self, plot_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM plot_points WHERE id=?", (plot_id,))
            self._conn.commit()

    def render(self, book_id: str = "main") -> str:
        """渲染成注入块（当前推进状态，供一章收尾/续写时注入）。"""
        points = self.list(book_id)
        if not points:
            return ""
        lines = ["# 关键点图谱（当前推进状态）"]
        for p in points:
            mark = "✓" if p.status == "resolved" else "○"
            ref = f"（{p.chapter_ref}）" if p.chapter_ref else ""
            lines.append(f"- {mark} [{p.category}] {p.content}{ref}")
        return "\n".join(lines)


PLOT_PROMPT = (
    "你是小说结构规划师。基于下面的作品设定与已写章节，生成**关键点图谱草案**（网状非大纲）：\n"
    "类别：主线冲突 / 角色弧 / 情感核 / 世界规则 / 情绪峰值 / 伏笔 / 节奏。\n"
    "每个关键点一句话，具体可操作（标出它大致落在哪章或全局）。\n"
    "输出（严格 JSON 数组，不要其它文字）：\n"
    '[{"category": "主线冲突", "content": "…", "chapter_ref": "第3章"}]\n\n'
    "作品设定：\n"
)


class PlotGenerator:
    """LLM 生成关键点图谱草案（模型无关）。"""

    def __init__(self, model: object) -> None:
        self._model = model

    def generate(self, book_id: str, store: PlotStore, settings: str = "") -> list[PlotPoint]:
        prompt = (
            PLOT_PROMPT + f"\n{settings[:2000]}\n\n已有关键点：\n{store.render(book_id)[:1500]}"
        )
        out = self._model.respond(  # type: ignore[attr-defined]
            [Message(role="system", content=prompt)],
            [],
        )
        points: list[PlotPoint] = []
        import re

        cleaned = out.text.strip()
        fence = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
        if fence:
            cleaned = fence.group(1)
        start, end = cleaned.find("["), cleaned.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(cleaned[start : end + 1])
                if isinstance(data, list):
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        content = str(item.get("content", "")).strip()
                        if not content:
                            continue
                        points.append(
                            store.add(
                                book_id,
                                str(item.get("category", "主线冲突")),
                                content,
                                str(item.get("chapter_ref", "")),
                            )
                        )
            except json.JSONDecodeError:
                pass
        return points
