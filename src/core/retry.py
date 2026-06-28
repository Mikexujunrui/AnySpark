import asyncio
import logging
from collections.abc import AsyncGenerator, Callable
from typing import Any, TypeVar

from openai import APIConnectionError, APIError, APITimeoutError, RateLimitError

logger = logging.getLogger(__name__)

T = TypeVar("T")

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504, 529}
MAX_RETRIES = 5

CONN_INITIAL_DELAY = 0.5
CONN_MAX_DELAY = 8.0

RATE_INITIAL_DELAY = 2.0
RATE_MAX_DELAY = 30.0


def is_retryable(error: Exception) -> bool:
    if isinstance(error, (RateLimitError, APIConnectionError, APITimeoutError)):
        return True
    if isinstance(error, APIError):
        if error.status_code in RETRYABLE_STATUS_CODES:
            return True
        body = str(error.body or "").lower()
        if "overloaded" in body or "rate limit" in body or "too many requests" in body:
            return True
    err_str = str(error).lower()
    if any(k in err_str for k in ("connection", "connect", "reset", "refused", "eof", "broken pipe")):
        return True
    return False


def is_connection_error(error: Exception) -> bool:
    if isinstance(error, (APIConnectionError, APITimeoutError)):
        return True
    if isinstance(error, ConnectionError):
        return True
    err_str = str(error).lower()
    return any(k in err_str for k in ("connection", "connect", "timeout", "reset", "refused", "eof"))


def is_context_overflow(error: Exception) -> bool:
    if isinstance(error, APIError):
        body = str(error.body or "").lower()
        if "context" in body and ("overflow" in body or "too long" in body or "exceed" in body):
            return True
        if "maximum context length" in body:
            return True
    return False


def calculate_delay(attempt: int, error: Exception | None = None) -> float:
    if isinstance(error, APIError) and hasattr(error, "headers"):
        headers = getattr(error, "headers", None) or {}
        retry_after = None
        if hasattr(headers, "get"):
            retry_after = headers.get("retry-after") or headers.get("Retry-After")
        if retry_after:
            try:
                return min(float(retry_after), RATE_MAX_DELAY)
            except (ValueError, TypeError):
                pass

    if error and is_connection_error(error):
        return min(CONN_INITIAL_DELAY * (2 ** attempt), CONN_MAX_DELAY)

    return min(RATE_INITIAL_DELAY * (2 ** attempt), RATE_MAX_DELAY)


async def with_retry(fn: Callable[..., Any], *args, max_retries: int = MAX_RETRIES, **kwargs) -> Any:
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            result = fn(*args, **kwargs)
            if asyncio.iscoroutine(result):
                return await result
            return result
        except Exception as e:
            last_error = e
            if not is_retryable(e):
                raise
            if attempt >= max_retries:
                raise
            delay = calculate_delay(attempt, e)
            error_type = "连接" if is_connection_error(e) else "服务"
            logger.warning(f"[{error_type}错误] 重试 {attempt + 1}/{max_retries}: {e!s:.80s} → {delay:.1f}s 后重试")
            await asyncio.sleep(delay)

    raise last_error


async def with_retry_stream(fn: Callable[..., AsyncGenerator], *args,
                            max_retries: int = 3, **kwargs) -> AsyncGenerator:
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            async for item in fn(*args, **kwargs):
                yield item
            return
        except Exception as e:
            last_error = e
            if not is_retryable(e):
                raise
            if attempt >= max_retries:
                raise
            delay = calculate_delay(attempt, e)
            error_type = "连接" if is_connection_error(e) else "服务"
            logger.warning(f"[{error_type}错误/流式] 重试 {attempt + 1}/{max_retries}: {e!s:.80s} → {delay:.1f}s 后重试")
            await asyncio.sleep(delay)

    raise last_error
