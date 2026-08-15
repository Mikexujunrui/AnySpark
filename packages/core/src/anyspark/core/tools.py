"""
anyspark.core.tools — 极简内置工具（演示/测试用）。

阶段 0 只提供两个最小工具，用于跑通"读提示→调工具→回填→输出"最小循环。
真实功能工具在阶段 1+ 由各包按需注册。
"""

from __future__ import annotations

from typing import Any

from .protocol import ParamSpec, ToolRegistry, ToolResult, ToolSpec
from .types import ToolCall


def echo_implementer(spec: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
    call = ToolCall(name=spec.name, arguments=arguments)
    text = str(arguments.get("text", ""))
    return ToolResult(call=call, ok=True, content=text, data={"text": text})


def add_implementer(spec: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
    call = ToolCall(name=spec.name, arguments=arguments)
    a = int(arguments.get("a", 0))
    b = int(arguments.get("b", 0))
    total = a + b
    return ToolResult(
        call=call,
        ok=True,
        content=f"{a} + {b} = {total}",
        data={"result": total},
    )


def builtin_echo_spec() -> ToolSpec:
    return ToolSpec(
        name="echo",
        description="原样返回给定的文本。用于测试工具链路。",
        params=[ParamSpec(name="text", type="string", required=True, description="要返回的文本")],
    )


def builtin_add_spec() -> ToolSpec:
    return ToolSpec(
        name="add",
        description="计算两个整数的和。",
        params=[
            ParamSpec(name="a", type="integer", required=True, description="第一个加数"),
            ParamSpec(name="b", type="integer", required=True, description="第二个加数"),
        ],
    )


def register_builtins(registry: ToolRegistry) -> None:
    """把内置最小工具注册进注册表。"""
    registry.register(builtin_echo_spec(), echo_implementer)
    registry.register(builtin_add_spec(), add_implementer)
