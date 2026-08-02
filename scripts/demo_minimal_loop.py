"""
AnySpark v4 — 阶段 0 验收冒烟：跑通"读提示→调工具→回填→输出"最小循环。

运行：uv run python scripts/demo_minimal_loop.py
"""

from __future__ import annotations

from anyspark import Agent, Message, ToolRegistry, register_builtins


class DemoModel:
    """演示模型：第一次输出调工具，收到回填后给出最终答案。"""

    def __init__(self, script: list[str]) -> None:
        self._script = list(script)

    def respond(self, messages: list[Message], tool_descriptions: str) -> str:
        # messages 含 system/user/tool(回填)；这里打印回填内容展示"回填"效果
        tool_in = [m.content for m in messages if m.role == "tool"]
        print(f"  模型看到 {len(messages)} 条上下文 | 回填累计 {len(tool_in)} 条")
        return self._script.pop(0)


def main() -> None:
    print("== AnySpark v4 S0 最小循环冒烟 ==")

    registry = ToolRegistry()
    register_builtins(registry)
    print("工具清单：\n" + registry.describe())

    agent = Agent(
        model=DemoModel(["`add(a=3, b=4)`", "`echo(text='完成')`", "1+1 的答案是 7，演示结束。"]),
        registry=registry,
        system_prompt="你是 AnySpark 演示助手。",
    )

    # 事件监听演示：观察 tool_call / tool_result / done
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
