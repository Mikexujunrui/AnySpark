"""
anyspark.server.tools_graph — 图谱查证/登记工具（从 tools_domain.py 拆出，S188 技术债清理）。

工厂函数创建 agent 工具（ToolSpec + implementer 对），接收 store 参数，
不引用闭包——从 tools_domain.py 提取无行为变化。
"""

from __future__ import annotations

from typing import Any

from anyspark.core import ToolCall
from anyspark.core.protocol import ParamSpec, ToolResult, ToolSpec

_QUERY_LIMIT = 10


_RELATION_LIMIT = 15


def make_graph_query_implementer(graph: Any, book_id: str = "main") -> tuple[Any, Any]:
    """图谱查询工具：查实体（含当前状态）/关系/事件，写作前查证用。"""

    spec = ToolSpec(
        name="graph_query",
        description=(
            "查询知识图谱：按关键词/名字查实体（角色/地点/事件/物件/设定，含当前状态）、"
            "实体间关系、时间线事件。写作前需要确认某人/某地/某设定的已知信息时使用"
            "（图谱不常驻注入——早期设定/角色状态主动查，避免漏设定）。"
        ),
        params=[
            ParamSpec(
                name="query",
                type="string",
                required=True,
                description="关键词/实体名（可模糊匹配，如'陈渡'、'雾城'）",
            )
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        q = str(arguments.get("query", "")).strip()
        if not q:
            return ToolResult(call=call, ok=False, content="缺少参数 query。")
        try:
            entities = graph.list_entities(book_id, q=q, limit=_QUERY_LIMIT)
            if not entities:
                return ToolResult(call=call, ok=False, content=f"图谱中未找到与「{q}」相关的实体。")
            names = [e.name for e in entities]
            lines = [f"图谱中与「{q}」相关的实体（{len(entities)} 个）："]
            for e in entities:
                state = getattr(e, "state", "") or ""
                desc = getattr(e, "description", "") or ""
                line = f"- {e.name}（{e.entity_type}）"
                # S157：不截断——graph_query 是写作前精确查证工具，返回实体少（关键词过滤），
                # 状态/描述全量注入避免 agent 漏关键设定（8-15 截断审查：写全了却截断没道理）
                if state:
                    line += f" 当前状态：{state}"
                elif desc:
                    line += f" {desc}"
                lines.append(line)
            # 相关关系（实体参与的三元组）
            relations = graph.list_relations(book_id, limit=_RELATION_LIMIT)
            rels = [r for r in relations if r.from_name in names or r.to_name in names][
                :_RELATION_LIMIT
            ]
            if rels:
                lines.append(f"相关关系（{len(rels)} 条）：")
                lines.extend(f"- {r.from_name} —{r.rel_type}→ {r.to_name}" for r in rels)
            return ToolResult(
                call=call,
                ok=True,
                content="\n".join(lines),
                data={"names": names},
            )
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"图谱查询失败：{exc}")

    return spec, implementer


def make_graph_register_implementer(graph: Any, book_id: str = "main") -> tuple[Any, Any]:
    """S72：图谱登记工具——对话中"把XX记进图谱"→ 立即登记实体（+可选关系）。

    对齐 mind_register（用户主动登记模式）：抽取会错/会漏，用户明确表述的设定
    应即时落库（source=user 高置信度），不依赖自动抽取。只登记不删除
    （删除走 API，内容裁决权在用户）。
    """

    spec = ToolSpec(
        name="graph_register",
        description=(
            "把用户明确表述的设定/角色/关系登记进知识图谱。"
            "当用户在对话中明确陈述设定（如'顾欣桐是赵光离的线人''雾城是边境城市'）"
            "或纠正图谱错误时使用。登记后写作时图谱注入会自动包含。"
            "只记事实（谁是谁/世界规则/关系）；剧情承诺/伏笔（'埋了线索待回收'）用"
            "plot_register，不要两处重复登记。"
        ),
        params=[
            ParamSpec(
                name="name",
                type="string",
                required=True,
                description="实体名（角色/地点/物件/设定）",
            ),
            ParamSpec(
                name="entity_type",
                type="string",
                required=False,
                description="类型：角色/地点/事件/物件/设定（缺省 设定）",
            ),
            ParamSpec(
                name="description",
                type="string",
                required=False,
                description="实体描述（自然语言）",
            ),
            ParamSpec(
                name="rel_to",
                type="string",
                required=False,
                description="关联的另一实体名（可选，同时登记关系时给）",
            ),
            ParamSpec(
                name="rel_type",
                type="string",
                required=False,
                description="关系类型（如 师父/线人/敌对；rel_to 有值时生效）",
            ),
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        name = str(arguments.get("name", "")).strip()
        if not name:
            return ToolResult(call=call, ok=False, content="缺少参数 name。")
        etype = str(arguments.get("entity_type", "设定")).strip() or "设定"
        desc = str(arguments.get("description", "")).strip()
        rel_to = str(arguments.get("rel_to", "")).strip()
        rel_type = str(arguments.get("rel_type", "")).strip()
        try:
            ent = graph.get_entity(book_id, name)
            if ent is None:
                graph.upsert_entity(book_id, name, etype, description=desc)
            elif desc:
                graph.update_entity_fields(book_id, name, description=desc, entity_type=etype)
            lines = [f"已登记实体：{name}（{etype}）"]
            if rel_to and rel_type:
                rel = graph.upsert_relation(book_id, name, rel_to, rel_type, description=desc)
                if rel is None:
                    lines.append(f"关系未登记：{rel_to} 不存在（先登记该实体）")
                else:
                    lines.append(f"已登记关系：{name} —{rel_type}→ {rel_to}")
            return ToolResult(
                call=call,
                ok=True,
                content="\n".join(lines),
                data={"entity": name, "type": etype},
            )
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"登记失败：{exc}")

    return spec, implementer
