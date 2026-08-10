"""
anyspark.review — 拟人化评审团（S64 可选增强）。

拟人化评审员（YAML persona + 评分维度）→ 并发评审 → 主席汇总裁决报告。
机制硬编码、内容自然语言：人设/维度/报告渲染全为内容；并发/解析/降级为机制。
与 check 的分工：check=确定性硬伤规则引擎（客观事实）；review=人格化评价（体验）。
"""

from __future__ import annotations

from .defs import ReviewerDef, ReviewReport, ReviewResult, ScoreDim
from .panel import DEFAULT_REVIEWERS_DIR, ReviewPanel, default_panel, run_review

__version__ = "0.0.1"

__all__ = [
    "DEFAULT_REVIEWERS_DIR",
    "ReviewPanel",
    "ReviewReport",
    "ReviewResult",
    "ReviewerDef",
    "ScoreDim",
    "default_panel",
    "run_review",
]
