"""
anyspark.server.retry — 流程基建：指数退避重试 + 超时熔断。

设计（DESIGN 模型局限弥补"不会自己调度 → 指数退避重试、超时熔断"）。
网络/上游抖动时自动重试，避免一次失败打断写作；重试间隔指数退避 + 抖动。
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

# 可重试的异常类型（网络/上游类；业务错误不重试）
RETRYABLE = (TimeoutError, ConnectionError, OSError)


def retry_with_backoff(
    fn: Callable[[], T],
    retries: int = 3,
    base: float = 1.0,
    max_wait: float = 10.0,
    on_retry: Callable[[int, Exception], None] | None = None,
) -> T:
    """指数退避重试：第 n 次等待 base * 2^n + 抖动，超过 retries 次则抛出最后异常。

    用法：result = retry_with_backoff(lambda: model.respond(...))
    """
    attempt = 0
    last_exc: Exception | None = None
    while True:
        try:
            return fn()
        except RETRYABLE as exc:
            attempt += 1
            last_exc = exc
            if attempt >= retries:
                break
            wait = min(max_wait, base * (2 ** (attempt - 1))) + random.uniform(0, 0.5)
            if on_retry:
                on_retry(attempt, exc)
            time.sleep(wait)
    assert last_exc is not None
    raise last_exc
