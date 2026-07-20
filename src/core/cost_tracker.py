# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Cost tracker — persistent token/cost accounting for LLM API usage.

Records per-tool-call token usage to data/metrics.jsonl (append-only).
Aggregates by book/tool/day for dashboard visualization.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.config import DATA_DIR

logger = logging.getLogger(__name__)

_METRICS_FILE = DATA_DIR / "metrics.jsonl"

# DeepSeek pricing (USD per 1M tokens). Configurable for other providers.
# Source: https://platform.deepseek.com/api-docs/pricing
_PRICING: dict[str, dict[str, float]] = {
    "deepseek-v4-pro": {"input": 2.0, "output": 8.0},
    "deepseek-v4-flash": {"input": 0.5, "output": 1.2},
    "deepseek-chat": {"input": 1.0, "output": 4.0},
    "deepseek-reasoner": {"input": 3.0, "output": 12.0},
    # Fallback for unknown models
    "default": {"input": 1.0, "output": 4.0},
}


@dataclass
class CostSummary:
    """Aggregated cost summary for a book."""

    total_tokens: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    by_tool: dict[str, dict] = field(default_factory=dict)
    by_model: dict[str, dict] = field(default_factory=dict)
    by_day: dict[str, dict] = field(default_factory=dict)
    total_calls: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_tokens": self.total_tokens,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 4),
            "by_tool": dict(self.by_tool),
            "by_model": dict(self.by_model),
            "by_day": dict(self.by_day),
            "total_calls": self.total_calls,
        }


def estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Estimate USD cost for a single API call.

    Pricing is per 1M tokens. Returns 0.0 for zero usage.
    """
    pricing = _PRICING.get(model, _PRICING["default"])
    cost = (input_tokens / 1_000_000) * pricing["input"]
    cost += (output_tokens / 1_000_000) * pricing["output"]
    return round(cost, 6)


def record_usage(
    book_id: str,
    session_id: str,
    tool_name: str,
    input_tokens: int,
    output_tokens: int,
    model: str = "deepseek-chat",
) -> None:
    """Persist a single usage record to the metrics JSONL file.

    Append-only, thread-safe via atomic file append. Failures are logged
    but never raised — cost tracking is best-effort and must not break
    the writing pipeline.
    """
    if input_tokens <= 0 and output_tokens <= 0:
        return

    record = {
        "timestamp": datetime.now().isoformat(),
        "book_id": book_id,
        "session_id": session_id,
        "tool_name": tool_name,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "estimated_cost_usd": estimate_cost(input_tokens, output_tokens, model),
    }

    try:
        _METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_METRICS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.warning("Failed to record cost metrics: %s", e)


def _load_records(book_id: str) -> list[dict]:
    """Load all metric records for a given book."""
    if not _METRICS_FILE.exists():
        return []
    records: list[dict] = []
    try:
        with open(_METRICS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("book_id") == book_id:
                        records.append(rec)
                except json.JSONDecodeError:
                    continue
    except OSError as e:
        logger.warning("Failed to read metrics file: %s", e)
    return records


def _day_key(timestamp: str) -> str:
    """Extract YYYY-MM-DD from ISO timestamp."""
    try:
        return timestamp[:10]
    except (IndexError, TypeError):
        return "unknown"


def get_book_cost(book_id: str) -> CostSummary:
    """Aggregate all cost data for a book."""
    records = _load_records(book_id)
    summary = CostSummary()

    for rec in records:
        in_tok = rec.get("input_tokens", 0)
        out_tok = rec.get("output_tokens", 0)
        total = rec.get("total_tokens", in_tok + out_tok)
        cost = rec.get("estimated_cost_usd", 0.0)
        tool = rec.get("tool_name", "unknown")
        model = rec.get("model", "unknown")
        day = _day_key(rec.get("timestamp", ""))

        summary.total_tokens += total
        summary.total_input_tokens += in_tok
        summary.total_output_tokens += out_tok
        summary.estimated_cost_usd += cost
        summary.total_calls += 1

        # By tool
        if tool not in summary.by_tool:
            summary.by_tool[tool] = {"tokens": 0, "cost": 0.0, "calls": 0}
        summary.by_tool[tool]["tokens"] += total
        summary.by_tool[tool]["cost"] = round(summary.by_tool[tool]["cost"] + cost, 4)
        summary.by_tool[tool]["calls"] += 1

        # By model
        if model not in summary.by_model:
            summary.by_model[model] = {"tokens": 0, "cost": 0.0, "calls": 0}
        summary.by_model[model]["tokens"] += total
        summary.by_model[model]["cost"] = round(summary.by_model[model]["cost"] + cost, 4)
        summary.by_model[model]["calls"] += 1

        # By day
        if day not in summary.by_day:
            summary.by_day[day] = {"tokens": 0, "cost": 0.0, "calls": 0}
        summary.by_day[day]["tokens"] += total
        summary.by_day[day]["cost"] = round(summary.by_day[day]["cost"] + cost, 4)
        summary.by_day[day]["calls"] += 1

    # Sort by_day chronologically
    summary.by_day = dict(sorted(summary.by_day.items()))
    return summary


def get_cost_trend(book_id: str, days: int = 30) -> list[dict]:
    """Get daily cost trend for the last N days."""
    summary = get_book_cost(book_id)
    now = datetime.now()
    trend: list[dict] = []
    for i in range(days - 1, -1, -1):
        day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        data = summary.by_day.get(day, {"tokens": 0, "cost": 0.0, "calls": 0})
        trend.append({"date": day, **data})
    return trend


# Import here to avoid circular imports at module level
from datetime import timedelta  # noqa: E402
