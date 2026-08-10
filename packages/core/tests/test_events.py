"""anyspark.core.events 测试。"""

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
