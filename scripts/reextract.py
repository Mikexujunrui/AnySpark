"""Re-extract all chapters for a given book ID."""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data.json_store import json_store
from core.extractor import extract_from_text, accept_proposal
from core.graph_store import get_store
from core.llm_client import chat as llm_chat
from tools._common import (
    get_extraction_system_prompt,
    _build_existing_cards,
    _EntityCache,
    _parse_progressive_result,
    _apply_progressive_result_batch,
    _should_skip_chapter,
)
from core.config import config
from core.thread_pools import llm_pool as ai_executor

BOOK_ID = "1781418567324"

def main():
    chapters = json_store.load_chapters(BOOK_ID)
    print(f"共 {len(chapters)} 章待提取")
    for i, ch in enumerate(chapters):
        view = json_store._chapter_view(ch) if "versions" in ch else ch
        title = view.get("title", "")
        content = view.get("content", "")
        print(f"  第{i+1}章: {title[:30]} ({len(content)}字)")

    store = get_store(BOOK_ID)
    system_prompt = get_extraction_system_prompt()
    entity_cache = _EntityCache(store)

    total_new = 0
    total_updated = 0
    total_rels = 0
    total_fs = 0
    total_tl = 0

    for idx, ch in enumerate(chapters):
        view = json_store._chapter_view(ch) if "versions" in ch else ch
        title = view.get("title", "")
        content = view.get("content", "")
        if not content or len(content) < 50:
            print(f"\n第{idx+1}章: 跳过（内容过短）")
            continue

        print(f"\n提取第{idx+1}/{len(chapters)}章: {title[:30]}...")

        # Build existing cards context
        cards = _build_existing_cards(store)

        # Build prompt
        chapter_label = f"第{idx+1}章"
        prompt = f"## {title}\n{content[:config.storage.max_extraction_chars]}\n\n已有知识卡片:\n{cards[:4000]}\n\n请提取本章的新实体、关系、空间关系、伏笔和时间线事件。输出JSON:"

        try:
            response = llm_chat(prompt, system=system_prompt, temperature=0.1, task="extraction")
            if not response:
                print(f"  空响应，跳过")
                continue

            result = _parse_progressive_result(response)
            new_c, upd_c, rel_c, fs_c = _apply_progressive_result_batch(result, store, BOOK_ID)

            # Process timeline events from result
            tl_created = 0
            te_list = result.get("timeline_events", [])
            if te_list:
                all_entities = store.list_entities()
                name_to_id = {}
                for e in all_entities:
                    name_to_id[e.name] = e.id
                    name_to_id[e.name.lower()] = e.id
                    for alias in e.aliases:
                        name_to_id[alias] = e.id
                        name_to_id[alias.lower()] = e.id

                from core.knowledge import TimelineEvent
                for te in te_list:
                    time_order = te.get("time_order", idx + 1)
                    label = te.get("label", title)
                    chapter_ref = te.get("chapter_ref", f"#{idx+1}")
                    characters = te.get("characters", [])
                    if not time_order or not label:
                        continue
                    _to_str = str(time_order).replace(".", "_")
                    evt_id = f"evt_ch{_to_str}"
                    existing = store._run(
                        "MATCH (t:Timeline {id: $tid, project_id: $pid}) RETURN t",
                        {"tid": evt_id, "pid": BOOK_ID}
                    )
                    if not existing:
                        loc_ref = te.get("location", "")
                        store.add_timeline_event(TimelineEvent(
                            id=evt_id,
                            time_point=chapter_label,
                            label=label,
                            time_order=time_order,
                            description="",
                            chapter_ref=chapter_ref,
                            track_id="main",
                            track_name="主线",
                            track_color="#22d3ee",
                            time_label=chapter_label,
                            location_ref=loc_ref,
                        ))
                        tl_created += 1
                    # Link characters
                    matched_ids = []
                    for char_name in characters:
                        eid = name_to_id.get(char_name)
                        if not eid:
                            for alias, aid in name_to_id.items():
                                if char_name.lower() in alias.lower() or alias.lower() in char_name.lower():
                                    eid = aid
                                    break
                        if eid:
                            matched_ids.append(eid)
                    if matched_ids:
                        store.link_timeline_to_entities(evt_id, matched_ids[:30])
                    # Link event to location
                    loc_name = te.get("location", "")
                    if loc_name:
                        loc_id = name_to_id.get(loc_name) or name_to_id.get(loc_name.lower())
                        if loc_id:
                            try:
                                store._run("""
                                    MATCH (t:Timeline {id: $tid, project_id: $pid})
                                    MATCH (l:Entity {id: $lid, project_id: $pid})
                                    MERGE (t)-[:OCCURRED_AT]->(l)
                                """, {"tid": evt_id, "lid": loc_id, "pid": BOOK_ID})
                            except Exception:
                                pass

            # Process spatial relations
            spatial_added = 0
            import uuid
            from core.knowledge import Relation, RelationType
            all_entities = store.list_entities()
            name_to_id = {}
            for e in all_entities:
                name_to_id[e.name] = e.id
                name_to_id[e.name.lower()] = e.id
                for alias in e.aliases:
                    name_to_id[alias] = e.id
                    name_to_id[alias.lower()] = e.id

            for sr in result.get("spatial_relations", []):
                raw_type = sr.get("type", "located_in")
                try:
                    srtype = RelationType(raw_type.lower())
                except (ValueError, KeyError):
                    srtype = RelationType.LOCATED_IN
                from_name = sr.get("from", "")
                to_name = sr.get("to", "")
                from_id = name_to_id.get(from_name) or name_to_id.get(from_name.lower())
                to_id = name_to_id.get(to_name) or name_to_id.get(to_name.lower())
                if from_id and to_id and from_id != to_id:
                    store.add_relation(Relation(
                        id=str(uuid.uuid4())[:8],
                        from_entity=from_id,
                        to_entity=to_id,
                        type=srtype,
                        data={"label": sr.get("label", "")},
                    ))
                    spatial_added += 1

            # Auto-complete transitive spatial containment
            if spatial_added > 0:
                try:
                    store._run("""
                        MATCH (a:Entity:Location {project_id: $pid})-[:LOCATED_IN]->(b:Entity:Location {project_id: $pid})-[:LOCATED_IN]->(c:Entity:Location {project_id: $pid})
                        WHERE a.id <> c.id AND NOT (a)-[:LOCATED_IN]->(c)
                        MERGE (a)-[:LOCATED_IN]->(c)
                    """, {"pid": BOOK_ID})
                except Exception:
                    pass

            # Auto-complete relations
            ac = store.auto_complete_relations()

            total_new += new_c
            total_updated += upd_c
            total_rels += rel_c
            total_fs += fs_c
            total_tl += tl_created

            parts = []
            if new_c: parts.append(f"新增{new_c}")
            if upd_c: parts.append(f"更新{upd_c}")
            if rel_c: parts.append(f"关系{rel_c}")
            if spatial_added: parts.append(f"空间{spatial_added}")
            if fs_c: parts.append(f"伏笔{fs_c}")
            if tl_created: parts.append(f"时间线{tl_created}")
            ac_parts = []
            if ac.get("symmetry_added"): ac_parts.append(f"对称+{ac['symmetry_added']}")
            if ac.get("cooccur_added"): ac_parts.append(f"共现+{ac['cooccur_added']}")
            if ac.get("transitive_added"): ac_parts.append(f"传递+{ac['transitive_added']}")
            if ac.get("structural_added"): ac_parts.append(f"结构等价+{ac['structural_added']}")
            if ac.get("multihop_added"): ac_parts.append(f"多跳+{ac['multihop_added']}")
            if ac.get("jaccard_added"): ac_parts.append(f"Jaccard+{ac['jaccard_added']}")
            if ac.get("llm_suggested"): ac_parts.append(f"LLM+{ac['llm_suggested']}")
            print(f"  {' | '.join(parts)}" + (f" | 补全: {' '.join(ac_parts)}" if ac_parts else ""))

        except Exception as e:
            print(f"  错误: {str(e)[:80]}")

    # Run Pass 2: foreshadow resolution matching
    print("\n=== Pass 2: 伏笔回收匹配 ===")
    chapters_raw = json_store.load_chapters(BOOK_ID)
    match_result = store.match_foreshadow_resolutions(chapters_raw, llm_chat=llm_chat)
    print(f"回收匹配: 匹配{match_result.get('matched',0)} / 未匹配{match_result.get('unmatched',0)} / 悬置{match_result.get('dangling',0)} / 总计{match_result.get('total',0)}")

    # Final summary
    print(f"\n=== 提取完成 ===")
    print(f"实体: 新增{total_new} 更新{total_updated}")
    print(f"关系: {total_rels}条")
    print(f"伏笔: {total_fs}个")
    print(f"时间线: {total_tl}个事件")

    # Print final stats
    entities = store.list_entities()
    relations = store.list_relations()
    fores = store.list_foreshadows()
    open_fs = [f for f in fores if f.status == "open"]
    resolved_fs = [f for f in fores if f.status == "resolved"]
    dangling_fs = [f for f in fores if f.status == "dangling"]
    print(f"\n最终知识库: {len(entities)}实体, {len(relations)}关系, {len(fores)}伏笔")
    print(f"伏笔状态: {len(open_fs)}待回收, {len(resolved_fs)}已回收, {len(dangling_fs)}悬置")

if __name__ == "__main__":
    main()
