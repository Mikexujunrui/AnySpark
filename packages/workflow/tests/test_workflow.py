"""anyspark-workflow 包测试（S59）：定义校验 / 条件解析 / 引擎三结构 / 断点恢复 / 生成器解析。"""

from __future__ import annotations

import os
import tempfile
import threading
from typing import Any

import pytest

from anyspark.workflow import (
    WorkflowDef,
    WorkflowEngine,
    WorkflowGenerator,
    WorkflowNode,
    WorkflowStore,
    evaluate_rule,
    wait_approval,
)
from anyspark.workflow.engine import NodeResult


# ---------------------------------------------------------------------------
# 定义模型
# ---------------------------------------------------------------------------
def _wf_dict() -> dict[str, Any]:
    return {
        "name": "质量把关",
        "nodes": [
            {
                "id": "n1",
                "kind": "agent",
                "params": {"instruction": "审读", "output_key": "review"},
            },
            {"id": "g", "kind": "gate"},
            {"id": "n3", "kind": "agent", "params": {"instruction": "改写", "output_key": "fixed"}},
            {"id": "n4", "kind": "approval", "params": {"prompt": "确认?"}},
        ],
        "edges": [
            {"source": "n1", "target": "g"},
            {
                "source": "g",
                "target": "n3",
                "condition": {"type": "rule", "expression": "{{review}} contains '硬伤'"},
            },
            {
                "source": "g",
                "target": "n4",
                "condition": {"type": "rule", "expression": "{{review}} NOT_CONTAINS '硬伤'"},
            },
            {"source": "n3", "target": "n4"},
        ],
    }


def test_definition_valid() -> None:
    wf = WorkflowDef.from_dict(_wf_dict())
    assert wf.validate() == []
    assert wf.start_node() is not None
    assert wf.start_node().id == "n1"  # type: ignore[union-attr]


def test_definition_invalid_unknown_edge() -> None:
    d = _wf_dict()
    d["edges"].append({"source": "nope", "target": "n1"})
    wf = WorkflowDef.from_dict(d)
    assert any("nope" in e for e in wf.validate())


def test_definition_loop_requires_max() -> None:
    d = _wf_dict()
    d["nodes"].append({"id": "l", "kind": "loop", "params": {"body": ["n1"]}})
    wf = WorkflowDef.from_dict(d)
    assert any("max_iterations" in e for e in wf.validate())


# ---------------------------------------------------------------------------
# 条件解析
# ---------------------------------------------------------------------------
def test_rule_comparisons() -> None:
    assert evaluate_rule("{{n}} > 0", {"n": 3}) is True
    assert evaluate_rule("{{n}} > 0", {"n": 0}) is False
    assert evaluate_rule('{{s}} == "done"', {"s": "done"}) is True


def test_rule_contains() -> None:
    assert evaluate_rule("{{s}} contains '硬伤'", {"s": "硬伤数: 2"}) is True
    assert evaluate_rule("{{s}} NOT_CONTAINS '硬伤'", {"s": "无问题"}) is True
    assert evaluate_rule("{{s}} NOT_CONTAINS '硬伤'", {"s": "硬伤数: 2"}) is False


def test_rule_logic() -> None:
    assert evaluate_rule('{{a}} > 1 AND {{b}} == "yes"', {"a": 5, "b": "yes"}) is True
    assert evaluate_rule('{{a}} > 1 AND {{b}} == "yes"', {"a": 0, "b": "yes"}) is False
    assert evaluate_rule("NOT {{a}} > 1", {"a": 0}) is True
    assert evaluate_rule("({{a}} > 1 OR {{a}} < 0) AND {{b}} == 'x'", {"a": 3, "b": "x"}) is True


def test_rule_default_and_missing() -> None:
    assert evaluate_rule("", {"a": 1}) is True  # 空=默认分支
    assert evaluate_rule("{{missing}} > 0", {}) is False  # 未定义=空串


# ---------------------------------------------------------------------------
# 引擎（fake runner）
# ---------------------------------------------------------------------------
class _FakeRunner:
    """审读永远报硬伤 → gate 走改写 → approval 等待。"""

    def __call__(self, ctx: object, node: WorkflowNode) -> NodeResult:
        n: WorkflowNode = node
        if n.kind == "approval":
            wait_approval()
        if node.params.get("instruction") == "审读":
            return NodeResult(output="硬伤数: 2")
        return NodeResult(output="已改写")


