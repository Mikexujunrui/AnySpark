"""
anyspark.models.deepseek — 真实 DeepSeek 模型适配器（OpenAI 兼容）。

实现 core 的 Model 协议，用 OpenAI SDK 真实调用 DeepSeek（DashScope 兼容端点）。
不做任何模拟/降级：使用原生 chat.completions + 原生 tool calling。

配置（优先级从高到低）：
1. 构造时显式传 base_url / api_key / model
2. 环境变量 DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_MODEL
"""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from anyspark.core.protocol import ToolSpec
from anyspark.core.types import Message, ModelOutput, ToolCall

# 与 pi 同款默认：DashScope 兼容端点 + deepseek-v4-flash
DEFAULT_BASE_URL = os.getenv(
    "DEEPSEEK_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
DEFAULT_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")


def to_openai_tool(spec: ToolSpec) -> dict[str, Any]:
    """把 core 的 ToolSpec 转成 OpenAI 原生 tools 定义（真实函数调用 schema）。"""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for p in spec.params:
        properties[p.name] = {
            "type": p.type,
            "description": p.description,
        }
        if p.required:
            required.append(p.name)
    fn = {
        "name": spec.name,
        "description": spec.description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }
    return {"type": "function", "function": fn}


def to_openai_message(m: Message) -> dict[str, Any]:
    """把 core 的 Message 转成 OpenAI chat 消息。"""
    return {"role": m.role, "content": m.content}


class DeepSeekModel:
    """基于 OpenAI SDK 的真实 DeepSeek 调用器（实现 core.Model 协议）。"""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> None:
        self._base_url = base_url or DEFAULT_BASE_URL
        self._api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        if not self._api_key:
            raise ValueError("未配置 DeepSeek API key：请设置 DEEPSEEK_API_KEY 或传 api_key 参数")
        self._model = model or DEFAULT_MODEL
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = OpenAI(
            base_url=self._base_url,
            api_key=self._api_key,
        )

    @property
    def model_name(self) -> str:
        return self._model

    def respond(self, messages: list[Message], tools: list[ToolSpec]) -> ModelOutput:
        """真实调用 DeepSeek，返回模型无关的 ModelOutput。"""
        openai_messages = [to_openai_message(m) for m in messages]
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": openai_messages,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        if tools:
            kwargs["tools"] = [to_openai_tool(t) for t in tools]
            kwargs["tool_choice"] = "auto"

        response = self._client.chat.completions.create(**kwargs)
        message = response.choices[0].message

        text = message.content or ""
        tool_calls: list[ToolCall] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                fn = tc.function
                try:
                    args: dict[str, Any] = json.loads(fn.arguments) if fn.arguments else {}
                except json.JSONDecodeError:
                    args = {"_raw": fn.arguments}
                tool_calls.append(ToolCall(name=fn.name, arguments=args))

        return ModelOutput(text=text, tool_calls=tool_calls)
