# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

import asyncio
import logging
import os
import time
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass, field

import httpx
from httpx import Timeout
from openai import OpenAI

from .config import config
from .retry import calculate_delay, is_connection_error, is_context_overflow, is_retryable, with_retry

logger = logging.getLogger(__name__)

# ── Provider client cache ──────────────────────────────────────────────────
_clients: dict = {}  # provider_id → OpenAI client instance

# Legacy MODELS dict — kept for backward compat (mode.py, system_prompt, etc.)
MODELS = {
    "pro": config.llm.model_pro,
    "flash": config.llm.model_flash,
}

CREATIVE_TASKS = set(config.llm.creative_tasks)


# ── Mode helpers ────────────────────────────────────────────────────────────


def _settings():
    """Lazy import to avoid circular deps."""
    from .settings import get_settings

    return get_settings()


def get_mode() -> str:
    try:
        return _settings().mode
    except (AttributeError, RuntimeError):
        return config.llm.mode


def set_mode(mode: str):
    """Update mode in settings (persisted)."""
    from .settings import VALID_MODES, get_settings, update_settings

    if mode not in VALID_MODES:
        return
    s = get_settings()
    s.mode = mode
    update_settings(s)
    # Also keep MODELS in sync
    _sync_models()


def _sync_models():
    """Refresh MODELS dict from current settings slots."""
    global MODELS
    try:
        s = _settings()
        MODELS["pro"] = s.slot_pro.model or config.llm.model_pro
        MODELS["flash"] = s.slot_flash.model or config.llm.model_flash
    except (AttributeError, RuntimeError):
        MODELS["pro"] = config.llm.model_pro
        MODELS["flash"] = config.llm.model_flash


# ── Model resolution ────────────────────────────────────────────────────────


def model_for(task: str) -> str:
    """Return model name for the given task (legacy signature)."""
    _, model = _resolve(task)
    return model


def _resolve(task: str) -> tuple:
    """Return (provider_id, model_name) for the given task."""
    try:
        from .settings import get_settings, task_to_type

        s = get_settings()
        mode = s.mode

        if mode == "quality":
            slot = s.slot_pro
        elif mode == "flash":
            slot = s.slot_flash
        elif mode == "split":
            slot = s.slot_pro if task in CREATIVE_TASKS else s.slot_flash
        elif mode == "custom":
            task_type = task_to_type(task)
            slot_name = s.custom_map.get(task_type, "flash")
            slot = s.slot_pro if slot_name == "pro" else s.slot_flash
        else:
            slot = s.slot_flash

        return (slot.provider_id, slot.model)
    except (AttributeError, RuntimeError, KeyError):
        # Fallback to legacy config
        if get_mode() == "quality":
            return ("", config.llm.model_pro)
        return ("", config.llm.model_flash)


# ── Client factory ──────────────────────────────────────────────────────────


def _make_httpx_client() -> httpx.Client:
    """Create an httpx client that bypasses system proxy by default.

    On Windows, httpx respects WinINET proxy settings (System Proxy).
    VPN/Clash proxies (e.g. 127.0.0.1:29290) intercept TLS connections
    and cause [SSL: UNEXPECTED_EOF_WHILE_READING] errors during long
    streaming responses. Setting trust_env=False bypasses this.

    Users who need a proxy can set LLM_PROXY env var explicitly.
    """
    proxy_url = os.getenv("LLM_PROXY", "")
    kwargs = {
        "timeout": Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0),
    }
    if proxy_url:
        kwargs["proxy"] = proxy_url
    else:
        # Bypass system proxy (WinINET on Windows, HTTP_PROXY env on Linux)
        kwargs["trust_env"] = False
    return httpx.Client(**kwargs)


def _get_client_for_provider(provider_id: str) -> OpenAI:
    """Get or create an OpenAI client for the given provider."""
    if provider_id in _clients:
        return _clients[provider_id]

    try:
        from .settings import get_settings

        s = get_settings()
        provider = s.get_provider(provider_id)
        if provider:
            client = OpenAI(
                api_key=provider.api_key,
                base_url=provider.base_url or "https://api.deepseek.com",
                timeout=Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0),
                max_retries=0,
                http_client=_make_httpx_client(),
            )
            _clients[provider_id] = client
            return client
    except Exception as e:
        logger.warning(f"Failed to create client for provider {provider_id}: {e}")

    # Fallback: legacy single client
    return get_client()


