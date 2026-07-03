import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class EventType(StrEnum):
    # Actively emitted events (6 types)
    KNOWLEDGE_EXTRACTED = "knowledge.extracted"
    CHAPTER_CREATED = "chapter.created"
    CHAPTER_DELETED = "chapter.deleted"
    CHAPTER_UPDATED = "chapter.updated"
    BOOK_DELETED = "book.deleted"
    TOOL_EXECUTED = "tool.executed"
    TOOL_FAILED = "tool.failed"
    # Reserved for future use — not currently emitted
    KNOWLEDGE_UPDATED = "knowledge.updated"
    SESSION_CREATED = "session.created"
    SESSION_DELETED = "session.deleted"
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    # Task engine events (persistent task queue + autopilot + supervisor)
    TASK_STARTED = "task.started"
    TASK_STEP_COMPLETED = "task.step_completed"
    TASK_STEP_FAILED = "task.step_failed"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_PAUSED = "task.paused"
    TASK_NOTIFICATION = "task.notification"  # supervisor → frontend
    HEADLESS_LOOP_PROGRESS = "headless.progress"  # headless loop → online SSE


@dataclass
class Event:
    type: EventType
    data: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    source: str = ""


Listener = Callable[[Event], Any]
AsyncListener = Callable[[Event], Coroutine]


class EventBus:
    def __init__(self):
        self._listeners: dict[str, list[Listener | AsyncListener]] = defaultdict(list)
        self._wildcard_listeners: list[Listener | AsyncListener] = []
        self._history: list[Event] = []
        self._max_history = 100

    def on(self, event_type: EventType | str, listener: Listener | AsyncListener):
        key = event_type.value if isinstance(event_type, EventType) else event_type
        if key == "*":
            self._wildcard_listeners.append(listener)
        else:
            self._listeners[key].append(listener)

    def off(self, event_type: EventType | str, listener: Listener | AsyncListener):
        key = event_type.value if isinstance(event_type, EventType) else event_type
        if key == "*":
            self._wildcard_listeners = [ln for ln in self._wildcard_listeners if ln != listener]
        elif key in self._listeners:
            self._listeners[key] = [ln for ln in self._listeners[key] if ln != listener]

    async def emit(self, event: Event):
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        key = event.type.value if isinstance(event.type, EventType) else event.type
        listeners = self._listeners.get(key, []) + self._wildcard_listeners

        if not listeners:
            logger.debug(f"EventBus: event {key!r} emitted with no listeners")

        for listener in listeners:
            try:
                result = listener(event)
                if asyncio.iscoroutine(result):
                    await result
            except (ValueError, TypeError, RuntimeError) as e:
                logger.warning(f"EventBus listener error for {key}: {e}")

    def emit_sync(self, event: Event):
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        key = event.type.value if isinstance(event.type, EventType) else event.type
        listeners = self._listeners.get(key, []) + self._wildcard_listeners

        if not listeners:
            logger.debug(f"EventBus: event {key!r} emitted with no listeners")

        for listener in listeners:
            try:
                result = listener(event)
                if asyncio.iscoroutine(result):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.call_soon_threadsafe(asyncio.ensure_future, result)
                    except RuntimeError:
                        result.close()
            except (ValueError, TypeError) as e:
                logger.warning(f"EventBus sync listener error for {key}: {e}")

    def get_history(self, event_type: EventType | str = None, limit: int = 20) -> list[Event]:
        if event_type:
            key = event_type.value if isinstance(event_type, EventType) else event_type
            filtered = [e for e in self._history if (e.type.value if isinstance(e.type, EventType) else e.type) == key]
            return filtered[-limit:]
        return self._history[-limit:]

    def clear_history(self):
        self._history.clear()


bus = EventBus()
