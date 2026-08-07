"""
anyspark.explore — 探索引擎包。

设计规格（DESIGN.md 机制 7）：
- 意图理解者 → 探索策略集 → 探索者×3-4 并行 → 用户判别 → 固化
- 默认探索维度：情节驱动/角色驱动/氛围驱动/结构实验/文笔质感/用户指导
- 探索方向三来源：模板派生 / 作品内在生长 / 用户指导
- 轻量优先：探索者多数是单次 LLM 调用
"""

from .direction import (
    DEFAULT_DIMENSIONS,
    DimensionStore,
    DirectionCard,
    ProjectArchive,
)
from .explorers import ExplorationEngine, run_exploration
from .intent import IntentUnderstander
from .roleplay import RolePlayEngine, RolePlayResult, run_roleplay
from .strategy import ExplorationStrategy, extract_json_dict

__all__ = [
    "DEFAULT_DIMENSIONS",
    "DimensionStore",
    "DirectionCard",
    "ExplorationEngine",
    "ExplorationStrategy",
    "IntentUnderstander",
    "ProjectArchive",
    "RolePlayEngine",
    "RolePlayResult",
    "extract_json_dict",
    "run_exploration",
    "run_roleplay",
]
