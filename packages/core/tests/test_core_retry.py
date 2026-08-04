"""anyspark.core.retry — 重试组件测试（S15：流程基建提升为 core 可拼接组件）。"""

from __future__ import annotations

from anyspark.core.retry import RetryingModel, retry_with_backoff
from anyspark.core.types import Message, ModelOutput


class _FlakyModel:
    """fake inner：前 n 次抛网络异常，之后成功（验证组合包装重试）。"""

    def __init__(self, fail_times: int = 2) -> None:
        self.calls = 0
        self.fail_times = fail_times
        self.model_name = "flaky"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ConnectionError("网络抖动")
        return ModelOutput(text="成功")


def test_retrying_model_recovers() -> None:
    """组合包装：失败自动重试，恢复后返回内层结果。"""
    inner = _FlakyModel(fail_times=2)
    model = RetryingModel(inner, retries=4, base=0.01)
    out = model.respond([], [])
    assert out.text == "成功"
    assert inner.calls == 3


def test_retrying_model_gives_up() -> None:
    """超过重试次数抛出最后异常。"""
    inner = _FlakyModel(fail_times=99)
    model = RetryingModel(inner, retries=2, base=0.01)
    try:
        model.respond([], [])
        raise AssertionError("应抛出 ConnectionError")
    except ConnectionError:
        assert inner.calls == 2


def test_retrying_model_passthrough_model_name() -> None:
    """model_name 穿透到内层（组合包装对装配透明）。"""
    inner = _FlakyModel()
    model = RetryingModel(inner)
    assert model.model_name == "flaky"
    assert model.inner is inner  # 组合根可解包判断底层能力


def test_retry_not_swallow_business_error() -> None:
    """业务错误不重试（只重试网络/上游类）。"""

    def fn() -> None:
        raise ValueError("业务错误")

    try:
        retry_with_backoff(fn, retries=3, base=0.01)
        raise AssertionError("应抛出 ValueError")
    except ValueError:
        pass


def test_retry_classifies_http_429() -> None:
    """S22（D2）：OpenAI SDK 的 APIStatusError（429/5xx，非网络异常子类）
    按错误文本分类为可重试——限流/过载时自动重试。"""
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            # OpenAI SDK APIStatusError 的真实形态：非 OSError 子类
            raise RuntimeError(
                "Error code: 429 - {'error': {'message': 'Rate limit reached', "
                "'type': 'rate_limit_error'}}"
            )
        return "恢复"

    assert retry_with_backoff(fn, retries=3, base=0.01) == "恢复"
    assert calls["n"] == 2


def test_retry_classifies_http_503() -> None:
    """S22（D2）：503 service unavailable 可重试（上游抖动）。"""
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("Error code: 503 - Service Unavailable")
        return "恢复"

    assert retry_with_backoff(fn, retries=3, base=0.01) == "恢复"


def test_quota_error_not_retried() -> None:
    """S22（D2）：quota/billing 类错误不可重试（移植 pi：立刻失败，不浪费退避）。"""
    calls = {"n": 0}

    def fn() -> None:
        calls["n"] += 1
        raise RuntimeError("Error code: 429 - insufficient_quota: 余额不足")

    try:
        retry_with_backoff(fn, retries=3, base=0.01)
        raise AssertionError("应抛出（quota 不重试）")
    except RuntimeError:
        pass
    assert calls["n"] == 1  # 一次即失败


def test_retry_sleep_cancelled() -> None:
    """S22（D2）：重试退避睡眠期间取消回调触发 → 提前抛出最后异常。"""
    calls = {"n": 0}

    def fn() -> None:
        calls["n"] += 1
        raise ConnectionError("网络抖动")

    try:
        retry_with_backoff(fn, retries=5, base=0.5, cancelled=lambda: True)
        raise AssertionError("应抛出 ConnectionError")
    except ConnectionError:
        pass
    assert calls["n"] == 1  # 第一次失败后睡眠被取消，不再重试
