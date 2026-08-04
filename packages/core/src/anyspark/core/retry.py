"""
anyspark.core.retry — 流程基建：指数退避重试 + 可组合的重试包装（A 类硬编码）。

设计（DESIGN §1 模型局限弥补"不会自己调度 → 指数退避重试、超时熔断"）：
- retry 属于过程控制（硬编码 A 类），且应是**可拼接组件**——任何实现 Model 协议的模型
  都能套 RetryingModel 获得重试能力，不依赖具体适配器（模型无关）。
- 网络/上游抖动时自动重试，避免一次失败打断写作；重试间隔指数退避 + 抖动。
- 业务错误（ValueError 等）不重试——重试只针对网络/上游类异常。
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Any, TypeVar, cast

from .loop import Model
from .protocol import ToolSpec
from .types import Message, ModelOutput

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


class RetryingModel:
    """组合式重试包装：给任意 Model 协议实现套上指数退避重试。

    用法（组合根装配，模型无关）：
        model = RetryingModel(DeepSeekModel(...))   # 任何适配器可套
    通过 .inner 可访问被包装的模型（如判断流式能力、取 model_name）。
    """

    def __init__(
        self,
        model: Model,
        retries: int = 3,
        base: float = 1.0,
        max_wait: float = 10.0,
        on_retry: Callable[[int, Exception], None] | None = None,
    ) -> None:
        self.inner = model
        self._retries = retries
        self._base = base
        self._max_wait = max_wait
        self._on_retry = on_retry

    @property
    def model_name(self) -> str:
        name = getattr(self.inner, "model_name", None)
        return str(name) if name else "unknown"

    def respond(self, messages: list[Message], tools: list[ToolSpec]) -> ModelOutput:
        return retry_with_backoff(
            lambda: self.inner.respond(messages, tools),
            retries=self._retries,
            base=self._base,
            max_wait=self._max_wait,
            on_retry=self._on_retry,
        )

    def respond_stream(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        on_event: Callable[[Any], None] | None = None,
    ) -> ModelOutput:
        """流式透传（S21）：内层支持 respond_stream 则流式+重试；否则回退非流式。"""
        inner = self.inner
        if not hasattr(inner, "respond_stream"):
            return self.respond(messages, tools)
        stream_fn = inner.respond_stream
        return retry_with_backoff(
            lambda: cast(ModelOutput, stream_fn(messages, tools, on_event)),
            retries=self._retries,
            base=self._base,
            max_wait=self._max_wait,
            on_retry=self._on_retry,
        )
