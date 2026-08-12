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
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from .events import Event, EventEmitter
from .protocol import (
    Cancellable,
    ContextCompressor,
    Model,
    ToolRegistry,
    ToolSpec,
    backfill_content_tool_result,
    execute,
)
from .storage import ConversationStore, InMemoryConversationStore
from .types import Message, ModelOutput, Role, ToolCall, ToolResult, Turn

logger = logging.getLogger(__name__)


def _messages_differ(a: list[Message], b: list[Message]) -> bool:
    """S26：判断两条消息列表是否实质不同（压缩是否真的发生了）。"""
    if len(a) != len(b):
        return True
    return any(
        x.role != y.role or x.content != y.content or x.metadata != y.metadata
        for x, y in zip(a, b, strict=True)
    )


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


@dataclass
class Agent:
    """极简 Agent：持有模型、工具注册表、存储、事件发射器。

    S25：steer_queue / followup_queue（对齐 pi 的 steeringQueue / followUpQueue）——
    Agent 运行中可**中途插话**（steer：当前轮工具结果后、下一轮 LLM 前注入）
    或**排队追问**（follow_up：agent 即将停止时注入续跑）。队列线程安全，
    API 层可从任意线程入队。
    """

    model: Model
    registry: ToolRegistry = field(default_factory=ToolRegistry)
    store: ConversationStore = field(default_factory=InMemoryConversationStore)
    events: EventEmitter = field(default_factory=EventEmitter)
    system_prompt: str = ""
    max_tool_iterations: int = (
        16  # 防无限循环硬上限（S21：读2章+写留足空间；pi 用智能终止替代硬上限）
    )
    context_compressor: ContextCompressor | None = None  # 可选：token 预算压缩（app 注入）
    # S26：压缩持久化回写（pi compaction entry 语义）——压缩后的上下文写回 store，
    # 跨重启/续聊用压缩后上下文，store 不再无限膨胀。默认关（测试不干扰），app 装配开启。
    persist_compression: bool = False
    # S27（对齐 pi beforeToolCall / afterToolCall 钩子）：
    # before_tool_call：执行前钩子，返回非 None = 拦截原因（不执行，回填错误）；
    # after_tool_call：执行后钩子，可改写结果（安全统一/信号采集挂点）。
    before_tool_call: Callable[[ToolCall], str | None] | None = None
    after_tool_call: Callable[[ToolCall, ToolResult], ToolResult] | None = None
    # S25：运行中插话/追问队列（线程安全，pi steering/followUp 移植）
    steer_queue: queue.SimpleQueue[Message] = field(default_factory=queue.SimpleQueue)
    followup_queue: queue.SimpleQueue[Message] = field(default_factory=queue.SimpleQueue)

    def steer(self, text: str, role: Role = "user") -> None:
        """S25：运行中插话（对齐 pi Agent.steer）——消息在当前轮工具结果后、
        下一轮 LLM 前注入。写作场景：用户可在 AI 写作时中途说"别写太血腥"。"""
        self.steer_queue.put(Message(role=role, content=text))

    def follow_up(self, text: str, role: Role = "user") -> None:
        """S25：排队追问（对齐 pi Agent.followUp）——agent 即将停止（无更多工具调用）
        时注入续跑，而不是结束。"""
        self.followup_queue.put(Message(role=role, content=text))

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

        turn_index = 0
        for _ in range(self.max_tool_iterations):
            turn_index += 1
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
            # S25 steering：运行中插话在下一轮 LLM 前注入（对齐 pi getSteeringMessages）——
            # 模型上一轮的工具结果已回填，插话作为 user 消息接在后面，语义完整。
            steer_msgs = self._drain(self.steer_queue)
            for m in steer_msgs:
                store.append(conversation_id, m)
                self.events.emit(Event(type="user_text", payload={"content": m.content}))
            self.events.emit(
                Event(
                    type="turn_start",
                    # S98：带轮次信息——前端进度条用真实轮次进度（turn_index/max_iterations）
                    payload={
                        "turn_index": turn_index,
                        "max_iterations": self.max_tool_iterations,
                    },
                )
            )
            history = store.messages(conversation_id)
            prompt_messages = (
                [Message(role="system", content=system_block)] if system_block else []
            ) + history
            # token 预算：可选压缩（prune/summarize 两阶段，实现由 app 注入）
            if self.context_compressor is not None:
                prompt_messages = self.context_compressor(prompt_messages)
                # S26：压缩持久化回写——压缩后的上下文（去掉 system 指令）写回 store：
                # 下一轮/下次会话读到的就是压缩后历史（摘要+保留段），跨重启不失效。
                if self.persist_compression:
                    compressed_history = prompt_messages[1:] if system_block else prompt_messages
                    if _messages_differ(history, compressed_history):
                        store.replace_messages(conversation_id, compressed_history)

            tools: list[ToolSpec] = self.registry.specs()
            # 流式核心（S21 移植 pi 模式）：模型支持 respond_stream 则事件驱动流式，
            # 否则回退非流式 respond（向后兼容）。
            # S22（D1）：模型调用包异常——调用失败（网络/API 错误，重试耗尽后）时
            # **不冒泡不毒化上下文**：append assistant 失败消息保持 user/assistant 配对，
            # 结束本轮并把错误说明带给 API 层（转 5xx / SSE error 帧）。
            # 防御：output 先置 None——异常路径绝不读它（except 已 return）；
            # 成功路径才在 None 校验后进入 _emit_record，杜绝任何 UnboundLocalError 可能。
            output: ModelOutput | None = None
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

            assert output is not None  # 走到此必然成功赋值（异常已 return）
            self._emit_record(conversation_id, turn_index, prompt_messages, output, results)
            if not output.tool_calls:
                # 终答前统一检查插话/追问（对齐 pi：内层循环末尾检查 steering、
                # 外层检查 followUp）——用户在模型生成期间插话时，即使本轮恰好是
                # 终答，插话也不丢失：先把本轮终答落上下文，再注入队列消息续跑。
                queued = self._drain(self.steer_queue) + self._drain(self.followup_queue)
                if queued:
                    store.append(conversation_id, Message(role="assistant", content=output.text))
                    self.events.emit(Event(type="text", payload={"content": output.text}))
                    for m in queued:
                        store.append(conversation_id, m)
                        self.events.emit(Event(type="user_text", payload={"content": m.content}))
                    continue
                # 真终答
                store.append(conversation_id, Message(role="assistant", content=output.text))
                self.events.emit(Event(type="text", payload={"content": output.text}))
                self.events.emit(Event(type="done", payload={}))
                return Turn(text=output.text, tool_calls=executed, tool_results=results)

            # 有工具调用：并行执行并把结果回填（S21 移植 pi 的 executeToolCallsParallel；
            # ThreadPoolExecutor 保持输入顺序，写工具内部有锁保证线程安全）
            self.events.emit(
                Event(
                    type="tool_call",
                    payload={
                        "name": [c.name for c in output.tool_calls],
                        # F2.6：带 arguments——前端据此做"写作预览"（写章时展示区实时显正文）
                        "arguments": [c.arguments for c in output.tool_calls],
                    },
                )
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
            # S25：工具执行事件（对齐 pi tool_execution_start/end）——前端显示"正在执行…"；
            # sequential 模式（对齐 pi executionMode）：批内任一工具标 sequential 则整批串行，
            # 防止写类工具与读类工具并行产生逻辑错序（写工具内部锁只保数据不保逻辑顺序）。
            has_sequential = False
            for c in calls:
                entry = self.registry.get(c.name)
                if entry is not None and entry[0].execution_mode == "sequential":
                    has_sequential = True
                    break

            def _run_one(call: ToolCall) -> ToolResult:
                """S27：单工具执行——before 拦截（不执行）→ execute → after 改写。"""
                if self.before_tool_call is not None:
                    reason = self.before_tool_call(call)
                    if reason is not None:
                        return ToolResult(
                            call=call,
                            ok=False,
                            content=f"工具 {call.name} 被拦截：{reason}",
                        )
                result = execute(self.registry, call)
                if self.after_tool_call is not None:
                    try:
                        result = self.after_tool_call(call, result)
                    except Exception as exc:  # 钩子异常不炸循环，回填错误
                        result = ToolResult(
                            call=call,
                            ok=False,
                            content=f"after_tool_call 钩子异常: {exc}",
                        )
                return result

            if len(calls) > 1 and not has_sequential:
                from concurrent.futures import ThreadPoolExecutor

                for c in calls:
                    self.events.emit(
                        Event(
                            type="tool_execution_start",
                            payload={"name": c.name, "id": c.id},
                        )
                    )
                import time as _time

                started = _time.monotonic()
                with ThreadPoolExecutor(max_workers=min(len(calls), 8)) as pool:
                    results_ordered = list(pool.map(_run_one, calls))
                for c, r in zip(calls, results_ordered, strict=True):
                    self.events.emit(
                        Event(
                            type="tool_execution_end",
                            payload={
                                "name": c.name,
                                "id": c.id,
                                "ok": r.ok,
                                "ms": int(
                                    (_time.monotonic() - started) * 1000 / max(len(calls), 1)
                                ),
                            },
                        )
                    )
            else:
                results_ordered = []
                for c in calls:
                    self.events.emit(
                        Event(
                            type="tool_execution_start",
                            payload={"name": c.name, "id": c.id},
                        )
                    )
                    import time as _time

                    started = _time.monotonic()
                    r = _run_one(c)
                    self.events.emit(
                        Event(
                            type="tool_execution_end",
                            payload={
                                "name": c.name,
                                "id": c.id,
                                "ok": r.ok,
                                "ms": int((_time.monotonic() - started) * 1000),
                            },
                        )
                    )
                    results_ordered.append(r)
            for call, result in zip(calls, results_ordered, strict=True):
                executed.append(call)
                results.append(result)
                self._append_tool_result(store, conversation_id, call, result)
                self.events.emit(
                    Event(type="tool_result", payload={"name": call.name, "ok": result.ok})
                )
            # S27 智能停止（对齐 pi shouldTerminateToolBatch）：批内**全部**工具
            # terminate=True → 不再进入下一轮，直接结束（避免无意义死磕迭代上限）。
            if results_ordered and all(r.terminate for r in results_ordered):
                msg = "（工具声明任务完成，Agent 停止。）"
                store.append(conversation_id, Message(role="assistant", content=msg))
                self.events.emit(Event(type="text", payload={"content": msg}))
                self.events.emit(Event(type="done", payload={}))
                return Turn(text=msg, tool_calls=executed, tool_results=results)
        # 达到迭代上限则报错返回（S22：带 error 字段，API 层直接读，不再文本匹配）
        msg = "达到最大工具迭代次数，已终止。"
        store.append(conversation_id, Message(role="assistant", content=msg))
        return Turn(text=msg, tool_calls=executed, tool_results=results, error=msg)

    @staticmethod
    def _drain(q: queue.SimpleQueue[Message]) -> list[Message]:
        """S25：安全排空一个队列（线程安全，非阻塞）。"""
        out: list[Message] = []
        while not q.empty():
            try:
                out.append(q.get_nowait())
            except queue.Empty:
                break
        return out

    def _emit_record(
        self,
        conversation_id: str,
        turn_index: int,
        prompt_messages: list[Message],
        output: ModelOutput,
        results: list[ToolResult],
    ) -> None:
        """S49 运行记录事件：完整轮次快照（上下文 + 输出含思维链 + 工具结果）。

        只发事件不落盘——存储由 app 层订阅（写 data/records/*.jsonl）；
        思维链 reasoning **不注入上下文**（只进记录，训练/复盘用）。
        """
        self.events.emit(
            Event(
                type="record",
                payload={
                    "turn_index": turn_index,
                    "prompt": [{"role": m.role, "content": m.content} for m in prompt_messages],
                    "output": {
                        "text": output.text,
                        "reasoning": output.reasoning,
                        "tool_calls": [
                            {"name": c.name, "arguments": c.arguments} for c in output.tool_calls
                        ],
                        "truncated": output.truncated,
                    },
                    "tool_results": [
                        {
                            "name": r.call.name,
                            "ok": r.ok,
                            "content": r.content,
                        }
                        for r in results
                    ],
                },
            )
        )

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
        使重试退避睡眠期间可被 cancel 中断（分段检查）。模型不支持则静默跳过。

        S62：用显式 Cancellable 协议（runtime_checkable isinstance）替代
        getattr 探测——loop 不再隐式依赖"存在会睡眠的包装器"的方法名。
        """
        if token is None:
            return
        if isinstance(model, Cancellable):
            model.set_cancelled(token.is_cancelled)
