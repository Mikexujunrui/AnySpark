"""
anyspark.core.retry — 流程基建：指数退避重试 + 可组合的重试包装（A 类硬编码）。

设计（DESIGN §1 模型局限弥补"不会自己调度 → 指数退避重试、超时熔断"）：
- retry 属于过程控制（硬编码 A 类），且应是**可拼接组件**——任何实现 Model 协议的模型
  都能套 RetryingModel 获得重试能力，不依赖具体适配器（模型无关）。
- 网络/上游抖动时自动重试，避免一次失败打断写作；重试间隔指数退避 + 抖动。
- 业务错误（ValueError 等）不重试——重试只针对网络/上游类异常。
- S22 移植 pi 的错误分类（pi-ai/dist/utils/retry.js）：**按错误消息正则分类**——
  瞬时类（429/5xx/rate limit/overloaded/connection/timeout）可重试；
  quota/billing 类（insufficient_quota/out of budget/quota exceeded/billing）不可重试，立刻失败。
  覆盖 OpenAI SDK 的 APIStatusError（429/500/502/503 等，非 TimeoutError/ConnectionError 子类）。
"""

from __future__ import annotations

import random
import re
import time
from collections.abc import Callable
from typing import Any, TypeVar, cast

from .loop import Model
from .protocol import ToolSpec
from .types import Message, ModelOutput

T = TypeVar("T")

# 可重试的异常类型（网络/上游类；业务错误不重试）
RETRYABLE_EXC_TYPES = (TimeoutError, ConnectionError, OSError)
# 兼容别名（S15 旧名）：S22 起判定升级为 is_retryable()（类型+文本双通道），
# 此常量保留给旧调用方（server/retry.py re-export 等）
RETRYABLE = RETRYABLE_EXC_TYPES

# ---- S22：错误消息文本分类（pi 模式）----
# 瞬时/上游类错误（可重试）：HTTP 5xx、限流、过载、连接/超时、流提前终止
_RETRYABLE_TEXT = re.compile(
    r"("
    r"overloaded|rate.?limit|too many requests|429|"
    r"500|502|503|504|524|service.?unavailable|server.?error|internal.?error|"
    r"provider.?returned.?error|network.?error|connection.?(error|refused|lost)|"
    r"fetch failed|getaddrinfo|ENOTFOUND|EAI_AGAIN|upstream.?connect|reset before headers|"
    r"socket hang up|socket connection was closed|timed? ?out|timeout|terminated|"
    r"ended without|stream ended|http2 request did not get a response|"
    r"you can retry your request|try your request again|please retry your request|"
    r"ResourceExhausted"
    r")",
    re.IGNORECASE,
)
# 配额/余额类错误（不可重试）：立刻失败，不浪费重试
_NON_RETRYABLE_TEXT = re.compile(
    r"("
    r"GoUsageLimitError|FreeUsageLimitError|insufficient_quota|out of budget|"
    r"quota exceeded|billing|available balance|monthly usage limit reached"
    r")",
    re.IGNORECASE,
)


def is_retryable(exc: Exception) -> bool:
    """判定一次异常是否值得重试（S22：类型 + 错误文本双通道，移植 pi 分类）。

    - 网络/超时类异常类型 → 可重试
    - 文本命中 quota/billing 类 → 不可重试（立刻失败）
    - 文本命中瞬时类（429/5xx/限流/过载/断流）→ 可重试
    - 其余（业务 ValueError 等）→ 不重试
    """
    if isinstance(exc, RETRYABLE_EXC_TYPES):
        return True
    text = str(exc)
    if _NON_RETRYABLE_TEXT.search(text):
        return False
    return bool(_RETRYABLE_TEXT.search(text))


def retry_with_backoff(
    fn: Callable[[], T],
    retries: int = 3,
    base: float = 1.0,
    max_wait: float = 10.0,
    on_retry: Callable[[int, Exception], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> T:
    """指数退避重试：第 n 次等待 base * 2^n + 抖动，超过 retries 次则抛出最后异常。

    cancelled（S22）：可选取消回调（如检查 CancellationToken）——睡眠期间分段检查，
    取消则立即抛出最后一次异常（上游可转成 aborted），不等完整个退避。
    """
    attempt = 0
    last_exc: Exception | None = None
    while True:
        try:
            return fn()
        except Exception as exc:  # 分类由 is_retryable 决定
            if not is_retryable(exc):
                raise
            attempt += 1
            last_exc = exc
            if attempt >= retries:
                break
            wait = min(max_wait, base * (2 ** (attempt - 1))) + random.uniform(0, 0.5)
            if on_retry:
                on_retry(attempt, exc)
            _sleep_checking_cancel(wait, cancelled)
            if cancelled is not None and cancelled():
                # 取消：不等完退避，抛出最后异常（上游转成 aborted）
                break
    assert last_exc is not None
    raise last_exc


def _sleep_checking_cancel(wait: float, cancelled: Callable[[], bool] | None) -> None:
    """睡眠等待，期间分段检查取消回调（默认 200ms 粒度）——取消则提前抛出。"""
    if cancelled is None:
        time.sleep(wait)
        return
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if cancelled():
            return  # 取消：由上层把最后一次异常转成 aborted
        time.sleep(min(0.2, deadline - time.monotonic()))


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
        # S22：当前运行的取消回调（Agent run 时注入，重试睡眠期间可中断）
        self._cancelled: Callable[[], bool] | None = None

    def set_cancelled(self, cancelled: Callable[[], bool] | None) -> None:
        """注入取消回调（Agent 每轮 run 时设置；线程安全由调用方保证——同会话串行）。"""
        self._cancelled = cancelled

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
            cancelled=self._cancelled,
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
            cancelled=self._cancelled,
        )
