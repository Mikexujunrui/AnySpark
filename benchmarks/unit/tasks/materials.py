"""单元层任务组：资料消化（T17-T18）+ 关键点图谱（T19）。"""

from __future__ import annotations

from benchmarks.unit.core import ApiClient


# ---------------------------------------------------------------------------
# T17 材料摘要卡结构（上传→LLM 消化→字段齐全）
# ---------------------------------------------------------------------------
def t17_material_card(api: ApiClient) -> tuple[bool, dict, str]:
    text = (
        "雾都侦探设定：主角陈渡，雾城私人侦探，习惯在深夜的码头观察来往船只。"
        "他的主要线索来源是码头工人的闲聊。雾城常年大雾，街道终年潮湿，"
        "市民称之为'雾瘴'。陈渡的搭档是法医沈青山。"
    )
    card = api.post("/api/materials", {"text": text, "title": "雾城设定", "purpose": "fact"})
    required = ("title", "topic", "key_points", "characters", "key_settings", "terms", "graph_entities")
    missing = [k for k in required if k not in card]
    topic_ok = bool(card.get("topic"))
    chars_ok = isinstance(card.get("characters"), list) and len(card["characters"]) >= 1
    points_ok = isinstance(card.get("key_points"), list) and len(card["key_points"]) >= 1
    passed = not missing and topic_ok and chars_ok and points_ok
    return (
        passed,
        {"missing_fields": missing, "topic_ok": topic_ok, "n_characters": len(card.get("characters", [])), "n_points": len(card.get("key_points", []))},
        f"topic={str(card.get('topic', ''))[:60]} | points={card.get('key_points', [])[:2]}",
    )


# ---------------------------------------------------------------------------
# T18 材料→图谱关联（摘要卡实体链接图谱——测已入库实体被正确解析关联）
# ---------------------------------------------------------------------------
def t18_material_graph_link(api: ApiClient) -> tuple[bool, dict, str]:
    # 自包含：先入库一段含哈利波特实体的文本，再测材料摘要卡→图谱关联命中
    api.post(
        "/api/graph/extract",
        {"chapter_ref": "关联测试", "text": "哈利·波特住在女贞路4号，邓布利多把他送到这里。"},
    )
    text = "角色：哈利·波特，邓布利多。地点：女贞路4号。"
    card = api.post("/api/materials", {"text": text, "title": "角色卡", "purpose": "fact"})
    linked = card.get("graph_entities", [])
    passed = isinstance(linked, list) and len(linked) >= 1
    return (
        passed,
        {"linked_ids": len(linked)},
        f"linked={linked} | material_chars={card.get('characters')}",
    )


# ---------------------------------------------------------------------------
# T19 关键点图谱草案（主线冲突/角色弧/伏笔 分类条目）
# ---------------------------------------------------------------------------
def t19_plot_draft(api: ApiClient) -> tuple[bool, dict, str]:
    points = api.post("/api/plot", {"settings": "雨夜侦探收到一封写着自己死亡时间的信，追查写信人。"})
    if not isinstance(points, list) or not points:
        return False, {"n_points": 0}, "无关键点生成"
    categories = {p.get("category", "") for p in points}
    # 应有主线冲突/角色弧等核心分类
    core = {"主线冲突", "角色弧", "伏笔"}
    hit = len(core & categories)
    passed = hit >= 1 and len(points) >= 3
    return (
        passed,
        {"n_points": len(points), "categories": sorted(categories), "core_hit": hit},
        "; ".join(p.get("content", "")[:40] for p in points[:5]),
    )
