"""Check extraction results."""
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.graph_store import get_store

BOOK_ID = "1781418567324"
store = get_store(BOOK_ID)

entities = store.list_entities()
relations = store.list_relations()
fores = store.list_foreshadows()
tl_events = store.list_timeline_events()

print("=== 当前知识库状态 ===")
print(f"实体: {len(entities)}")
print(f"关系: {len(relations)}")
print(f"伏笔: {len(fores)}")
print(f"时间线: {len(tl_events)}")

# Entity types
type_counts = Counter(e.type for e in entities)
print("\n实体类型分布:")
for t, c in type_counts.most_common():
    print(f"  {t}: {c}")

# Relation types
rel_types = Counter(r.type.upper() for r in relations)
print("\n关系类型分布:")
for t, c in rel_types.most_common():
    print(f"  {t}: {c}")

# Foreshadow statuses
open_fs = [f for f in fores if f.status == "open"]
resolved_fs = [f for f in fores if f.status == "resolved"]
dangling_fs = [f for f in fores if f.status == "dangling"]
extracted_count = sum(1 for f in fores if f.source == "extracted")
planted_count = sum(1 for f in fores if f.source == "planted")
has_plant = sum(1 for f in fores if f.plant_chapter)
has_kw = sum(1 for f in fores if f.resolve_keywords)
has_conf = sum(1 for f in fores if f.confidence != "high")

print(f"\n伏笔状态: {len(open_fs)}待回收, {len(resolved_fs)}已回收, {len(dangling_fs)}悬置")
print(f"伏笔来源: {extracted_count}提取, {planted_count}创作")
print(f"伏笔新字段: {has_plant}有plant_chapter, {has_kw}有resolve_keywords, {has_conf}非high置信度")

# Spatial relations
loc_rels = [r for r in relations if r.type.upper() in ("LOCATED_IN", "ADJACENT_TO", "OCCURRED_AT")]
print(f"\n空间关系: {len(loc_rels)}条")
for r in loc_rels[:8]:
    from_e = store.get_entity(r.from_entity)
    to_e = store.get_entity(r.to_entity)
    fn = from_e.name if from_e else r.from_entity
    tn = to_e.name if to_e else r.to_entity
    print(f"  {fn} -[{r.type.upper()}]-> {tn}")

# Timeline events
has_loc = sum(1 for t in tl_events if t.location_ref)
print(f"\n时间线事件: {len(tl_events)}个, {has_loc}个有location")
for t in sorted(tl_events, key=lambda x: x.time_order)[:8]:
    loc = t.location_ref or "无"
    print(f"  {t.time_order}: {t.label[:35]} (ch:{t.chapter_ref}, loc:{loc})")

# Foreshadow details
print("\n=== 伏笔详情 ===")
for f in fores[:8]:
    kw = f.resolve_keywords[:3] if f.resolve_keywords else []
    print(f"  [{f.status}] {f.text[:50]}")
    print(f"    plant={f.plant_chapter}, conf={f.confidence}, kw={kw}")

# Location connectivity check
print("\n=== 地点连通性检查 ===")
locs = store.list_entities(entity_type="location")
loc_ids = {l.id for l in locs}
loc_conns = store._run("""
    MATCH (a:Entity:Location {project_id: $pid})-[r]->(b:Entity:Location {project_id: $pid})
    RETURN a.name as from_name, b.name as to_name, type(r) as rel_type
""", {"pid": BOOK_ID})
print(f"地点实体: {len(locs)}个, 地点间连接: {len(loc_conns)}条")
for r in loc_conns[:8]:
    print(f"  {r['from_name']} -[{r['rel_type']}]-> {r['to_name']}")

# Isolated locations
iso_locs = store._run("""
    MATCH (loc:Entity:Location {project_id: $pid})
    WHERE NOT (loc)-[:LOCATED_IN|ADJACENT_TO|BELONGS_TO|LOCATED_AT]-()
    RETURN loc.name as name
""", {"pid": BOOK_ID})
print(f"孤立地点(无空间关系): {len(iso_locs)}个")
for r in iso_locs[:5]:
    print(f"  {r['name']}")
