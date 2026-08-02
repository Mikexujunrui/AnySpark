"""
anyspark.core.loop — Agent 循环（机制 1 的过程控制，硬编码）。

极简单元循环（DESIGN.md 第 4 节"协议层"）：
    while True:
        读系统提示 + 历史消息 → 模型输出（结构化 ModelOutput）
        if 无工具调用: 产出最终文本，结束本轮
        else: 逐一执行工具 → 结果回填进上下文 → 回到开头

核心不认识任何具体功能（对齐/探索等均外置），只负责走通这个循环。
模型无关：通过注入的 `Model` 协议解耦（适配器把真实 LLM 的响应翻译成
模型无关的 ModelOutput）。工具调用采用真实结构化协议，不做文本解析降级。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .events import Event, EventEmitter
from .protocol import ToolRegistry, ToolSpec, backfill_content_tool_result, execute
from .storage import ConversationStore, InMemoryConversationStore
from .types import Message, ModelOutput, ToolCall, ToolResult, Turn


class Model(Protocol):
    """模型协议：输入上下文消息 + 工具清单，返回结构化 ModelOutput。

    适配器自行把真实 LLM（如 DeepSeek）的响应翻译成模型无关的 ModelOutput
    （text + tool_calls）。这是"模型无关"的解耦点。
    """

    def respond(self, messages: list[Message], tools: list[ToolSpec]) -> ModelOutput: ...


@dataclass
class Agent:
    """极简 Agent：持有模型、工具注册表、存储、事件发射器。"""

    model: Model
    registry: ToolRegistry = field(default_factory=ToolRegistry)
    store: ConversationStore = field(default_factory=InMemoryConversationStore)
    events: EventEmitter = field(default_factory=EventEmitter)
    system_prompt: str = ""
    max_tool_iterations: int = 8  # 防无限循环硬上限

    def run(self, user_prompt: str, conversation_id: str | None = None) -> Turn:
        """跑一轮：读提示 → 调工具（可多轮）→ 回填 → 输出。返回最终 Turn。"""
        store = self.store
        if conversation_id is None:
            conv = store.create()
            conversation_id = conv.id
        elif store.get(conversation_id) is None:
            store.create(conversation_id)

        return self._loop(conversation_id, user_prompt)

    def _loop(self, conversation_id: str, user_prompt: str) -> Turn:
        store = self.store
        store.append(conversation_id, Message(role="user", content=user_prompt))
        self.events.emit(Event(type="user_text", payload={"content": user_prompt}))

        executed: list[ToolCall] = []
        results: list[ToolResult] = []

        # 系统提示（核心不注入工具语法文本；工具由 Model 适配器以原生 schema 传递）
        system_block = self.system_prompt.strip()

        for _ in range(self.max_tool_iterations):
            self.events.emit(Event(type="turn_start", payload={}))
            history = store.messages(conversation_id)
            prompt_messages = (
                [Message(role="system", content=system_block)] if system_block else []
            ) + history

            tools: list[ToolSpec] = self.registry.specs()
            output = self.model.respond(prompt_messages, tools)

            if not output.tool_calls:
                # 本轮无工具调用 → 产出最终文本
                store.append(conversation_id, Message(role="assistant", content=output.text))
                self.events.emit(Event(type="text", payload={"content": output.text}))
                self.events.emit(Event(type="done", payload={}))
                return Turn(text=output.text, tool_calls=executed, tool_results=results)

            # 有工具调用：执行并把结果回填
            self.events.emit(
                Event(type="tool_call", payload={"name": [c.name for c in output.tool_calls]})
            )
            for call in output.tool_calls:
                result = execute(self.registry, call)
                executed.append(call)
                results.append(result)
                backfill = backfill_content_tool_result(result)
                store.append(conversation_id, Message(role="tool", content=backfill))
                self.events.emit(
                    Event(type="tool_result", payload={"name": call.name, "ok": result.ok})
                )
        # 达到迭代上限则报错返回
        return Turn(
            text="达到最大工具迭代次数，已终止。",
            tool_calls=executed,
            tool_results=results,
        )
