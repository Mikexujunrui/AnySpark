"""anyspark.models — 真实模型适配器（S131 多协议：openai/anthropic/gemini/responses）。"""

from .anthropic import AnthropicModel
from .deepseek import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DeepSeekModel,
    to_openai_message,
    to_openai_tool,
    validate_thinking,
)
from .gemini import GeminiModel
from .registry import PROTOCOLS, validate_protocol
from .responses import ResponsesModel

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "PROTOCOLS",
    "AnthropicModel",
    "DeepSeekModel",
    "GeminiModel",
    "ResponsesModel",
    "to_openai_message",
    "to_openai_tool",
    "validate_protocol",
    "validate_thinking",
]
