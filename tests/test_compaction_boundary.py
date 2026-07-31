"""Compaction boundary tests — M2.5 of .pi/plan.md.

Pin the threshold edge behaviour: compaction must fire only above the
configured ratio, and stale-tool-result pruning must preserve the
protected tail (the rounds the LLM still needs).
"""

import pytest

from core import compaction


@pytest.fixture
def fixed_context(monkeypatch):
    """Force deterministic limits: 1000-token context, small protected tail."""
    monkeypatch.setattr(compaction, "get_context_limit", lambda model: 1000)
    monkeypatch.setattr(compaction, "PROTECTED_TAIL_TOKENS", 120)
    monkeypatch.setattr(compaction, "STALE_TOOL_PREVIEW_TOKENS", 15)
    return compaction


def _msg(text: str, role: str = "user") -> dict:
    return {"role": role, "content": text}


def test_needs_compaction_below_threshold(fixed_context):
    # threshold_ratio 0.5 → fires at >500 tokens of 1000.
    messages = [_msg("短消息")]
    assert not fixed_context.needs_compaction(messages)


def test_needs_compaction_above_threshold(fixed_context):
    big = _msg("词" * 800)  # well over 500 tokens
    assert fixed_context.needs_compaction([big])


def test_needs_compaction_boundary_just_under(fixed_context):
    # ~1 token per CJK char; 480 chars ≈ 480 tokens < 500 → no compaction.
    messages = [_msg("字" * 450)]
    assert not fixed_context.needs_compaction(messages)


def test_prune_stale_tool_results_keeps_tail(fixed_context):
    # 10 rounds of tool results (~30 tokens each) with a 60-token protected
    # tail → only the last ~2 rounds survive; the earlier 8 are truncated.
    messages: list[dict] = []
    for i in range(10):
        messages.append(_msg(f"user round {i}", "user"))
        messages.append(_msg("工具输出内容很长的一段" * 4, "tool"))

    pruned, changed = fixed_context.prune_stale_tool_results(messages)
    assert changed
    tool_msgs = [m for m in pruned if m["role"] == "tool"]
    # Tail tool messages keep their full length; stale ones carry the marker.
    assert any("stale" in m.get("content", "") or "已截断" in m.get("content", "") for m in tool_msgs[:-3])
    assert any(len(m["content"]) >= len("工具输出内容很长的一段" * 4) for m in tool_msgs[-2:])


def test_compact_messages_reduces_size(fixed_context, monkeypatch):
    # 不访问 LLM：summary 由假实现提供（CI 无 API key）。
    monkeypatch.setattr(fixed_context, "chat", lambda *a, **k: "[模拟摘要]")
    messages = []
    for i in range(10):
        messages.append(_msg(f"第{i}轮问题", "user"))
        messages.append(_msg("回答内容" * 200, "assistant"))

    compacted = fixed_context.compact_messages(messages)
    assert len(compacted) <= len(messages)