def _new_store() -> tuple[WorkflowStore, str]:
    db = os.path.join(tempfile.mkdtemp(), "wf.db")
    return WorkflowStore(db), db


def test_engine_sequence_gate_approval() -> None:
    store, _ = _new_store()
    wf = WorkflowDef.from_dict(_wf_dict())
    task_id = store.create_task(wf, book_id="main")
    eng = WorkflowEngine(store, _FakeRunner())

    def _run() -> None:
        eng.run_task(task_id)

    t = threading.Thread(target=_run)
    t.start()
    t.join(timeout=10)
    task = store.get_task(task_id)
    assert task is not None
    assert task["status"] == "waiting_approval"
    assert task["current_node_id"] == "n4"

    # 人工确认后续跑
    eng2 = WorkflowEngine(store, _FakeRunner())
    result = eng2.approve(task_id, decision="ok")
    assert result["status"] == "done"
    states = {s["node_id"]: s["status"] for s in result["node_states"]}
    assert states == {"n1": "done", "g": "done", "n3": "done", "n4": "done"}


def test_engine_loop_max_iterations() -> None:
    class LoopRunner:
        def __call__(self, ctx: object, node: WorkflowNode) -> NodeResult:
            if node.params.get("instruction") == "审读":
                return NodeResult(output="硬伤数: 1")  # 永远有硬伤 → 跑满
            return NodeResult(output="改完")

    store, _ = _new_store()
    wf = WorkflowDef.from_dict(
        {
            "name": "循环",
            "nodes": [
                {
                    "id": "l",
                    "kind": "loop",
                    "params": {
                        "body": ["n1", "n2"],
                        "max_iterations": 3,
                        "continue_condition": "{{review}} contains '硬伤'",
                    },
                },
                {
                    "id": "n1",
                    "kind": "agent",
                    "params": {"instruction": "审读", "output_key": "review"},
                },
                {
                    "id": "n2",
                    "kind": "agent",
                    "params": {"instruction": "改写", "output_key": "fixed"},
                },
                {
                    "id": "end",
                    "kind": "agent",
                    "params": {"instruction": "收尾", "output_key": "final"},
                },
            ],
            "edges": [{"source": "l", "target": "end"}],
        }
    )
    task_id = store.create_task(wf, book_id="main")
    result = WorkflowEngine(store, LoopRunner()).run_task(task_id)
    assert result["status"] == "done"
    loop_state = next(s for s in result["node_states"] if s["node_id"] == "l")
    assert "3" in loop_state["output"]  # 跑满 3 次防死循环


def test_engine_loop_break_early() -> None:
    class LoopBreakRunner:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, ctx: object, node: WorkflowNode) -> NodeResult:
            if node.params.get("instruction") == "审读":
                self.calls += 1
                if self.calls == 1:
                    return NodeResult(output="硬伤数: 2")
                return NodeResult(output="审读通过，无问题")  # 第二次通过 → 提前退出
            return NodeResult(output="改完")

    store, _ = _new_store()
    wf = WorkflowDef.from_dict(
        {
            "name": "循环早退",
            "nodes": [
                {
                    "id": "l",
                    "kind": "loop",
                    "params": {
                        "body": ["n1", "n2"],
                        "max_iterations": 5,
                        "continue_condition": "{{review}} contains '硬伤'",
                    },
                },
                {
                    "id": "n1",
                    "kind": "agent",
                    "params": {"instruction": "审读", "output_key": "review"},
                },
                {
                    "id": "n2",
                    "kind": "agent",
                    "params": {"instruction": "改写", "output_key": "fixed"},
                },
            ],
            "edges": [],
        }
    )
    task_id = store.create_task(wf, book_id="main")
    runner = LoopBreakRunner()
    result = WorkflowEngine(store, runner).run_task(task_id)
    assert result["status"] == "done"
    assert runner.calls == 2  # 第二次无硬伤 → 退出


