"""
AnySpark v4 — S7 真实链路冒烟：章节 → LLM 实体抽取 → 图谱入库 → 当前时空点注入 → 检索。

运行：uv run python scripts/graph_smoke.py
需要：.env 配置 DEEPSEEK_API_KEY（真实 DeepSeek）
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from dotenv import load_dotenv

from anyspark.graph import GraphExtractor, GraphInjector, GraphStore, GraphVerifier
from anyspark.models.deepseek import DeepSeekModel

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

CHAPTER = """雨夜，陈渡抵达雾城站。他拎着旧皮箱走进站前旅馆，柜台后的老板娘抬头看了他一眼。
"一间房。"陈渡说。老板娘递来钥匙："三楼最里面那间，以前住过一位警察。"
陈渡接过钥匙，指尖顿了一下。三楼最里面——二十年前，他的父亲就死在那个房间。
次日清晨，陈渡去了城西的钟表铺。铺主老周是父亲的老友，见到他先是一愣，随后叹了口气：
"你长得越来越像他了。"陈渡没有接话，只问："那块怀表，还在吗？"
老周从柜台下摸出一块锈迹斑斑的怀表，表盖内侧刻着一个名字：沈青山。"""


def main() -> None:
    model = DeepSeekModel()
    graph = GraphStore(Path(tempfile.mkdtemp()) / "graph.db")
    extractor = GraphExtractor(model)
    injector = GraphInjector(graph)
    verifier = GraphVerifier(graph)
    print(f"模型: {model.model_name}\n")

    print("== 1. 实体抽取（真实 DeepSeek）==")
    existing = [e.to_dict() for e in graph.list_entities("main")]
    ext = extractor.extract("第一章", CHAPTER, existing)
    print(f"  实体 {len(ext.entities)} / 关系 {len(ext.relations)} / 事件 {len(ext.events)}")
    for e in ext.entities:
        print(f"  - {e.name} [{e.entity_type}] {e.description[:50]}")
    for r in ext.relations:
        print(f"  ~ {r.from_name} {r.rel_type} {r.to_name}")

    print("\n== 2. 图谱入库（幂等）==")
    graph.ingest_chapter("main", "第一章", 1, ext)
    graph.ingest_chapter("main", "第一章", 1, ext)
    print(
        f"  库内 实体{len(graph.list_entities('main'))} "
        f"关系{len(graph.list_relations('main'))} 事件{len(graph.list_events('main'))}"
    )

    print("\n== 3. 当前时空点注入块 ==")
    block = injector.build_block("main", up_to_order=1)
    print(block if block else "  （空图谱，无注入）")

    print("\n== 4. FTS 检索 ==")
    for q in ("陈渡", "钟表铺", "沈青山"):
        hits = graph.search("main", q)
        print(f"  搜'{q}': {[e.name for e in hits]}")

    print("\n== 5. 确定性校验证据（图谱比对）==")
    text = "陈渡走进旅馆，老周在柜台后等他。"
    facts = verifier.facts_for("main", text)
    print(f"  文本涉及 {len(facts)} 个已知实体")
    for f in facts:
        print(f"  - {f.entity.name}（{f.entity.entity_type}）{f.entity.description[:40]}")


if __name__ == "__main__":
    main()
