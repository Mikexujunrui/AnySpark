#
# AnySpark v4 — anyspark-core 内核包
# 本包是 v4 内核，只承载极简单元循环所需的最小协议。
# 铁律：core 不依赖任何其他包；机制硬编码，内容自然语言，模型无关。
# 版本：0.0.1（S0 地基）
#
__version__ = "0.0.1"

from .events import GENERIC_EVENT_TYPES, Event, EventEmitter, EventListener
from .loop import Agent, CancellationToken, ContextCompressor, Model
from .protocol import (
    ParamSpec,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    backfill_content_tool_result,
    execute,
)
from .retry import RETRYABLE_EXC_TYPES, RetryingModel, retry_with_backoff
from .storage import Conversation, ConversationStore, InMemoryConversationStore
from .tools import (
    add_implementer,
    echo_implementer,
    register_builtins,
)
from .types import Message, ModelOutput, ToolCall, Turn

__all__ = [
    "GENERIC_EVENT_TYPES",
    "RETRYABLE_EXC_TYPES",
    "Agent",
    "CancellationToken",
    "ContextCompressor",
    "Conversation",
    "ConversationStore",
    "Event",
    "EventEmitter",
    "EventListener",
    "InMemoryConversationStore",
    "Message",
    "Model",
    "ModelOutput",
    "ParamSpec",
    "RetryingModel",
    "ToolCall",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "Turn",
    "add_implementer",
    "backfill_content_tool_result",
    "echo_implementer",
    "execute",
    "register_builtins",
    "retry_with_backoff",
]
