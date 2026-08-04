"""
anyspark.graph.inject — 当前时空点已知事实注入（写作时）。

设计（DESIGN §8.3 + 模型局限弥补"记不住长篇小说事实"）：写作第 N 章时，
把"当前时空点（≤N 章）已知事实"检索注入：最近出现实体 + 其间关系 + 最近事件。
省 token（注入摘要而非全量图谱）、防串书（实体带类型）、模型无关（纯自然语言）。
复刻 align 注入器模式（build_system_block → 拼进系统提示）。
"""

from __future__ import annotations

from .schema import GraphStore

MAX_ENTITIES = 15
MAX_RELATIONS = 20
MAX_EVENTS = 8


class GraphInjector:
    """把图谱已知事实渲染成自然语言注入块。"""

    def __init__(self, graph: GraphStore) -> None:
        self._graph = graph

    def build_block(self, book_id: str = "main", up_to_order: int | None = None) -> str:
        """当前时空点已知事实（无事实返回空串，不注入）。"""
        facts = self._graph.known_facts(
            book_id,
            up_to_order=up_to_order,
            max_entities=MAX_ENTITIES,
            max_relations=MAX_RELATIONS,
            max_events=MAX_EVENTS,
        )
        lines: list[str] = []
        if facts["entities"]:
            lines.append("# 已固化事实（知识图谱）")
            for e in facts["entities"]:
                # S20：优先显示截至当前时空点的状态（角色/地点随时间演化），无状态退回静态描述
                note = (e.state or e.description or "")[:120]
                lines.append(f"- {e.name}（{e.entity_type}）{('：' + note) if note else ''}")
        if facts["relations"]:
            lines.append("实体关系：")
            for r in facts["relations"]:
                desc = f"（{r.description[:60]}）" if r.description else ""
                lines.append(f"- {r.from_name} {r.rel_type} {r.to_name}{desc}")
        if facts["events"]:
            lines.append("最近事件：")
            for ev in facts["events"]:
                desc = f"（{ev.description[:60]}）" if ev.description else ""
                lines.append(f"- {ev.time_point or ev.chapter_ref}：{ev.label}{desc}")
        if not lines:
            return ""
        return "\n".join(lines)
