"""
anyspark.explore.strategy — 探索策略集（主 Agent 定义差异化分派）。

设计（DESIGN 机制 7）：多样性不自动保证——主 Agent 先定义探索策略集，
每个探索者拿不同维度指令（按叙事维度/模板/自由/用户指导分派）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .direction import DEFAULT_DIMENSIONS, DirectionCard, Source

# 探索者固定分派映射（供 card 标注维度/来源；探索者不知道自己维度，避免自证偏见）
_EXPLORER_MIX: list[Source] = ["template", "grow", "user", "template"]


def _explorer_source(index: int) -> Source:
    return _EXPLORER_MIX[index % len(_EXPLORER_MIX)]


def extract_json_dict(text: str) -> dict[str, Any]:
    """宽容地从模型输出中提取第一个 JSON 对象。"""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(cleaned[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {}


@dataclass
class ExplorationStrategy:
    """一次探索的分派策略：每个探索者一个差异化指令。"""

    seed: str
    intent_confirmed: dict[str, Any]  # 意图理解者的对齐确认
    constraints: list[str] = field(default_factory=list)  # 已固化设定约束（不得撞墙）
    dimensions: list[str] = field(default_factory=lambda: list(DEFAULT_DIMENSIONS))
    mix: list[Source] = field(default_factory=lambda: list(_EXPLORER_MIX))

    def assign(self, index: int) -> tuple[str, Source]:
        """给第 index 个探索者分派（维度 + 来源）。"""
        dim = self.dimensions[index % len(self.dimensions)]
        src = self.mix[index % len(self.mix)]
        return dim, src

    def explorer_prompt(self, index: int) -> str:
        """构造第 index 个探索者的指令（轻量上下文）。"""
        dim, src = self.assign(index)
        concept = self.intent_confirmed.get("concept", {})
        concept_text = (
            f"种子：{self.seed}\n"
            f"概念：{concept.get('core', '')}（基调：{concept.get('mood', '')}，"
            f"类型直觉：{concept.get('genre', '')}）"
        )
        constraint_block = ""
        if self.constraints:
            constraint_block = "\n已固化设定约束（必须避开，不得冲突）：\n- " + "\n- ".join(
                self.constraints
            )
        source_desc = {
            "template": "从成熟叙事模板/流派套路派生一个方向（用流派术语标注）",
            "grow": "完全从种子+作品内在逻辑自然生长，不走模板，追求原创",
            "user": "用户脑中非常规约束/直觉直接作为方向（如'没有情节只有氛围'）",
        }[src]
        return (
            f"你是小说创作方向探索者。任务：从「{dim}」维度出发，{source_desc}。\n\n"
            f"{concept_text}{constraint_block}\n\n"
            "产出方向卡（严格 JSON）：\n"
            '{"title": "方向标题", "summary": "方向说明(2-3句，明确可执行)", '
            '"term": "流派术语标注（如废柴流开局·反差铺垫，无则空串）"}'
        )

    def card_from_response(self, index: int, raw: str) -> DirectionCard:
        """把探索者返回的 JSON 解析成方向卡（含维度/来源标注）。"""
        data = extract_json_dict(raw)
        dim, src = self.assign(index)
        return DirectionCard(
            title=str(data.get("title", f"方向 {index + 1}")),
            summary=str(data.get("summary", "")),
            dimension=dim,
            source=src,
            term=str(data.get("term", "")),
        )
