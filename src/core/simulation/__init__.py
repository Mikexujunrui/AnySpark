"""Simulation package — 推演功能3.0 核心模块.

Provides:
    - SimulationStore: JSONL 事件流存储（分支/状态/快捷选择）
    - CharacterAgent: 轻量级角色智能体（图谱画像 + LLM响应）
    - NarratorAgent: 推演中央调度器（裁定循环 + 记忆压缩）
    - HotChoicesAgent: 快捷选择生成器
    - StateAgent: 结构化状态追踪
    - TurnEvent, StateOp: 数据结构
"""

from .character_agent import CharacterAgent, CharacterProfile
from .hot_choices_agent import HotChoicesAgent
from .narrator_agent import NarratorAgent
from .simulation_store import SimulationStore, StateOp, TurnEvent, apply_state_ops
from .state_agent import StateAgent

__all__ = [
    "SimulationStore", "TurnEvent", "StateOp", "apply_state_ops",
    "CharacterAgent", "CharacterProfile",
    "NarratorAgent",
    "HotChoicesAgent",
    "StateAgent",
]
