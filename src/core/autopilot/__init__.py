# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Autopilot — intelligent book-writing planner with intent classification."""

from .config import INTENT_PATTERNS, QUALITY_THRESHOLDS, AutopilotConfig, PlanIntent
from .planner import AutopilotPlanner, _classify_intent, _parse_chapter_indices, _parse_skip_indices

__all__ = [
    "AutopilotConfig",
    "PlanIntent",
    "QUALITY_THRESHOLDS",
    "INTENT_PATTERNS",
    "_classify_intent",
    "_parse_chapter_indices",
    "_parse_skip_indices",
    "AutopilotPlanner",
]
