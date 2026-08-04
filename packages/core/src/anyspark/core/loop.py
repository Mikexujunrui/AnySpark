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

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from .events import Event, EventEmitter
from .protocol import ToolRegistry, ToolSpec, backfill_content_tool_result, execute
from .storage import ConversationStore, InMemoryConversationStore
from .types import Message, ModelOutput, ToolCall, ToolResult, Turn

logger = logging.getLogger(__name__)


class CancellationToken:
    """协作式取消令牌（S21 移植 pi 的 AbortSignal 模式）。

    线程安全：Agent 循环在工作线程跑，API 层的 cancel 端点可在任意线程
    调用 cancel()；循环在每轮与工具执行前检查 is_cancelled() 提前终止。
    """

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


class Model(Protocol):
    """模型协议：输入上下文消息 + 工具清单，返回结构化 ModelOutput。

    适配器自行把真实 LLM（如 DeepSeek）的响应翻译成模型无关的 ModelOutput
    （text + tool_calls）。这是"模型无关"的解耦点。
    """

    def respond(self, messages: list[Message], tools: list[ToolSpec]) -> ModelOutput: ...


class StreamModel(Protocol):
    """流式模型协议（可选）：实现后 Agent 循环以流式事件驱动。

    移植自 pi 的 streamAssistantResponse 模式：模型边生成边通过 on_event
    回调发出流式事件（text_delta / toolcall_delta / done），最后返回完整
    ModelOutput。事件名与 pi 对齐。未实现此协议的模型走 respond 非流式路径。
    """

    def respond_stream(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        on_event: Callable[[Event], None],
    ) -> ModelOutput: ...


# 上下文压缩协议：输入完整 prompt 消息列表，输出压缩后的列表（token 预算）。
# 核心只声明协议（零依赖铁律）；具体实现（tiktoken 计数 + prune/summarize）由
# app 层注入（见 anyspark.server.context.TokenBudget）。模型无关。
ContextCompressor = Callable[[list[Message]], list[Message]]


