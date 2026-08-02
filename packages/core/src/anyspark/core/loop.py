"""
anyspark.core.loop — Agent 循环（机制 1 的过程控制，硬编码）。

极简单元循环（DESIGN.md 第 4 节"协议层"）：
    while True:
        读系统提示 + 历史消息 → 模型输出
        解析输出中的工具调用
        if 无工具调用: 产出最终文本，结束本轮
        else: 逐一执行工具 → 结果回填进上下文 → 回到开头

核心不认识任何具体功能（对齐/探索等均外置），只负责走通这个循环。
模型无关：通过注入的 `Model` 协议解耦，任何"文本进文本出"的模型都能接入。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .events import Event, EventEmitter
from .protocol import (
    ToolRegistry,
    backfill_content_tool_result,
    execute,
    parse_tool_calls,
)
from .storage import ConversationStore, InMemoryConversationStore
from .types import Message, ToolCall, ToolResult, Turn


class Model(Protocol):
    """模型协议：输入上下文消息 + 工具清单，返回 assistant 输出文本。

    文本输出中可包含工具调用（由 loop 用 parse_tool_calls 解析）。
    这是"模型无关"的解耦点——真实模型接入时实现此协议即可。
    """

    def respond(self, messages: list[Message], tool_descriptions: str) -> str: ...


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

        tool_desc = self.registry.describe()
        # 组装系统提示（注入工具清单 + 系统指令）
        system_block = self.system_prompt
        if system_block:
            system_block += "\n\n"
        system_block += (
            "可用工具：\n"
            + (tool_desc if tool_desc else "（本期无工具）")
            + "\n需要时用 `tool(a=…)` 形式调用工具；不需要工具则直接输出最终结果。"
        )

        for _ in range(self.max_tool_iterations):
            self.events.emit(Event(type="turn_start", payload={}))
            history = store.messages(conversation_id)
            prompt_messages = [Message(role="system", content=system_block), *history]

            raw = self.model.respond(prompt_messages, tool_desc)
            calls = parse_tool_calls(raw)

            if not calls:
                # 本轮无工具调用 → 产出最终文本
                store.append(conversation_id, Message(role="assistant", content=raw))
                self.events.emit(Event(type="text", payload={"content": raw}))
                self.events.emit(Event(type="done", payload={}))
                return Turn(text=raw, tool_calls=executed, tool_results=results)

            # 有工具调用：执行并把结果回填
            self.events.emit(Event(type="tool_call", payload={"name": [c.name for c in calls]}))
            for call in calls:
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
