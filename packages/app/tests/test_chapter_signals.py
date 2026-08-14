"""S132b 章节操作 → 信号 测试：稿纸保存/定点编辑 → modified；删除不发信号。

设计（克制）：只对**确定性操作**发信号（内容实际变化），不做语义猜测；
章节删除是管理操作（结构重排）不是内容否定，不发 deleted 信号防误提炼。
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from anyspark.core.types import Message, ModelOutput


class ProbeModel:
    def __init__(self) -> None:
        self.model_name = "probe"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        return ModelOutput(text="好的。")


def _signals(db: Path) -> list[dict]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT kind, content, context FROM signals ORDER BY rowid").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _client(tmp: Path):
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    return TestClient(build_app(model=ProbeModel(), db_path=tmp / "t.db"))


def _create(client, title: str = "第一章", content: str = "他慢慢地走进了房间。") -> str:
    r = client.post("/api/chapters", json={"title": title, "content": content})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_save_change_sends_modified_signal() -> None:
    db = Path(tempfile.mkdtemp())
    client = _client(db)
    cid = _create(client)
    # 内容变化保存 → modified 信号（稿纸保存）
    r = client.put(f"/api/chapters/{cid}", json={"content": "他推门进来。"})
    assert r.status_code == 200, r.text
    sigs = _signals(db / "t.db")
    assert len(sigs) == 1
    assert sigs[0]["kind"] == "modified"
    assert sigs[0]["context"] == "稿纸保存"
    assert "他推门进来" in sigs[0]["content"]


def test_save_no_change_no_signal() -> None:
    db = Path(tempfile.mkdtemp())
    client = _client(db)
    cid = _create(client)
    # 内容未变化保存 → 不刷信号
    client.put(f"/api/chapters/{cid}", json={"content": "他慢慢地走进了房间。"})
    assert _signals(db / "t.db") == []


def test_patch_change_sends_modified_signal() -> None:
    db = Path(tempfile.mkdtemp())
    client = _client(db)
    cid = _create(client)
    # 定点编辑（replace）→ modified 信号
    r = client.post(
        f"/api/chapters/{cid}/patch",
        json={"operations": [{"type": "replace", "anchor": "他慢慢地", "content": "他大步"}]},
    )
    assert r.status_code == 200, r.text
    sigs = _signals(db / "t.db")
    assert len(sigs) == 1
    assert sigs[0]["kind"] == "modified"
    assert sigs[0]["context"] == "定点编辑"


def test_delete_no_signal() -> None:
    db = Path(tempfile.mkdtemp())
    client = _client(db)
    cid = _create(client)
    # 删除章节是管理操作，不发 deleted 信号（防误提炼）
    r = client.delete(f"/api/chapters/{cid}")
    assert r.status_code == 200, r.text
    assert _signals(db / "t.db") == []
