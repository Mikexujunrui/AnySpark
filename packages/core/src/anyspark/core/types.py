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
    """模型发起的一次工具调用（由 loop 解析模型输出得到）。

    id: 厂商返回的工具调用 ID（S23 协议完整化——tool 消息回填时配对用）；
        厂商未提供时为空字符串，回填仍可依赖名称+自然语言前缀（兼容旧链路）。
    """

    name: str
    arguments: dict[str, Any]
    id: str = ""


@dataclass
class ToolResult:
    """工具执行结果，用于回填进上下文。

    terminate（S27 对齐 pi ToolResult.terminate）：置 True 表示"本批到此为止"——
    Agent 循环不再进入下一轮（如"完成/终止"类工具声明）；仅当批内全部 terminate 才生效
    （pi shouldTerminateToolBatch 语义）。
    """

    call: ToolCall
    ok: bool
    content: str  # 自然语言结果描述（回填给模型，模型无关）
    data: dict[str, Any] | None = field(default_factory=dict)  # 结构化负载（可选）
    terminate: bool = False


@dataclass
class Turn:
    """Agent 循环的一步：一次输出，可能含文本与若干工具调用。

    error（S22）：本轮非正常结束的错误说明（模型调用失败/达到迭代上限）；
    None 表示正常结束。API 层据此返回 5xx，而不是依赖文本前缀匹配。
    """

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    error: str | None = None


@dataclass
class ModelOutput:
    """模型一次响应的结构化结果：文本 + 请求的工具调用（模型无关）。

    core 定义此结构，任何真实模型适配器（如 anyspark-app 的 DeepSeekModel）
    把自家 API 的响应翻译成此结构返回给 Agent 循环。

    truncated（S22 移植 pi 的 stopReason=length 判定）：输出被 token 上限截断。
    适配器在 finish_reason=="length" 时置 True；Agent 循环据此**批量拒绝**工具调用
    （截断的参数可能 JSON 合法但语义残缺，执行会写坏数据），让模型重发。

    reasoning（S49）：思维链（推理过程文本，如 DeepSeek 的 reasoning_content）。
    **只进运行记录（训练/复盘用），不注入上下文**——推理过程不是输出，
    回填/注入会污染上下文、改变模型行为（决策记录：保留但看情况才注入）。
    """

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    truncated: bool = False
    reasoning: str = ""
    # S99：token 消耗（模型适配器从 API usage 字段上报：prompt/completion/total_tokens）
    # 只进运行记录/SSE 汇总（前端展示消耗），不参与任何上下文逻辑
    usage: dict[str, int] | None = None
