"""anyspark.server.app — FastAPI 路由测试（注入 fake model，不走网络）。"""

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.core.types import Message, ModelOutput, ToolCall
from anyspark.server.app import build_app


class FakeWritingModel:
    """fake model：第一次回 tool_call 调 write_chapter，第二次回最终文本，
    第三次（后台图谱抽取）回抽取 JSON。"""

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
        if self.calls == 2:
            return ModelOutput(text="第一章已写好。")
        # 后台图谱抽取（S7）：返回实体 JSON
        return ModelOutput(
            text='{"entities": [{"name": "陈渡", "type": "角色", "aliases": [], '
            '"description": "雨夜抵达雾城的侦探"}, {"name": "雾城", "type": "地点", '
            '"aliases": [], "description": "故事发生的城市"}], '
            '"relations": [{"from": "陈渡", "to": "雾城", "type": "抵达", '
            '"description": "陈渡抵达雾城"}], "events": []}'
        )


class FakeExtractModel:
    """fake model：始终返回图谱抽取 JSON（手动抽取路由测试用）。"""

    def __init__(self) -> None:
        self.model_name = "fake-extract"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        return ModelOutput(
            text='{"entities": [{"name": "沈歆", "type": "角色", "aliases": ["沈姑娘"], '
            '"description": "陈渡的妹妹"}, {"name": "雾城钟表铺", "type": "地点", '
            '"aliases": [], "description": "城西的钟表铺"}], '
            '"relations": [{"from": "沈歆", "to": "陈渡", "type": "兄妹", '
            '"description": "亲兄妹"}], '
            '"events": [{"time_point": "第二章", "label": "兄妹相认", '
            '"description": "沈歆在钟表铺等陈渡", "involved": ["沈歆", "陈渡"]}]}'
        )


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


def test_chat_auto_extracts_graph() -> None:
    """S7：write_chapter 落盘后自动抽取图谱（后台任务同步执行）。"""
    client = _make_client()
    resp = client.post("/api/chat", json={"message": "写第一章"})
    assert resp.status_code == 200
    entities = client.get("/api/graph/entities").json()
    names = {e["name"] for e in entities}
    assert "陈渡" in names and "雾城" in names
    # 注入块非空（当前时空点已知事实）
    ctx = client.get("/api/graph/context").json()
    assert "已固化事实" in ctx["block"]


def test_graph_api_manual_extract() -> None:
    """S7：手动抽取路由（补抽/重抽），实体/关系/事件入库可见。"""
    db = Path(tempfile.mkdtemp()) / "test.db"
    app = build_app(model=FakeExtractModel(), db_path=db)
    client = TestClient(app)
    r = client.post(
        "/api/graph/extract",
        json={"chapter_ref": "第二章", "text": "沈歆在雾城钟表铺等他，兄妹相认。"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["entities"] >= 2 and body["relations"] >= 1 and body["events"] >= 1
    entities = client.get("/api/graph/entities").json()
    names = {e["name"] for e in entities}
    assert "沈歆" in names and "雾城钟表铺" in names
    relations = client.get("/api/graph/relations").json()
    assert any(rr["rel_type"] == "兄妹" for rr in relations)
    events = client.get("/api/graph/events").json()
    assert any(ev["label"] == "兄妹相认" for ev in events)
    # 事件引用的缺失实体（陈渡）被自动补建
    assert "陈渡" in {e["name"] for e in client.get("/api/graph/entities").json()}


def test_chat_stream_sse_frames() -> None:
    """S8：/api/chat/stream 返回 SSE 帧（事件协议 → 传输层）。

    fake model 无逐字流，但事件帧完整：turn_start → tool_call → text → done。
    """
    client = _make_client()
    r = client.post("/api/chat/stream", json={"message": "写第一章"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    body = r.text
    assert "event: turn_start" in body
    assert "event: tool_call" in body
    assert "event: text" in body
    assert "event: done" in body
    assert "conversation_id" in body
    # 图谱抽取也照常触发（后台任务）
    entities = client.get("/api/graph/entities").json()
    assert any(e["name"] == "陈渡" for e in entities)


def test_chat_stream_error_frame() -> None:
    """S8：异常转 error 帧，不中断连接。"""

    class BoomModel:
        model_name = "boom"

        def respond(self, messages, tools):  # type: ignore[no-untyped-def]
            raise RuntimeError("模型爆炸")

    db = Path(tempfile.mkdtemp()) / "test.db"
    app = build_app(model=BoomModel(), db_path=db)
    client = TestClient(app)
    r = client.post("/api/chat/stream", json={"message": "hi"})
    assert r.status_code == 200
    assert "event: error" in r.text
    assert "模型爆炸" in r.text


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


def test_templates_list() -> None:
    client = _make_client()
    r = client.get("/api/templates")
    assert r.status_code == 200
    templates = r.json()
    assert len(templates) >= 5
    assert templates[0]["granularity"]  # 四要素元数据
