"""anyspark.server.app — FastAPI 路由测试（注入 fake model，不走网络）。"""

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.core.types import Message, ModelOutput, ToolCall
from anyspark.server.app import build_app


class FakeWritingModel:
    """fake model：第一次回 tool_call 调 write_chapter，第二次回最终文本。"""

    def __init__(self) -> None:
        self.calls = 0
        self.model_name = "fake-model"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.calls == 1:
            return ModelOutput(
                tool_calls=[
                    ToolCall(
                        name="write_chapter",
                        arguments={"title": "第一章", "content": "雨夜，陈渡抵达雾城站。"},
                    )
                ]
            )
        return ModelOutput(text="第一章已写好。")


def _make_client() -> TestClient:
    db = Path(tempfile.mkdtemp()) / "test.db"
    app = build_app(model=FakeWritingModel(), db_path=db)
    return TestClient(app)


def test_health() -> None:
    client = _make_client()
    assert client.get("/api/health").status_code == 200


def test_chat_writes_chapter() -> None:
    client = _make_client()
    resp = client.post("/api/chat", json={"message": "写第一章"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["conversation_id"]
    # 写入的章节可见
    chapters = client.get("/api/chapters").json()
    assert chapters, "应有被写入的章节"
    assert chapters[0]["title"] == "第一章"
    assert "雨夜，陈渡" in chapters[0]["content"]


def test_chat_uses_same_conversation_for_continuation() -> None:
    client = _make_client()
    first = client.post("/api/chat", json={"message": "写第一章"}).json()
    conv_id = first["conversation_id"]
    second = client.post("/api/chat", json={"message": "续写", "conversation_id": conv_id})
    assert second.status_code == 200
    assert second.json()["conversation_id"] == conv_id


def test_manual_crud_via_api() -> None:
    client = _make_client()
    # 新增
    r = client.post("/api/manual", json={"content": "不要破折号", "confidence": 0.9})
    assert r.status_code == 200
    entry_id = r.json()["id"]
    assert r.json()["source"] == "user"
    # 列出
    entries = client.get("/api/manual?scope=project").json()
    assert any(e["id"] == entry_id for e in entries)
    # 锁定
    r2 = client.patch(f"/api/manual/{entry_id}", json={"locked": True})
    assert r2.status_code == 200
    assert r2.json()["locked"] is True
    # 删除
    r3 = client.delete(f"/api/manual/{entry_id}")
    assert r3.status_code == 200
    entries = client.get("/api/manual?scope=project").json()
    assert not any(e["id"] == entry_id for e in entries)


def test_record_signal_via_api() -> None:
    client = _make_client()
    r = client.post(
        "/api/signals",
        json={"kind": "modified", "content": "原文", "new_content": "新文", "context": "稿纸"},
    )
    assert r.status_code == 200
    assert r.json()["kind"] == "modified"
    assert r.json()["context"] == "稿纸"


def test_check_rule_via_api() -> None:
    client = _make_client()
    r = client.post(
        "/api/check/rule",
        json={"rule": "不要破折号", "text": "他——她走了。"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["hits"]  # 命中破折号


def test_check_unknown_rule_via_api() -> None:
    client = _make_client()
    r = client.post("/api/check/rule", json={"rule": "今天天气不错", "text": "abc"})
    assert r.status_code == 200
    assert r.json()["ok"] is False
