"""
本地侧 harness：用本地 Agent 循环跑脚本化场景，输出归一化轨迹（与 pi_harness.mjs 同格式）。

目的：与 pi_harness.mjs 输出对比——证明本地循环与 pi 循环在
工具调用/结果回填/截断防护/插话等行为上语义一致。

用法：python local_harness.py <scenario_id>
输出：stdout 一个 JSON：{"id": ..., "trace": [strings]}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "app" / "src"))

from anyspark.core import Agent, Message, ModelOutput, ToolCall, ToolRegistry, ToolResult, ToolSpec

HERE = Path(__file__).resolve().parent
SCENARIOS = json.loads((HERE / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]


# ---------------------------------------------------------------------------
# 工具（与 pi harness 语义一致）
# ---------------------------------------------------------------------------
def _do_add(spec: ToolSpec, arguments: dict[str, object]) -> ToolResult:
    a, b = arguments["a"], arguments["b"]
    return ToolResult(
        call=ToolCall(name="add", arguments=arguments),
        ok=True,
        content=f"{a} + {b} = {a + b}",
    )


def _do_echo(spec: ToolSpec, arguments: dict[str, object]) -> ToolResult:
    return ToolResult(
        call=ToolCall(name="echo", arguments=arguments),
        ok=True,
        content=f"echo:{arguments['text']}",
    )


def _do_boom(spec: ToolSpec, arguments: dict[str, object]) -> ToolResult:
    raise RuntimeError("boom 异常")


def _make_registry(on_add_done: object | None = None) -> ToolRegistry:
    def _do_add_with_hook(spec: ToolSpec, arguments: dict[str, object]) -> ToolResult:
        r = _do_add(spec, arguments)
        if on_add_done is not None:
            on_add_done()  # 模拟真实 API 场景：工具执行完成后插话到达（对齐 pi 的内层循环末尾检查）
        return r

    reg = ToolRegistry()
    reg.register(ToolSpec(name="add", params=[]), _do_add_with_hook)
    reg.register(ToolSpec(name="echo", params=[]), _do_echo)
    reg.register(ToolSpec(name="boom", params=[]), _do_boom)
    return reg


# ---------------------------------------------------------------------------
# 脚本化模型（按场景 steps 依次返回）
# ---------------------------------------------------------------------------
class ScriptedModel:
    def __init__(self, steps: list[dict], on_before_respond: object | None = None) -> None:
        self._steps = list(steps)
        self._on_before_respond = on_before_respond
        self.answered: list[list[Message]] = []

    def respond(self, messages: list[Message], tools: list[ToolSpec]) -> ModelOutput:
        # 每次模型调用前回调（harness 用它模拟"首轮工具结果后注入 steer"）
        if self._on_before_respond is not None:
            self._on_before_respond(len(self.answered))
        self.answered.append(list(messages))
        step = self._steps.pop(0)
        if "text" in step:
            return ModelOutput(text=step["text"])
        calls = [
            ToolCall(name=tc["name"], arguments=tc["args"], id=tc.get("id", ""))
            for tc in step.get("toolCalls", [])
        ]
        return ModelOutput(text="", tool_calls=calls, truncated=step.get("stopReason") == "length")


def trace_line(m: Message) -> str:
    if m.role == "user":
        return f"user:{m.content}"
    if m.role == "assistant":
        calls = m.metadata.get("tool_calls")
        if calls:
            parts = ",".join(
                f"{c['name']}({json.dumps(c['arguments'], ensure_ascii=False)})#{c.get('id', '')}"
                for c in calls
            )
            return f"assistant:toolCalls[{parts}]"
        return f"assistant:{m.content}"
    if m.role == "tool":
        ok = m.content.startswith("[工具") and " 成功" in m.content
        status = "ok" if ok else "error"
        if not ok:
            # 错误消息是自然语言（双方措辞自由）——只比较结构，不比文本
            return f"toolResult:{m.metadata.get('tool_call_id', '')}:{status}"
        body = m.content.split("] ", 1)[-1] if "] " in m.content else m.content
        return f"toolResult:{m.metadata.get('tool_call_id', '')}:{status}:{body}"
    return f"{m.role}:{m.content}"


def run_scenario(scenario: dict) -> list[str]:
    steps = json.loads(json.dumps(scenario["steps"]))
    steer_after = scenario.get("steerAfterStep", -1)
    steer_text = scenario.get("steerText", "")

    steer_hook = None
    if steer_after >= 0:

        def _steer_hook() -> None:
            # 模拟真实 API 场景：工具执行完成时插话到达（对齐 pi：getSteeringMessages
            # 在内层循环末尾检查——工具结果后、下轮 LLM 前注入）
            agent.steer(steer_text)

        steer_hook = _steer_hook
    model = ScriptedModel(steps)
    agent = Agent(model=model, registry=_make_registry(steer_hook))
    agent.store.create("parity")

    # 记录消息轨迹（user 消息由 loop 落 store）
    turn = agent.run("任务", "parity")
    if turn.error:
        agent.store.append("parity", Message(role="assistant", content=f"turn_error:{turn.error}"))
    return [trace_line(m) for m in agent.store.messages("parity")]


def main() -> None:
    scenario_id = sys.argv[1] if len(sys.argv) > 1 else ""
    scenario = next((s for s in SCENARIOS if s["id"] == scenario_id), None)
    if scenario is None:
        print(
            f"场景不存在: {scenario_id}（可用: {', '.join(s['id'] for s in SCENARIOS)}）",
            file=sys.stderr,
        )
        sys.exit(1)
    trace = run_scenario(scenario)
    print(json.dumps({"id": scenario_id, "trace": trace}, ensure_ascii=False))


if __name__ == "__main__":
    main()
