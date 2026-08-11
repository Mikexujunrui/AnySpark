"""
anyspark.review — 拟人化评审团（S64 可选增强）。

拟人化评审员（YAML persona + 评分维度）→ 并发评审 → 主席汇总裁决报告。
机制硬编码、内容自然语言：人设/维度/报告渲染全为内容；并发/解析/降级为机制。
与 check 的分工：check=确定性硬伤规则引擎（客观事实）；review=人格化评价（体验）。

⚠️ 命名注意（S71 有意重复 + S83 消歧）：本包与 anyspark.check **都导出 run_review /
ReviewReport**（同名不同实现）——硬伤检测用 `from anyspark.check import run_review`，
人格化评审用 `from anyspark.review import run_review_panel`（或 ReviewPanel 实例方法）。
勿混用。
"""

from __future__ import annotations

from .defs import ReviewerDef, ReviewReport, ReviewResult, ScoreDim
from .panel import DEFAULT_REVIEWERS_DIR, ReviewPanel, default_panel, run_review

# S83 消歧：人格化评审的明确别名（与 check.run_review 区分）
run_review_panel = run_review

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
    "run_review_panel",
]
