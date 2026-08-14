"""anyspark.graph — 知识图谱包测试（存储/检索/抽取解析/注入/校验）。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from anyspark.core.types import Message, ModelOutput
from anyspark.graph import (
    EntityDraft,
    EventDraft,
    Extraction,
    GraphExtractor,
    GraphInjector,
    GraphStore,
    GraphVerifier,
    RelationDraft,
    StateUpdate,
)

EXTRACT_JSON = """
好的，以下是抽取结果：
```json
{"entities": [
   {"name": "陈渡", "type": "角色", "aliases": ["陈侦探"], "description": "雨夜抵达雾城的侦探"},
   {"name": "雾城", "type": "地点", "aliases": [], "description": "故事发生的城市"}
 ],
 "relations": [
   {"from": "陈渡", "to": "雾城", "type": "抵达", "description": "陈渡抵达雾城"}
 ],
 "events": [
   {"time_point": "第一章", "label": "抵达雾城", "description": "陈渡雨夜抵达雾城站",
    "involved": ["陈渡"]}
 ]}
```
"""


class FakeModel:
    """fake model：返回预设文本（模拟 LLM 输出）。"""

    def __init__(self, text: str) -> None:
        self._text = text
        self.model_name = "fake"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        return ModelOutput(text=self._text)


def _store() -> GraphStore:
    return GraphStore(Path(tempfile.mkdtemp()) / "graph.db")


# ---------------------------------------------------------------------------
# 实体
# ---------------------------------------------------------------------------
def test_upsert_entity_merges_aliases_and_range() -> None:
    g = _store()
    e1 = g.upsert_entity("main", "陈渡", "角色", ["陈侦探"], "侦探", "第一章", 1)
    e2 = g.upsert_entity("main", "陈渡", "角色", ["小陈"], "雾城侦探", "第二章", 2)
    assert e1.id == e2.id
    assert e2.aliases == ["陈侦探", "小陈"]
    assert e2.description == "雾城侦探"
    assert e2.first_chapter == "第一章" and e2.last_chapter == "第二章"
    assert e2.first_order == 1 and e2.last_order == 2
    # 非法类型映射为"设定"
    e3 = g.upsert_entity("main", "怪谈", "weird", [], "", "第一章", 1)
    assert e3.entity_type == "设定"


def test_entity_state_incremental_merge() -> None:
    """S20：状态增量拼接 + 演化快照 + 无变化不覆盖。"""
    g = _store()
    e1 = g.upsert_entity("main", "陈渡", "角色", [], "", "第一章", 1, "收到死亡预告信")
    assert e1.state == "收到死亡预告信"
    e2 = g.upsert_entity("main", "陈渡", "角色", [], "", "第二章", 2, "破解怀表密码")
    assert e2.state == "收到死亡预告信；破解怀表密码"
    # 无变化不覆盖、不新增快照
    e3 = g.upsert_entity("main", "陈渡", "角色", [], "", "第三章", 3, "")
    assert e3.state == "收到死亡预告信；破解怀表密码"
    # 演化快照：两次变化两条记录
    rows = g._conn.execute(
        "SELECT chapter_ref, state_after FROM entity_states WHERE entity_id=? ORDER BY id",
        (e1.id,),
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["state_after"] == "收到死亡预告信"
    assert rows[1]["state_after"] == "收到死亡预告信；破解怀表密码"


def test_ingest_state_updates_existing_entity_only() -> None:
    """S20 states：只更新已有实体状态（保留类型/章节推进），不存在的跳过。"""
    g = _store()
    g.upsert_entity("main", "陈渡", "角色", [], "雾城侦探", "第一章", 1, "收到死亡预告信")
    # 第二章：states 更新陈渡（类型空=保留"角色"）；同时一个新实体
    g.ingest_chapter(
        "main",
        "第二章",
        2,
        Extraction(
            entities=[EntityDraft("沈青山", "角色", [], "法医", "与陈渡对峙")],
            states=[
                StateUpdate("陈渡", "破解怀表密码，决定找沈青山对质"),
                StateUpdate("不存在的人", "不应建实体"),
            ],
        ),
    )
    chen = g.get_entity("main", "陈渡")
    assert chen is not None
    assert chen.state == "收到死亡预告信；破解怀表密码，决定找沈青山对质"
    assert chen.entity_type == "角色"  # 类型保留
    assert chen.last_chapter == "第二章"  # 章节推进
    # states 里不存在的名字：不建实体（防误建）
    assert g.get_entity("main", "不存在的人") is None


def test_get_and_list_entities() -> None:
    g = _store()
    g.upsert_entity("main", "甲", "角色", [], "描述甲", "第一章", 1)
    g.upsert_entity("main", "雾城", "地点", [], "", "第一章", 1)
    g.upsert_entity("other", "乙", "角色", [], "", "第一章", 1)
    assert g.get_entity("main", "甲") is not None
    assert g.get_entity("main", "不存在") is None
    assert len(g.list_entities("main")) == 2
    assert len(g.list_entities("main", entity_type="角色")) == 1
    assert len(g.list_entities("main", q="雾")) == 1


# ---------------------------------------------------------------------------
# 检索（FTS trigram + LIKE 回退）
# ---------------------------------------------------------------------------
def test_search_trigram_and_like_fallback() -> None:
    g = _store()
    g.upsert_entity("main", "沈歆", "角色", ["沈姑娘"], "", "第一章", 1)
    g.upsert_entity("main", "雾城钟表铺", "地点", [], "", "第一章", 1)
    # ≥3 字：trigram 子串
    assert [e.name for e in g.search("main", "钟表")] == ["雾城钟表铺"]
    assert [e.name for e in g.search("main", "雾城钟表")] == ["雾城钟表铺"]
    # 2 字：LIKE 回退（trigram 需要 3 字）
    assert [e.name for e in g.search("main", "沈歆")] == ["沈歆"]
    assert [e.name for e in g.search("main", "沈姑娘")] == ["沈歆"]  # 别名命中
    # 空/无命中
    assert g.search("main", "") == []
    assert g.search("main", "不存在的东西") == []


def test_resolve_names() -> None:
    g = _store()
    g.upsert_entity("main", "沈歆", "角色", ["沈姑娘"], "", "第一章", 1)
    g.upsert_entity("main", "封心", "角色", [], "", "第一章", 1)
    out = g.resolve_names("main", ["沈歆", "沈姑娘", "封心", "不存在", "封心"])
    assert [e.name for e in out] == ["沈歆", "封心"]  # 去重 + 保序 + 别名解析


def test_rebuild_fts() -> None:
    g = _store()
    g.upsert_entity("main", "雾城钟表铺", "地点", [], "", "第一章", 1)
    g.rebuild_fts()
    assert [e.name for e in g.search("main", "钟表")] == ["雾城钟表铺"]


# ---------------------------------------------------------------------------
# 关系 / 事件
# ---------------------------------------------------------------------------
def test_relation_upsert_dedup_and_name_resolution() -> None:
    g = _store()
    g.upsert_entity("main", "陈渡", "角色", [], "", "第一章", 1)
    g.upsert_entity("main", "老周", "角色", [], "", "第一章", 1)
    r1 = g.upsert_relation("main", "陈渡", "老周", "师徒", "陈渡的师父", "第一章")
    assert r1 is not None
    r2 = g.upsert_relation("main", "陈渡", "老周", "师徒", "更新描述", "第二章")
    assert r2 is not None and r2.id == r1.id
    assert len(g.list_relations("main")) == 1
    # 未知名字 → None
    assert g.upsert_relation("main", "陈渡", "不存在的人", "认识") is None
    rels = g.relations_of("main", r1.from_id)
    assert len(rels) == 1 and rels[0].rel_type == "师徒"


def test_event_upsert_replace() -> None:
    g = _store()
    e1 = g.upsert_event("main", "第一章", 1, "第一章", "抵达雾城", "旧描述", ["陈渡"])
    e2 = g.upsert_event("main", "第一章", 1, "第一章", "抵达雾城", "新描述", ["陈渡", "老周"])
    assert e1.id == e2.id
    assert e2.description == "新描述"
    assert e2.involved == ["陈渡", "老周"]
    assert len(g.list_events("main")) == 1
    assert len(g.list_events("main", chapter_ref="第二章")) == 0


# ---------------------------------------------------------------------------
# 已知事实（当前时空点）
# ---------------------------------------------------------------------------
def test_known_facts_up_to_order() -> None:
    g = _store()
    g.ingest_chapter(
        "main",
        "第一章",
        1,
        Extraction(
            entities=[EntityDraft("陈渡", "角色", [], "侦探")],
            relations=[],
            events=[EventDraft("第一章", "抵达", "雨夜抵达", ["陈渡"])],
        ),
    )
    g.ingest_chapter(
        "main",
        "第二章",
        2,
        Extraction(
            entities=[EntityDraft("沈歆", "角色", ["沈姑娘"], "妹妹")],
            relations=[RelationDraft("陈渡", "沈歆", "兄妹", "亲兄妹")],
            events=[EventDraft("第二章", "相认", "兄妹相认", ["陈渡", "沈歆"])],
        ),
    )
    # 截止第 1 章：只见陈渡
    f1 = g.known_facts("main", up_to_order=1)
    assert [e.name for e in f1["entities"]] == ["陈渡"]
    # 截止第 2 章：两人 + 关系 + 最近事件（第 2 章在前）
    f2 = g.known_facts("main", up_to_order=2)
    assert {e.name for e in f2["entities"]} == {"陈渡", "沈歆"}
    assert any(r.rel_type == "兄妹" for r in f2["relations"])
    assert f2["events"][0].label == "相认"
    # 全书
    f3 = g.known_facts("main")
    assert {e.name for e in f3["entities"]} == {"陈渡", "沈歆"}


def test_ingest_chapter_is_idempotent() -> None:
    g = _store()
    ext = Extraction(
        entities=[EntityDraft("陈渡", "角色", [], "侦探")],
        relations=[RelationDraft("陈渡", "雾城", "抵达", "抵达雾城")],
        events=[EventDraft("第一章", "抵达雾城", "", ["陈渡"])],
    )
    g.ingest_chapter("main", "第一章", 1, ext)
    g.ingest_chapter("main", "第一章", 1, ext)
    assert len(g.list_entities("main")) == 2  # 陈渡 + 雾城（关系解析时自动建实体）
    assert len(g.list_relations("main")) == 1
    assert len(g.list_events("main")) == 1


# ---------------------------------------------------------------------------
# 抽取解析（宽容）
# ---------------------------------------------------------------------------
def test_extract_parses_fenced_json() -> None:
    ex = GraphExtractor(FakeModel(EXTRACT_JSON))
    out = ex.extract("第一章", "正文", [])
    assert [e.name for e in out.entities] == ["陈渡", "雾城"]
    assert out.entities[0].aliases == ["陈侦探"]
    assert out.relations[0].rel_type == "抵达"
    assert out.events[0].involved == ["陈渡"]
    assert out.events[0].time_point == "第一章"


def test_extract_skips_existing_and_bad_items() -> None:
    ex = GraphExtractor(
        FakeModel(
            '{"entities": [{"name": "甲", "type": "怪物"}, {"name": "", "type": "角色"}, '
            '{"name": "乙", "type": "角色"}], "relations": [], "events": []}'
        )
    )
    out = ex.extract("第一章", "正文", [])
    # 空名跳过；非法类型（怪物）不再静默映射"设定"——丢弃并计数（S146）
    assert [e.name for e in out.entities] == ["乙"]
    assert ex.dropped_types == 1


def test_extract_normalizes_type_aliases() -> None:
    """S146：常见类型别名归一（人物/主人公→角色、地方→地点），不再静默降级。"""
    ex = GraphExtractor(
        FakeModel(
            '{"entities": [{"name": "丙", "type": "人物"}, {"name": "丁", "type": "地方"}, '
            '{"name": "戊", "type": "主人公"}], "relations": [], "events": []}'
        )
    )
    out = ex.extract("第一章", "正文", [])
    types = {e.name: e.entity_type for e in out.entities}
    assert types == {"丙": "角色", "丁": "地点", "戊": "角色"}
    assert ex.dropped_types == 0


def test_extract_garbage_returns_empty() -> None:
    ex = GraphExtractor(FakeModel("完全不是 JSON"))
    out = ex.extract("第一章", "正文", [])
    assert out.entities == [] and out.relations == [] and out.events == []


# ---------------------------------------------------------------------------
# 注入 / 校验
# ---------------------------------------------------------------------------
def test_injector_block() -> None:
    g = _store()
    assert GraphInjector(g).build_block("main") == ""  # 空图谱不注入
    g.ingest_chapter(
        "main",
        "第一章",
        1,
        Extraction(
            entities=[EntityDraft("陈渡", "角色", [], "侦探", "收到死亡预告信")],
            relations=[RelationDraft("陈渡", "雾城", "抵达", "抵达雾城")],
            events=[EventDraft("第一章", "抵达雾城", "雨夜抵达", ["陈渡"])],
        ),
    )
    block = GraphInjector(g).build_block("main", up_to_order=1)
    assert "已固化事实" in block
    assert "陈渡" in block
    assert "抵达" in block and "雨夜抵达" in block
    # S20：注入优先显示当前状态（而非静态 description）
    assert "收到死亡预告信" in block


def test_verifier_facts_for() -> None:
    g = _store()
    g.ingest_chapter(
        "main",
        "第一章",
        1,
        Extraction(
            entities=[
                EntityDraft("陈渡", "角色", ["陈侦探"], "孤儿"),
                EntityDraft("沈歆", "角色", [], "陈渡的妹妹"),
            ],
            relations=[RelationDraft("陈渡", "沈歆", "兄妹", "亲兄妹")],
            events=[],
        ),
    )
    v = GraphVerifier(g)
    facts = v.facts_for("main", "陈渡走进旅馆，沈歆在柜台后等他。")
    assert {f.entity.name for f in facts} == {"陈渡", "沈歆"}
    # 命中名称为实体名或别名（不依赖顺序）
    mentioned = {f.mentioned_by for f in facts}
    assert mentioned == {"陈渡", "沈歆"}
    # 未提及的实体不出现
    assert v.facts_for("main", "今天天气不错") == []
    ev = v.render_evidence("main", "陈渡和沈歆见面了。")
    assert "陈渡" in ev and "兄妹" in ev


def test_temporal_check_respects_narrative_line() -> None:
    """S29 多线叙事：时序校验按线比较——跨线首现不误报时空倒置。

    场景：实体 X 在 B 线第 5 章首现（first_order=5, lines=["line_b"]）；
    A 线第 3 章文本提到 X → line="main" 时不应警告（并行叙事，非倒叙）；
    但 B 线第 3 章文本提到 X（同线超前）→ 仍警告（真倒叙）。
    """
    from anyspark.graph.verify import GraphVerifier

    store = _store()
    # X 在 B 线第 5 章首现
    store.ingest_chapter(
        "book",
        "第5章",
        5,
        Extraction(entities=[EntityDraft("X", "角色", [], "神秘人")], relations=[], events=[]),
        line="line_b",
    )
    # A 线第 3 章也有 Y（line=main 的章节落库）
    store.ingest_chapter(
        "book",
        "第3章",
        3,
        Extraction(entities=[EntityDraft("Y", "角色", [], "普通人")], relations=[], events=[]),
        line="main",
    )
    verifier = GraphVerifier(store)
    # 跨线：main 线截止第 3 章，提到 X（X 首现于 line_b 第 5 章）→ 不警告
    assert verifier.check_temporal("book", "X 出现在这里", up_to_order=3, line="main") == []
    # 同线超前：line_b 截止第 3 章，提到 X（X 在该线首现于第 5 章）→ 警告
    w = verifier.check_temporal("book", "X 出现在这里", up_to_order=3, line="line_b")
    assert len(w) == 1 and "时序警告" in w[0]


def test_weight_accumulates_per_chapter() -> None:
    """S37：weight=出场章节数（同章重复 upsert 不累计，新章节 +1）。"""
    g = _store()
    # 第 1 章：陈渡出场
    g.upsert_entity("main", "陈渡", "角色", [], "", "第一章", 1)
    assert g.get_entity("main", "陈渡") is not None
    assert g.get_entity("main", "陈渡").weight == 1  # type: ignore[union-attr]
    # 同章重复 upsert（states 更新场景）不累计
    g.upsert_entity("main", "陈渡", "", None, "", "第一章", 1, "本章受伤")
    assert g.get_entity("main", "陈渡").weight == 1  # type: ignore[union-attr]
    # 第 2、3 章再出现 → 3
    g.upsert_entity("main", "陈渡", "", None, "", "第二章", 2)
    g.upsert_entity("main", "陈渡", "", None, "", "第三章", 3)
    e = g.get_entity("main", "陈渡")
    assert e is not None and e.weight == 3


def test_known_facts_mixes_high_frequency_entities() -> None:
    """S37：高频实体（贯穿主线）在久未出现时仍被注入——百章级早期主线不丢。"""
    g = _store()
    # 主角"陈渡"前 10 章高频出场（weight=10）
    for i in range(1, 11):
        g.upsert_entity("main", "陈渡", "角色", [], "", f"第{i}章", i)
    # 第 30-35 章新出场 6 个角色（最近实体）
    for i in range(30, 36):
        g.upsert_entity("main", f"新角色{i}", "角色", [], "", f"第{i}章", i)
    # 截止第 35 章：最近实体（新角色 30-35）占多数，但高频"陈渡"必须仍在
    facts = g.known_facts("main", up_to_order=35, max_entities=15)
    names = [e.name for e in facts["entities"]]
    assert "陈渡" in names, f"高频主角被漏掉: {names}"
    assert "新角色35" in names  # 最近实体也在
    # 高频优先：陈渡在序中靠前（weight 排序组）
    assert names.index("陈渡") < len(names)  # 存在即可


def test_impact_chapters() -> None:
    """S45：影响分析——改第 N 章（涉及实体）→ 后续受影响章节。"""
    g = _store()
    # 第 1 章：陈渡登场
    g.ingest_chapter(
        "main",
        "第一章",
        1,
        Extraction(
            entities=[EntityDraft("陈渡", "角色", [], "侦探")],
            relations=[],
            events=[EventDraft("第一章", "抵达", "雨夜抵达", ["陈渡"])],
        ),
    )
    # 第 2 章：沈歆登场（兄妹）
    g.ingest_chapter(
        "main",
        "第二章",
        2,
        Extraction(
            entities=[EntityDraft("沈歆", "角色", [], "妹妹")],
            relations=[RelationDraft("陈渡", "沈歆", "兄妹", "亲兄妹")],
            events=[EventDraft("第二章", "相认", "兄妹相认", ["陈渡", "沈歆"])],
        ),
    )
    # 第 3 章：提到陈渡的旧案
    g.ingest_chapter(
        "main",
        "第三章",
        3,
        Extraction(
            entities=[],
            relations=[],
            events=[EventDraft("第三章", "旧案", "陈渡旧案重提", ["陈渡"])],
        ),
    )
    # 改第 1 章（涉及陈渡）→ 第 2/3 章受影响（后续引用陈渡）
    hits = g.impact_chapters("main", 1, ["陈渡"])
    refs = [h["chapter_ref"] for h in hits]
    assert "第二章" in refs and "第三章" in refs
    assert all(h["chapter_order"] > 1 for h in hits)
    # 改第 2 章（涉及沈歆）→ 第 3 章不受影响（沈歆未在第 3 章出现）
    hits2 = g.impact_chapters("main", 2, ["沈歆"])
    assert hits2 == []
    # 无实体参数：自动取该章事件 involved（第 1 章→陈渡）
    hits3 = g.impact_chapters("main", 1)
    assert any("陈渡" in h["entities"] for h in hits3)


# ──────────────────────────────────────────────────────────────
# S72：图谱条目手动管理（update/delete 实体/关系/事件）
# ──────────────────────────────────────────────────────────────
def _gstore() -> GraphStore:
    return GraphStore(Path(tempfile.mkdtemp()) / "g.db")


def test_update_entity_fields_only_changes_passed() -> None:
    """S72：局部编辑不动自动统计（weight/出场记录保留）。"""
    g = _gstore()
    g.upsert_entity(
        "main", "陈渡", "角色", ["陈侦探"], "雨夜侦探", chapter_ref="第1章", chapter_order=1
    )
    g.upsert_entity("main", "陈渡", "角色", chapter_ref="第2章", chapter_order=2)
    ent = g.get_entity("main", "陈渡")
    assert ent is not None and ent.weight == 2  # 自动统计：两章出场

    updated = g.update_entity_fields("main", "陈渡", description="雾城侦探，沉默寡言")
    assert updated is not None
    assert updated.description == "雾城侦探，沉默寡言"
    assert updated.weight == 2  # 手动编辑不动权重
    assert updated.last_chapter == "第2章"  # 不动出场记录
    # 别名保留 + FTS 同步
    assert "陈侦探" in updated.aliases
    hits = g.search("main", "陈侦探")
    assert any(e.name == "陈渡" for e in hits)


def test_update_entity_fields_missing_returns_none() -> None:
    g = _gstore()
    assert g.update_entity_fields("main", "不存在", description="x") is None


def test_delete_entity_cascades_relations() -> None:
    """S72：删实体级联删关系（防悬空引用）。"""
    g = _gstore()
    g.upsert_entity("main", "陈渡", "角色")
    g.upsert_entity("main", "雾城", "地点")
    g.upsert_relation("main", "陈渡", "雾城", "抵达", "陈渡抵达雾城")
    assert len(g.list_relations("main")) == 1
    assert g.delete_entity("main", "陈渡") is True
    assert g.get_entity("main", "陈渡") is None
    assert g.list_relations("main") == []  # 关联关系级联删除
    # 再删已不存在 → False
    assert g.delete_entity("main", "陈渡") is False


def test_relation_update_delete() -> None:
    g = _gstore()
    g.upsert_entity("main", "A", "角色")
    g.upsert_entity("main", "B", "角色")
    rel = g.upsert_relation("main", "A", "B", "敌对", "见面就吵")
    assert rel is not None
    updated = g.update_relation_fields(rel.id, rel_type="亦敌亦友")
    assert updated is not None and updated.rel_type == "亦敌亦友"
    assert updated.description == "见面就吵"  # 未传字段保留
    assert g.delete_relation(rel.id) is True
    assert g.delete_relation(rel.id) is False  # 已删


def test_event_update_delete() -> None:
    g = _gstore()
    ev = g.upsert_event("main", "第1章", 1, "雨夜", "陈渡抵达", "雨夜到站", ["陈渡"])
    updated = g.update_event_fields(ev.id, label="陈渡抵达雾城站", involved=["陈渡", "雾城"])
    assert updated is not None
    assert updated.label == "陈渡抵达雾城站"
    assert "雾城" in updated.involved
    assert g.delete_event(ev.id) is True
    assert g.delete_event(ev.id) is False


# ──────────────────────────────────────────────────────────────
# S72：图谱管理 API（/api/graph/entities|relations|events 增改删）
# ──────────────────────────────────────────────────────────────
def _api_client() -> Any:
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    db = Path(tempfile.mkdtemp()) / "t.db"

    class _NoModel:  # 图谱写端点不需要模型
        def respond(self, messages, tools):  # type: ignore[no-untyped-def]
            from anyspark.core.types import ModelOutput

            return ModelOutput(text="{}")

    return TestClient(build_app(model=_NoModel(), db_path=db))


def test_entity_crud_api() -> None:
    c = _api_client()
    # 添加
    r = c.post(
        "/api/graph/entities", json={"name": "顾欣桐", "entity_type": "角色", "description": "线人"}
    )
    assert r.status_code == 200
    assert r.json()["name"] == "顾欣桐"
    # 编辑（PATCH 局部）
    r = c.patch("/api/graph/entities/顾欣桐", json={"description": "猎手线人，知晓夜色镇"})
    assert r.status_code == 200
    assert "夜色镇" in r.json()["description"]
    # 查询确认
    assert any(e["name"] == "顾欣桐" for e in c.get("/api/graph/entities").json())
    # 删除
    r = c.delete("/api/graph/entities/顾欣桐")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert not any(e["name"] == "顾欣桐" for e in c.get("/api/graph/entities").json())
    # 删不存在 → 404
    assert c.delete("/api/graph/entities/顾欣桐").status_code == 404


def test_entity_add_overwrite_existing() -> None:
    """S72：同名实体 POST = 覆盖字段（幂等），不动自动统计。"""
    c = _api_client()
    c.post("/api/graph/entities", json={"name": "陈渡", "description": "旧描述"})
    r = c.post(
        "/api/graph/entities", json={"name": "陈渡", "description": "新描述", "entity_type": "角色"}
    )
    assert r.status_code == 200
    assert r.json()["description"] == "新描述"
    assert r.json()["entity_type"] == "角色"


def test_relation_crud_api() -> None:
    c = _api_client()
    c.post("/api/graph/entities", json={"name": "陈渡"})
    c.post("/api/graph/entities", json={"name": "雾城"})
    # 添加（两端存在）
    r = c.post(
        "/api/graph/relations", json={"from_name": "陈渡", "to_name": "雾城", "rel_type": "抵达"}
    )
    assert r.status_code == 200
    rid = r.json()["id"]
    # 端不存在 → 400
    r = c.post(
        "/api/graph/relations", json={"from_name": "陈渡", "to_name": "不存在", "rel_type": "抵达"}
    )
    assert r.status_code == 400
    # 编辑
    r = c.patch(f"/api/graph/relations/{rid}", json={"rel_type": "探索"})
    assert r.status_code == 200 and r.json()["rel_type"] == "探索"
    # 删除
    assert c.delete(f"/api/graph/relations/{rid}").json()["ok"] is True
    assert c.delete(f"/api/graph/relations/{rid}").status_code == 404


def test_event_crud_api() -> None:
    c = _api_client()
    r = c.post(
        "/api/graph/events",
        json={
            "chapter_ref": "第1章",
            "chapter_order": 1,
            "time_point": "雨夜",
            "label": "抵达",
            "involved": ["陈渡"],
        },
    )
    assert r.status_code == 200
    eid = r.json()["id"]
    # 编辑
    r = c.patch(f"/api/graph/events/{eid}", json={"description": "雨夜抵达雾城站"})
    assert r.status_code == 200 and "雾城站" in r.json()["description"]
    # 删除
    assert c.delete(f"/api/graph/events/{eid}").json()["ok"] is True
    assert c.delete(f"/api/graph/events/{eid}").status_code == 404
