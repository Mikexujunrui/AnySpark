# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Foreshadow Network — DAG-based multi-relationship foreshadowing engine.

Extends the simple 1:1 foreshadow matcher in ``foreshadow_matcher.py``
with a full directed-acyclic-graph model where:

- One foreshadow can hint at multiple payoffs (e.g. a judgment poem
  predicting multiple character fates).
- One payoff can resolve multiple foreshadows.
- Foreshadows can amplify each other (chain/stack).
- Each edge has a strength weight and optional evidence text.

Pure-Python data model with Neo4j persistence for the graph.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ForeshadowType(StrEnum):
    """Types of foreshadowing devices."""
    PROPHECY_POEM = "prophecy_poem"          # 判词/曲/签诗/酒令
    DIALOGUE_HINT = "dialogue_hint"          # 对话中的暗示
    BEHAVIOR_SYMBOL = "behavior_symbol"      # 象征性行为
    OBJECT_SYMBOL = "object_symbol"          # 物品象征（信物/法器/宝物等）
    DREAM_OMEN = "dream_omen"               # 托梦/预感
    NAMED_OMEN = "named_omen"              # 名字谐音
    EVENT_FORESHADOW = "event_foreshadow"   # 事件铺垫
    CONTEXTUAL_HINT = "contextual_hint"      # 环境/景物暗示


class EdgeType(StrEnum):
    """Foreshadow network edge types."""
    HINTS_AT = "HINTS_AT"                   # 伏笔→暗示的结局
    INVOLVES = "INVOLVES"                    # 伏笔→关联实体
    PAID_OFF_BY = "PAID_OFF_BY"             # 伏笔→被某回收节点回收
    AMPLIFIES = "AMPLIFIES"                 # 伏笔A→加强伏笔B
    RESOLVES_IN = "RESOLVES_IN"             # 伏笔→应回收的章节
    CONTRASTS = "CONTRASTS"                 # 伏笔A→伏笔B (对比关系)


# ── Neo4j Schema helpers ────────────────────────────────────────────────

FORESHADOW_NODE_LABELS = {
    "foreshadow": "Foreshadow",
    "payoff": "Payoff",
}

# Relationship types to register in graph_schema.py
FORESHADOW_REL_TYPES: list[str] = [
    "HINTS_AT",
    "PAID_OFF_BY",
    "AMPLIFIES",
    "RESOLVES_IN",
    "CONTRASTS",
]


@dataclass
class ForeshadowNode:
    """伏笔节点——在 Neo4j 中作为一个实体存储。"""
    id: str
    type: ForeshadowType
    description: str
    source_chapter: int                     # 埋设章节
    linked_entities: list[str]              # 关联的角色/物品ID
    hints_at_outcomes: list[str]            # 暗示的结局描述
    confidence: float = 1.0                 # 0-1, 证据强度
    project_id: str = "default"

    def to_neo4j_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "entity_type": "foreshadow",
            "foreshadow_type": self.type.value,
            "name": self.description[:80],
            "data": {
                "description": self.description,
                "source_chapter": self.source_chapter,
                "linked_entities": self.linked_entities,
                "hints_at_outcomes": self.hints_at_outcomes,
                "confidence": self.confidence,
            },
            "project_id": self.project_id,
        }


@dataclass
class PayoffNode:
    """回收节点——在 Neo4j 中作为一个实体存储。"""
    id: str
    chapter: int
    description: str
    related_foreshadows: list[str]          # 回收了哪些伏笔的ID
    project_id: str = "default"

    def to_neo4j_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "entity_type": "payoff",
            "name": f"回收于第{self.chapter}章: {self.description[:40]}",
            "data": {
                "description": self.description,
                "chapter": self.chapter,
                "related_foreshadows": self.related_foreshadows,
            },
            "project_id": self.project_id,
        }


@dataclass
class ForeshadowEdge:
    """伏笔→回收的边（多对多）。"""
    foreshadow_id: str
    target_id: str                          # Payoff ID 或其他 Foreshadow ID
    edge_type: EdgeType = EdgeType.PAID_OFF_BY
    strength: float = 1.0                   # 0-1, 匹配强度
    evidence: str = ""                      # 文本证据（批注/评论/原文暗示）


