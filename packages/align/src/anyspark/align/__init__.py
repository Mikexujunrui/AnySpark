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
from .inject import ManualInjector, MemoryInjector
from .manual import ManualEntry, ManualStore, render_manual
from .mood import MOOD_DIMS, build_mood_block
from .signals import Signal, SignalCollector, SignalStore
from .summarize import MemoryStore, SceneMemory, SessionSummarizer
from .worldsettings import WorldSetting, WorldSettingStore, render_settings

__all__ = [
    "DEFAULT_ID",
    "DEFAULT_LEVELS",
    "MOOD_DIMS",
    "AgencyLevel",
    "AgencyStore",
    "BiasStore",
    "ManualEntry",
    "ManualInjector",
    "ManualStore",
    "MemoryInjector",
    "MemoryStore",
    "PreferenceExtractor",
    "SceneMemory",
    "SessionSummarizer",
    "Signal",
    "SignalCollector",
    "SignalStore",
    "WorldSetting",
    "WorldSettingStore",
    "build_agency_block",
    "build_mood_block",
    "parse_agency_declaration",
    "render_manual",
    "render_settings",
    "temperature_for",
]