def test_engine_auto_retry() -> None:
    class RetryRunner:
        def __init__(self) -> None:
            self.n = 0

        def __call__(self, ctx: object, node: WorkflowNode) -> NodeResult:
            if node.params.get("instruction") == "必失败":
                self.n += 1
                if self.n == 1:
                    return NodeResult(error="第一次失败")
                return NodeResult(output="第二次成功")
            return NodeResult(output="ok")

    store, _ = _new_store()
    wf = WorkflowDef.from_dict(
        {
            "name": "重试",
            "nodes": [
                {
                    "id": "a",
                    "kind": "agent",
                    "params": {"instruction": "必失败", "output_key": "x"},
                    "fail": {"auto_retry_count": 1},
                },
                {"id": "b", "kind": "agent", "params": {"instruction": "后续", "output_key": "y"}},
            ],
            "edges": [{"source": "a", "target": "b"}],
        }
    )
    task_id = store.create_task(wf, book_id="main")
    result = WorkflowEngine(store, RetryRunner()).run_task(task_id)
    assert result["status"] == "done"


def test_engine_fail_auto_skip() -> None:
    class SkipRunner:
        def __call__(self, ctx: object, node: WorkflowNode) -> NodeResult:
            if node.params.get("instruction") == "必败":
                return NodeResult(error="一直失败")
            return NodeResult(output="后续ok")

    store, _ = _new_store()
    wf = WorkflowDef.from_dict(
        {
            "name": "跳过",
            "nodes": [
                {
                    "id": "a",
                    "kind": "agent",
                    "params": {"instruction": "必败", "output_key": "x"},
                    "fail": {"fail_auto_skip": True},
                },
                {"id": "b", "kind": "agent", "params": {"instruction": "后续", "output_key": "y"}},
            ],
            "edges": [{"source": "a", "target": "b"}],
        }
    )
    task_id = store.create_task(wf, book_id="main")
    result = WorkflowEngine(store, SkipRunner()).run_task(task_id)
    assert result["status"] == "done"
    a_state = next(s for s in result["node_states"] if s["node_id"] == "a")
    assert a_state["status"] == "skipped"


def test_engine_task_failed_without_policy() -> None:
    class FailRunner:
        def __call__(self, ctx: object, node: WorkflowNode) -> NodeResult:
            return NodeResult(error="总是失败")

    store, _ = _new_store()
    wf = WorkflowDef.from_dict(
        {
            "name": "失败",
            "nodes": [
                {"id": "a", "kind": "agent", "params": {"instruction": "必败", "output_key": "x"}}
            ],
            "edges": [],
        }
    )
    task_id = store.create_task(wf, book_id="main")
    result = WorkflowEngine(store, FailRunner()).run_task(task_id)
    assert result["status"] == "failed"
    assert "失败" in result["error"]


# ---------------------------------------------------------------------------
# 生成器解析（fake model：直接返回预置 JSON）
# ---------------------------------------------------------------------------
class _FakeModel:
    def __init__(self, raw: str) -> None:
        self._raw = raw

    def respond(self, messages: object, tools: object) -> object:
        from anyspark.core import ModelOutput

        return ModelOutput(text=self._raw, tool_calls=[])


def test_generator_parse_and_validate() -> None:
    raw = """{"name":"章节审读","description":"审读+按需改写",
      "nodes":[{"id":"n1","kind":"agent","params":{"instruction":"审读当前章节","output_key":"review"}},
               {"id":"g","kind":"gate"},
               {"id":"n2","kind":"approval","params":{"prompt":"是否满意"}}],
      "edges":[{"source":"n1","target":"g"},
               {"source":"g","target":"n2","condition":{"type":"rule","expression":"{{review}} contains '硬伤'"}}]}"""
    gen = WorkflowGenerator(_FakeModel(raw))  # type: ignore[arg-type]
    wf = gen.generate("审读章节")
    assert wf.validate() == []
    assert wf.name == "章节审读"
    assert any(n.kind == "approval" for n in wf.nodes)


def test_generator_rejects_invalid() -> None:
    raw = """{"name":"坏流程","nodes":[{"id":"n1","kind":"agent"}],
      "edges":[{"source":"ghost","target":"n1"}]}"""
    gen = WorkflowGenerator(_FakeModel(raw))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        gen.generate("坏需求")