@dataclass
class ForeshadowNetwork:
    """完整伏笔网络的概要数据。"""
    book_id: str = ""
    foreshadow_count: int = 0
    payoff_count: int = 0
    unresolved_count: int = 0                # 未收伏笔数
    network_density: float = 0.0             # 网络密度
    foreshadow_nodes: list[ForeshadowNode] = field(default_factory=list)
    payoff_nodes: list[PayoffNode] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "book_id": self.book_id,
            "foreshadow_count": self.foreshadow_count,
            "payoff_count": self.payoff_count,
            "unresolved_count": self.unresolved_count,
            "network_density": round(self.network_density, 4),
        }

    def to_prompt_fragment(self) -> str:
        """生成伏笔约束注入文本。"""
        if not self.book_id:
            return ""
        lines = ["## 伏笔网络约束"]
        open_nodes = [f for f in self.foreshadow_nodes
                      if not any(f.id in p.related_foreshadows for p in self.payoff_nodes)]
        lines.append(f"开放伏笔: {len(open_nodes)} 个待回收")
        if open_nodes[:5]:
            lines.append("待回收伏笔:")
            for f in open_nodes[:5]:
                lines.append(f"  - [{f.type.value}] {f.description[:60]}")
        lines.append(f"已回收: {self.payoff_count} 个节点")
        if self.network_density > 0:
            lines.append(f"伏笔网络密度: {self.network_density:.3f}")
        return "\n".join(lines)


# ── Helper functions ───────────────────────────────────────────────────


def get_outgoing_payoff_pairs(
    foreshadow_id: str,
    edges: list[ForeshadowEdge],
    payoffs: list[PayoffNode],
) -> list[tuple[ForeshadowEdge, PayoffNode]]:
    """获取一个伏笔的所有回收配对。"""
    result = []
    payoff_map = {p.id: p for p in payoffs}
    for edge in edges:
        if edge.foreshadow_id == foreshadow_id and edge.target_id in payoff_map:
            result.append((edge, payoff_map[edge.target_id]))
    return result


def get_foreshadows_for_payoff(
    payoff_id: str,
    edges: list[ForeshadowEdge],
    foreshadows: list[ForeshadowNode],
) -> list[tuple[ForeshadowEdge, ForeshadowNode]]:
    """获取一个回收节点关联的所有伏笔。"""
    result = []
    fs_map = {f.id: f for f in foreshadows}
    for edge in edges:
        if edge.target_id == payoff_id and edge.foreshadow_id in fs_map:
            result.append((edge, fs_map[edge.foreshadow_id]))
    return result


def find_unresolved_foreshadows(
    foreshadows: list[ForeshadowNode],
    payoffs: list[PayoffNode],
    edges: list[ForeshadowEdge],
) -> list[ForeshadowNode]:
    """找出所有尚未被回收的伏笔。"""
    resolved_ids = set()
    for edge in edges:
        if edge.edge_type == EdgeType.PAID_OFF_BY:
            resolved_ids.add(edge.foreshadow_id)
    return [f for f in foreshadows if f.id not in resolved_ids]


# ── Persistence (JSON file based, supplements Neo4j) ───────────────────

FNW_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "foreshadow_network"


def _ensure_dir():
    FNW_DATA_DIR.mkdir(parents=True, exist_ok=True)


def save_network(book_id: str, network: ForeshadowNetwork) -> None:
    """Save foreshadow network to JSON cache."""
    _ensure_dir()
    path = FNW_DATA_DIR / f"{book_id}.json"
    data = {
        "book_id": book_id,
        "foreshadows": [f.to_neo4j_dict() for f in network.foreshadow_nodes],
        "payoffs": [p.to_neo4j_dict() for p in network.payoff_nodes],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_network(book_id: str) -> ForeshadowNetwork | None:
    """Load foreshadow network from JSON cache."""
    path = FNW_DATA_DIR / f"{book_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        foreshadows = [ForeshadowNode(
            id=f["id"],
            type=ForeshadowType(f.get("data", {}).get("foreshadow_type", "event_foreshadow")),
            description=f.get("data", {}).get("description", ""),
            source_chapter=f.get("data", {}).get("source_chapter", 0),
            linked_entities=f.get("data", {}).get("linked_entities", []),
            hints_at_outcomes=f.get("data", {}).get("hints_at_outcomes", []),
            confidence=f.get("data", {}).get("confidence", 1.0),
            project_id=f.get("project_id", "default"),
        ) for f in data.get("foreshadows", [])]
        payoffs = [PayoffNode(
            id=p["id"],
            chapter=p.get("data", {}).get("chapter", 0),
            description=p.get("data", {}).get("description", ""),
            related_foreshadows=p.get("data", {}).get("related_foreshadows", []),
            project_id=p.get("project_id", "default"),
        ) for p in data.get("payoffs", [])]
        return ForeshadowNetwork(
            book_id=book_id,
            foreshadow_count=len(foreshadows),
            payoff_count=len(payoffs),
            unresolved_count=len(find_unresolved_foreshadows(foreshadows, payoffs, [])),
            foreshadow_nodes=foreshadows,
            payoff_nodes=payoffs,
        )
    except Exception as e:
        logger.warning("Failed to load foreshadow network %s: %s", book_id, e)
        return None