@dataclass
class Agent:
    """极简 Agent：持有模型、工具注册表、存储、事件发射器。"""

    model: Model
    registry: ToolRegistry = field(default_factory=ToolRegistry)
    store: ConversationStore = field(default_factory=InMemoryConversationStore)
    events: EventEmitter = field(default_factory=EventEmitter)
    system_prompt: str = ""
    max_tool_iterations: int = (
        16  # 防无限循环硬上限（S21：读2章+写留足空间；pi 用智能终止替代硬上限）
    )
    context_compressor: ContextCompressor | None = None  # 可选：token 预算压缩（app 注入）

    def run(
        self,
        user_prompt: str,
        conversation_id: str | None = None,
        token: CancellationToken | None = None,
    ) -> Turn:
        """跑一轮：读提示 → 调工具（可多轮）→ 回填 → 输出。返回最终 Turn。

        token（S21）：协作式取消——循环与工具执行前检查，取消则提前终止。
        """
        store = self.store
        if conversation_id is None:
            conv = store.create()
            conversation_id = conv.id
        elif store.get(conversation_id) is None:
            store.create(conversation_id)

        return self._loop(conversation_id, user_prompt, token)

    def _loop(
        self,
        conversation_id: str,
        user_prompt: str,
        token: CancellationToken | None = None,
    ) -> Turn:
        store = self.store
        store.append(conversation_id, Message(role="user", content=user_prompt))
        self.events.emit(Event(type="user_text", payload={"content": user_prompt}))

        executed: list[ToolCall] = []
        results: list[ToolResult] = []

        # 系统提示（核心不注入工具语法文本；工具由 Model 适配器以原生 schema 传递）
        system_block = self.system_prompt.strip()
        # S22：重试睡眠可中断——把取消回调注入模型包装（RetryingModel 支持）
        self._set_cancelled_hook(model=self.model, token=token)

        for _ in range(self.max_tool_iterations):
            # 协作式取消检查（S21）：用户中断则提前终止。
            # S22（D5）：终止前 append assistant 消息——上下文永远平衡（user, assistant 成对），
            # 用户随后发"继续"时不会出现 user 接 user 的失衡上下文。
            if token is not None and token.is_cancelled():
                self._finish_aborted(conversation_id, store, executed, results)
                return Turn(
                    text="已中断（用户取消）。",
                    tool_calls=executed,
                    tool_results=results,
                )
            self.events.emit(Event(type="turn_start", payload={}))
            history = store.messages(conversation_id)
            prompt_messages = (
                [Message(role="system", content=system_block)] if system_block else []
            ) + history
            # token 预算：可选压缩（prune/summarize 两阶段，实现由 app 注入）
            if self.context_compressor is not None:
                prompt_messages = self.context_compressor(prompt_messages)

            tools: list[ToolSpec] = self.registry.specs()
            # 流式核心（S21 移植 pi 模式）：模型支持 respond_stream 则事件驱动流式，
            # 否则回退非流式 respond（向后兼容）。
            # S22（D1）：模型调用包异常——调用失败（网络/API 错误，重试耗尽后）时
            # **不冒泡不毒化上下文**：append assistant 失败消息保持 user/assistant 配对，
            # 结束本轮并把错误说明带给 API 层（转 5xx / SSE error 帧）。
            try:
                if hasattr(self.model, "respond_stream"):
                    output = self.model.respond_stream(
                        prompt_messages,
                        tools,
                        on_event=lambda e: self.events.emit(e),
                    )
                else:
                    output = self.model.respond(prompt_messages, tools)
            except Exception as exc:  # 任何模型/网络异常都要保持上下文平衡
                logger.warning("模型调用失败: %s", exc)
                err_text = f"（生成失败）{exc}"
                store.append(conversation_id, Message(role="assistant", content=err_text))
                self.events.emit(Event(type="text", payload={"content": err_text}))
                self.events.emit(Event(type="error", payload={"message": err_text}))
                self.events.emit(Event(type="done", payload={}))
                return Turn(
                    text=err_text,
                    tool_calls=executed,
                    tool_results=results,
                    error=err_text,
                )

            if not output.tool_calls:
                # 本轮无工具调用 → 产出最终文本
                store.append(conversation_id, Message(role="assistant", content=output.text))
                self.events.emit(Event(type="text", payload={"content": output.text}))
                self.events.emit(Event(type="done", payload={}))
                return Turn(text=output.text, tool_calls=executed, tool_results=results)

            # 有工具调用：并行执行并把结果回填（S21 移植 pi 的 executeToolCallsParallel；
            # ThreadPoolExecutor 保持输入顺序，写工具内部有锁保证线程安全）
            self.events.emit(
                Event(type="tool_call", payload={"name": [c.name for c in output.tool_calls]})
            )
            calls = list(output.tool_calls)

            # S23 协议完整化：**先把 assistant 消息（含原生 tool_calls 声明）落进 store**，
            # 再回填 tool 结果——上下文序列变为合法配对：
            #   user → assistant(tool_calls 声明) → tool(带 tool_call_id) → ...
            # （此前只存 tool 结果、assistant 声明丢失，DashScope 宽容模式能跑但不规范，
            #   多工具并行时模型只能靠文本前缀猜归属）
            store.append(
                conversation_id,
                Message(
                    role="assistant",
                    content=output.text,
                    metadata={
                        "tool_calls": [
                            {
                                "name": c.name,
                                "arguments": c.arguments,
                                "id": c.id or "",
                            }
                            for c in calls
                        ]
                    },
                ),
            )

            # S22（D3）截断防护完整化（移植 pi 的 stopReason=length 全拒）：
            # 输出被 token 上限截断时，工具参数可能 JSON 合法但语义残缺——无条件拒绝整批，
            # 回填错误让模型下一轮重发。仅靠 _malformed（JSON 解析失败）不够：
            # 流式参数可能恰好凑出完整 JSON。
            if output.truncated:
                for call in calls:
                    result = ToolResult(
                        call=call,
                        ok=False,
                        content=(
                            f"工具 {call.name} 未执行：模型输出被 token 上限截断"
                            "（参数可能不完整），请重新发起完整调用。"
                        ),
                    )
                    executed.append(call)
                    results.append(result)
                    self._append_tool_result(store, conversation_id, call, result)
                    self.events.emit(
                        Event(type="tool_result", payload={"name": call.name, "ok": False})
                    )
                continue  # 下一轮：模型看到错误回填后重发完整调用

            # 工具执行前再检查取消（S21）：取消则不再执行剩余工具
            if token is not None and token.is_cancelled():
                self._finish_aborted(conversation_id, store, executed, results)
                return Turn(
                    text="已中断（用户取消）。",
                    tool_calls=executed,
                    tool_results=results,
                )
            if len(calls) > 1:
                from concurrent.futures import ThreadPoolExecutor

                with ThreadPoolExecutor(max_workers=min(len(calls), 8)) as pool:
                    results_ordered = list(pool.map(lambda c: execute(self.registry, c), calls))
            else:
                results_ordered = [execute(self.registry, calls[0])]
            for call, result in zip(calls, results_ordered, strict=True):
                executed.append(call)
                results.append(result)
                self._append_tool_result(store, conversation_id, call, result)
                self.events.emit(
                    Event(type="tool_result", payload={"name": call.name, "ok": result.ok})
                )
        # 达到迭代上限则报错返回（S22：带 error 字段，API 层直接读，不再文本匹配）
        msg = "达到最大工具迭代次数，已终止。"
        store.append(conversation_id, Message(role="assistant", content=msg))
        return Turn(text=msg, tool_calls=executed, tool_results=results, error=msg)

    def _finish_aborted(
        self,
        conversation_id: str,
        store: ConversationStore,
        executed: list[ToolCall],
        results: list[ToolResult],
    ) -> None:
        """取消终止的收尾（S22 D5）：append assistant 消息保持上下文平衡 + 发事件。"""
        cancel_text = "已中断（用户取消）。"
        store.append(conversation_id, Message(role="assistant", content=cancel_text))
        self.events.emit(Event(type="aborted", payload={}))
        self.events.emit(Event(type="text", payload={"content": cancel_text}))
        self.events.emit(Event(type="done", payload={}))

    @staticmethod
    def _append_tool_result(
        store: ConversationStore,
        conversation_id: str,
        call: ToolCall,
        result: ToolResult,
    ) -> None:
        """S23：tool 结果回填——metadata 带 tool_call_id（与 assistant 声明配对）。"""
        backfill = backfill_content_tool_result(result)
        metadata: dict[str, object] = {}
        if call.id:
            metadata["tool_call_id"] = call.id
        store.append(conversation_id, Message(role="tool", content=backfill, metadata=metadata))

    @staticmethod
    def _set_cancelled_hook(model: Model, token: CancellationToken | None) -> None:
        """S22（D2）：把取消回调注入模型包装（RetryingModel.set_cancelled），
        使重试退避睡眠期间可被 cancel 中断（分段检查）。模型不支持则静默跳过。"""
        if token is None:
            return
        setter = getattr(model, "set_cancelled", None)
        if setter is not None:
            setter(token.is_cancelled)
