"""
anyspark.server.retry — 重试组件（re-export，向后兼容）。

S15 起重试实现移到 core（anyspark.core.retry）——流程基建（A 类硬编码）提升为
可组合组件（RetryingModel 包装，任何模型可套，模型无关）。
本模块保留 `retry_with_backoff` 的 re-export，旧调用方（test_retry 等）不受影响。
"""

from anyspark.core.retry import RETRYABLE, RetryingModel, retry_with_backoff

__all__ = ["RETRYABLE", "RetryingModel", "retry_with_backoff"]
