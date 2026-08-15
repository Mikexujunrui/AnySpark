"""
anyspark.models.anthropic — Anthropic Messages API 适配器（Claude 直连/中转，S131）。

实现 core 的 Model + StreamModel 协议，用 httpx2 手写 HTTP 调用（零新增依赖，
Messages API 是简单 JSON；不引 anthropic SDK，避免 SDK 版本与 httpx 生态耦合）。
支持：文本 / 工具调用（tool_use 块 + tool_result 回填）/ 思考（thinking budget）/
流式（SSE：content_block_delta 增量 + message_delta 收尾）。

思考强度映射（与 openai 协议同款档位 off/low/medium/high/xhigh/max）：
- None/off → 不传 thinking（Anthropic 默认关闭思考）
- low/medium/high/xhigh/max → thinking: {type: "enabled", budget_tokens: N}
  budget 映射（token）：low=2048 / medium=4096 / high=8192 / xhigh=16384 / max=32768
  ⚠️ Anthropic 硬性限制：开启 thinking 时 temperature 必须为 1——适配器强制覆盖。

配置：
- base_url 默认 https://api.anthropic.com（国内中转站改 base_url 即可）
- api_key 默认读 ANTHROPIC_API_KEY
- anthropic-version 请求头默认 2023-06-01（可经 ANTHROPIC_VERSION 覆盖）
"""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Callable
from typing import Any

import httpx2 as httpx  # S66：httpx2（下一代 httpx；重命名迁移，API 兼容）

from anyspark.core import (
    Event,
    Message,
    ModelOutput,
    ToolCall,
    sanitize_tool_pairing,
)
from anyspark.core.protocol import ToolSpec

DEFAULT_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
DEFAULT_VERSION = os.getenv("ANTHROPIC_VERSION", "2023-06-01")

# 思考档位 → thinking budget_tokens（Anthropic thinking 预算，token 计）
THINKING_BUDGETS: dict[str, int] = {
    "low": 2048,
    "medium": 4096,
    "high": 8192,
    "xhigh": 16384,
    "max": 32768,
}


def thinking_to_anthropic(thinking: str | None) -> dict[str, Any] | None:
    """思考强度档位 → Anthropic thinking 参数（None/off=不传，模型默认关闭思考）。"""
    if not thinking or thinking == "off":
        return None
    budget = THINKING_BUDGETS.get(thinking)
    if budget is None:
        raise ValueError(f"非法思考强度 {thinking!r}：可选 off/low/medium/high/xhigh/max")
    return {"type": "enabled", "budget_tokens": budget}


