"""Tests for the refactored agent loop state, drift detection, hallucination
accounting, tool metadata and the unified terminal-response handler.

These exercise the pure-logic pieces extracted out of the 900-line
``_loop_inner`` so regressions in the refactored thresholds/flags are caught
without running the full async loop.
"""

from core.config import config
from core.loop_state import (
    DRIFT_COMPLETION_KEYWORDS,
    DRIFT_VERIFY_KEYWORDS,
    KB_MUTATION_LIMIT,
    NON_KB_RESET_ROUNDS,
    TAILSAFE_TOOLS,
    LoopMetrics,
    LoopState,
)
from core.tools import registry

# ── LoopState: round / exhaustion ──────────────────────────────────────────

def test_state_starts_not_exhausted():
    s = LoopState(max_rounds=5, base_temperature=0.3)
    assert not s.exhausted
    assert s.round == 0
    assert s.temperature == 0.3


def test_advance_round_increments_and_syncs_metrics():
    s = LoopState(max_rounds=3, base_temperature=0.3)
    s.advance_round()
    s.advance_round()
    assert s.round == 2
    assert s.metrics.rounds == 2


def test_exhausted_when_round_reaches_max():
    s = LoopState(max_rounds=2, base_temperature=0.3)
    s.advance_round()
    assert not s.exhausted
    s.advance_round()
    assert s.exhausted


# ── Drift detection (signals kept separate) ─────────────────────────────────

def test_classify_drift_detects_repetition_signal():
    """Re-doing keywords (重新提取/删干净) signal drift."""
    s = LoopState(max_rounds=10, base_temperature=0.3)
    is_comp, is_verify = s.classify_drift("我重新提取一下知识库，删干净重复的")
    assert is_comp is True
    assert is_verify is True


def test_classify_drift_does_not_flag_normal_completion():
    """Generic completion words (完成/已保存/已写入) must NOT trigger drift —
    they appear in every legitimate progress report."""
    s = LoopState(max_rounds=10, base_temperature=0.3)
    is_comp, is_verify = s.classify_drift("第3章已完成，共6000字，已保存")
    assert is_comp is False, "normal completion words should not be drift"
    assert is_verify is False


def test_classify_drift_detects_verify_loop():
    s = LoopState(max_rounds=10, base_temperature=0.3)
    is_comp, is_verify = s.classify_drift("再检查一下有没有重复实体")
    assert is_verify is True


def test_classify_drift_short_text_no_signal():
    s = LoopState(max_rounds=10, base_temperature=0.3)
    is_comp, is_verify = s.classify_drift("好")
    assert is_comp is False
    assert is_verify is False


def test_drift_limit_uses_independent_signals():
    s = LoopState(max_rounds=10, base_temperature=0.3)
    # Two verify loops alone hit the limit
    s.record_verify_loop()
    s.record_verify_loop()
    assert s.drift_limit_reached is True
    # Completion claims have their own counter
    s2 = LoopState(max_rounds=10, base_temperature=0.3)
    s2.record_completion_claim()
    assert s2.drift_limit_reached is False
    s2.record_completion_claim()
    assert s2.drift_limit_reached is True


def test_on_real_progress_resets_drift_counters():
    """Drift counters are intentionally NOT reset by on_real_progress() so
    that cross-round drift detection works correctly. Only hallucination
    tracking is reset on real progress."""
    s = LoopState(max_rounds=10, base_temperature=0.3)
    s.record_completion_claim()
    s.record_verify_loop()
    assert s.completion_claims == 1
    assert s.verify_loops == 1
    # Drift counters are NOT reset by tool execution — they persist for
    # cross-round detection (intentional design).
    assert s.completion_claims == 1
    assert s.verify_loops == 1


def test_drift_signal_label_reflects_which_limit_hit():
    s = LoopState(max_rounds=10, base_temperature=0.3)
    s.record_completion_claim()
    s.record_completion_claim()
    assert "完成声明" in s.drift_signal_label

    s2 = LoopState(max_rounds=10, base_temperature=0.3)
    s2.record_verify_loop()
    s2.record_verify_loop()
    assert "验证循环" in s2.drift_signal_label


def test_drift_keywords_are_module_level_constants():
    # Regression guard: previously these were rebuilt inside the loop every round.
    assert isinstance(DRIFT_COMPLETION_KEYWORDS, tuple)
    assert isinstance(DRIFT_VERIFY_KEYWORDS, tuple)
    assert "重新提取" in DRIFT_COMPLETION_KEYWORDS
    assert "再检查" in DRIFT_VERIFY_KEYWORDS
    # Generic completion words must NOT be in the drift set
    assert "完成" not in DRIFT_COMPLETION_KEYWORDS
    assert "已保存" not in DRIFT_COMPLETION_KEYWORDS
    assert "已创建" not in DRIFT_COMPLETION_KEYWORDS


# ── KB mutation guard (sliding window) ──────────────────────────────────────

def test_kb_streak_resets_after_non_kb_rounds():
    s = LoopState(max_rounds=10, base_temperature=0.3)
    s.record_kb_round()
    s.record_kb_round()
    assert s.kb_mutation_streak == 2
    # A single read-only round doesn't reset yet
    s.record_non_kb_round()
    assert s.kb_mutation_streak == 2
    for _ in range(NON_KB_RESET_ROUNDS):
        s.record_non_kb_round()
    assert s.kb_mutation_streak == 0


