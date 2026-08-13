"""S49 运行记录器：完整上下文 + 思维链 JSONL，修 bug/训练素材。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from anyspark.core.types import Message, ModelOutput, ToolCall
from anyspark.server.recorder import RunRecorder


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "t.db"


class _RecModel:
    """模拟：第一轮带思维链+工具调用，第二轮终答。"""

    model_name = "rec-probe"

    def __init__(self) -> None:
        self.calls = 0

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.calls == 1:
            return ModelOutput(
                tool_calls=[ToolCall(name="list_chapters", arguments={})],
                reasoning="先看有没有章节，再决定怎么写。",
            )
        return ModelOutput(text="写好了。", reasoning="无需工具，直接收尾。")


def test_recorder_captures_full_turn_with_reasoning() -> None:
    """record 事件：含完整 prompt 上下文 + 思维链 + 工具调用，落 JSONL。"""
    root = Path(tempfile.mkdtemp()) / "records"
    rec = RunRecorder(root=root)
    model = _RecModel()

    # 直接构造一个最小 agent 验证 attach（不依赖 build_app 的默认 recorder）
    from anyspark.core import Agent, ToolRegistry
    from anyspark.server.app import DEFAULT_SYSTEM

    reg = ToolRegistry()
    from anyspark.server.tools_writing import register_writing_tools
    from anyspark.store import ChapterStore

    register_writing_tools(reg, ChapterStore(_db()))
    from anyspark.store import SqliteConversationStore

    agent = Agent(
        model=model,
        registry=reg,
        store=SqliteConversationStore(_db()),
        system_prompt=DEFAULT_SYSTEM,
    )
    conv = agent.store.create()
    rec.attach(agent, conv.id, {"ts": "t0", "model": "probe"})
    agent.run("写一章", conv.id)

    meta = json.loads((root / conv.id / "meta.json").read_text(encoding="utf-8"))
    assert meta["model"] == "probe"
    lines = (root / conv.id / "events.jsonl").read_text(encoding="utf-8").strip().split("\n")
    events = [json.loads(ln) for ln in lines]
    # 至少两轮（工具轮 + 终答轮）
    assert len(events) >= 2
    first = events[0]
    assert first["prompt"]  # 完整上下文快照（含系统提示）
    assert first["prompt"][0]["role"] == "system"
    # 思维链保留
    reasoning = [e["output"]["reasoning"] for e in events if e["output"]["reasoning"]]
    assert any("先看有没有章节" in r for r in reasoning)
    # 工具调用记录
    assert events[0]["output"]["tool_calls"][0]["name"] == "list_chapters"
    # 思维链不注入上下文：store 里没有 reasoning
    msgs = agent.store.messages(conv.id)
    assert all("先看有没有章节" not in (m.content or "") for m in msgs)


def _compress(msgs: list[Message]) -> list[Message]:
    """模拟上下文压缩器：压掉中间历史，只留首尾（触发 context_compressed）。"""
    if len(msgs) <= 2:
        return msgs
    return [msgs[0], Message(role="assistant", content="（摘要：前面的对话被压缩）"), msgs[-1]]


def test_recorder_captures_system_events() -> None:
    """S116 事件溯源：context_compressed + steering_injected 落盘（model 所见如何被改变）。"""
    root = Path(tempfile.mkdtemp()) / "records"
    rec = RunRecorder(root=root)

    class _SteerModel:
        model_name = "steer-probe"

        def __init__(self) -> None:
            self.calls = 0

        def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                return ModelOutput(tool_calls=[ToolCall(name="list_chapters", arguments={})])
            return ModelOutput(text="终答。")

    from anyspark.core import Agent, ToolRegistry
    from anyspark.server.app import DEFAULT_SYSTEM
    from anyspark.server.tools_writing import register_writing_tools
    from anyspark.store import ChapterStore, SqliteConversationStore

    reg = ToolRegistry()
    register_writing_tools(reg, ChapterStore(_db()))
    model = _SteerModel()
    agent = Agent(
        model=model,
        registry=reg,
        store=SqliteConversationStore(_db()),
        system_prompt=DEFAULT_SYSTEM,
        context_compressor=_compress,  # 每轮触发压缩（多轮后变短）
        persist_compression=True,
    )
    conv = agent.store.create()
    rec.attach(agent, conv.id, {"ts": "t0", "model": "steer-probe"})

    # 工具轮后注入 steering，再继续
    agent.run("写一章", conv.id)
    agent.steer("别写太血腥")
    agent.run("继续", conv.id)

    lines = (root / conv.id / "events.jsonl").read_text(encoding="utf-8").strip().split("\n")
    events = [json.loads(ln) for ln in lines]
    kinds = {e.get("event", "record") for e in events}
    assert "record" in kinds
    assert "steering_injected" in kinds
    steer_ev = next(e for e in events if e.get("event") == "steering_injected")
    assert steer_ev["content"] == "别写太血腥"
    assert steer_ev["source"] == "steer"


def test_records_api_endpoint() -> None:
    """S116：GET /api/records/{conv_id} 返回 meta + 事件序列（回放）。"""
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    m = _Probe()
    client = TestClient(build_app(model=m, db_path=_db()))
    r = client.post(
        "/api/chat",
        json={"message": "写《第1章》10字：晨光。", "book_id": "main"},
    )
    assert r.status_code == 200
    conv_id = r.json()["conversation_id"]
    rr = client.get(f"/api/records/{conv_id}")
    assert rr.status_code == 200
    data = rr.json()
    assert data["ok"] is True
    assert data["meta"]["endpoint"] == "chat"
    assert isinstance(data["events"], list)
    assert any(e.get("event", "record") == "record" for e in data["events"])


class _Probe:
    """终答模型（build_app 装配用）。"""

    model_name = "probe"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        return ModelOutput(text="晨光洒落，新的一天。")
