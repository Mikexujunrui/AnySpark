"""anyspark.server.stats — T7 验证指标测试（纯 SQL 统计，零新表）。

覆盖：空库默认值 / 修改率（判别型信号 + 按天分桶）/ 提问率（AI 每千字问句 + 按会话排序）
/ 完成率漏斗（方向固化→章节）/ API 端点 /api/stats 可用性。
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.core.types import Message, ModelOutput
from anyspark.server.app import build_app
from anyspark.server.stats import compute_stats


def _make_db() -> Path:
    """空库（只建 signals/messages/chapters/archived_directions 表，stats 只依赖这几张）。"""
    db_path = Path(tempfile.mkdtemp()) / "stats.db"
    db = sqlite3.connect(str(db_path))
    db.executescript(
        """
        CREATE TABLE signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            context TEXT NOT NULL DEFAULT '',
            delta TEXT,
            book_id TEXT NOT NULL DEFAULT 'main',
            created_at TEXT NOT NULL
        );
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}',
            seq INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE chapters (
            id TEXT PRIMARY KEY,
            book_id TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            order_index INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE archived_directions (
            id TEXT PRIMARY KEY,
            book_id TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            dimension TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            term TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        """
    )
    db.commit()
    db.close()
    return db_path


def test_empty_db() -> None:
    """空库：指标全为空值/0，不崩溃。"""
    s = compute_stats(_make_db())
    assert s["modify_rate"]["overall"] is None
    assert s["modify_rate"]["total"] == 0
    assert s["question_rate"]["overall_per_1k_chars"] is None
    assert s["completion_rate"]["directions"] == 0
    assert s["completion_rate"]["chapters"] == 0
    assert s["completion_rate"]["direction_to_chapter"] is None


def test_modify_rate() -> None:
    """修改率 = 判别型信号中非接受占比；按天分桶趋势。"""
    db_path = _make_db()
    db = sqlite3.connect(str(db_path))
    kinds = [
        ("accepted", "2026-08-01T10:00:00"),
        ("accepted", "2026-08-01T11:00:00"),
        ("modified", "2026-08-01T12:00:00"),
        ("modified", "2026-08-02T10:00:00"),
        ("deleted", "2026-08-02T11:00:00"),
    ]
    db.executemany("INSERT INTO signals (kind, content, created_at) VALUES (?, '', ?)", kinds)
    db.commit()
    db.close()

    mr = compute_stats(db_path)["modify_rate"]
    assert mr["total"] == 5
    assert mr["accepted"] == 2
    assert mr["changed"] == 3
    assert mr["overall"] == 0.6
    # 按天分桶：8-01 桶 2 接受 1 改动 → 1/3；8-02 桶 0 接受 2 改动 → 1.0
    assert mr["by_day"][0] == {"bucket": "2026-08-01", "rate": round(1 / 3, 3), "total": 3}
    assert mr["by_day"][1] == {"bucket": "2026-08-02", "rate": 1.0, "total": 2}


def test_modify_rate_ignores_non_judge_kinds() -> None:
    """custom/locked 等非判别型信号不计入修改率。"""
    db_path = _make_db()
    db = sqlite3.connect(str(db_path))
    db.executemany(
        "INSERT INTO signals (kind, content, created_at) VALUES (?, '', ?)",
        [("accepted", "2026-08-01T10:00:00"), ("custom", "2026-08-01T11:00:00")],
    )
    db.commit()
    db.close()

    mr = compute_stats(db_path)["modify_rate"]
    assert mr["total"] == 1
    assert mr["overall"] == 0.0


def test_question_rate() -> None:
    """提问率：AI 每千字问句数；按会话先后排序。"""
    db_path = _make_db()
    db = sqlite3.connect(str(db_path))
    # 会话 A：1000 字含 2 问句；会话 B：500 字含 1 问句
    db.executemany(
        "INSERT INTO messages (conversation_id, role, content, seq, created_at) "
        "VALUES (?, 'assistant', ?, 0, '2026-08-01T10:00:00')",
        [
            ("conv-a", "他推开窗。雾来了吗？雨停了吗？" + "续" * 985),
            ("conv-b", "他坐下。接下来呢？" + "续" * 491),
        ],
    )
    db.commit()
    db.close()

    qr = compute_stats(db_path)["question_rate"]
    assert qr["total_chars"] == 1500
    assert qr["total_questions"] == 3
    assert qr["overall_per_1k_chars"] == 2.0
    assert [c["conversation_id"] for c in qr["by_conversation"]] == ["conv-a", "conv-b"]
    assert qr["by_conversation"][0]["questions"] == 2
    assert qr["by_conversation"][1]["questions"] == 1


def test_completion_rate() -> None:
    """完成率漏斗：方向固化 2 → 章节 1，direction_to_chapter = 0.5。"""
    db_path = _make_db()
    db = sqlite3.connect(str(db_path))
    db.executemany(
        "INSERT INTO archived_directions (id, book_id, title, created_at) "
        "VALUES (?, 'main', ?, '2026-08-01')",
        [("d1", "方向A"), ("d2", "方向B")],
    )
    db.execute(
        "INSERT INTO chapters (id, book_id, title, content, created_at, updated_at) "
        "VALUES ('c1', 'main', '第一章', '正文', '2026-08-01', '2026-08-01')"
    )
    db.commit()
    db.close()

    cr = compute_stats(db_path)["completion_rate"]
    assert cr["directions"] == 2
    assert cr["chapters"] == 1
    assert cr["direction_to_chapter"] == 0.5
    assert "种子层未落盘" in cr["note"]


def test_stats_api_endpoint() -> None:
    """GET /api/stats 返回三指标结构（注入 fake model，不走网络）。"""
    db_path = _make_db()
    db = sqlite3.connect(str(db_path))
    db.execute(
        "INSERT INTO signals (kind, content, created_at) "
        "VALUES ('accepted', '', '2026-08-01T10:00:00')"
    )
    db.commit()
    db.close()

    class FakeModel:
        def __init__(self) -> None:
            self.model_name = "fake-stats"

        def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
            raise AssertionError("stats 端点不应调用模型")

    app = build_app(model=FakeModel(), db_path=db_path)
    client = TestClient(app)
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"modify_rate", "question_rate", "completion_rate"}
    assert body["modify_rate"]["total"] == 1
    assert body["modify_rate"]["overall"] == 0.0
