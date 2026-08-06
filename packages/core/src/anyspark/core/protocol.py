"""
anyspark.core.protocol — 工具调用协议。

设计边界（DESIGN.md 第 4 节）：
- 工具调用协议：模型怎么调工具、参数解析、结果回填。
- 核心只提供**解析与执行机制**（硬编码），具体工具由调用方注册（内容自然语言）。

参数用轻量 JSON Schema 描述（name + description + 参数类型），模型无关。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from .types import ToolCall as ToolCall
from .types import ToolResult as ToolResult


# ---------------------------------------------------------------------------
# 工具参数 schema（极简 JSON-Schema 子集，够描述当前极简工具）
# ---------------------------------------------------------------------------
@dataclass
class ParamSpec:
    name: str
    type: str  # "string" | "integer" | "number" | "boolean"
    required: bool = False
    description: str = ""


@dataclass
class ToolSpec:
    name: str
    description: str = ""
    params: list[ParamSpec] = field(default_factory=list)
    # S25（对齐 pi AgentTool.executionMode）：
    # "parallel"（默认）可与其他工具并行；"sequential" 时**整批串行执行**——
    # 适合会改变共享状态的写类工具（write_chapter 等），防止与 read 类工具并行产生逻辑错序。
    execution_mode: str = "parallel"

    def validate(self, arguments: dict[str, Any]) -> list[str]:
        """校验参数是否满足 schema，返回错误列表（空=通过）。"""
        errors: list[str] = []
        for p in self.params:
            if p.required and p.name not in arguments:
                errors.append(f"缺少必填参数: {p.name}")
                continue
            if p.name not in arguments:
                continue
            v = arguments[p.name]
            if p.type == "string" and not isinstance(v, str):
                errors.append(f"参数 {p.name} 应为 string，得到 {type(v).__name__}")
            elif p.type == "integer" and not isinstance(v, int):
                errors.append(f"参数 {p.name} 应为 integer，得到 {type(v).__name__}")
            elif p.type == "number" and not isinstance(v, (int, float)):
                # S56 宽松：数字字符串（如 "30"）也接受——模型常把数字参数当字符串传
                if not (isinstance(v, str) and v.strip().lstrip("-").isdigit()):
                    errors.append(f"参数 {p.name} 应为 number，得到 {type(v).__name__}")
            elif p.type == "boolean" and not isinstance(v, bool):
                errors.append(f"参数 {p.name} 应为 boolean，得到 {type(v).__name__}")
        return errors


# 工具可调用对象协议：接收规范 + 已解析参数 → 返回 ToolResult
class ToolImplementer(Protocol):
    def __call__(self, spec: ToolSpec, arguments: dict[str, Any]) -> ToolResult: ...


# ---------------------------------------------------------------------------
# 工具注册表（模型看到的名字 <-> 执行函数）
# ---------------------------------------------------------------------------
class ToolRegistry:
    """管理可被模型调用的工具集合。"""

    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolSpec, ToolImplementer]] = {}

    def register(self, spec: ToolSpec, implementer: ToolImplementer) -> None:
        if spec.name in self._tools:
            raise ValueError(f"工具 {spec.name} 已注册")
        self._tools[spec.name] = (spec, implementer)

    def specs(self) -> list[ToolSpec]:
        """返回给模型看到的工具清单（自然语言描述）。"""
        return [s for s, _ in self._tools.values()]

    def get(self, name: str) -> tuple[ToolSpec, ToolImplementer] | None:
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def describe(self) -> str:
        """人类/模型可读的工具清单（注入系统提示用，模型无关）。"""
        lines: list[str] = []
        for spec, _ in self._tools.values():
            params = ", ".join(
                f"{p.name}:{p.type}{'#' if p.required else '?'}= {p.description}"
                for p in spec.params
            )
            lines.append(f"- {spec.name}({params}) — {spec.description}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 执行（注册表 → 结果）
# ---------------------------------------------------------------------------
def execute(
    registry: ToolRegistry,
    call: ToolCall,
) -> ToolResult:
    """按注册表执行一次工具调用，返回回填用的结果。

    截断防护（S21 移植 pi 的 failToolCallsFromTruncatedMessage）：
    参数解析失败的调用（_malformed 标记，可能是输出 token 截断）**不执行**，
    返回错误让模型重新发起完整调用——防半截参数写坏数据。
    """
    if call.arguments.get("_malformed"):
        return ToolResult(
            call=call,
            ok=False,
            content=(
                f"工具 {call.name} 的参数解析失败（可能被输出截断），"
                "请重新发起完整调用。原始参数：" + str(call.arguments.get("_raw", ""))[:200]
            ),
        )
    entry = registry.get(call.name)
    if entry is None:
        return ToolResult(
            call=call,
            ok=False,
            content=f"未知工具: {call.name}（可用: {', '.join(s.name for s in registry.specs())}）",
        )
    spec, implementer = entry
    errors = spec.validate(call.arguments)
    if errors:
        return ToolResult(
            call=call,
            ok=False,
            content="参数校验失败: " + "; ".join(errors),
        )
    try:
        return implementer(spec, call.arguments)
    except Exception as exc:
        return ToolResult(
            call=call,
            ok=False,
            content=f"工具执行异常: {exc.__class__.__name__}: {exc}",
        )


def backfill_content_tool_result(result: ToolResult) -> str:
    """把工具结果格式化为回填上下文的自然语言文本（模型无关）。"""
    status = "成功" if result.ok else "失败"
    return f"[工具 {result.call.name} {status}] {result.content}"
