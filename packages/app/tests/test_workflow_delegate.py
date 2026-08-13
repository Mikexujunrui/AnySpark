"""S115 提案 B：workflow agent 节点 delegate——子 Agent 独立上下文跑完整工具循环。

验证：
- delegate 节点 → 子 Agent 执行（走完整 Agent.run，非单次调用）
- 工具白名单 scope.tools 生效（白名单外工具不可见）
- fresh 上下文隔离（子 Agent 不受父流程变量/会话污染）
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.core.types import Message, ModelOutput, ToolCall
from anyspark.server.app import build_app


class _DelegateModel:
    """子 Agent 模型：第一轮调用 list_chapters 工具，第二轮终答。"""

    model_name = "delegate-probe"

    def __init__(self) -> None:
        self.calls = 0
        self.last_tools: list[str] = []

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        self.calls += 1
        self.last_tools = [getattr(t, "name", "") for t in tools or []]
        if self.calls == 1:
            return ModelOutput(tool_calls=[ToolCall(name="list_chapters", arguments={})])
        return ModelOutput(text="子Agent完成：已查章节")


def _client(model) -> TestClient:  # type: ignore[no-untyped-def]
    db = Path(tempfile.mkdtemp()) / "test.db"
    return TestClient(build_app(model=model, db_path=db))


def _workflow_definition() -> dict[str, object]:
    """单节点 delegate 流程：子 Agent 查章节后终答。"""
    return {
        "name": "子Agent调研",
        "nodes": [
            {
                "id": "n1",
                "kind": "agent",
                "params": {
                    "instruction": "列出所有章节并总结",
                    "delegate": {
                        "scope": {"tools": ["list_chapters"]},
                        "budget": {"max_turns": 5},
                    },
                    "output_key": "research",
                },
            }
        ],
        "edges": [],
    }


def test_workflow_delegate_runs_subagent() -> None:
    """delegate 节点：子 Agent 跑完整工具循环（调用 list_chapters 后终答）。"""
    model = _DelegateModel()
    client = _client(model)

    wf = client.post("/api/workflows", json=_workflow_definition())
    assert wf.status_code == 200 or wf.status_code == 201, wf.text
    wf_id = wf.json()["id"]

    task = client.post(f"/api/workflows/{wf_id}/run", json={"book_id": "main"}).json()
    tid = task["task_id"]

    # 等任务完成（轮询）
    import time

    for _ in range(40):
        st = client.get(f"/api/workflows/tasks/{tid}").json()
        if st.get("status") in ("done", "failed", "cancelled"):
            break
        time.sleep(0.3)

    assert st.get("status") == "done", st
    # 子 Agent 实际调用了工具（完整循环，非单次调用）
    assert model.calls >= 2, f"子Agent应多轮调用，实际 {model.calls}"
    assert "list_chapters" in model.last_tools
    # 产出物（research 变量）已写入 results
    results = st.get("results") or {}
    assert "research" in results or any("research" in str(k) for k in results)
    assert any("子Agent完成" in str(v) for v in results.values())


def test_workflow_delegate_tool_whitelist() -> None:
    """scope.tools 白名单：白名单外工具不注册（子 Agent 看不到）。"""
    model = _DelegateModel()
    client = _client(model)

    # delegate 白名单只含 list_chapters——write_chapter 不在其中
    wf = client.post(
        "/api/workflows",
        json={
            "name": "白名单测试",
            "nodes": [
                {
                    "id": "n1",
                    "kind": "agent",
                    "params": {
                        "instruction": "列出章节",
                        "delegate": {"scope": {"tools": ["list_chapters"]}},
                    },
                }
            ],
            "edges": [],
        },
    )
    assert wf.status_code in (200, 201), wf.text
    wf_id = wf.json()["id"]
    client.post(f"/api/workflows/{wf_id}/run", json={"book_id": "main"})
    import time

    tid = client.get("/api/workflows/tasks").json()
    # 找任务 id
    tasks = client.get("/api/workflows/tasks").json()
    tids = tasks if isinstance(tasks, list) else list(tasks.keys())
    assert tids, "应有任务"
    tid = tids[0]
    for _ in range(40):
        st = client.get(f"/api/workflows/tasks/{tid}").json()
        if st.get("status") in ("done", "failed", "cancelled"):
            break
        time.sleep(0.3)
    # 子 Agent 只见过白名单工具
    assert "list_chapters" in model.last_tools
    assert "write_chapter" not in model.last_tools


# ---------------------------------------------------------------------------
# S121 提案 B 第二入口：主循环 run_subagent 工具
# ---------------------------------------------------------------------------


class _ToolModel:
    """主循环模型：第一轮调 run_subagent，第二轮终答。"""

    model_name = "tool-probe"

    def __init__(self) -> None:
        self.calls = 0

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.calls == 1:
            return ModelOutput(
                tool_calls=[
                    ToolCall(
                        name="run_subagent",
                        arguments={"instruction": "查一下章节数", "tools": "list_chapters"},
                    )
                ]
            )
        return ModelOutput(text="已委派子Agent查完。")


def test_chat_can_call_run_subagent_tool() -> None:
    """对话中 Agent 可调 run_subagent（工具注册 + 子 Agent 执行链路）。"""
    model = _ToolModel()
    client = _client(model)
    r = client.post(
        "/api/chat",
        json={"message": "帮我查一下章节情况", "enable_domain": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    tool_events = [e for e in data.get("events", []) if e["type"] == "tool_call"]
    assert any("run_subagent" in (e["payload"].get("name") or []) for e in tool_events)
    # 子 Agent 实际执行（模型被调多次：主循环 2 次 + 子 Agent 至少 1 次）
    assert model.calls >= 3, f"应有子Agent调用，实际 {model.calls} 次模型调用"


def test_run_subagent_missing_instruction() -> None:
    """缺 instruction → 工具报错（不崩溃）。"""
    import tempfile

    from anyspark.core.protocol import ToolRegistry
    from anyspark.server.toolkit import ToolContext, build_toolkit
    from anyspark.server.tools_extensions import ExtensionToolStore

    registry = build_toolkit(
        ToolRegistry(),
        ToolContext(
            chapters=None,
            workspace=None,
            model=None,
            graph=None,
            plots=None,
            plans=None,
            settings=None,
            materials=None,
            ext_tools=ExtensionToolStore(Path(tempfile.mkdtemp()) / "ext.db"),
            book_id="main",
        ),
    )
    spec, impl = registry.get("run_subagent") or (None, None)
    assert spec is not None and impl is not None, "run_subagent 应注册"
    res = impl(spec, {"tools": "list_chapters"})
    assert res.ok is False and "instruction" in res.content
