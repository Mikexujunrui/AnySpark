"""
anyspark.align.bias — AI 倾向档案（双向黑盒解法，DESIGN §2）。

问题：用户不知道 AI 的倾向（换模型还会变）→ 摩擦。
解法：AI 主动暴露当前倾向（"我这个模型写对话偏克制"），存成可读档案，
注入后续对话——让用户能预测 AI、敢放手（摩擦前置）。
半硬编码：档案机制硬编码，内容模型自述 + 用户修正（自然语言，模型无关）。
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class BiasStore:
    """AI 倾向档案存储（SQLite）：条目 = 自然语言短句 + 来源 + 时间。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db, check_same_thread=False, timeout=30)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ai_bias (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'ai',
                created_at TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def add(self, content: str, source: str = "ai") -> dict[str, Any]:
        """新增一条倾向自述（AI 声明或用户修正）。"""
        content = content.strip()
        if not content:
            return {}
        bid = uuid.uuid4().hex
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO ai_bias (id, content, source, created_at) VALUES (?,?,?,?)",
                (bid, content, source, now),
            )
            self._conn.commit()
        return {"id": bid, "content": content, "source": source, "created_at": now}

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, content, source, created_at FROM ai_bias ORDER BY rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "content": r["content"],
                "source": r["source"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def delete(self, bias_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM ai_bias WHERE id=?", (bias_id,))
            self._conn.commit()

    def render(self, limit: int = 10) -> str:
        """渲染成注入块（自然语言，模型无关）。"""
        entries = self.list(limit)
        if not entries:
            return ""
        lines = ["# AI 倾向档案（我的自我认知，供你预测我的写作风格）"]
        for e in entries:
            src = "AI 自述" if e["source"] == "ai" else "用户修正"
            lines.append(f"- {e['content']}（{src}）")
        return "\n".join(lines)
