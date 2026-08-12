"""S99 会话消息队列路由测试（排队接力第一步：排队/查看/删/转插入）。

覆盖：入队 → 查看 → 删除（含删空清理）→ 转插入失败分支（未运行/不存在）；
成功分支（运行中 steer+移除）依赖 active_agents 注入，HTTP 层无法稳定构造，
逻辑简单（steer + 移除，与失败分支共享移除路径），以代码审查保证。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from anyspark.core import ModelOutput
from anyspark.server.app import build_app


def _client() -> TestClient:
    return TestClient(build_app(db_path=":memory:"))


def test_queue_enqueue_and_list() -> None:
    client = _client()
    # 入队两条
    r = client.post(
        "/api/chat/queue", json={"conversation_id": "conv-1", "message": "第一章改含蓄点"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert len(body["queue"]) == 1
    item_id = body["queue"][0]["id"]
    assert body["queue"][0]["text"] == "第一章改含蓄点"

    r = client.post("/api/chat/queue", json={"conversation_id": "conv-1", "message": "结局反转"})
    assert r.status_code == 200
    assert len(r.json()["queue"]) == 2

    # 查看：队列含 conv-1 两条；无运行中会话
    r = client.get("/api/chat/queues")
    assert r.status_code == 200
    status = r.json()
    assert "conv-1" in status["queues"]
    assert len(status["queues"]["conv-1"]) == 2
    assert status["running"] == []

    # 删除第一条 → 剩一条
    r = client.delete(f"/api/chat/queue/conv-1/{item_id}")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert len(r.json()["queue"]) == 1

    # 删除最后一条 → 键清理（queues 不再含 conv-1）
    last_id = r.json()["queue"][0]["id"]
    r = client.delete(f"/api/chat/queue/conv-1/{last_id}")
    assert r.json()["ok"] is True
    assert r.json()["queue"] == []
    r = client.get("/api/chat/queues")
    assert "conv-1" not in r.json()["queues"]


def test_queue_delete_missing_item() -> None:
    client = _client()
    r = client.delete("/api/chat/queue/conv-x/not-exist")
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_queue_steer_rejects_idle_session_and_keeps_item() -> None:
    """转插入：会话未运行时 ok=False 且队列项保留（区别于删除，不丢指令）。"""
    client = _client()
    r = client.post(
        "/api/chat/queue", json={"conversation_id": "conv-idle", "message": "别写太血腥"}
    )
    item_id = r.json()["queue"][0]["id"]

    r = client.post(f"/api/chat/queue/conv-idle/{item_id}/steer")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "未在运行" in body["reason"]
    # 队列项仍在
    r = client.get("/api/chat/queues")
    assert len(r.json()["queues"]["conv-idle"]) == 1


def test_queue_steer_missing_item() -> None:
    client = _client()
    r = client.post("/api/chat/queue/conv-missing/not-exist/steer")
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "不存在" in r.json()["reason"]


def test_delete_conversation_clears_queue() -> None:
    """S99：删除会话顺带清空其排队消息。"""
    client = _client()
    # 建会话
    r = client.post("/api/conversations", json={"title": "会话A", "book_id": "main"})
    conv_id = r.json()["id"]
    client.post("/api/chat/queue", json={"conversation_id": conv_id, "message": "排队中"})
    assert client.get("/api/chat/queues").json()["queues"].get(conv_id)

    r = client.delete(f"/api/conversations/{conv_id}")
    assert r.status_code == 200
    status = client.get("/api/chat/queues").json()
    assert conv_id not in status["queues"]


# ---------------------------------------------------------------------------
# S99 第二步：SSE 循环化接力执行（单连接跑完整条队列）
# ---------------------------------------------------------------------------


class _RelayModel:
    """fake model：每轮 respond 直接返回文本（无工具调用，一轮一次）。"""

    def __init__(self) -> None:
        self.calls = 0
        self.model_name = "fake-relay"

    def respond(self, messages, tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        self.calls += 1
        return ModelOutput(text=f"第{self.calls}轮回复")


def _relay_client() -> TestClient:
    from anyspark.server.app import build_app

    return TestClient(build_app(db_path=":memory:", model=_RelayModel()))


def test_stream_relay_consumes_queue() -> None:
    """S99 第二步：首轮完成后自动消费队列——queue_consume 帧 2 次、done rounds=3、队列清空。"""
    client = _relay_client()
    r = client.post("/api/conversations", json={"title": "会话", "book_id": "main"})
    conv_id = r.json()["id"]
    client.post("/api/chat/queue", json={"conversation_id": conv_id, "message": "接力一"})
    client.post("/api/chat/queue", json={"conversation_id": conv_id, "message": "接力二"})

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "首条", "conversation_id": conv_id},
    ) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())

    # 两条 queue_consume 帧（文本 + 剩余数递减）
    assert body.count("queue_consume") == 2
    assert '"remaining": 1' in body
    assert '"remaining": 0' in body
    # 三轮文本都流式输出（text_delta 帧含各轮回复）+ 最终 done 帧带 rounds=3
    assert "第1轮回复" in body
    assert "第2轮回复" in body
    assert "第3轮回复" in body
    assert '"rounds": 3' in body
    # 队列已被消费清空
    status = client.get("/api/chat/queues").json()
    assert conv_id not in status["queues"]


def test_stream_relay_empty_queue_single_round() -> None:
    """S99 第二步：无队列时保持单轮行为（done rounds=1，无 queue_consume）。"""
    client = _relay_client()
    r = client.post("/api/conversations", json={"title": "会话", "book_id": "main"})
    conv_id = r.json()["id"]

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "单独一轮", "conversation_id": conv_id},
    ) as resp:
        body = "".join(resp.iter_text())

    assert "queue_consume" not in body
    assert '"rounds": 1' in body
