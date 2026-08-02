"""
anyspark.check — 检测网包。

设计规格（DESIGN.md 机制 9）：三层协作生成（骨架/AI动态/用户规则）+ 多检测者并行。
机制 8：轻量规则编译器（用户自然语言 → 检测函数，只读纯文本）。
"""

from .report import Finding, ReviewReport
from .reviewers import ReviewEngine, run_review
from .rules import CompiledRule, check_text, compile_rule
from .skeleton import SKELETON_CHECKS, SkeletonCheckItem

__all__ = [
    "SKELETON_CHECKS",
    "CompiledRule",
    "Finding",
    "ReviewEngine",
    "ReviewReport",
    "SkeletonCheckItem",
    "check_text",
    "compile_rule",
    "run_review",
]
