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
from collections.abc import Callable
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
        stream: bool = False,
        on_delta: Callable[[str], None] | None = None,
        timeout: float = 120.0,
    ) -> None:
        """
        stream: 流式传输（SSE 用）；on_delta: 文本增量回调（stream=True 时逐段触发）。
        timeout: 单次请求超时（秒）。
        重试由组合式包装提供（core.RetryingModel，S15 起不内嵌在模型内）——
        任何模型可套同一重试组件，换模型不丢流程基建。
        非流式路径与旧行为完全一致（协议向后兼容）。
        """
        self._base_url = base_url or DEFAULT_BASE_URL
        self._api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        if not self._api_key:
            raise ValueError("未配置 DeepSeek API key：请设置 DEEPSEEK_API_KEY 或传 api_key 参数")
        self._model = model or DEFAULT_MODEL
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._stream = stream
        self._on_delta = on_delta
        self._timeout = timeout
        self._client = OpenAI(
            base_url=self._base_url,
            api_key=self._api_key,
            timeout=self._timeout,
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

        if self._stream:
            return self._respond_stream(kwargs)

        def _call() -> ModelOutput:
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

        return _call()

    def _respond_stream(self, kwargs: dict[str, Any]) -> ModelOutput:
        """流式路径：文本 delta 逐段回调 on_delta；tool_calls 分片累积。"""
        kwargs["stream"] = True
        stream = self._client.chat.completions.create(**kwargs)
        text_parts: list[str] = []
        tool_acc: dict[int, dict[str, str]] = {}  # index -> {name, arguments}
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                text_parts.append(delta.content)
                if self._on_delta:
                    self._on_delta(delta.content)
            for tc in delta.tool_calls or []:
                acc = tool_acc.setdefault(tc.index, {"name": "", "arguments": ""})
                if tc.function and tc.function.name:
                    acc["name"] += tc.function.name
                if tc.function and tc.function.arguments:
                    acc["arguments"] += tc.function.arguments
        text = "".join(text_parts)
        tool_calls: list[ToolCall] = []
        for idx in sorted(tool_acc):
            acc = tool_acc[idx]
            try:
                args: dict[str, Any] = json.loads(acc["arguments"]) if acc["arguments"] else {}
            except json.JSONDecodeError:
                args = {"_raw": acc["arguments"]}
            tool_calls.append(ToolCall(name=acc["name"], arguments=args))
        return ModelOutput(text=text, tool_calls=tool_calls)