def get_client() -> OpenAI:
    """Legacy: return client for the default (pro) provider."""
    try:
        from .settings import get_settings

        s = get_settings()
        return _get_client_for_provider(s.slot_pro.provider_id)
    except (AttributeError, RuntimeError, KeyError):
        pass

    # Ultimate fallback
    global _clients
    if "_legacy" not in _clients:
        _clients["_legacy"] = OpenAI(
            api_key=config.llm.api_key,
            base_url=config.llm.base_url,
            timeout=Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0),
            max_retries=0,
            http_client=_make_httpx_client(),
        )
    return _clients["_legacy"]


def reload_clients():
    """Clear all cached clients (call after provider changes).

    Properly closes existing client connections to prevent TCP connection leaks.
    """
    global _clients
    for c in _clients.values():
        try:
            c.close()
        except Exception:
            pass
    _clients = {}
    _sync_models()


# ── Sync calls ──────────────────────────────────────────────────────────────

_STREAM_MAX_RETRIES = 5


def chat(prompt: str, system: str = "", temperature: float = 0.3, task: str = "general") -> str:
    """Sync chat with retry on transient connection errors."""
    last_error = None
    for attempt in range(_STREAM_MAX_RETRIES + 1):
        try:
            provider_id, model = _resolve(task)
            client = _get_client_for_provider(provider_id)
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=65536 if task in ("writing", "editing", "workflow") else 16384,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            last_error = e
            if not is_retryable(e) or attempt >= _STREAM_MAX_RETRIES:
                raise
            delay = calculate_delay(attempt, e)
            err_type = "连接" if is_connection_error(e) else "服务"
            logger.warning(
                f"[{err_type}错误] 重试 {attempt + 1}/{_STREAM_MAX_RETRIES}: {e!s:.80s} → {delay:.1f}s 后重试"
            )
            time.sleep(delay)
    raise last_error  # unreachable


def chat_stream(
    prompt: str, system: str = "", temperature: float = 0.3, task: str = "general"
) -> Generator[str, None, None]:
    """Streaming chat with retry on transient connection errors.

    Retry is only safe BEFORE any content is yielded. Once the stream
    starts producing output, a mid-stream disconnect cannot be retried
    (would produce duplicate content). In that case the error propagates.
    """
    last_error = None
    for attempt in range(_STREAM_MAX_RETRIES + 1):
        try:
            provider_id, model = _resolve(task)
            client = _get_client_for_provider(provider_id)
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            stream = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                stream=True,
                max_tokens=65536 if task in ("writing", "editing", "workflow") else 16384,
            )
            content_yielded = False
            for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    content_yielded = True
                    yield content
            return  # success
        except Exception as e:
            last_error = e
            # If content was already yielded, we cannot retry (would duplicate)
            if content_yielded or not is_retryable(e) or attempt >= _STREAM_MAX_RETRIES:
                raise
            delay = calculate_delay(attempt, e)
            err_type = "连接" if is_connection_error(e) else "服务"
            logger.warning(
                f"[{err_type}错误/流式] 重试 {attempt + 1}/{_STREAM_MAX_RETRIES}: {e!s:.80s} → {delay:.1f}s 后重试"
            )
            time.sleep(delay)
    raise last_error  # unreachable


# ── Data classes ────────────────────────────────────────────────────────────


@dataclass
class ToolCall:
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class StreamEvent:
    type: str
    data: dict = field(default_factory=dict)


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = ""
    reasoning: str = ""  # DeepSeek reasoner reasoning_content (captured, not injected back)


# ── Tool calls ──────────────────────────────────────────────────────────────


def chat_with_tools(
    messages: list[dict],
    tools: list[dict] | None = None,
    temperature: float = 0.3,
    task: str = "general",
    stream: bool = False,
) -> LLMResponse:
    provider_id, model = _resolve(task)
    client = _get_client_for_provider(provider_id)
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        kwargs["tools"] = [{"type": "function", "function": t} for t in tools]
        kwargs["tool_choice"] = "auto"

    response = client.chat.completions.create(**kwargs)
    msg = response.choices[0].message

    result = LLMResponse(
        content=msg.content or "",
        finish_reason=response.choices[0].finish_reason or "",
        reasoning=getattr(msg, "reasoning_content", "") or "",
    )
    if msg.tool_calls:
        result.tool_calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments) for tc in msg.tool_calls
        ]
    return result


async def chat_with_tools_async(
    messages: list[dict], tools: list[dict] | None = None, temperature: float = 0.3, task: str = "general"
) -> LLMResponse:
    loop = asyncio.get_running_loop()

    async def _call():
        return await loop.run_in_executor(None, lambda: chat_with_tools(messages, tools, temperature, task))

    return await with_retry(_call)


