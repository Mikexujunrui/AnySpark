# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Tests for cost tracker — pricing estimation and data serialization."""

from core.cost_tracker import (
    CostSummary,
    estimate_cost,
    record_usage,
    get_book_cost,
)


class TestEstimateCost:
    """Test cost estimation."""

    def test_zero_usage_zero_cost(self):
        assert estimate_cost(0, 0, "deepseek-chat") == 0.0

    def test_known_model_pricing(self):
        """DeepSeek chat: $1/1M input, $4/1M output."""
        cost = estimate_cost(1_000_000, 0, "deepseek-chat")
        assert cost == 1.0  # $1 per 1M input tokens

    def test_unknown_model_fallback(self):
        """Unknown model should use default pricing."""
        cost = estimate_cost(1_000_000, 0, "unknown-model")
        assert cost > 0  # falls back to default pricing

    def test_output_pricing(self):
        """Output tokens are more expensive than input."""
        input_cost = estimate_cost(0, 1_000_000, "deepseek-chat")
        assert input_cost == 4.0  # $4 per 1M output tokens

    def test_small_usage(self):
        """Small token counts produce small costs."""
        cost = estimate_cost(1000, 500, "deepseek-chat")
        assert 0 < cost < 0.01


class TestCostSummary:
    """Test CostSummary dataclass."""

    def test_empty_summary(self):
        summary = CostSummary()
        d = summary.to_dict()
        assert d["total_tokens"] == 0
        assert d["total_calls"] == 0
        assert d["estimated_cost_usd"] == 0.0

    def test_populated_summary(self):
        summary = CostSummary(
            total_tokens=50000,
            total_input_tokens=30000,
            total_output_tokens=20000,
            estimated_cost_usd=0.15,
            total_calls=10,
        )
        d = summary.to_dict()
        assert d["total_tokens"] == 50000
        assert d["estimated_cost_usd"] == 0.15
        assert d["total_calls"] == 10


class TestRecordUsage:
    """Test usage recording (integration with file system)."""

    def test_record_zero_usage_skipped(self, tmp_path, monkeypatch):
        """Zero token usage should not be recorded."""
        from core import cost_tracker
        monkeypatch.setattr(cost_tracker, "_METRICS_FILE", tmp_path / "test_metrics.jsonl")
        record_usage("test_book", "session1", "test_tool", 0, 0, "deepseek-chat")
        assert not (tmp_path / "test_metrics.jsonl").exists()

    def test_record_and_read_back(self, tmp_path, monkeypatch):
        """Recorded usage should be readable via get_book_cost."""
        from core import cost_tracker
        monkeypatch.setattr(cost_tracker, "_METRICS_FILE", tmp_path / "test_metrics.jsonl")
        record_usage("test_book", "s1", "write_chapter", 1000, 500, "deepseek-chat")
        record_usage("test_book", "s1", "extract_knowledge", 2000, 300, "deepseek-chat")

        summary = get_book_cost("test_book")
        assert summary.total_tokens == 3800
        assert summary.total_calls == 2
        assert "write_chapter" in summary.by_tool
        assert "extract_knowledge" in summary.by_tool

    def test_other_book_not_included(self, tmp_path, monkeypatch):
        """Records from other books should not be included."""
        from core import cost_tracker
        monkeypatch.setattr(cost_tracker, "_METRICS_FILE", tmp_path / "test_metrics2.jsonl")
        record_usage("book_a", "s1", "tool1", 1000, 500, "deepseek-chat")
        record_usage("book_b", "s1", "tool1", 2000, 500, "deepseek-chat")

        summary = get_book_cost("book_a")
        assert summary.total_tokens == 1500
        assert summary.total_calls == 1
