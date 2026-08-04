"""
anyspark.core.events — 事件协议。

设计边界（DESIGN.md 第 4 节）：
- 核心只发通用事件（text / done / error / tool_call 等）+ 类型化数据负载。
- 包（align/explore/etc）通过**注册钩子**扩展自定义事件类型，核心不认识它们。

事件是同步接线的（轻量、无并发负担）；需要流式（SSE）时由外层把事件转成
传输格式，核心本身只负责产生事件并通知已注册的监听器。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# 通用事件类型名（核心只认识这些；扩展包用 register 挂自己的类型）
GENERIC_EVENT_TYPES = {
    "text",  # 一段自然语言输出
    "text_delta",  # 流式文本增量（打字机；事件名对齐 pi 的 stream 事件）
    "toolcall_delta",  # 流式工具调用参数增量
    "done",  # 一轮完成
    "error",  # 出错
    "tool_call",  # 模型发起工具调用
    "tool_execution_start",  # 工具开始执行（S25 对齐 pi：前端显示"正在执行"）
    "tool_execution_end",  # 工具执行结束（S25：带 ok/耗时，前端显示结果）
    "tool_result",  # 工具执行结果
    "turn_start",  # 一轮开始
}


@dataclass
class Event:
    """统一事件结构：type 命名 + 类型化负载。"""

    type: str
    payload: dict[str, Any] = field(default_factory=dict)


# 监听器签名：接收事件
EventListener = Callable[[Event], None]


class EventEmitter:
    """最小事件总线：按事件类型分发到监听器，支持核心扩展类型。"""

    def __init__(self) -> None:
        self._listeners: dict[str, list[EventListener]] = {}
        # 注册钩子：run(payload, emit) → 产生自定义事件
        self._hooks: dict[str, Callable[[dict[str, Any], Callable[[Event], None]], None]] = {}
        for t in GENERIC_EVENT_TYPES:
            self._listeners[t] = []

    # ------------------------------------------------------------------
    # 注册 / 使用
    # ------------------------------------------------------------------
    def on(self, event_type: str, listener: EventListener) -> None:
        """注册某个事件类型的监听器。"""
        self._listeners.setdefault(event_type, []).append(listener)

    def off(self, event_type: str, listener: EventListener) -> None:
        """注销某个事件类型的监听器；未注册则静默忽略。"""
        listeners = self._listeners.get(event_type)
        if listeners and listener in listeners:
            listeners.remove(listener)

    def emit(self, event: Event) -> None:
        """同步分发一个事件给该类型的所有监听器。"""
        for listener in list(self._listeners.get(event.type, [])):
            listener(event)

    # ------------------------------------------------------------------
    # 类型扩展钩子（包注册自定义事件类型）
    # ------------------------------------------------------------------
    def register_hook(
        self,
        hook_name: str,
        hook: Callable[[dict[str, Any], Callable[[Event], None]], None],
    ) -> None:
        """扩展包注册一个自定义事件钩子：run(payload, emit)。

        core 不认识 hook_name 的语义，仅当别人调用 run_hook 时才触发。
        """
        self._hooks[hook_name] = hook

    def run_hook(self, hook_name: str, payload: dict[str, Any] | None = None) -> None:
        """触发一个已注册的自定义事件钩子。若未注册则静默忽略。"""
        hook = self._hooks.get(hook_name)
        if hook is None:
            return
        hook(payload or {}, self.emit)

    # ------------------------------------------------------------------
    # 便捷构造
    # ------------------------------------------------------------------
    @staticmethod
    def text(content: str) -> Event:
        return Event(type="text", payload={"content": content})

    @staticmethod
    def text_delta(content: str) -> Event:
        return Event(type="text_delta", payload={"content": content})

    @staticmethod
    def done() -> Event:
        return Event(type="done", payload={})

    @staticmethod
    def error(message: str) -> Event:
        return Event(type="error", payload={"message": message})
