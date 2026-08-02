"""
anyspark.core.protocol — 工具调用协议。

设计边界（DESIGN.md 第 4 节）：
- 工具调用协议：模型怎么调工具、参数解析、结果回填。
- 核心只提供**解析与执行机制**（硬编码），具体工具由调用方注册（内容自然语言）。

参数用轻量 JSON Schema 描述（name + description + 参数类型），模型无关。
"""

from __future__ import annotations

import json
import re
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
# 调用输出解析（模型输出 → 工具调用结构）
# ---------------------------------------------------------------------------
# 极简调用语法：工具调用以反引号包裹：`tool_name(a=value, b="value2")`
# 反引号是显式边界，避免与正文/普通文本里的括号混淆。
_TOOL_CALL_RE = re.compile(
    r"`\s*([a-zA-Z_][\w-]*)\s*\((.*?)\)\s*`",
    re.DOTALL,
)


def parse_tool_calls(text: str) -> list[ToolCall]:
    """从模型输出文本解析出工具调用。

    采用极简、模型无关的标记语法（后续接入真实模型时，此函数是可替换的
    "工具调用解析"适配点，符合 DESIGN 第 4 节"解析管道"硬编码）。
    工具调用必须用反引号包裹：`tool(a=1, b=2)`。
    非贪婪匹配，支持一行多个调用。
    """
    calls: list[ToolCall] = []
    for m in _TOOL_CALL_RE.finditer(text):
        name, args_str = m.group(1), m.group(2)
        args = _parse_args(args_str)
        calls.append(ToolCall(name=name, arguments=args))
    return calls


def _parse_args(args_str: str) -> dict[str, Any]:
    """解析 `k=v, k="v"...` 或逗号分隔的裸字面量（位置参数缺失名时跳过）。"""
    kwargs: dict[str, Any] = {}
    if not args_str.strip():
        return kwargs
    for token in _split_commas(args_str):
        token = token.strip()
        if not token:
            continue
        if "=" in token:
            k, _, v = token.partition("=")
            kwargs[k.strip()] = _coerce(v.strip())
    return kwargs


def _split_commas(s: str) -> list[str]:
    """按顶层逗号切分（忽略括号与引号内的逗号）。"""
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    quote: str | None = None
    for ch in s:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch in "([{":
            depth += 1
            buf.append(ch)
        elif ch in ")]}":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


def _coerce(raw: str) -> Any:
    """把字面量字符串转成 JSON 可序列化值（int/float/bool/null/string/JSON对象）。"""
    raw = raw.strip()
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw in ("null", "None"):
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    # 尝试 JSON 对象/数组
    if raw.startswith(("{", "[")):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return raw


# ---------------------------------------------------------------------------
# 执行（注册表 → 结果）
# ---------------------------------------------------------------------------
def execute(
    registry: ToolRegistry,
    call: ToolCall,
) -> ToolResult:
    """按注册表执行一次工具调用，返回回填用的结果。"""
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
