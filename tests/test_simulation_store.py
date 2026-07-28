"""Tests for SimulationStore — Sim namespace isolated storage.

Tests the JSON fallback path (no Neo4j required) for CI compatibility.
"""

import pytest

from core.simulation.simulation_store import SimulationStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Create a SimulationStore with JSONL storage (no Neo4j)."""
    monkeypatch.setattr("core.simulation.simulation_store.DATA_DIR", tmp_path)
    s = SimulationStore("test_book")
    return s


def test_create_session(store):
    """Test session creation with all fields."""
    session = store.create_session(
        mode="character_pov",
        setting="在城门口遇到旧友",
        pov_character_id="char_001",
        involved_character_ids=["char_001", "char_002"],
        style_name="古风",
    )
    assert session["id"].startswith("sim_")
    assert session["mode"] == "character_pov"
    assert session["setting"] == "在城门口遇到旧友"
    assert session["pov_character_id"] == "char_001"
    assert session["status"] == "active"
    assert session["turn_count"] == 0


def test_get_session(store):
    """Test session retrieval."""
    created = store.create_session(mode="narrator_pov", setting="测试")
    retrieved = store.get_session(created["id"])
    assert retrieved is not None
    assert retrieved["id"] == created["id"]
    assert retrieved["mode"] == "narrator_pov"


def test_get_session_not_found(store):
    """Test session retrieval for non-existent session."""
    assert store.get_session("sim_nonexistent") is None


def test_list_sessions(store):
    """Test listing sessions."""
    store.create_session(mode="character_pov", setting="推演1")
    store.create_session(mode="narrator_pov", setting="推演2")
    sessions = store.list_sessions()
    assert len(sessions) == 2


def test_list_sessions_by_status(store):
    """Test listing sessions filtered by status."""
    s1 = store.create_session(mode="character_pov")
    store.create_session(mode="narrator_pov")
    store.update_session(s1["id"], status="completed")
    active = store.list_sessions(status="active")
    assert len(active) == 1
    assert active[0]["mode"] == "narrator_pov"


def test_update_session(store):
    """Test session update."""
    session = store.create_session(mode="character_pov")
    updated = store.update_session(session["id"], status="completed", summary="推演结论")
    assert updated["status"] == "completed"
    assert updated["summary"] == "推演结论"


def test_delete_session(store):
    """Test session deletion and cleanup."""
    session = store.create_session(mode="character_pov")
    store.add_event(session["id"], "叙事内容", "narrative", 0)
    store.delete_session(session["id"])
    assert store.get_session(session["id"]) is None
    # Verify events are also gone
    events = store.get_events(session["id"])
    assert events == []


def test_add_and_get_events(store):
    """Test event CRUD."""
    session = store.create_session(mode="character_pov")
    store.add_event(session["id"], "第一段叙事", "narrative", 0)
    store.add_event(session["id"], "第二段叙事", "narrative", 1)
    events = store.get_events(session["id"])
    assert len(events) == 2
    assert events[0]["content"] == "第一段叙事"
    assert events[1]["turn_number"] == 1


def test_get_latest_event(store):
    """Test getting the latest event."""
    session = store.create_session(mode="character_pov")
    store.add_event(session["id"], "第一段", "narrative", 0)
    store.add_event(session["id"], "第二段", "narrative", 1)
    latest = store.get_latest_event(session["id"])
    assert latest is not None
    assert latest["turn_number"] == 1
    assert latest["content"] == "第二段"


def test_add_and_get_choices(store):
    """Test choice CRUD."""
    session = store.create_session(mode="character_pov")
    event = store.add_event(session["id"], "叙事", "narrative", 0)
    store.add_choice(event["id"], session["id"], "选项A", "后果A", "action")
    store.add_choice(event["id"], session["id"], "选项B", "后果B", "action")
    choices = store.get_choices(event["id"])
    assert len(choices) == 2
    assert choices[0]["text"] == "选项A"
    assert choices[1]["choice_type"] == "action"


def test_mark_choice_selected(store):
    """Test marking a choice as selected."""
    session = store.create_session(mode="character_pov")
    event = store.add_event(session["id"], "叙事", "narrative", 0)
    choice = store.add_choice(event["id"], session["id"], "选项", "", "action")
    assert choice["selected"] is False
    store.mark_choice_selected(choice["id"], session["id"])
    choices = store.get_choices(event["id"])
    assert choices[0]["selected"] is True


def test_add_character_response(store):
    """Test character response storage (narrator POV mode)."""
    session = store.create_session(mode="narrator_pov")
    event = store.add_event(session["id"], "条件设定", "narrative", 0)
    resp = store.add_character_response(
        session["id"],
        event["id"],
        "char_001",
        "角色决定反击",
        "内心想：不能坐以待毙",
    )
    assert resp["response_text"] == "角色决定反击"
    assert resp["internal_thoughts"] == "内心想：不能坐以待毙"

    responses = store.get_character_responses(event["id"])
    assert len(responses) == 1
    assert responses[0]["character_id"] == "char_001"


def test_turn_count_increments(store):
    """Test that turn_count increments when events are added."""
    session = store.create_session(mode="character_pov")
    store.add_event(session["id"], "叙事1", "narrative", 0)
    store.add_event(session["id"], "叙事2", "narrative", 1)
    updated = store.get_session(session["id"])
    assert updated["turn_count"] == 2


def test_narrator_pov_mode_session(store):
    """Test narrator POV mode session creation."""
    session = store.create_session(
        mode="narrator_pov",
        condition="王国突然覆灭",
        involved_character_ids=["char_a", "char_b", "char_c"],
    )
    assert session["mode"] == "narrator_pov"
    assert session["condition"] == "王国突然覆灭"
    assert len(session["involved_character_ids"]) == 3