def to_anthropic_tool(spec: ToolSpec) -> dict[str, Any]:
    """core ToolSpec → Anthropic tools 定义（input_schema 用 JSON Schema 对象）。"""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for p in spec.params:
        properties[p.name] = {"type": p.type, "description": p.description}
        if p.required:
            required.append(p.name)
    return {
        "name": spec.name,
        "description": spec.description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def to_anthropic_messages(
    messages: list[Message],
) -> tuple[str | None, list[dict[str, Any]]]:
    """core Message 列表 → (system, Anthropic messages)。

    Anthropic 消息语义：
    - system 角色 → 顶层 system 字段（Anthropic 的 system 不在 messages 数组里）
    - assistant 带 metadata.tool_calls → content 块 [{type: tool_use, id, name, input}]
    - tool 消息 → 并入 user 消息 content [{type: tool_result, tool_use_id, content}]
      （连续 tool 消息合并为一条 user；Anthropic 要求 user/assistant 严格交替）
    - 相邻同角色消息合并（防 agent 链路产生连续同角色消息）

    S190：转换前先跑 core 通用配对守卫（无孤儿 tool / 无悬挂声明），
    本层再补 Anthropic 特有的“严格紧邻”约束（下方 S174/S182/S189 防御）。
    """
    messages = sanitize_tool_pairing(messages)  # core 通用守卫（S190）
    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []
    pending_results: list[dict[str, Any]] = []  # 连续 tool 消息累积的 tool_result 块

    for m in messages:
        if m.role == "system":
            system_parts.append(m.content)
            continue
        if m.role == "tool":
            tid = m.metadata.get("tool_call_id")
            pending_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": str(tid or ""),
                    "content": m.content,
                }
            )
            continue
        if pending_results:
            converted.append({"role": "user", "content": pending_results})
            pending_results = []
        if m.role == "assistant":
            content: list[dict[str, Any]] = []
            if m.content:
                content.append({"type": "text", "text": m.content})
            calls = m.metadata.get("tool_calls")
            if isinstance(calls, list):
                for c in calls:
                    if isinstance(c, dict) and c.get("id"):
                        content.append(
                            {
                                "type": "tool_use",
                                "id": str(c["id"]),
                                "name": str(c.get("name") or ""),
                                "input": c.get("arguments") or {},
                            }
                        )
            converted.append({"role": "assistant", "content": content})
        else:
            converted.append({"role": "user", "content": m.content})
    if pending_results:
        converted.append({"role": "user", "content": pending_results})

    # S174/S182/S189：tool_use/tool_result 严格双向配对防御。
    # Anthropic 硬性要求：每个 tool_use 块在 messages[k]，对应 tool_result 必须出现在
    # **紧邻下一条** messages[k+1] 的 user 里（仅存在配对不够：被 steer 插话/其他消息
    # 隔开、同批部分配对、历史截断/跨协议切换后 id 错位时均 400）。
    # 两遍修剪（方向相反，交集收敛）：
    #   ① user 的 tool_result id 必须声明于其**紧邻前一条** assistant 的 tool_use 中，
    #     否则该 tool_result 移除（空 id / 无声明 / 前一条不是 assistant 的孤儿全灭）；
    #   ② assistant 的 tool_use id 必须出现在其**紧邻下一条** user 的 tool_result 中，
    #     否则该 tool_use 移除。第二遍读的是第一遍修剪后的 user，双向取交集——
    # 不会再把“任意历史出现过的 id”当合法放行（旧实现在全局集合累积，孤儿 tool_result
    # 可能被误留 → messages.N.content.0: tool_use_id found in tool_result blocks）。
    for i, c in enumerate(converted):
        if c["role"] != "user" or not isinstance(c["content"], list):
            continue
        prev_ids: set[str] = set()
        if i > 0 and converted[i - 1]["role"] == "assistant":
            prev = converted[i - 1]["content"]
            if isinstance(prev, list):
                prev_ids = {
                    str(b.get("id") or "")
                    for b in prev
                    if isinstance(b, dict) and b.get("type") == "tool_use"
                }
        c["content"] = [
            b
            for b in c["content"]
            if not (isinstance(b, dict) and b.get("type") == "tool_result")
            or str(b.get("tool_use_id") or "") in prev_ids
        ]
        if not c["content"]:
            c["content"] = ""  # 空 user 消息降为字符串（合并阶段处理）
    for i, c in enumerate(converted):
        if c["role"] != "assistant" or not isinstance(c["content"], list):
            continue
        next_ids: set[str] = set()
        if i + 1 < len(converted) and converted[i + 1]["role"] == "user":
            nxt_content = converted[i + 1]["content"]
            if isinstance(nxt_content, list):
                next_ids = {
                    str(b.get("tool_use_id") or "")
                    for b in nxt_content
                    if isinstance(b, dict) and b.get("type") == "tool_result"
                }
        c["content"] = [
            b
            for b in c["content"]
            if not (isinstance(b, dict) and b.get("type") == "tool_use")
            or str(b.get("id") or "") in next_ids
        ]
        # 移除后 content 空 → 补空 text 块（Anthropic 要求 assistant content 非空）
        if not c["content"]:
            c["content"] = [{"type": "text", "text": ""}]

    # 相邻同角色合并（Anthropic 严格交替；字符串 content 拼接，块列表 extend）
    merged: list[dict[str, Any]] = []
    for c in converted:
        if merged and merged[-1]["role"] == c["role"]:
            prev = merged[-1]["content"]
            cur = c["content"]
            if isinstance(prev, str) and isinstance(cur, str):
                merged[-1]["content"] = prev + "\n" + cur
            elif isinstance(prev, list) and isinstance(cur, list):
                merged[-1]["content"] = prev + cur
            else:
                merged.append(c)
        else:
            merged.append(c)
    system = "\n".join(system_parts) if system_parts else None
    # S174：system-only 兜底——内部管道（资料消化/技能提炼）只传 [system]，
    # system 提到顶层后 messages 空 → Anthropic 400。降为 user 消息保调用可用
    # （指令+原文作为 user 输入语义无误）。
    if not merged and system:
        merged = [{"role": "user", "content": system}]
        system = None
    return system, merged


