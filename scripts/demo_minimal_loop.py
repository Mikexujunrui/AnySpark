"""
AnySpark v4 — core 最小循环冒烟（结构化 ModelOutput，非降级文本解析）。

运行：uv run python scripts/demo_minimal_loop.py
"""

from __future__ import annotations

from anyspark import (
    Agent,
    Message,
    ModelOutput,
    ToolCall,
    ToolRegistry,
    ToolSpec,
)
from anyspark.core.tools import register_builtins


class ScriptedModel:
    """脚本化模型：先调工具，收到回填后给出最终答案。"""

    def __init__(self, outputs: list[ModelOutput]) -> None:
        self._script = list(outputs)

    def respond(self, messages: list[Message], tools: list[ToolSpec]) -> ModelOutput:
        tool_in = [m.content for m in messages if m.role == "tool"]
        print(f"  模型看到 {len(messages)} 条上下文 | 回填累计 {len(tool_in)} 条")
        return self._script.pop(0)


def main() -> None:
    print("== AnySpark v4 core 最小循环冒烟 ==")

    registry = ToolRegistry()
    register_builtins(registry)
    print("工具清单：\n" + registry.describe())

    agent = Agent(
        model=ScriptedModel(
            [
                ModelOutput(tool_calls=[ToolCall(name="add", arguments={"a": 3, "b": 4})]),
                ModelOutput(tool_calls=[ToolCall(name="echo", arguments={"text": "完成"})]),
                ModelOutput(text="1+1 的答案是 7，演示结束。"),
            ]
        ),
        registry=registry,
        system_prompt="你是 AnySpark 助手。",
    )

    agent.events.on("tool_call", lambda e: print(f"  [event tool_call] {e.payload}"))
    agent.events.on("tool_result", lambda e: print(f"  [event tool_result] ok={e.payload['ok']}"))
    agent.events.on("done", lambda e: print("  [event done] 本轮结束"))

    print("-- 用户说话 --")
    turn = agent.run("算一下 3+4 和 1+1，然后告诉我")
    print("-- 最终输出 --")
    print("  " + turn.text)
    print("-- 本轮回填进上下文的工具结果 --")
    for r in turn.tool_results:
        print(f"  {r.call.name} -> {r.content}")


if __name__ == "__main__":
    main()
