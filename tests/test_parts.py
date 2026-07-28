"""Tests for the structured Part system (parts.py).

Covers Part serialization, Turn reconstruction to/from flat LLM messages,
backward compatibility with legacy {role, text} history, and the guarantee
that reasoning is captured-but-not-replayed into LLM context.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.parts import (
    ChapterDiffPart,
    ReasoningPart,
    TextPart,
    ToolCallPart,
    ToolResultPart,
    Turn,
    part_from_dict,
    turns_from_history,
    turns_to_llm_messages,
)

# ── Part serialization round-trip ────────────────────────────────────────────


def test_text_part_roundtrip():
    p = TextPart(text="hello")
    d = p.to_dict()
    assert d["type"] == "text" and d["text"] == "hello"
    p2 = part_from_dict(d)
    assert isinstance(p2, TextPart) and p2.text == "hello"


def test_tool_call_part_roundtrip():
    p = ToolCallPart(tool_call_id="tc1", name="write_chapter", arguments='{"x":1}')
    p2 = part_from_dict(p.to_dict())
    assert isinstance(p2, ToolCallPart)
    assert p2.tool_call_id == "tc1" and p2.name == "write_chapter"


def test_chapter_diff_part_roundtrip():
    p = ChapterDiffPart(chapter_id="#3", chapter_title="第三章", operation="created", word_count=4500)
    p2 = part_from_dict(p.to_dict())
    assert isinstance(p2, ChapterDiffPart)
    assert p2.operation == "created" and p2.word_count == 4500


def test_unknown_part_type_falls_back_to_text():
    """Unknown type strings degrade to TextPart rather than crashing."""
    p = part_from_dict({"type": "nonexistent", "text": "x"})
    assert isinstance(p, TextPart)


# ── Turn.to_llm_messages reconstructs flat OpenAI format ─────────────────────


def test_turn_to_llm_messages_basic_user_assistant():
    t = Turn(user_text="写第3章", mode="write", final_text="已完成第3章")
    msgs = t.to_llm_messages()
    assert msgs[0]["role"] == "user"
    assert "[模式: write]" in msgs[0]["content"]
    assert msgs[-1]["role"] == "assistant"
    assert msgs[-1]["content"] == "已完成第3章"


def test_turn_reconstructs_tool_call_and_result_sequence():
    """A turn with tool calls must rebuild the assistant(tool_calls) → tool(result)
    ordering the OpenAI API expects."""
    t = Turn(
        user_text="写第3章",
        mode="write",
        parts=[
            ToolCallPart(tool_call_id="tc1", name="write_chapter", arguments='{"instruction":"x"}'),
            ToolResultPart(tool_call_id="tc1", result="已写入第3章", tool_name="write_chapter"),
            ChapterDiffPart(chapter_id="#3", operation="created", word_count=3000),
        ],
        final_text="第3章已写入",
    )
    msgs = t.to_llm_messages()
    roles = [m["role"] for m in msgs]
    assert roles == ["user", "assistant", "tool", "assistant"]
    assert msgs[1]["tool_calls"][0]["function"]["name"] == "write_chapter"
    assert msgs[2]["tool_call_id"] == "tc1"
    assert msgs[2]["content"] == "已写入第3章"


def test_turn_reasoning_not_replayed_to_llm():
    """Reasoning parts must NOT appear in the replayed LLM messages (saves
    tokens; explicit output > internal CoT for creative work)."""
    t = Turn(
        user_text="分析",
        parts=[
            ReasoningPart(text="我在思考角色的动机..."),
            ToolCallPart(tool_call_id="tc1", name="search_knowledge", arguments="{}"),
            ToolResultPart(tool_call_id="tc1", result="找到3个实体"),
        ],
        final_text="分析完成",
    )
    msgs = t.to_llm_messages()
    # No message should contain the reasoning text.
    for m in msgs:
        content = m.get("content", "")
        assert "我在思考角色的动机" not in content
    # But the turn retains it for UI display.
    assert "我在思考角色的动机" in t.reasoning()


def test_turn_chapter_diffs_accessor():
    t = Turn(
        parts=[
            ChapterDiffPart(chapter_id="#1", operation="patched"),
            ChapterDiffPart(chapter_id="#2", operation="created"),
            ToolCallPart(tool_call_id="x", name="x"),
        ]
    )
    diffs = t.chapter_diffs()
    assert len(diffs) == 2
    assert {d.chapter_id for d in diffs} == {"#1", "#2"}


# ── Backward compatibility with legacy history ───────────────────────────────


def test_turn_from_legacy_dict():
    """Old messages with only role+text load as minimal Turns."""
    t = Turn.from_dict({"role": "agent", "text": "旧回复", "ts": "10:00"})
    assert t.final_text == "旧回复"
    assert t.parts == []
    assert t.user_text == ""


def test_turns_from_history_legacy_messages():
    """Legacy {role, text} history pairs into Turns without parts."""
    raw = [
        {"role": "user", "text": "写第1章", "mode": "write"},
        {"role": "agent", "text": "完成", "ts": "10:00"},
        {"role": "user", "text": "写第2章", "mode": "write"},
        {"role": "agent", "text": "完成2", "ts": "10:01"},
    ]
    turns = turns_from_history(raw)
    assert len(turns) == 2
    assert turns[0].user_text == "写第1章"
    assert turns[0].final_text == "完成"
    assert turns[0].mode == "write"


def test_turns_from_history_structured_parts():
    """Structured turns (with parts) reconstruct with full tool history."""
    raw = [
        {"role": "user", "text": "写第3章", "mode": "write"},
        {
            "role": "agent",
            "text": "完成",
            "parts": [
                {"type": "tool_call", "tool_call_id": "tc1", "name": "write_chapter", "arguments": "{}"},
                {"type": "tool_result", "tool_call_id": "tc1", "result": "写入成功", "tool_name": "write_chapter"},
                {"type": "chapter_diff", "chapter_id": "#3", "operation": "created", "word_count": 3000},
            ],
            "user_text": "写第3章",
            "final_text": "完成",
        },
    ]
    turns = turns_from_history(raw)
    assert len(turns) == 1
    t = turns[0]
    assert len(t.parts) == 3
    assert isinstance(t.parts[0], ToolCallPart)
    assert isinstance(t.parts[2], ChapterDiffPart)
    # Replaying to LLM produces the right sequence.
    msgs = turns_to_llm_messages(turns)
    roles = [m["role"] for m in msgs]
    assert roles == ["user", "assistant", "tool", "assistant"]


def test_turns_to_llm_messages_excludes_reasoning_globally():
    """End-to-end: structured history with reasoning never leaks reasoning into
    the messages sent to the LLM."""
    raw = [
        {"role": "user", "text": "为什么这样写", "mode": "write"},
        {
            "role": "agent",
            "text": "因为...",
            "parts": [
                {"type": "reasoning", "text": "内部思考：角色动机是..."},
                {"type": "text", "text": "因为..."},
            ],
            "user_text": "为什么这样写",
            "final_text": "因为...",
        },
    ]
    turns = turns_from_history(raw)
    msgs = turns_to_llm_messages(turns)
    for m in msgs:
        assert "内部思考" not in m.get("content", "")


def test_turn_to_dict_includes_legacy_fields():
    """to_dict keeps role/text/mode so legacy readers still work."""
    t = Turn(user_text="hi", mode="write", final_text="hello", timestamp="10:00")
    d = t.to_dict()
    assert d["role"] == "agent"
    assert d["text"] == "hello"
    assert d["mode"] == "write"
