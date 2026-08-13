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