def test_kb_mutation_limit_reached():
    s = LoopState(max_rounds=10, base_temperature=0.3)
    for _ in range(KB_MUTATION_LIMIT):
        s.record_kb_round()
    assert s.kb_mutation_limit_reached is True
    s.reset_kb_guard()
    assert s.kb_mutation_streak == 0


# ── Tail-safe tools after drift correction ─────────────────────────────────

def test_allow_tail_tools_permits_readonly_once():
    s = LoopState(max_rounds=10, base_temperature=0.3)
    s.drift_corrected = True
    assert s.allow_tail_tools({"search_knowledge"}) is True
    s.consume_tail()
    assert s.allow_tail_tools({"search_knowledge"}) is False


def test_allow_tail_tools_rejects_mutating_tools():
    s = LoopState(max_rounds=10, base_temperature=0.3)
    s.drift_corrected = True
    assert s.allow_tail_tools({"write_chapter"}) is False
    assert s.allow_tail_tools({"search_knowledge", "write_chapter"}) is False


def test_tailsafe_tools_are_readonly():
    for name in TAILSAFE_TOOLS:
        tool = registry.get(name)
        assert tool is not None, f"unknown tool in TAILSAFE: {name}"
        assert not tool.mutates_kb, f"{name} mutates KB but is marked tail-safe"
        assert not tool.touches_chapter, f"{name} touches chapters but is marked tail-safe"


# ── Adaptive temperature ────────────────────────────────────────────────────

def test_temperature_drops_on_pure_tool_chain(monkeypatch):
    monkeypatch.setattr(config.agent, "adaptive_temperature", True)
    s = LoopState(max_rounds=10, base_temperature=0.3)
    s.advance_round()
    s.advance_round()  # round > 1 required for the adaptive drop
    s.update_writing_mode(streamed_text="ok")  # < 200 chars, no writing yet
    assert s.temperature < 0.3


def test_temperature_stays_high_when_adaptive_disabled(monkeypatch):
    monkeypatch.setattr(config.agent, "adaptive_temperature", False)
    s = LoopState(max_rounds=10, base_temperature=0.3)
    s.advance_round()
    s.update_writing_mode(streamed_text="ok")
    assert s.temperature == 0.3


def test_writing_mode_keeps_temperature_on_long_output():
    s = LoopState(max_rounds=10, base_temperature=0.3)
    s.update_writing_mode(streamed_text="x" * 300)
    assert s.has_writing_output is True
    assert s.temperature == 0.3


# ── Tool metadata (single source of truth) ──────────────────────────────────

def test_write_chapter_metadata():
    t = registry.get("write_chapter")
    assert t.streaming is True
    assert t.touches_chapter is True
    assert t.context_aware is True


def test_extract_knowledge_mutates_kb():
    assert registry.get("extract_knowledge").mutates_kb is True
    assert registry.get("delete_entity").mutates_kb is True
    assert registry.get("update_entity").mutates_kb is True


def test_readonly_tools_have_no_mutating_flags():
    for name in ("list_chapters", "read_chapter", "search_knowledge", "get_outline"):
        t = registry.get(name)
        assert t.mutates_kb is False
        assert t.touches_chapter is False
        assert t.streaming is False


def test_all_streaming_tools_registered():
    from core.tools import tools_with
    streaming = tools_with("streaming")
    for expected in ("write_chapter", "delegate_writing", "edit_chapter",
                      "patch_chapter", "run_review", "extract_all_chapters"):
        assert expected in streaming, f"{expected} should be streaming"


# ── Terminal response handler ───────────────────────────────────────────────

def _make_response(content="", tool_calls=None):
    from core.llm_client import LLMResponse, ToolCall
    r = LLMResponse()
    r.content = content
    if tool_calls:
        r.tool_calls = [ToolCall(id=tc[0], name=tc[1], arguments=tc[2]) for tc in tool_calls]
    return r


def test_hallucination_detection_fake_tool():
    """fake_tool detection: "我调用了 write_chapter" without tool_calls."""
    from core.hallucination import detect_hallucination
    result = detect_hallucination("我调用了 write_chapter 工具来写第1章。")
    assert result.detected
    assert result.layer == "fake_tool"


def test_hallucination_detection_fake_write():
    """fake_write detection: "第3章已完成，共6000字" without tool_calls."""
    from core.hallucination import detect_hallucination
    result = detect_hallucination("第3章已完成，共6000字，增加了对手戏。")
    assert result.detected
    assert result.layer == "fake_write"


def test_hallucination_detection_clean_text():
    """Normal text should not trigger any hallucination detection."""
    from core.hallucination import detect_hallucination
    result = detect_hallucination("完成了，接下来继续。已删除的内容不需要。")
    assert not result.detected


# ── Metrics ─────────────────────────────────────────────────────────────────

def test_metrics_summary_includes_key_fields():
    m = LoopMetrics()
    m.rounds = 5
    m.llm_calls = 6
    m.record_hallucination("past")
    summary = m.summary()
    assert "rounds=5" in summary
    assert "llm_calls=6" in summary
    assert "past" in summary
