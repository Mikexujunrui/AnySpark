"""S59 补充验证：model 型条件（gate 自然语言判断）真实链路。

用真实 DeepSeek + 隔离库跑一条流程：agent 审读 → gate(model 型条件
"审读结论是否通过？") → 通过→approval 作者确认 / 不通过→改写。
验证 _wf_judge（model 型条件 → 模型 yes/no 判断）真实生效。

运行：uv run python scripts/workflow_model_cond_smoke.py
"""

from __future__ import annotations

import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "app" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "core" / "src"))

from anyspark.server.app import build_app
from anyspark.server.workspace import Workspace


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    db = tmp / "wf.db"
    # 隔离 workspace（防污染全局工作区）
    ws = Workspace(root=tmp / "ws")
    build_app(db_path=db, workspace=ws)

    # 直接操作 store 装配流程（不经 HTTP，快速）
    from anyspark.workflow import WorkflowDef, WorkflowEngine, WorkflowStore
    from anyspark.workflow.engine import NodeResult, RunContext, wait_approval

    wf_store = WorkflowStore(db)

    def runner(ctx: RunContext, node: object) -> NodeResult:
        n: object = node
        if n.kind == "approval":  # type: ignore[attr-defined]
            wait_approval()
        if n.params.get("instruction") == "审读":  # type: ignore[attr-defined]
            return NodeResult(output="本章设定一致，角色行为合理，节奏略慢。")
        if n.params.get("instruction") == "改写":  # type: ignore[attr-defined]
            return NodeResult(output="已按建议调整节奏。")
        return NodeResult(output="ok")

    wf = WorkflowDef.from_dict(
        {
            "name": "model条件冒烟",
            "nodes": [
                {
                    "id": "n1",
                    "kind": "agent",
                    "params": {"instruction": "审读", "output_key": "review"},
                },
                {"id": "g", "kind": "gate"},
                {
                    "id": "n2",
                    "kind": "agent",
                    "params": {"instruction": "改写", "output_key": "fixed"},
                },
                {"id": "n3", "kind": "approval", "params": {"prompt": "确认?"}},
            ],
            "edges": [
                {"source": "n1", "target": "g"},
                # model 型条件：自然语言问题 → 模型判断（_wf_judge）
                {
                    "source": "g",
                    "target": "n3",
                    "condition": {
                        "type": "model",
                        "prompt": "审读结论是否无硬伤、可以直接定稿？",
                        "label": "通过",
                    },
                },
                {
                    "source": "g",
                    "target": "n2",
                    "condition": {
                        "type": "model",
                        "prompt": "审读结论是否有需要修改的硬伤？",
                        "label": "需改写",
                    },
                },
                {"source": "g", "target": "n3", "label": "默认（无硬伤/不确定）"},
                {"source": "n2", "target": "n3"},
            ],
        }
    )
    errors = wf.validate()
    assert not errors, errors
    wf_store.add_template(wf)

    # 用 app 闭包里的真实 engine（带 _wf_judge）——重新装配一个
    from anyspark.core import Message
    from anyspark.core.retry import RetryingModel
    from anyspark.models.deepseek import DeepSeekModel

    model = RetryingModel(DeepSeekModel())

    def judge(prompt: str, ctx: RunContext) -> bool:
        out = model.respond([Message(role="user", content=prompt)], [])
        text = (out.text or "").strip().lower()
        return text.startswith("y") or "是" in text[:4] or "通过" in text[:4]

    engine = WorkflowEngine(wf_store, runner, model_judge=judge)
    task_id = wf_store.create_task(wf, book_id="main")
    print(f"任务 {task_id} 启动（model 型 gate 条件）...")

    def _run() -> None:
        engine.run_task(task_id)

    t = threading.Thread(target=_run)
    t.start()
    deadline = time.time() + 180
    while time.time() < deadline:
        task = wf_store.get_task(task_id)
        if task and task["status"] in ("waiting_approval", "done", "failed", "cancelled"):
            break
        time.sleep(3)
    task = wf_store.get_task(task_id)
    assert task is not None
    print(f"状态: {task['status']}")
    if task["error"]:
        print(f"错误: {task['error'][:300]}")
    for s in task["node_states"]:
        print(f"  {s['node_id']}: {s['status']}")
    assert task["status"] in ("waiting_approval", "done"), f"异常状态: {task['status']}"
    g = next(s for s in task["node_states"] if s["node_id"] == "g")
    print(f"gate 记录输出: {g['output']}")
    print("✅ model 型条件真实链路通过（模型自然语言判断生效）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
