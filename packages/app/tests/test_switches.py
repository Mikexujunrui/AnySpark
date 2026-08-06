"""S15 增强按需装配开关测试：enable_search / extract_graph / skip_inject。

哲学依据（DESIGN §1/§4）："你要什么再装什么"——组合根装配一切增强，
但增强默认关闭或可细粒度关闭。这些开关让写作主链路保持轻量。
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.core.types import Message, ModelOutput, ToolCall
from anyspark.server.app import build_app


class ProbeModel:
    """记录每次 respond 收到的 system_prompt 与 tools（验证注入/工具注册开关）。"""

    def __init__(self) -> None:
        self.model_name = "probe"
        self.prompts: list[str] = []
        self.tool_names: list[list[str]] = []

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        # 系统提示 = 第一条 user 角色消息之前…Agent 会把 system_prompt 作为 system 消息
        for m in messages:
            if m.role == "system":
                self.prompts.append(m.content)
                break
        self.tool_names.append([t.name for t in tools])
        return ModelOutput(text="好的。")


def _client(model: ProbeModel) -> TestClient:
    db = Path(tempfile.mkdtemp()) / "test.db"
    return TestClient(build_app(model=model, db_path=db))


def test_search_tool_default_off() -> None:
    """enable_search 默认关：写作 Agent 不带 search_web（主链路轻量）。"""
    m = ProbeModel()
    client = _client(m)
    resp = client.post("/api/chat", json={"message": "写一段"})
    assert resp.status_code == 200
    assert m.tool_names, "Agent 应调用过 respond"
    assert "search_web" not in m.tool_names[0]


def test_search_tool_on_demand() -> None:
    """enable_search=true：search_web 注册进工具表（需要考据时点亮）。"""
    m = ProbeModel()
    client = _client(m)
    resp = client.post("/api/chat", json={"message": "考据一下", "enable_search": True})
    assert resp.status_code == 200
    assert any("search_web" in names for names in m.tool_names)


def test_skip_inject_disables_all_blocks() -> None:
    """skip_inject 全跳过：系统提示无任何注入块（纯对话最小化模式）。"""
    m = ProbeModel()
    client = _client(m)
    resp = client.post(
        "/api/chat",
        json={
            "message": "hi",
            "skip_inject": ["manual", "graph", "agency", "bias", "mood"],
        },
    )
    assert resp.status_code == 200
    prompt = m.prompts[-1]
    for marker in ("说明书", "当前时空点", "能动", "倾向", "氛围要求"):
        assert marker not in prompt, f"注入块未跳过: {marker}"


def test_mood_inject_default_on_and_skippable() -> None:
    """mood 注入默认生效；skip_inject=['mood'] 时可单独关闭。"""
    m = ProbeModel()
    client = _client(m)
    resp = client.post("/api/chat", json={"message": "写", "mood": {"tension": 80}})
    assert resp.status_code == 200
    # S50：数值语义化——注入块是程度词+描述，不是 80/100
    assert "氛围要求" in m.prompts[-1] and "紧张感：较强" in m.prompts[-1]
    assert "80/100" not in m.prompts[-1]

    m2 = ProbeModel()
    client2 = _client(m2)
    resp2 = client2.post(
        "/api/chat", json={"message": "写", "mood": {"tension": 80}, "skip_inject": ["mood"]}
    )
    assert resp2.status_code == 200
    assert "氛围要求" not in m2.prompts[-1]


def test_extract_graph_switch() -> None:
    """extract_graph 默认开（章节落盘后自动抽取）；false 时不抽取（省 token）。"""

    class GraphModel:
        """第一次写章节，第二次（图谱抽取）返回抽取 JSON。"""

        def __init__(self) -> None:
            self.calls = 0
            self.model_name = "graph-switch"

        def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                return ModelOutput(
                    tool_calls=[
                        ToolCall(
                            name="write_chapter",
                            arguments={"title": "第一章", "content": "雾城，雨夜，陈渡抵达。"},
                        )
                    ]
                )
            return ModelOutput(
                text='{"entities": [{"name": "陈渡", "type": "角色", "aliases": [],'
                ' "description": "侦探"}], "relations": [], "events": []}'
            )

    def entity_count(db_path: Path) -> int:
        import sqlite3

        db = sqlite3.connect(str(db_path))
        try:
            n = db.execute("SELECT COUNT(*) FROM graph_entities").fetchone()[0]
            return int(n)
        finally:
            db.close()

    # 默认开：抽取入库（后台 worker 异步——轮询等待，S7 既有踩坑）
    db = Path(tempfile.mkdtemp()) / "on.db"
    client = TestClient(build_app(model=GraphModel(), db_path=db))
    resp = client.post("/api/chat", json={"message": "写第一章"})
    assert resp.status_code == 200
    for _ in range(40):  # 最多等 4s（后台抽取正常秒级完成）
        if entity_count(db) == 1:
            break
        time.sleep(0.1)
    assert entity_count(db) == 1

    # 关闭：不抽取（写章节但不入库）
    db2 = Path(tempfile.mkdtemp()) / "off.db"
    client2 = TestClient(build_app(model=GraphModel(), db_path=db2))
    resp2 = client2.post("/api/chat", json={"message": "写第一章", "extract_graph": False})
    assert resp2.status_code == 200
    time.sleep(0.5)  # 给后台任务一点余量（正常应立即完成）
    assert entity_count(db2) == 0
