"""
anyspark.graph.verify — 确定性校验基础（图谱比对证据）。

设计（DESIGN 模型局限弥补"不稳定 → 确定性校验"）：检测网硬伤目前全靠 LLM，
本模块提供代码级兜底的**图谱事实证据**——给定文本，找出其中出现的图谱实体
及其已知描述/关系（如"孤儿"设定 vs 图谱中该角色的父母关系 = 设定冲突证据）。
时间线顺序/伏笔匹配等完整确定性规则留后续阶段（S7 先铺证据层）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .schema import Entity, GraphStore, Relation


@dataclass
class FactEvidence:
    """文本中出现的图谱事实（供检测比对）。"""

    entity: Entity
    mentioned_by: str  # 命中的名字/别名（在文本中的写法）
    relations: list[Relation]


class GraphVerifier:
    """给定文本 → 涉及的已知图谱事实（确定性证据）。"""

    def __init__(self, graph: GraphStore) -> None:
        self._graph = graph

    def facts_for(self, book_id: str, text: str) -> list[FactEvidence]:
        """扫描文本，找出其中提到的图谱实体及其关系证据。"""
        entities = self._graph.list_entities(book_id, limit=500)
        found: list[FactEvidence] = []
        for e in entities:
            hit = _find_mention(e, text)
            if hit:
                found.append(
                    FactEvidence(
                        entity=e,
                        mentioned_by=hit,
                        relations=self._graph.relations_of(book_id, e.id),
                    )
                )
        return found

    def render_evidence(self, book_id: str, text: str, max_len: int = 400) -> str:
        """渲染证据为自然语言块（供检测网注入比对）。"""
        facts = self.facts_for(book_id, text)
        if not facts:
            return ""
        lines: list[str] = ["# 图谱已知事实（该文本涉及的实体）"]
        for f in facts:
            desc = f.entity.description[:60] if f.entity.description else ""
            lines.append(f"- {f.entity.name}（{f.entity.entity_type}）：{desc}")
            for r in f.relations[:3]:
                lines.append(f"  · {r.from_name} {r.rel_type} {r.to_name}")
        out = "\n".join(lines)
        return out[:max_len]


def _find_mention(e: Entity, text: str) -> str:
    """返回命中的名字/别名；无命中返回空串。"""
    for name in [e.name, *e.aliases]:
        if name and name in text:
            return name
    return ""