def chat_with_tools_stream(
    messages: list[dict], tools: list[dict] | None = None, temperature: float = 0.3, task: str = "general"
) -> Generator[StreamEvent, None, None]:
    provider_id, model = _resolve(task)
    client = _get_client_for_provider(provider_id)
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    if tools:
        kwargs["tools"] = [{"type": "function", "function": t} for t in tools]
        kwargs["tool_choice"] = "auto"

    stream = client.chat.completions.create(**kwargs)

    current_tool_calls: dict[int, ToolCall] = {}
    content_started = False

    for chunk in stream:
        delta = chunk.choices[0].delta
        finish_reason = chunk.choices[0].finish_reason

        if delta.content:
            if not content_started:
                yield StreamEvent(type="text-start")
                content_started = True
            yield StreamEvent(type="text-delta", data={"text": delta.content})

        # DeepSeek reasoner emits reasoning_content separately. Capture it so
        # the turn history can preserve the model's thinking (for optional UI
        # viewing) — it is deliberately NOT replayed into later LLM context.
        reasoning_chunk = getattr(delta, "reasoning_content", None)
        if reasoning_chunk:
            yield StreamEvent(type="reasoning-delta", data={"text": reasoning_chunk})

        if delta.tool_calls:
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index
                if idx not in current_tool_calls:
                    current_tool_calls[idx] = ToolCall()
                    if tc_delta.id:
                        current_tool_calls[idx].id = tc_delta.id
                    yield StreamEvent(type="tool-call-start", data={"index": idx})

                if tc_delta.id and not current_tool_calls[idx].id:
                    current_tool_calls[idx].id = tc_delta.id
                if tc_delta.function:
                    if tc_delta.function.name:
                        current_tool_calls[idx].name = tc_delta.function.name
                    if tc_delta.function.arguments:
                        current_tool_calls[idx].arguments += tc_delta.function.arguments
                        yield StreamEvent(
                            type="tool-input-delta",
                            data={
                                "index": idx,
                                "delta": tc_delta.function.arguments,
                            },
                        )

        if finish_reason:
            if content_started:
                yield StreamEvent(type="text-end")
            for idx, tc in sorted(current_tool_calls.items()):
                yield StreamEvent(
                    type="tool-call-end",
                    data={
                        "index": idx,
                        "id": tc.id,
                        "name": tc.name,
                        "arguments": tc.arguments,
                    },
                )
            yield StreamEvent(type="finish", data={"reason": finish_reason})


async def chat_with_tools_stream_async(
    messages: list[dict],
    tools: list[dict] | None = None,
    temperature: float = 0.3,
    task: str = "general",
    max_stream_retries: int = 5,
) -> AsyncGenerator[StreamEvent, None]:
    from .retry import is_connection_error

    last_error = None

    for attempt in range(max_stream_retries + 1):
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()

        def _run_stream():
            try:
                for event in chat_with_tools_stream(messages, tools, temperature, task):
                    queue.put_nowait(event)
            except Exception as e:
                queue.put_nowait(StreamEvent(type="error", data={"error": str(e), "exception": e}))
            finally:
                queue.put_nowait(None)

        loop.run_in_executor(None, _run_stream)
        # Note: asyncio.Future.cancel() cannot interrupt a running thread.
        # The _run_stream thread uses queue.put_nowait which never blocks
        # (unbounded asyncio.Queue), so it runs to completion regardless.
        # We save the future for potential cancellation tracking, but the
        # primary cleanup mechanism is the generator's CancelledError handler.

        should_retry = False
        data_yielded = False

        while True:
            event = await queue.get()
            if event is None:
                break
            if event.type == "error":
                exc = event.data.get("exception")
                if exc and is_retryable(exc) and not data_yielded and attempt < max_stream_retries:
                    last_error = exc
                    should_retry = True
                    try:
                        while not queue.empty():
                            queue.get_nowait()
                    except (asyncio.QueueEmpty, ValueError):
                        pass
                    break
                if exc and is_context_overflow(exc):
                    yield StreamEvent(type="context-overflow", data={"error": str(exc)})
                    return
                elif exc and is_retryable(exc):
                    yield StreamEvent(type="retryable-error", data={"error": str(exc)})
                    return
                else:
                    yield StreamEvent(type="error", data={"error": event.data.get("error", "unknown")})
                    return
            if event.type in ("text-delta", "tool-call-end", "tool-input-delta"):
                data_yielded = True
            yield event

        if should_retry:
            delay = calculate_delay(attempt, last_error)
            err_type = "连接" if is_connection_error(last_error) else "服务"
            logger.warning(
                f"[{err_type}错误/流式] 重试 {attempt + 1}/{max_stream_retries}: "
                f"{last_error!s:.80s} → {delay:.1f}s 后重试"
            )
            await asyncio.sleep(delay)
            continue
        return

    yield StreamEvent(type="error", data={"error": f"流式调用重试 {max_stream_retries} 次后仍失败: {last_error}"})
