"""
anyspark.align — 对齐系统包。

设计规格（DESIGN.md 第 6 节 / T3）：
- 说明书 = 可读性高的自然语言文档（多条目），系统自动维护，用户是最终编辑者
- 条目元数据：内容 / 来源(自动提炼|用户手写) / 置信度(0-1) / 活跃度(高|中|低) / 锁定
- 分层：项目说明书（主体）+ 全局说明书（极小化）+ 会话层（临时不落盘）
- 注入优先级：项目级 > 全局级；项目级永远可覆盖全局
"""

from .agency import (
    DEFAULT_ID,
    DEFAULT_LEVELS,
    AgencyLevel,
    AgencyStore,
    build_agency_block,
    parse_agency_declaration,
    temperature_for,
)
from .bias import BiasStore
from .extract import PreferenceExtractor
from .manual import ManualEntry, ManualStore, render_manual
from .mind import MindPlanner, SessionPlan
from .mindgen import (
    build_agency_gen_prompt,
    build_agency_suggest_prompt,
    parse_agency_gen_result,
    parse_agency_suggest_result,
)
from .mindup import (
    build_learning_review_prompt,
    build_reconcile_prompt,
    parse_learning_review_result,
    parse_reconcile_result,
)
from .plan import ChapterPlan, StoryPlanStore, render_plan
from .signals import Signal, SignalCollector, SignalStore
from .skillgen import SkillGenerator, render_skill_candidates
from .skills import (
    DEFAULT_SKILLS,
    WritingSkill,
    WritingSkillStore,
    render_skill_index,
    render_skills_by_name,
)
from .storytree import (
    StoryNode,
    StoryThread,
    StoryThreadStore,
    StoryTreeStore,
)
from .summarize import MemoryStore, SceneMemory, SessionSummarizer
from .worldsettings import WorldSetting, WorldSettingStore, render_settings

__all__ = [
    "DEFAULT_ID",
    "DEFAULT_LEVELS",
    "DEFAULT_SKILLS",
    "AgencyLevel",
    "AgencyStore",
    "BiasStore",
    "ChapterPlan",
    "ManualEntry",
    "ManualStore",
    "MemoryStore",
    "MindPlanner",
    "PreferenceExtractor",
    "SceneMemory",
    "SessionPlan",
    "SessionSummarizer",
    "Signal",
    "SignalCollector",
    "SignalStore",
    "SkillGenerator",
    "StoryNode",
    "StoryPlanStore",
    "StoryThread",
    "StoryThreadStore",
    "StoryTreeStore",
    "WorldSetting",
    "WorldSettingStore",
    "WritingSkill",
    "WritingSkillStore",
    "build_agency_block",
    "build_agency_gen_prompt",
    "build_agency_suggest_prompt",
    "build_learning_review_prompt",
    "build_reconcile_prompt",
    "parse_agency_declaration",
    "parse_agency_gen_result",
    "parse_agency_suggest_result",
    "parse_learning_review_result",
    "parse_reconcile_result",
    "render_manual",
    "render_plan",
    "render_settings",
    "render_skill_candidates",
    "render_skill_index",
    "render_skills_by_name",
    "temperature_for",
]
