"""Tests for plan/write mode-boundary tracking across conversation turns.

When a user switches between plan and write mode mid-session, the agent loop
must be able to tell which turn ran under which mode. These tests lock in the
``_load_history_as_llm_messages`` / ``_persist_turn`` mode-field behavior.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from unittest.mock import patch

from core.agent_loop import AgentConfig, _prepare_initial_messages

# Import the module so we can patch json_store at the module level.
from routes import chat as chat_module


class _FakeStore:
    """Minimal in-memory stand-in for json_store used by chat.py helpers."""
    def __init__(self):
        self._messages = []

    def load_messages(self, session_id):
        return list(self._messages)

    def save_messages(self, book_id, session_id, history):
        self._messages = list(history)


# ── _persist_turn records the mode on each message ──────────────────────────

def test_persist_turn_stores_mode_field():
    store = _FakeStore()
    with patch.object(chat_module, 'json_store', store):
        chat_module._persist_turn("book1", "sess1", "写第3章", "已完成", mode="write")
        msgs = store.load_messages("sess1")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["mode"] == "write"
    assert msgs[1]["role"] == "agent"
    assert msgs[1]["mode"] == "write"


def test_persist_turn_defaults_empty_mode():
    """Legacy callers without mode get an empty string (backward compat)."""
    store = _FakeStore()
    with patch.object(chat_module, 'json_store', store):
        chat_module._persist_turn("book1", "sess1", "hi", "hello")
        msgs = store.load_messages("sess1")
    assert msgs[0]["mode"] == ""


# ── _load_history_as_llm_messages injects mode markers ───────────────────────

def test_load_history_injects_mode_marker_on_user_turns():
    store = _FakeStore()
    store._messages = [
        {"role": "user", "text": "分析一下角色", "mode": "plan"},
        {"role": "agent", "text": "这是一个分析...", "mode": "plan"},
        {"role": "user", "text": "写第3章", "mode": "write"},
        {"role": "agent", "text": "已完成第3章", "mode": "write"},
    ]
    with patch.object(chat_module, 'json_store', store):
        msgs = chat_module._load_history_as_llm_messages("sess1")
    # User turns get a [模式: X] prefix; agent turns stay clean.
    assert msgs[0]["content"].startswith("[模式: plan]")
    assert "分析一下角色" in msgs[0]["content"]
    assert msgs[1]["content"] == "这是一个分析..."
    assert msgs[2]["content"].startswith("[模式: write]")
    assert "写第3章" in msgs[2]["content"]


def test_load_history_legacy_messages_without_mode():
    """Old messages with no mode field load without a marker (no crash)."""
    store = _FakeStore()
    store._messages = [
        {"role": "user", "text": "旧消息"},  # no mode key
        {"role": "agent", "text": "旧回复"},
    ]
    with patch.object(chat_module, 'json_store', store):
        msgs = chat_module._load_history_as_llm_messages("sess1")
    assert msgs[0]["content"] == "旧消息"  # no marker prepended
    assert msgs[1]["content"] == "旧回复"


# ── _prepare_initial_messages tags the current turn too ─────────────────────

def test_prepare_messages_tags_current_turn_with_mode():
    cfg = AgentConfig(agent_type="write", mode="write", book_id="", session_id="")
    msgs = _prepare_initial_messages("写第5章", cfg, None)
    # Last message is the current user turn, prefixed with the mode marker.
    assert msgs[-1]["role"] == "user"
    assert msgs[-1]["content"].startswith("[模式: write]")
    assert "写第5章" in msgs[-1]["content"]


def test_prepare_messages_tags_plan_mode():
    cfg = AgentConfig(agent_type="plan", mode="plan", book_id="", session_id="")
    msgs = _prepare_initial_messages("分析一下角色弧光", cfg, None)
    assert msgs[-1]["content"].startswith("[模式: plan]")


def test_prepare_messages_mode_switch_visible_across_turns():
    """Simulate the user's scenario: plan turn then write turn.
    The assembled messages must show both mode markers so the LLM can see the
    switch from read-only analysis to executable mode."""
    history = [
        {"role": "user", "content": "[模式: plan] 分析一下角色"},
        {"role": "assistant", "content": "这是只读分析..."},
    ]
    cfg = AgentConfig(agent_type="write", mode="write", book_id="", session_id="")
    msgs = _prepare_initial_messages("按刚才分析写第3章", cfg, history)
    # history plan turn + current write turn both visible
    contents = [m["content"] for m in msgs if m["role"] == "user"]
    assert any("[模式: plan]" in c for c in contents)
    assert any("[模式: write]" in c for c in contents)
