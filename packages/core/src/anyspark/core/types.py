"""
anyspark.core.types — 核心数据类型。

模型无关：消息/工具调用/工具结果均为"明确无歧义的自然语言或结构化 JSON"，
不绑定任何具体模型厂商协议。

铁律：这里只放"循环走起来"必需的最小类型，YAGNI——不为用不到的类型建接口。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# 消息角色（Agent 循环上下文的最小单位）
Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class Message:
    """对话中的一条消息（最小持久化单位，见 storage）。"""

    role: Role
    content: str
    # 保留位：未来 token 计算/压缩用；当前不强制
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 工具调用协议
# ---------------------------------------------------------------------------
@dataclass
class ToolCall:
    """模型发起的一次工具调用（由 loop 解析模型输出得到）。"""

    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    """工具执行结果，用于回填进上下文。"""

    call: ToolCall
    ok: bool
    content: str  # 自然语言结果描述（回填给模型，模型无关）
    data: dict[str, Any] | None = field(default_factory=dict)  # 结构化负载（可选）


@dataclass
class Turn:
    """Agent 循环的一步：一次输出，可能含文本与若干工具调用。"""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)


@dataclass
class ModelOutput:
    """模型一次响应的结构化结果：文本 + 请求的工具调用（模型无关）。

    core 定义此结构，任何真实模型适配器（如 anyspark-app 的 DeepSeekModel）
    把自家 API 的响应翻译成此结构返回给 Agent 循环。
    """

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
