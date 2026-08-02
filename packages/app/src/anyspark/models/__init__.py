"""anyspark.models — 真实模型适配器。"""

from .deepseek import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DeepSeekModel,
    to_openai_message,
    to_openai_tool,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "DeepSeekModel",
    "to_openai_message",
    "to_openai_tool",
]
