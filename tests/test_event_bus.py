import pytest

from core.event_bus import Event, EventBus, EventType


@pytest.fixture
def bus():
    return EventBus()


def test_emit_sync(bus):
    received = []
    bus.on(EventType.CHAPTER_CREATED, lambda e: received.append(e))
    bus.emit_sync(Event(type=EventType.CHAPTER_CREATED, data={"title": "Test"}))
    assert len(received) == 1
    assert received[0].data["title"] == "Test"


def test_wildcard_listener(bus):
    received = []
    bus.on("*", lambda e: received.append(e))
    bus.emit_sync(Event(type=EventType.CHAPTER_CREATED))
    bus.emit_sync(Event(type=EventType.KNOWLEDGE_UPDATED))
    assert len(received) == 2


def test_off(bus):
    received = []

    def handler(e):
        return received.append(e)

    bus.on(EventType.CHAPTER_CREATED, handler)
    bus.off(EventType.CHAPTER_CREATED, handler)
    bus.emit_sync(Event(type=EventType.CHAPTER_CREATED))
    assert len(received) == 0


def test_history(bus):
    bus.emit_sync(Event(type=EventType.CHAPTER_CREATED, data={"n": 1}))
    bus.emit_sync(Event(type=EventType.CHAPTER_CREATED, data={"n": 2}))
    history = bus.get_history(EventType.CHAPTER_CREATED)
    assert len(history) == 2


def test_history_limit(bus):
    for i in range(150):
        bus.emit_sync(Event(type=EventType.TOOL_EXECUTED, data={"i": i}))
    assert len(bus._history) == 100


@pytest.mark.asyncio
async def test_async_emit(bus):
    received = []

    async def handler(e):
        received.append(e)

    bus.on(EventType.KNOWLEDGE_EXTRACTED, handler)
    await bus.emit(Event(type=EventType.KNOWLEDGE_EXTRACTED, data={"count": 5}))
    assert len(received) == 1
    assert received[0].data["count"] == 5
