"""
anyspark — AnySpark v4 内核包。

铁律（见 DESIGN.md 第 4 节）：
- core 不依赖任何其他包（单向依赖、无循环）。
- 模型无关：所有承载物为明确无歧义自然语言。
- 机制硬编码（设计者写），内容自然语言（模型生成）。

本层只做便捷再导出；真实实现全部在 anyspark.core 子包。
（per-file-ignores 关闭本文件的 F401，详见根 pyproject.toml）
"""

from anyspark.core import (
    GENERIC_EVENT_TYPES,
    Agent,
    Conversation,
    ConversationStore,
    Event,
    EventEmitter,
    InMemoryConversationStore,
    Message,
    Model,
    ParamSpec,
    ToolCall,
    ToolRegistry,
    ToolResult,
    ToolSpec,
    Turn,
    add_implementer,
    backfill_content_tool_result,
    echo_implementer,
    execute,
    parse_tool_calls,
    register_builtins,
)
from anyspark.core import __version__ as __version__
