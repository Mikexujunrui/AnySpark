"""
anyspark.template.materials — 资料消化（机制 10）。

流程：上传材料 → [入库消化·自动] 模型生成材料摘要卡（主题/要点/关键设定/涉及角色/术语）
  → 摘要卡关联图谱实体 → 原文保留（可查全文）
写作/探索时：注入摘要卡（省 token），需细节再查全文。
用途标注：文风参考 / 设定事实 / 两者（防材料角色串进正文）。
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from anyspark.core import Message, Model

# 资料用途（S50：默认建议集 style/fact/both；纯类型注解无运行时校验，
# 内容层可自由扩展——用户可写任意用途标签，不强制枚举）
Purpose = Literal["style", "fact", "both"]


@dataclass
class MaterialCard:
    """材料摘要卡（核心：入库压缩，写作注入摘要卡而非原文）。"""

    title: str
    topic: str  # 主题
    key_points: list[str]  # 要点
    key_settings: list[str]  # 关键设定
    characters: list[str]  # 涉及角色
    terms: list[str]  # 术语
    purpose: Purpose = "fact"
    source_text: str = ""  # 原文（保留可查全文）
    graph_entities: list[str] = field(default_factory=list)  # 关联图谱实体 id（机制 10）
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=lambda: _now())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "topic": self.topic,
            "key_points": self.key_points,
            "key_settings": self.key_settings,
            "characters": self.characters,
            "terms": self.terms,
            "purpose": self.purpose,
            "source_text": self.source_text,
            "graph_entities": self.graph_entities,
            "created_at": self.created_at,
        }

    def summarize(self, max_len: int = 300) -> str:
        """渲染成注入用的自然语言摘要（省 token）。"""
        lines = [
            f"材料《{self.title}》：{self.topic}",
            "要点：" + "；".join(self.key_points[:3]),
        ]
        if self.key_settings:
            lines.append("设定：" + "；".join(self.key_settings[:3]))
        if self.characters:
            lines.append("角色：" + "；".join(self.characters[:3]))
        text = "\n".join(lines)
        return text[:max_len]


def _now() -> str:
    return datetime.now(UTC).isoformat()


class MaterialStore:
    """资料存储（SQLite）：摘要卡 + 原文。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS materials (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                topic TEXT NOT NULL DEFAULT '',
                key_points TEXT NOT NULL DEFAULT '[]',
                key_settings TEXT NOT NULL DEFAULT '[]',
                characters TEXT NOT NULL DEFAULT '[]',
                terms TEXT NOT NULL DEFAULT '[]',
                purpose TEXT NOT NULL DEFAULT 'fact',
                source_text TEXT NOT NULL DEFAULT '',
                graph_entities TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            """
        )
        # 旧库兼容：已存在的 materials 表补列（幂等）
        try:
            self._conn.execute(
                "ALTER TABLE materials ADD COLUMN graph_entities TEXT NOT NULL DEFAULT '[]'"
            )
            self._conn.commit()
        except sqlite3.OperationalError:
            pass  # 列已存在
        self._conn.commit()

    def save(self, card: MaterialCard) -> MaterialCard:
        import json

        with self._lock:
            self._conn.execute(
                "INSERT INTO materials (id, title, topic, key_points, key_settings, "
                "characters, terms, purpose, source_text, graph_entities, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    card.id,
                    card.title,
                    card.topic,
                    json.dumps(card.key_points, ensure_ascii=False),
                    json.dumps(card.key_settings, ensure_ascii=False),
                    json.dumps(card.characters, ensure_ascii=False),
                    json.dumps(card.terms, ensure_ascii=False),
                    card.purpose,
                    card.source_text,
                    json.dumps(card.graph_entities, ensure_ascii=False),
                    card.created_at,
                ),
            )
            self._conn.commit()
        return card

    def list(self) -> list[MaterialCard]:
        import json

        with self._lock:
            rows = self._conn.execute("SELECT * FROM materials ORDER BY rowid DESC").fetchall()
        return [
            MaterialCard(
                id=r["id"],
                title=r["title"],
                topic=r["topic"],
                key_points=json.loads(r["key_points"]),
                key_settings=json.loads(r["key_settings"]),
                characters=json.loads(r["characters"]),
                terms=json.loads(r["terms"]),
                purpose=r["purpose"],
                source_text=r["source_text"],
                graph_entities=json.loads(r["graph_entities"] or "[]"),
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def get(self, material_id: str) -> MaterialCard | None:
        import json

        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM materials WHERE id=?", (material_id,)
            ).fetchone()
        if not row:
            return None
        return MaterialCard(
            id=row["id"],
            title=row["title"],
            topic=row["topic"],
            key_points=json.loads(row["key_points"]),
            key_settings=json.loads(row["key_settings"]),
            characters=json.loads(row["characters"]),
            terms=json.loads(row["terms"]),
            purpose=row["purpose"],
            source_text=row["source_text"],
            graph_entities=json.loads(row["graph_entities"] or "[]"),
            created_at=row["created_at"],
        )

    def close(self) -> None:
        self._conn.close()


DIGEST_PROMPT = """你是资料消化器。把下面的材料压缩成**摘要卡**（供写作时注入，省 token）。
输出（严格 JSON，不要其它文字）：
{
  "title": "材料标题",
  "topic": "主题一句话",
  "key_points": ["要点1", "要点2", "要点3"],
  "key_settings": ["关键设定1", "关键设定2"],
  "characters": ["涉及角色1", "涉及角色2"],
  "terms": ["术语1", "术语2"]
}

材料：
"""


class MaterialDigestor:
    """真实 LLM 把上传材料消化成摘要卡。"""

    def __init__(self, model: Model) -> None:
        self._model = model

    def digest(self, raw_text: str, purpose: Purpose = "fact") -> MaterialCard:
        prompt = DIGEST_PROMPT + raw_text[:4000]
        output = self._model.respond(
            [Message(role="system", content=prompt)],
            [],
        )
        import json
        import re

        cleaned = output.text.strip()
        fence = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
        if fence:
            cleaned = fence.group(1)
        start, end = cleaned.find("{"), cleaned.rfind("}")
        data: dict[str, object] = {}
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(cleaned[start : end + 1])
                if isinstance(parsed, dict):
                    data = parsed
            except json.JSONDecodeError:
                data = {}

        def _lst(key: str) -> list[str]:
            v = data.get(key, [])
            return [str(x) for x in v] if isinstance(v, list) else []

        title = str(data.get("title", raw_text[:20]))
        return MaterialCard(
            title=title,
            topic=str(data.get("topic", "")),
            key_points=_lst("key_points"),
            key_settings=_lst("key_settings"),
            characters=_lst("characters"),
            terms=_lst("terms"),
            purpose=purpose,
            source_text=raw_text,
        )
