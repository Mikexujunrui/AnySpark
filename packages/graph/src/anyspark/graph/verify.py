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

    def check_temporal(
        self, book_id: str, text: str, up_to_order: int, line: str = "main"
    ) -> list[str]:
        """时序校验（确定性规则）：文本中提及的实体若在当前**叙事线**中首次出现于
        更晚的章节（first_order > up_to_order 且该线在实体 lines 中），提示"时空倒置"。

        S29 多线叙事：跨线首现不警告——A 线第 3 章提到 B 线第 5 章才首现的角色
        是并行叙事（时间差正常），不是倒叙。仅同线内 first_order 超前才报警。
        """
        warnings: list[str] = []
        entities = self._graph.list_entities(book_id, limit=500)
        for e in entities:
            if e.first_order > up_to_order and e.name in text and line in e.lines:
                warnings.append(
                    f"时序警告：{e.name}（{e.entity_type}）在{line}线首次出现于"
                    f"{e.first_chapter}，而当前是截止第 {up_to_order} 章的时空点——"
                    "它此刻还不该登场（如确需提及，请确认是否为倒叙/回忆）。"
                )
        return warnings


def _find_mention(e: Entity, text: str) -> str:
    """返回命中的名字/别名；无命中返回空串。"""
    for name in [e.name, *e.aliases]:
        if name and name in text:
            return name
    return ""
