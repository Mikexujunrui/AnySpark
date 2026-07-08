"""Tests for writing performance optimizations."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from unittest.mock import patch

from core.compaction import (
    STALE_PRUNED_MARKER,
    prune_stale_tool_results,
)
from core.config import config


# Mock token counter for fast tests — avoids encoding huge strings
def _mock_count_tokens(text):
    """Mock: 1 token per char for simple predictable math."""
    if not text:
        return 0
    return len(text)


def test_config_values():
    """Optimization 2: compaction threshold lowered."""
    assert config.compaction.threshold_ratio == 0.70
    assert config.compaction.max_tool_output_tokens == 30000
    assert config.compaction.protected_tail_tokens == 60000
    assert config.compaction.tail_turns_to_keep == 4


@patch('core.compaction.count_tokens', side_effect=_mock_count_tokens)
def test_prune_stale_tool_result(mock_ct):
    """Optimization 3: old tool results get truncated to preview."""
    big_tool_result = "A" * 10000   # mock: 2500 tokens
    big_assistant = "x" * 100000   # mock: 25000 tokens, tail starts here

    messages = [
        {"role": "system", "content": "You are a writer."},
        {"role": "user", "content": "Write chapter 1."},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "tc1", "type": "function", "function": {"name": "read_chapter", "arguments": "{}"}}
        ]},
        {"role": "tool", "tool_call_id": "tc1", "content": big_tool_result},
        {"role": "assistant", "content": big_assistant},
        {"role": "user", "content": "Next task."},
    ]

    result, pruned = prune_stale_tool_results(messages)
    assert pruned, "Should have pruned the stale tool result"

    tool_msg = [m for m in result if m.get("role") == "tool"][0]
    assert STALE_PRUNED_MARKER in tool_msg["content"], "Should have stale marker"
    assert len(tool_msg["content"]) < len(big_tool_result), "Should be shorter"


@patch('core.compaction.count_tokens', side_effect=_mock_count_tokens)
def test_prune_protected_tail_not_pruned(mock_ct):
    """Optimization 3: tool results in protected tail are NOT pruned."""
    messages = [
        {"role": "system", "content": "You are a writer."},
        {"role": "user", "content": "Write."},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "tc1", "type": "function", "function": {"name": "read_chapter", "arguments": "{}"}}
        ]},
        {"role": "tool", "tool_call_id": "tc1", "content": "B" * 10000},
    ]

    result, pruned = prune_stale_tool_results(messages)
    assert not pruned, "Should NOT prune recent tool result in protected tail"


@patch('core.compaction.count_tokens', side_effect=_mock_count_tokens)
def test_prune_already_pruned_not_double_pruned(mock_ct):
    """Optimization 3: already-pruned messages are not pruned again."""
    already_pruned_content = "Short preview" + STALE_PRUNED_MARKER
    messages = [
        {"role": "system", "content": "S" * 300000},  # mock: 75K tokens
        {"role": "tool", "tool_call_id": "tc1", "content": already_pruned_content},
        {"role": "assistant", "content": "A" * 200000},  # mock: 50K tokens
    ]

    result, pruned = prune_stale_tool_results(messages)
    assert not pruned, "Should NOT double-prune"


@patch('core.compaction.count_tokens', side_effect=_mock_count_tokens)
def test_prune_small_tool_result_not_pruned(mock_ct):
    """Optimization 3: small tool results are not pruned."""
    messages = [
        {"role": "system", "content": "S" * 300000},
        {"role": "tool", "tool_call_id": "tc1", "content": "small result"},
        {"role": "assistant", "content": "A" * 200000},
    ]

    result, pruned = prune_stale_tool_results(messages)
    assert not pruned, "Should NOT prune small tool result"


def test_planner_instruction_changed():
    """Optimization 1: verify the planner instruction no longer says '参考前面的章节内容'."""
    planner_path = os.path.join(
        os.path.dirname(__file__), "..", "src", "core", "autopilot", "planner.py"
    )
    with open(planner_path, encoding="utf-8") as f:
        content = f.read()

    assert "请参考前面的章节内容" not in content, "Old instruction should be removed"
    assert "前情提要" in content, "New instruction should mention 前情提要"


if __name__ == "__main__":
    test_config_values()
    print("PASS: test_config_values")

    test_prune_stale_tool_result()
    print("PASS: test_prune_stale_tool_result")

    test_prune_protected_tail_not_pruned()
    print("PASS: test_prune_protected_tail_not_pruned")

    test_prune_already_pruned_not_double_pruned()
    print("PASS: test_prune_already_pruned_not_double_pruned")

    test_prune_small_tool_result_not_pruned()
    print("PASS: test_prune_small_tool_result_not_pruned")

    test_planner_instruction_changed()
    print("PASS: test_planner_instruction_changed")

    print("\nAll optimization tests passed!")
