# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Autopilot configuration and intent classification data structures."""

from dataclasses import dataclass, field


@dataclass
class AutopilotConfig:
    book_id: str
    instruction: str
    session_id: str = ""
    max_chapters_per_run: int = 10
    token_budget: int = 500_000
    auto_review: bool = True
    auto_extract: bool = True
    pause_between_chapters: int = 5
    confirm_before_start: bool = True
    audit_mode: str = "soft"  # "hard" | "soft" | "autonomous"
    quality_gate: str = "medium"  # "low" | "medium" | "high"
    use_smart_planner: bool = True  # Enable LLM-based planning for complex intents
    enable_replan: bool = True  # Enable dynamic replan on failure
    max_replans: int = 3  # Maximum replan attempts per task


# ── Quality thresholds by gate level ──

QUALITY_THRESHOLDS = {
    "low": 5.0,
    "medium": 7.0,
    "high": 8.5,
}


# ── Intent Classification ──

@dataclass
class PlanIntent:
    """Structured representation of parsed user intent."""
    intent_type: str  # write_new | batch_edit | global_replace | targeted_edit | analysis | insert_content | style_change | import_and_refine | mixed
    scope: str = "all"  # "all" | "#3-#8" | "#5" | "existing"
    directive: str = ""  # Original instruction
    chapter_indices: list = field(default_factory=list)  # Parsed chapter indices (target range)
    skip_indices: list = field(default_factory=list)  # Parsed skip indices (chapters to skip)
    ref_book_id: str = ""  # Optional: reference book ID for import_and_refine
    requires_outline: bool = False
    requires_writing: bool = False
    requires_edit: bool = False
    requires_analysis: bool = False
    sequential_dependency: bool = False  # Whether steps have serial dependencies
    priority_notes: str = ""  # Key requirements extracted


# Intent classification keyword patterns
INTENT_PATTERNS = {
    "write_new": {
        "keywords": ["写完", "续写", "写完全书", "写新书", "按大纲写", "写完这本书",
                     "完成全书", "创作", "新书", "写下去", "继续写", "把书写完"],
        "requires_outline": True,
        "requires_writing": True,
    },
    "batch_edit": {
        "keywords": ["改得更", "修改第", "改写第", "调整第", "优化第", "批量改",
                     "把.*章.*改", "对.*章.*修改", "修改这几章", "改这几章"],
        "requires_edit": True,
    },
    "global_replace": {
        "keywords": ["替换", "换成", "统一改为", "全部改成", "全书.*改成",
                     "把.*改成", "替换成", "改名为", "统一称呼", "全书替换"],
        "requires_edit": True,
    },
    "style_change": {
        "keywords": ["风格改", "文风", "改成.*风格", "统一风格", "调整文风",
                     "换成.*风格", "古风", "白话", "文言", "restyle",
                     "全书.*文风", "全书.*风格"],
        "requires_edit": True,
    },
    "targeted_edit": {
        "keywords": ["重写第", "精修第", "修改第", "改第", "第.*章.*改",
                     "让主角", "让.*更", "衔接", "连贯性", "优化.*章"],
        "requires_edit": True,
    },
    "analysis": {
        "keywords": ["检查", "分析", "矛盾", "一致性", "时间线", "伏笔回收",
                     "找问题", "审查", "检测", "扫描全书"],
        "requires_analysis": True,
    },
    "insert_content": {
        "keywords": ["插入", "加入", "添加.*描写", "每章.*加入", "在.*加入",
                     "补充伏笔", "补充.*描写", "插入到每章", "加入.*描写"],
        "requires_edit": True,
    },
    "import_and_refine": {
        "keywords": ["从参考书", "导入原著", "导入.*精修", "导入.*润色",
                     "导入.*改写", "参考书.*导入", "导入.*同人",
                     "原著导入", "批量导入.*改写", "参考书导入"],
        "requires_edit": True,
    },
}
