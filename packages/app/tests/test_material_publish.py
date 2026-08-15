"""S123 提案 D：项目 → 全局池提交通道（/api/materials/publish）。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.core.types import Message, ModelOutput
from anyspark.server.app import build_app


class _P:
    model_name = "probe"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        return ModelOutput(text="ok")


def _client() -> TestClient:
    db = Path(tempfile.mkdtemp()) / "t.db"
    return TestClient(build_app(model=_P(), db_path=db))


def test_publish_project_to_global() -> None:
    """项目 inspiration 卡 → publish → 全局池出现（inspiration 可见 + 溯源）。"""
    client = _client()
    # 项目池建一张 inspiration 卡（book_id=novel-a）
    created = client.post(
        "/api/materials",
        json={
            "book_id": "novel-a",
            "kind": "inspiration",
            "title": "雾城设定",
            "text": "雾城是江边之城，常年有雾。",
            "purpose": "fact",
        },
    )
    assert created.status_code == 200, created.text
    card_id = created.json()["id"]

    # 发布到全局
    r = client.post(
        "/api/materials/publish",
        json={"card_id": card_id, "from_book_id": "novel-a"},
    )
    assert r.status_code == 200, r.text
    pub = r.json()
    assert pub["kind"] == "inspiration"  # 发布=贡献，非 copy 冷藏
    assert pub["source_ref"] == f"project:novel-a:{card_id}"

    # 全局池可见
    gl = client.get("/api/materials", params={"book_id": "global"}).json()
    assert any(m["id"] == pub["id"] and m["title"] == "雾城设定" for m in gl)
    # 源项目卡保留（复制非移动）
    src = client.get("/api/materials", params={"book_id": "novel-a"}).json()
    assert any(m["id"] == card_id for m in src)


def test_publish_validation() -> None:
    """发布校验：非本池卡 / copy 卡 / 全局卡 → 明确报错。"""
    client = _client()
    created = client.post(
        "/api/materials",
        json={"book_id": "novel-a", "kind": "inspiration", "title": "X", "text": "内容"},
    ).json()
    card_id = created["id"]

    # 跨池（卡在 novel-a，声称为 novel-b）
    r = client.post("/api/materials/publish", json={"card_id": card_id, "from_book_id": "novel-b"})
    assert r.status_code == 400 and "不在项目" in r.json()["detail"]

    # copy 卡不能发布
    copy_id = client.post(
        "/api/materials",
        json={"book_id": "novel-a", "kind": "copy", "title": "Y", "text": "内容"},
    ).json()["id"]
    r2 = client.post("/api/materials/publish", json={"card_id": copy_id, "from_book_id": "novel-a"})
    assert r2.status_code == 400 and "inspiration" in r2.json()["detail"]

    # 全局卡再发布 → 400
    gid = client.post(
        "/api/materials",
        json={"book_id": "global", "kind": "inspiration", "title": "Z", "text": "内容"},
    ).json()["id"]
    r3 = client.post("/api/materials/publish", json={"card_id": gid, "from_book_id": "global"})
    assert r3.status_code == 400
