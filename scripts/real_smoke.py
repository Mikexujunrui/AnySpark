"""
AnySpark v4 — 真实 DeepSeek 端到端冒烟。

用真实 DeepSeek (pi 同款 DashScope 端点 + deepseek-v4-flash) 走通
「读提示 → 真实原生调工具 → 回填 → 输出」完整循环。

运行：uv run python scripts/real_smoke.py
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from anyspark.core import Agent, ToolRegistry, ToolResult, ToolSpec
from anyspark.core.protocol import ParamSpec
from anyspark.core.types import ToolCall
from anyspark.models.deepseek import DeepSeekModel

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _add_implementer(spec: ToolSpec, arguments: dict) -> ToolResult:
    a = int(arguments["a"])
    b = int(arguments["b"])
    return ToolResult(
        call=ToolCall(name=spec.name, arguments=arguments),
        ok=True,
        content=f"{a} + {b} = {a + b}",
        data={"a": a, "b": b, "sum": a + b},
    )


def main() -> None:
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("缺少 DEEPSEEK_API_KEY，请在 .env 配置")
        return

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="add",
            description="计算两个整数相加的和",
            params=[
                ParamSpec(name="a", type="integer", required=True, description="第一个加数"),
                ParamSpec(name="b", type="integer", required=True, description="第二个加数"),
            ],
        ),
        _add_implementer,
    )

    model = DeepSeekModel()
    print(f"模型: {model.model_name}")

    agent = Agent(
        model=model,
        registry=registry,
        system_prompt=(
            "你是计算助手。遇到需要算数的任务，必须先调用 add 工具得到准确结果，再据此回答。"
        ),
    )
    agent.events.on("tool_call", lambda e: print("  ==> [tool_call]", e.payload))
    agent.events.on("tool_result", lambda e: print("  ==> [tool_result]", e.payload))

    print("-- 用户提问 --")
    turn = agent.run("请算出 12345 加 6789 等于多少，告诉我结果数字。")
    print("-- 最终输出 --")
    print(turn.text)
    print("-- 本轮回填的工具结果 --")
    for r in turn.tool_results:
        print(f"  {r.call.name} -> {r.content}  (ok={r.ok})")


if __name__ == "__main__":
    main()
