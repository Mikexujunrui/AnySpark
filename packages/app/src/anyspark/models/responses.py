"""
anyspark.models.responses — OpenAI Responses API 适配器（GPT-5 系，S131）。

实现 core 的 Model + StreamModel 协议，复用 openai SDK（client.responses.*，
SDK 2.x 原生支持；不新增依赖）。base_url 可指向 OpenAI 或兼容 Responses 端点。

为什么单独一个协议：GPT-5 系列只在 Responses API 提供（chat.completions 老端点
用不了 gpt-5），且 Responses 的 input/tools/reasoning 结构与 Completions 不同
（扁平 function tool、function_call_output item、reasoning.effort）。

思考强度映射（同款档位 off/low/medium/high/xhigh/max）：
- None/off → 不传 reasoning（交模型默认）
- low/medium/high → reasoning: {effort: "low"|"medium"|"high"}
- xhigh/max → effort: "high"（Responses 公开档位最高 high；minimal=极低不用）

配置：base_url 默认 https://api.openai.com/v1；api_key 默认读 OPENAI_API_KEY。
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

import httpx2 as httpx  # S66：httpx2（下一代 httpx；重命名迁移，API 兼容）
from openai import OpenAI

from anyspark.core import (
    Event,
    Message,
    ModelOutput,
    ToolCall,
    sanitize_tool_pairing,
)
from anyspark.core.protocol import ToolSpec

DEFAULT_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# 思考档位 → Responses reasoning.effort（Responses 公开档位 low/medium/high/minimal）
_EFFORT_MAP: dict[str, str] = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "high",
    "max": "high",
}


def thinking_to_responses(thinking: str | None) -> dict[str, Any] | None:
    """思考强度档位 → Responses reasoning 参数（None/off=不传，交模型默认）。"""
    if not thinking or thinking == "off":
        return None
    effort = _EFFORT_MAP.get(thinking)
    if effort is None:
        raise ValueError(f"非法思考强度 {thinking!r}：可选 off/low/medium/high/xhigh/max")
    return {"effort": effort}


def to_responses_tool(spec: ToolSpec) -> dict[str, Any]:
    """core ToolSpec → Responses function tool（扁平结构，非 Completions 嵌套）。"""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for p in spec.params:
        properties[p.name] = {"type": p.type, "description": p.description}
        if p.required:
            required.append(p.name)
    return {
        "type": "function",
        "name": spec.name,
        "description": spec.description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def to_responses_input(messages: list[Message]) -> list[dict[str, Any]]:
    """core Message 列表 → Responses input 数组（message + item 混合）。

    - system → {role: system, content}
    - assistant 带 metadata.tool_calls → 文本消息 + 每个调用一个 function_call item
      （Responses 的 function_call 是顶层 item；call_id 配对 function_call_output）
    - tool 消息 → function_call_output item（紧跟对应 function_call）
    """
    messages = sanitize_tool_pairing(messages)  # core 通用守卫（S190）
    result: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "system":
            result.append({"role": "system", "content": m.content})
        elif m.role == "assistant":
            if m.content:
                result.append({"role": "assistant", "content": m.content})
            calls = m.metadata.get("tool_calls")
            if isinstance(calls, list):
                for c in calls:
                    if isinstance(c, dict) and c.get("id"):
                        result.append(
                            {
                                "type": "function_call",
                                "call_id": str(c["id"]),
                                "name": str(c.get("name") or ""),
                                "arguments": json.dumps(
                                    c.get("arguments") or {}, ensure_ascii=False
                                ),
                            }
                        )
        elif m.role == "tool":
            tid = m.metadata.get("tool_call_id")
            result.append(
                {
                    "type": "function_call_output",
                    "call_id": str(tid or ""),
                    "output": m.content,
                }
            )
    # S176：悬挂 function_call 防御——assistant 声明了 function_call 但无对应
    # function_call_output（取消/异常/坏数据遗留）→ 移除未配对的 function_call，
    # 否则 Responses API 配对失败。
    responded_ids: set[str] = set()
    for item in result:
        if isinstance(item, dict) and item.get("type") == "function_call_output":
            responded_ids.add(str(item.get("call_id") or ""))
    result = [
        item
        for item in result
        if not (isinstance(item, dict) and item.get("type") == "function_call")
        or str(item.get("call_id") or "") in responded_ids
    ]
    return result


def _parse_output(output: list[Any]) -> tuple[str, list[ToolCall], str]:
    """Responses output 数组 → (text, tool_calls, reasoning)。"""
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    reasoning_parts: list[str] = []
    for item in output:
        itype = getattr(item, "type", None)
        if itype == "message":
            for block in getattr(item, "content", []) or []:
                if getattr(block, "type", None) == "output_text":
                    text_parts.append(getattr(block, "text", "") or "")
                elif getattr(block, "type", None) == "reasoning":
                    reasoning_parts.append(getattr(block, "summary", "") or "")
        elif itype == "function_call":
            raw = getattr(item, "arguments", "") or ""
            try:
                args: dict[str, Any] = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                # 截断防护（S21）：参数非法→标记，不执行，让模型重发
                args = {"_raw": raw, "_malformed": True}
            tool_calls.append(
                ToolCall(
                    name=getattr(item, "name", "") or "",
                    arguments=args,
                    id=getattr(item, "call_id", "") or "",
                )
            )
    return "".join(text_parts), tool_calls, "".join(reasoning_parts)


class ResponsesModel:
    """OpenAI Responses API 真实调用器（实现 core.Model + StreamModel 协议）。"""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        context_window: int | None = None,
        thinking: str | None = None,
    ) -> None:
        self._base_url = base_url or DEFAULT_BASE_URL
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        if not self._api_key:
            raise ValueError("未配置 OpenAI API key：请设置 OPENAI_API_KEY 或传 api_key 参数")
        self._model = model or "gpt-5"
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._reasoning = thinking_to_responses(thinking)
        self._context_window = context_window or int(os.getenv("OPENAI_CONTEXT_WINDOW", "200000"))
        # S131：同 deepseek.py——trust_env=False 防环境变量代理劫持本地端点请求（502）
        # S214：超时分阶段——connect/pool 10s，read 不超时（流式思考数分钟不断产 token）
        _httpx_timeout = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0)
        self._client = OpenAI(
            base_url=self._base_url,
            api_key=self._api_key,
            timeout=120.0,
            http_client=httpx.Client(trust_env=False, timeout=_httpx_timeout),  # type: ignore[arg-type]
        )

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def context_window(self) -> int:
        return self._context_window

    def _kwargs(self, messages: list[Message], tools: list[ToolSpec]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "input": to_responses_input(messages),
            "temperature": self._temperature,
            "max_output_tokens": self._max_tokens,
        }
        if tools:
            kwargs["tools"] = [to_responses_tool(t) for t in tools]
        if self._reasoning is not None:
            kwargs["reasoning"] = self._reasoning
        return kwargs

    def respond(self, messages: list[Message], tools: list[ToolSpec]) -> ModelOutput:
        """真实调用 Responses API，返回模型无关的 ModelOutput（非流式）。"""
        resp = self._client.responses.create(**self._kwargs(messages, tools))
        output = list(getattr(resp, "output", []) or [])
        text, tool_calls, reasoning = _parse_output(output)
        truncated = getattr(resp, "incomplete_details", None) is not None
        usage: dict[str, int] | None = None
        u = getattr(resp, "usage", None)
        if u is not None:
            usage = {
                "prompt_tokens": int(getattr(u, "input_tokens", 0) or 0),
                "completion_tokens": int(getattr(u, "output_tokens", 0) or 0),
                "total_tokens": int(getattr(u, "total_tokens", 0) or 0),
            }
        return ModelOutput(
            text=text,
            tool_calls=tool_calls,
            truncated=truncated,
            reasoning=reasoning,
            usage=usage,
        )

    def respond_stream(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        on_event: Callable[[Any], None] | None = None,
    ) -> ModelOutput:
        """流式协议：SDK 事件流 → text_delta / toolcall_delta 事件。"""
        kwargs = self._kwargs(messages, tools)
        kwargs["stream"] = True
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_acc: dict[int, dict[str, str]] = {}  # output_index -> {name, args, call_id}
        truncated = False
        usage: dict[str, int] | None = None
        final_output: list[Any] = []

        stream = self._client.responses.create(**kwargs)
        for event in stream:
            etype = getattr(event, "type", "")
            if etype == "response.output_text.delta":
                t = getattr(event, "delta", "") or ""
                text_parts.append(t)
                if on_event is not None:
                    on_event(Event(type="text_delta", payload={"content": t}))
            elif etype == "response.function_call_arguments.delta":
                idx = getattr(event, "output_index", 0) or 0
                acc = tool_acc.setdefault(idx, {"name": "", "args": "", "call_id": ""})
                acc["args"] += getattr(event, "delta", "") or ""
                if on_event is not None:
                    on_event(
                        Event(
                            type="toolcall_delta",
                            payload={"content": getattr(event, "delta", "") or ""},
                        )
                    )
            elif etype == "response.function_call_arguments.done":
                idx = getattr(event, "output_index", 0) or 0
                acc = tool_acc.setdefault(idx, {"name": "", "args": "", "call_id": ""})
                acc["args"] = getattr(event, "arguments", "") or ""
                acc["call_id"] = getattr(event, "item_id", "") or ""
            elif etype == "response.function_call_created":
                idx = getattr(event, "output_index", 0) or 0
                acc = tool_acc.setdefault(idx, {"name": "", "args": "", "call_id": ""})
                acc["name"] = getattr(event, "name", "") or ""
            elif etype == "response.reasoning_summary_text.delta":
                reasoning_parts.append(getattr(event, "delta", "") or "")
                # S213：思考增量实时转发——避免思考期 SSE 静默致前端 idle 超时误杀
                if on_event is not None:
                    _rd = getattr(event, "delta", "") or ""
                    on_event(Event(
                        type="reasoning_delta",
                        payload={"content": _rd},
                    ))
            elif etype == "response.completed":
                resp = getattr(event, "response", None)
                if resp is not None:
                    final_output = list(getattr(resp, "output", []) or [])
                    truncated = getattr(resp, "incomplete_details", None) is not None
                    u = getattr(resp, "usage", None)
                    if u is not None:
                        usage = {
                            "prompt_tokens": int(getattr(u, "input_tokens", 0) or 0),
                            "completion_tokens": int(getattr(u, "output_tokens", 0) or 0),
                            "total_tokens": int(getattr(u, "total_tokens", 0) or 0),
                        }
            elif etype == "response.failed":
                raise RuntimeError(f"Responses API 流式失败: {getattr(event, 'error', '')}")

        # 流式工具调用可能未在 function_call_created 拿到 name——从 final_output 兜底解析
        if final_output:
            _, final_calls, _ = _parse_output(final_output)
            return ModelOutput(
                text="".join(text_parts),
                tool_calls=final_calls,
                truncated=truncated,
                reasoning="".join(reasoning_parts),
                usage=usage,
            )

        tool_calls: list[ToolCall] = []
        for idx in sorted(tool_acc):
            acc = tool_acc[idx]
            raw = acc["args"]
            try:
                args = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                # 截断防护（S21）：参数非法→标记，不执行，让模型重发
                args = {"_raw": raw, "_malformed": True}
            tool_calls.append(ToolCall(name=acc["name"], arguments=args, id=acc.get("call_id", "")))
        return ModelOutput(
            text="".join(text_parts),
            tool_calls=tool_calls,
            truncated=truncated,
            reasoning="".join(reasoning_parts),
            usage=usage,
        )
