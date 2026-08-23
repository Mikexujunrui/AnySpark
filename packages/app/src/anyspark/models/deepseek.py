"""
anyspark.models.deepseek — OpenAI Chat Completions 兼容适配器（DeepSeek 及绝大多数厂商）。

实现 core 的 Model 协议，用 OpenAI SDK 真实调用 chat.completions 端点（原生 tool calling）。
S131 泛化定位：本适配器即“openai”协议——凡是 OpenAI 兼容端点（DeepSeek/DashScope、
通义、Kimi、GLM、豆包、Groq、Cerebras、Mistral、xAI、OpenRouter、本地 Ollama/
LM Studio/vLLM/llama.cpp 等）都通过它接入（base_url 指向对应端点）。
不做任何模拟/降级：使用原生 chat.completions + 原生 tool calling。

配置（优先级从高到低）：
1. 构造时显式传 base_url / api_key / model
2. 环境变量 DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_MODEL
（类名/模块名保留 DeepSeek 历史名，向后兼容既有引用）

思考强度（thinking，S47 新增）：deepseek-v4 系列默认开启思考模式，
通过 OpenAI 标准参数 reasoning_effort 调整强度（low/medium/high/xhigh/max），
非标准参数 enable_thinking 走 extra_body 显式开关。取值：
- None  不传（交给模型默认）
- "off"  extra_body={"enable_thinking": False}（显式关闭思考）
- low/medium/high/xhigh/max  顶层 reasoning_effort（按模型支持映射）
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

# 与 pi 同款默认：DashScope 兼容端点 + deepseek-v4-flash
DEFAULT_BASE_URL = os.getenv(
    "DEEPSEEK_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
DEFAULT_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

# 思考强度合法取值（S47）：None=不传（模型默认）；off=显式关闭；
# low/medium/high/xhigh/max = reasoning_effort（OpenAI 标准参数，可顶层直传）
THINKING_VALUES: tuple[str, ...] = ("off", "low", "medium", "high", "xhigh", "max")


def _usage_dict(usage: Any) -> dict[str, int] | None:
    """S99：OpenAI 兼容 usage 对象 → 模型无关 dict（无 usage 返回 None）。"""
    if usage is None:
        return None
    return {
        "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(usage, "total_tokens", 0) or 0),
    }


def validate_thinking(thinking: str | None) -> str | None:
    """校验思考强度取值；非法值抛 ValueError（配置错误应尽早暴露）。"""
    if thinking is None:
        return None
    v = str(thinking).strip().lower()
    if v not in THINKING_VALUES:
        raise ValueError(f"非法思考强度 {thinking!r}：可选 {THINKING_VALUES}（或省略交模型默认）")
    return v


def _apply_thinking(kwargs: dict[str, Any], thinking: str | None) -> None:
    """把思考强度写入请求参数（S47）。

    - "off"：显式关闭思考——两个平台的参数**同时发**（S136 双平台兼容）：
      DashScope/千问认识 enable_thinking（非 OpenAI 标准 → extra_body），
      DeepSeek 官方 API（api.deepseek.com）认识 thinking: {type: disabled}——
      只发 enable_thinking 切官方 API 时开关无效/可能报错（官方文档用 thinking.type）。
      未知字段按 OpenAI 兼容约定被忽略，双发无害。
    - low/medium/high/xhigh/max：reasoning_effort 是 OpenAI 标准参数 → 顶层直传
      （v4-flash 默认思考开，effort 控制推理强度；low/medium 映射 high、xhigh 映射 max）
    """
    if thinking is None:
        return
    if thinking == "off":
        extra = dict(kwargs.get("extra_body") or {})
        extra["enable_thinking"] = False
        extra["thinking"] = {"type": "disabled"}  # S136：DeepSeek 官方 API 开关参数
        kwargs["extra_body"] = extra
    else:
        kwargs["reasoning_effort"] = thinking


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
    """把 core 的 Message 转成 OpenAI chat 消息。

    S23 协议完整化：metadata 里的结构化信息转成原生字段——
    - assistant 消息带 metadata.tool_calls → OpenAI 原生 tool_calls 数组（配对声明）
    - assistant 消息带 metadata.reasoning → reasoning_content 字段（思考模式回传）
    - tool 消息带 metadata.tool_call_id → OpenAI 原生 tool_call_id（配对结果）
    旧数据（无 metadata）保持纯文本，兼容 DashScope 宽容模式。

    思考模式回传（S49 修正）：DeepSeek 思考模式下生成的 assistant 消息带
    reasoning_content，后续请求把该消息作为上下文发回时 MUST 带回 reasoning_content，
    否则 API 返回 400「reasoning_content must be passed back」——表现为前端一直
    「思考中」但无响应（流连接打开 200/0ms 后模型调用立即失败）。
    """
    msg: dict[str, Any] = {"role": m.role, "content": m.content}
    if m.role == "assistant":
        calls = m.metadata.get("tool_calls")
        # 仅当全部调用都带真实 id 才发原生 tool_calls 声明（配对完整性）：
        # 无 id 的旧链路保持纯文本（DashScope 宽容模式）；否则 assistant 声明了
        # 而 tool 消息不配对会导致严格模式 400。
        if (
            isinstance(calls, list)
            and calls
            and all(isinstance(c, dict) and c.get("id") for c in calls)
        ):
            native_calls: list[dict[str, Any]] = []
            for c in calls:
                native_calls.append(
                    {
                        "id": str(c.get("id")),
                        "type": "function",
                        "function": {
                            "name": str(c.get("name") or ""),
                            "arguments": json.dumps(c.get("arguments") or {}, ensure_ascii=False),
                        },
                    }
                )
            msg["tool_calls"] = native_calls
        # 思考模式回传：metadata.reasoning 非空时作为 reasoning_content 发回
        reasoning = m.metadata.get("reasoning")
        if isinstance(reasoning, str) and reasoning:
            msg["reasoning_content"] = reasoning
    elif m.role == "tool":
        tid = m.metadata.get("tool_call_id")
        if isinstance(tid, str) and tid:
            msg["tool_call_id"] = tid
    return msg


class DeepSeekModel:
    """基于 OpenAI SDK 的真实 DeepSeek 调用器（实现 core.Model 协议）。"""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        stream: bool = False,
        on_delta: Callable[[str], None] | None = None,
        timeout: float = 120.0,
        context_window: int | None = None,
        thinking: str | None = None,
    ) -> None:
        """
        stream: 流式传输（SSE 用）；on_delta: 文本增量回调（stream=True 时逐段触发）。
        timeout: 单次请求超时（秒）。
        max_tokens（S26）：单次输出上限 4096→8192——长章节写作（>4000 token）不再频繁触顶截断；
            可显式传参覆盖（写超长章时调用方可调）。
        context_window（S26）：模型上下文窗口（token），用于驱动 token 预算按窗口配置
            （build_app 装配 TokenBudget 时使用）。默认从环境变量 DEEPSEEK_CONTEXT_WINDOW 读，
            缺省 65536（保守；DeepSeek 兼容端点窗口未公开精确值，留安全余量）。
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
        self._thinking = validate_thinking(thinking)
        self._context_window = context_window or int(os.getenv("DEEPSEEK_CONTEXT_WINDOW", "65536"))
        # S131：显式 trust_env=False——openai SDK 默认 client 会读环境变量代理（国内网络
        # 常配 HTTP(S)_PROXY），把本地端点（Ollama/vLLM 等 127.0.0.1）请求发到代理导致 502。
        # 用 httpx2 自建 client 关闭代理读取；远端 API 不受影响（SDK 直连不走系统代理）。
        # S214：超时分阶段——connect/pool 10s 快速发现连不上；read 不超时（流式深度思考
        # 可能数分钟持续产 token，read timeout 会误杀正常流。idle 兜底由 SSE 层管）。
        _httpx_timeout = httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0)
        self._client = OpenAI(
            base_url=self._base_url,
            api_key=self._api_key,
            timeout=self._timeout,
            http_client=httpx.Client(trust_env=False, timeout=_httpx_timeout),  # type: ignore[arg-type]
        )

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def context_window(self) -> int:
        """S26：模型上下文窗口（token）——token 预算按窗口配置的输入。"""
        return self._context_window

    def respond(self, messages: list[Message], tools: list[ToolSpec]) -> ModelOutput:
        """真实调用 DeepSeek，返回模型无关的 ModelOutput（非流式路径）。"""
        messages = sanitize_tool_pairing(messages)  # core 通用守卫（S190）
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
        _apply_thinking(kwargs, self._thinking)

        if self._stream:
            return self._respond_stream(kwargs, None)

        def _call() -> ModelOutput:
            response = self._client.chat.completions.create(**kwargs)
            message = response.choices[0].message
            choice = response.choices[0] if response.choices else None
            fr = getattr(choice, "finish_reason", "") or ""
            # S22（D3）：finish_reason=="length" = 输出被 token 上限截断 → 标记
            truncated = fr == "length"

            text = message.content or ""
            # S49：思维链（reasoning_content）保留进 ModelOutput（只进运行记录，不注入上下文）
            reasoning = getattr(message, "reasoning_content", None) or ""
            tool_calls: list[ToolCall] = []
            if message.tool_calls:
                for tc in message.tool_calls:
                    fn = tc.function
                    try:
                        args: dict[str, Any] = json.loads(fn.arguments) if fn.arguments else {}
                    except json.JSONDecodeError:
                        # 截断防护（S21）：参数非法→标记，不执行，让模型重发
                        args = {"_raw": fn.arguments, "_malformed": True}
                    tool_calls.append(ToolCall(name=fn.name, arguments=args, id=tc.id or ""))

            return ModelOutput(
                text=text,
                tool_calls=tool_calls,
                truncated=truncated,
                reasoning=reasoning,
                finish_reason=fr,
            )

        return _call()

    def respond_stream(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        on_event: Callable[[Any], None] | None = None,
    ) -> ModelOutput:
        """流式协议（S21 移植 pi 模式）：边生成边 on_event 回调流式事件，
        返回完整 ModelOutput。事件名对齐 pi：text_delta / toolcall_delta / done。
        """
        messages = sanitize_tool_pairing(messages)  # core 通用守卫（S190）
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
        _apply_thinking(kwargs, self._thinking)
        return self._respond_stream(kwargs, on_event)

    def _respond_stream(
        self, kwargs: dict[str, Any], on_event: Callable[[Any], None] | None
    ) -> ModelOutput:
        """流式路径（S21 移植 pi 模式）：文本 delta / 工具参数 delta 逐段回调。

        - on_event 非空：发出 text_delta / toolcall_delta / done 事件（Agent 流式核心）
        - 同时兼容旧构造参数 on_delta（stream=True 旧路径）
        """
        kwargs["stream"] = True
        # S99：流式 usage 上报——OpenAI 兼容流式末尾会发 choices 为空的 usage 帧
        # （DeepSeek 支持 stream_options.include_usage，OpenAI 标准参数）
        kwargs["stream_options"] = {"include_usage": True}
        stream = self._client.chat.completions.create(**kwargs)
        text_parts: list[str] = []
        reasoning_parts: list[str] = []  # S49：思维链（流式 delta.reasoning_content）
        tool_acc: dict[int, dict[str, str]] = {}  # index -> {name, arguments}
        usage: dict[str, int] | None = None
        # S22（D3）：流式路径跟踪 finish_reason——"length" = 输出被截断
        truncated = False
        finish_reason = ""
        for chunk in stream:
            if not chunk.choices:
                # usage 帧（choices 为空）：流式结束前携带累计 token
                if getattr(chunk, "usage", None) is not None:
                    usage = _usage_dict(chunk.usage)
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if choice.finish_reason:
                finish_reason = choice.finish_reason
                truncated = truncated or choice.finish_reason == "length"
            if delta.content:
                text_parts.append(delta.content)
                if on_event is not None:
                    on_event(Event(type="text_delta", payload={"content": delta.content}))
                if self._on_delta:
                    self._on_delta(delta.content)
            rc = getattr(delta, "reasoning_content", None)
            if rc:
                reasoning_parts.append(str(rc))
                # S213：思考增量实时转发—避免思考期 SSE
                # 静默致前端 idle 超时误杀（对齐 pi）
                if on_event is not None:
                    on_event(
                        Event(
                            type="reasoning_delta",
                            payload={"content": str(rc)},
                        )
                    )
            for tc in delta.tool_calls or []:
                acc = tool_acc.setdefault(tc.index, {"name": "", "arguments": "", "id": ""})
                if tc.function and tc.function.name:
                    acc["name"] += tc.function.name
                if tc.function and tc.function.arguments:
                    acc["arguments"] += tc.function.arguments
                    if on_event is not None:
                        on_event(
                            Event(
                                type="toolcall_delta",
                                payload={"content": tc.function.arguments},
                            )
                        )
                if tc.id and not acc["id"]:
                    acc["id"] = tc.id
        text = "".join(text_parts)
        reasoning = "".join(reasoning_parts)
        tool_calls: list[ToolCall] = []
        for idx in sorted(tool_acc):
            acc = tool_acc[idx]
            try:
                args: dict[str, Any] = json.loads(acc["arguments"]) if acc["arguments"] else {}
            except json.JSONDecodeError:
                # 截断防护（S21）：参数非法→标记，不执行，让模型重发
                args = {"_raw": acc["arguments"], "_malformed": True}
            tool_calls.append(ToolCall(name=acc["name"], arguments=args, id=acc.get("id", "")))
        # 注意：这里**不发 done 事件**——done 由 Agent 循环在轮次语义完成后 emit
        # （无工具终答/取消/错误）。若模型层发 done，SSE 端会收到"假 done"提前断开，
        # 后续 tool_call/tool_result/text 事件全丢（S25 修复：工具场景 SSE 提前断）。
        return ModelOutput(
            text=text,
            tool_calls=tool_calls,
            truncated=truncated,
            reasoning=reasoning,
            usage=usage,  # S99：流式 usage（include_usage 末尾帧）
            finish_reason=finish_reason,
        )
