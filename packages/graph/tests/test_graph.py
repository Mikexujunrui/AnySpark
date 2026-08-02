"""anyspark.graph — 知识图谱包测试（存储/检索/抽取解析/注入/校验）。"""

from __future__ import annotations

import tempfile
from pathlib import Path

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
    # 空名跳过；非法类型映射"设定"
    assert [e.name for e in out.entities] == ["甲", "乙"]
    assert out.entities[0].entity_type == "设定"


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
            entities=[EntityDraft("陈渡", "角色", [], "侦探")],
            relations=[RelationDraft("陈渡", "雾城", "抵达", "抵达雾城")],
            events=[EventDraft("第一章", "抵达雾城", "雨夜抵达", ["陈渡"])],
        ),
    )
    block = GraphInjector(g).build_block("main", up_to_order=1)
    assert "已固化事实" in block
    assert "陈渡" in block and "侦探" in block
    assert "抵达" in block and "雨夜抵达" in block


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