def _parse_content(content: list[dict[str, Any]]) -> tuple[str, list[ToolCall], str]:
    """Anthropic content 块 → (text, tool_calls, reasoning)。"""
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    for block in content:
        btype = block.get("type")
        if btype == "text":
            text_parts.append(block.get("text") or "")
        elif btype == "tool_use":
            raw = block.get("input")
            args: dict[str, Any]
            if isinstance(raw, dict):
                args = raw
            else:  # 截断防护（S21）：input 非对象 → 标记，不执行，让模型重发
                args = {"_raw": json.dumps(raw, ensure_ascii=False), "_malformed": True}
            tool_calls.append(
                ToolCall(
                    name=block.get("name") or "",
                    arguments=args,
                    id=block.get("id") or "",
                )
            )
        elif btype == "thinking":
            reasoning_parts.append(block.get("thinking") or "")
    return "".join(text_parts), tool_calls, "".join(reasoning_parts)


class AnthropicModel:
    """Anthropic Messages API 真实调用器（实现 core.Model + StreamModel 协议）。"""

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
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "") or ""
        if not self._api_key:
            raise ValueError("未配置 Anthropic API key：请设置 ANTHROPIC_API_KEY 或传 api_key 参数")
        self._model = model or "claude-sonnet-4-5"
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._thinking = thinking_to_anthropic(thinking)
        self._context_window = context_window or int(
            os.getenv("ANTHROPIC_CONTEXT_WINDOW", "200000")
        )
        self._client = httpx.Client(trust_env=False, timeout=120.0)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def context_window(self) -> int:
        return self._context_window

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": DEFAULT_VERSION,
            "content-type": "application/json",
        }

    def _payload(
        self, messages: list[Message], tools: list[ToolSpec], stream: bool
    ) -> dict[str, Any]:
        system, msgs = to_anthropic_messages(messages)
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": msgs,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [to_anthropic_tool(t) for t in tools]
        if self._thinking:
            # Anthropic 硬性限制：thinking enabled 时 temperature 必须为 1
            payload["thinking"] = self._thinking
            payload["temperature"] = 1.0
        else:
            payload["temperature"] = self._temperature
        if stream:
            payload["stream"] = True
        return payload

    def respond(self, messages: list[Message], tools: list[ToolSpec]) -> ModelOutput:
        """真实调用 Anthropic Messages，返回模型无关的 ModelOutput（非流式）。"""
        payload = self._payload(messages, tools, stream=False)
        resp = self._client.post(
            f"{self._base_url}/v1/messages",
            json=payload,
            headers=self._headers(),
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Anthropic API {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        text, tool_calls, reasoning = _parse_content(data.get("content") or [])
        truncated = data.get("stop_reason") == "max_tokens"
        usage: dict[str, int] | None = None
        u = data.get("usage")
        if isinstance(u, dict):
            usage = {
                "prompt_tokens": int(u.get("input_tokens") or 0),
                "completion_tokens": int(u.get("output_tokens") or 0),
                "total_tokens": int(u.get("input_tokens") or 0) + int(u.get("output_tokens") or 0),
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
        """流式协议（S21 移植 pi 模式）：SSE 增量 → text_delta / toolcall_delta 事件。"""
        payload = self._payload(messages, tools, stream=True)
        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_acc: dict[int, dict[str, str]] = {}  # index -> {id, name, input(累积)}
        truncated = False
        usage: dict[str, int] | None = None
        current_event = ""
        current_data: list[str] = []

        def _handle(event: str, data: dict[str, Any]) -> None:
            nonlocal truncated, usage
            etype = data.get("type")
            if etype == "content_block_delta":
                idx = int(data.get("index") or 0)
                delta = data.get("delta") or {}
                dtype = delta.get("type")
                if dtype == "text_delta":
                    t = delta.get("text") or ""
                    text_parts.append(t)
                    if on_event is not None:
                        on_event(Event(type="text_delta", payload={"content": t}))
                elif dtype == "thinking_delta":
                    reasoning_parts.append(delta.get("thinking") or "")
                elif dtype == "input_json_delta":
                    acc = tool_acc.setdefault(idx, {"id": "", "name": "", "input": ""})
                    acc["input"] += delta.get("partial_json") or ""
                    if on_event is not None:
                        on_event(
                            Event(
                                type="toolcall_delta",
                                payload={"content": delta.get("partial_json") or ""},
                            )
                        )
            elif etype == "content_block_start":
                idx = int(data.get("index") or 0)
                block = data.get("content_block") or {}
                if block.get("type") == "tool_use":
                    acc = tool_acc.setdefault(idx, {"id": "", "name": "", "input": ""})
                    acc["id"] = block.get("id") or ""
                    acc["name"] = block.get("name") or ""
            elif etype == "message_delta":
                d = data.get("delta") or {}
                if d.get("stop_reason") == "max_tokens":
                    truncated = True
                # S180：message_delta 的 usage 含最终 output_tokens（message_start
                # 的 output_tokens 是初始值 ~1）；不捕获则记录的 completion_tokens 恒为 ~1
                u2 = data.get("usage")
                if isinstance(u2, dict):
                    usage = {
                        "prompt_tokens": int(u2.get("input_tokens") or 0),
                        "completion_tokens": int(u2.get("output_tokens") or 0),
                        "total_tokens": int(u2.get("input_tokens") or 0)
                        + int(u2.get("output_tokens") or 0),
                    }
            elif etype == "message_start":
                msg = data.get("message") or {}
                u = msg.get("usage")
                if isinstance(u, dict):
                    usage = {
                        "prompt_tokens": int(u.get("input_tokens") or 0),
                        "completion_tokens": int(u.get("output_tokens") or 0),
                        "total_tokens": int(u.get("input_tokens") or 0)
                        + int(u.get("output_tokens") or 0),
                    }

        with self._client.stream(
            "POST",
            f"{self._base_url}/v1/messages",
            json=payload,
            headers=self._headers(),
        ) as resp:
            if resp.status_code != 200:
                # httpx2 流式响应未消费：直接访问 .text 抛 ResponseNotRead——先 read 再取错误详情
                try:
                    resp.read()
                    detail = resp.text[:300]
                except Exception:
                    detail = "(无法读取错误详情)"
                raise RuntimeError(f"Anthropic API {resp.status_code}: {detail}")
            for line in resp.iter_lines():
                if line == "":
                    if current_data:
                        with contextlib.suppress(json.JSONDecodeError):
                            _handle(current_event, json.loads("\n".join(current_data)))
                    current_event = ""
                    current_data = []
                elif line.startswith("event:"):
                    current_event = line[len("event:") :].strip()
                elif line.startswith("data:"):
                    current_data.append(line[len("data:") :].strip())

        tool_calls: list[ToolCall] = []
        for idx in sorted(tool_acc):
            acc = tool_acc[idx]
            raw = acc["input"]
            try:
                args = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                # 截断防护（S21）：参数非法→标记，不执行，让模型重发
                args = {"_raw": raw, "_malformed": True}
            tool_calls.append(ToolCall(name=acc["name"], arguments=args, id=acc.get("id", "")))
        return ModelOutput(
            text="".join(text_parts),
            tool_calls=tool_calls,
            truncated=truncated,
            reasoning="".join(reasoning_parts),
            usage=usage,
        )
