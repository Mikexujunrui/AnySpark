"""anyspark.core.events 测试。"""

from collections.abc import Callable
from typing import Any

from anyspark.core.events import Event, EventEmitter


def test_event_roundtrip() -> None:
    e = Event(type="text", payload={"content": "hi"})
    assert e.type == "text"
    assert e.payload["content"] == "hi"


def test_emit_dispatches_to_listener() -> None:
    em = EventEmitter()
    seen: list[Event] = []

    em.on("text", lambda ev: seen.append(ev))
    em.emit(Event(type="text", payload={"content": "x"}))

    assert len(seen) == 1
    assert seen[0].payload["content"] == "x"


def test_listener_off() -> None:
    em = EventEmitter()
    seen: list[str] = []

    def listener(ev: Event) -> None:
        seen.append(ev.type)

    em.on("done", listener)
    em.emit(Event(type="done"))
    em.off("done", listener)
    em.emit(Event(type="done"))

    assert seen == ["done"]


def test_extension_hook_register_run() -> None:
    em = EventEmitter()
    emitted: list[Event] = []

    em.on("my_event", lambda ev: emitted.append(ev))

    def hook(payload: dict[str, Any], upstream: Callable[[Event], None]) -> None:
        upstream(Event(type="my_event", payload=payload))

    em.register_hook("align.note", hook)
    em.run_hook("align.note", {"msg": "hello"})

    assert len(emitted) == 1
    assert emitted[0].payload["msg"] == "hello"


def test_unknown_hook_is_silently_ignored() -> None:
    em = EventEmitter()
    em.run_hook("no.such.hook", {})  # 不抛错
