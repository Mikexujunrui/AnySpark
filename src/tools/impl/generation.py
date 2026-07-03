"""Generation tool implementations — outline, worldbuilding, timeline, location map."""
import asyncio
import json

from core.config import config
from core.llm_client import chat as llm_chat
from core.thread_pools import llm_pool as _ai_executor
from core.utils import extract_json_from_response
from data.json_store import json_store
from tools._common import _parse_chapter_range

OUTLINE_SYSTEM = """你是小说大纲概括专家。根据章节原文生成简洁精准的大纲条目。

输出严格JSON:
{
  "synopsis": "2-3句话概括本章主要情节走向",
  "key_events": ["关键事件1", "关键事件2", "关键事件3"],
  "characters": ["本章出场的重要角色名"],
  "turning_point": "本章的转折点或悬念（如果有，没有则留空）"
}

只提取原文明确的内容，不推测。"""

OUTLINE_SUMMARY_SYSTEM = """你是小说大纲总编。根据每章的概要，写一段全书总纲（3-5句话），概括：
1. 故事主线
2. 主要矛盾/冲突
3. 整体叙事弧线（开端→发展→高潮→结局的走向）

直接输出总纲文本，不要加标题或格式。"""

def _coerce_to_dict(v) -> dict:
    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return {}
        try:
            parsed = json.loads(s)
        except (json.JSONDecodeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}

def _parse_progressive_result(response: str) -> dict:
    j = extract_json_from_response(response)
    try:
        return json.loads(j.strip())
    except json.JSONDecodeError:
        return {"new_entities": [], "updates": [], "relations": [], "foreshadows": []}

async def _generate_outline(loop, args: dict, kb, book_id: str, msg: str = "", queue=None) -> str:
    chapters_range = args.get("chapters", "all").strip()
    all_chapters = json_store.load_chapters(book_id)
    if not all_chapters:
        return "当前书籍没有章节。"

    target_indices = _parse_chapter_range(chapters_range, len(all_chapters))
    if not target_indices:
        return f"无法解析章节范围: {chapters_range}"

    outline = json_store.get_outline(book_id)
    existing_chapters = outline.get("chapters", [])
    existing_extras = outline.get("extras", [])
    while len(existing_chapters) < len(all_chapters):
        next_ch = all_chapters[len(existing_chapters)]
        view = json_store._chapter_view(next_ch) if "versions" in next_ch else next_ch
        existing_chapters.append({"chapter_id": next_ch["id"],
                                  "title": view.get("title", ""),
                                  "synopsis": "",
                                  "key_events": [],
                                  "characters": [],
                                  "notes": ""})

    regular_indices = [i for i in target_indices if not all_chapters[i].get("is_extra")]
    extra_indices = [i for i in target_indices if all_chapters[i].get("is_extra")]

    total_extra_count = sum(1 for c in all_chapters if c.get("is_extra"))
    while len(existing_extras) < total_extra_count:
        existing_extras.append({"chapter_id": "", "title": "", "synopsis": "",
                                "key_events": [], "characters": [], "notes": ""})

    generated = 0
    failed = 0

    for idx in regular_indices:
        ch = all_chapters[idx]
        view = json_store._chapter_view(ch) if "versions" in ch else ch
        content = view.get("content", "")
        title = view.get("title", "")

        if not content or len(content) < 50:
            continue

        if queue:
            await queue.put({"_progress": f"概括第{idx + 1}/{len(all_chapters)}章: {title[:15]}..."})

        prompt = f"## 章节: {title}\n{content[:config.storage.max_extraction_chars]}\n\n请输出JSON:"

        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    _ai_executor, llm_chat, prompt, OUTLINE_SYSTEM, 0.1, "extraction"),
                timeout=120
            )
            data = _parse_progressive_result(response)
            existing_chapters[idx] = {
                "chapter_id": ch["id"], "title": title,
                "synopsis": data.get("synopsis", ""),
                "key_events": data.get("key_events", []),
                "characters": data.get("characters", []),
                "turning_point": data.get("turning_point", ""),
                "notes": existing_chapters[idx].get("notes", ""),
            }
            generated += 1
            if queue:
                await queue.put({"_progress": f"✅ 第{idx + 1}章: {data.get('synopsis', '')[:40]}..."})
        except Exception as e:
            failed += 1
            if queue:
                await queue.put({"_progress": f"❌ 第{idx + 1}章: {str(e)[:40]}"})

    for extra_pos, idx in enumerate(extra_indices):
        ch = all_chapters[idx]
        view = json_store._chapter_view(ch) if "versions" in ch else ch
        content = view.get("content", "")
        title = view.get("title", "")
        if not content or len(content) < 50:
            continue
        if queue:
            await queue.put({"_progress": f"概括番外{extra_pos + 1}: {title[:15]}..."})
        prompt = f"## 章节: {title}\n{content[:config.storage.max_extraction_chars]}\n\n请输出JSON:"
        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(_ai_executor, llm_chat, prompt, OUTLINE_SYSTEM, 0.1, "extraction"),
                timeout=120
            )
            data = _parse_progressive_result(response)
            existing_extras[extra_pos] = {
                "chapter_id": ch["id"], "title": title,
                "synopsis": data.get("synopsis", ""),
                "key_events": data.get("key_events", []),
                "characters": data.get("characters", []),
                "notes": existing_extras[extra_pos].get("notes", "") if extra_pos < len(existing_extras) else "",
            }
            generated += 1
            if queue:
                await queue.put({"_progress": f"✅ 番外{extra_pos + 1}: {data.get('synopsis', '')[:40]}..."})
        except Exception as e:
            failed += 1
            if queue:
                await queue.put({"_progress": f"❌ 番外{extra_pos + 1}: {str(e)[:40]}"})

    outline["chapters"] = existing_chapters
    outline["extras"] = existing_extras

    if queue:
        await queue.put({"_progress": "生成全书总纲..."})

    try:
        chapter_summaries = "\n".join(
            f"第{i + 1}章 {c.get('title', '')}: {c.get('synopsis', '')}"
            for i, c in enumerate(existing_chapters) if c.get("synopsis"))
        extra_summaries = "\n".join(
            f"番外{i + 1} {e.get('title', '')}: {e.get('synopsis', '')}"
            for i, e in enumerate(existing_extras) if e.get("synopsis"))
        if extra_summaries:
            chapter_summaries = chapter_summaries + "\n" + extra_summaries
        summary = await asyncio.wait_for(
            loop.run_in_executor(_ai_executor, llm_chat, chapter_summaries, OUTLINE_SUMMARY_SYSTEM, 0.1, "extraction"),
            timeout=60
        )
        outline["summary"] = summary.strip()
    except Exception:
        outline["summary"] = outline.get("summary", "")

    json_store.save_outline(book_id, outline)
    result_parts = [f"大纲生成完成: {generated} 章已概括, {failed} 章失败", ""]
    for i, c in enumerate(existing_chapters):
        if c.get("synopsis"):
            result_parts.append(f"  #{i + 1} {c.get('title', '')[:15]}: {c['synopsis'][:50]}")
    if outline.get("summary"):
        result_parts.append(f"\n全书总纲: {outline['summary'][:200]}")
    return "\n".join(result_parts)

def _match_extra_outline(book_id: str, instruction: str, is_extra: bool):
    import re as _re
    if not is_extra and "番外" not in instruction:
        return None
    extra_num = None
    for pat in [r'番外\s*(\d+)', r'#E(\d+)']:
        m = _re.search(pat, instruction)
        if m:
            extra_num = int(m.group(1))
            break
    if extra_num is None:
        chs = json_store.load_chapters(book_id)
        extra_count = sum(1 for c in chs if c.get("is_extra"))
        extra_num = extra_count + 1
    outline = json_store.get_outline(book_id)
    extras_outline = outline.get("extras", [])
    outline_entry = extras_outline[extra_num - 1] if 0 <= extra_num - 1 < len(extras_outline) else None
    detailed = json_store.get_detailed_outline(book_id)
    extras_detail = detailed.get("extras", [])
    detail_entry = extras_detail[extra_num - 1] if 0 <= extra_num - 1 < len(extras_detail) else None
    return {"extra_num": extra_num, "outline_entry": outline_entry, "detail_entry": detail_entry}

def _get_outline(book_id: str, args: dict = None) -> str:
    outline = json_store.get_outline(book_id)
    if not outline.get("chapters") and not outline.get("summary") and not outline.get("extras"):
        return "尚未生成大纲。请使用 generate_outline 工具生成。"
    chapter_index = None
    if args and args.get("chapter_index") is not None:
        chapter_index = int(args["chapter_index"]) - 1
    parts = []
    if chapter_index is not None:
        chapters = outline.get("chapters", [])
        if chapter_index < 0 or chapter_index >= len(chapters):
            return f"章节序号 {chapter_index + 1} 超出范围（共 {len(chapters)} 章）"
        c = chapters[chapter_index]
        if not c.get("synopsis"):
            return f"第{chapter_index + 1}章尚无大纲。"
        parts.append(f"第{chapter_index + 1}章大纲: {c.get('title', '')}")
        if c.get("chapter_id"):
            parts.append(f"章节ID: {c['chapter_id']}")
        parts.append(f"概要: {c['synopsis']}")
        if c.get("key_events"):
            parts.append(f"关键事件: {', '.join(c['key_events'])}")
        if c.get("characters"):
            parts.append(f"出场角色: {', '.join(c['characters'])}")
        if c.get("turning_point"):
            parts.append(f"转折: {c['turning_point']}")
        if c.get("notes"):
            parts.append(f"备注: {c['notes']}")
        return "\n".join(parts)
    if outline.get("summary"):
        parts.append(f"全书总纲:\n{outline['summary']}\n")
    chapters = outline.get("chapters", [])
    if chapters:
        parts.append(f"章节大纲 ({len([c for c in chapters if c.get('synopsis')])} 章):")
        for i, c in enumerate(chapters):
            if not c.get("synopsis"):
                continue
            parts.append(f"\n  #{i + 1} {c.get('title', '')}")
            if c.get("chapter_id"):
                parts.append(f"  章节ID: {c['chapter_id']}")
            parts.append(f"  概要: {c['synopsis']}")
            if c.get("key_events"):
                parts.append(f"  事件: {', '.join(c['key_events'])}")
            if c.get("characters"):
                parts.append(f"  角色: {', '.join(c['characters'])}")
            if c.get("turning_point"):
                parts.append(f"  转折: {c['turning_point']}")
            if c.get("notes"):
                parts.append(f"  备注: {c['notes']}")
    extras = outline.get("extras", [])
    if extras:
        parts.append(f"\n番外大纲 ({len([e for e in extras if e.get('synopsis')])} 篇):")
        for i, e in enumerate(extras):
            if not e.get("synopsis"):
                continue
            parts.append(f"\n  #E{i + 1} {e.get('title', '')}")
            if e.get("chapter_id"):
                parts.append(f"  章节ID: {e['chapter_id']}")
            parts.append(f"  概要: {e['synopsis']}")
            if e.get("key_events"):
                parts.append(f"  事件: {', '.join(e['key_events'])}")
            if e.get("characters"):
                parts.append(f"  角色: {', '.join(e['characters'])}")
            if e.get("notes"):
                parts.append(f"  备注: {e['notes']}")
    return "\n".join(parts) if parts else "大纲为空。"

def _update_outline(args: dict, book_id: str) -> str:
    chapter_index = args.get("chapter_index")
    synopsis = args.get("synopsis")
    notes = args.get("notes")
    summary = args.get("summary")
    is_extra = bool(args.get("is_extra", False))
    if chapter_index is not None:
        idx = int(chapter_index) - 1
        update = {}
        if synopsis:
            update["synopsis"] = synopsis
        if notes:
            update["notes"] = notes
        if not update:
            return "错误: 需要提供 synopsis 或 notes"
        if is_extra:
            json_store.update_outline_extra(book_id, idx, update)
            return f"已更新番外{idx + 1}大纲。"
        else:
            json_store.update_outline_chapter(book_id, idx, update)
            return f"已更新第{idx + 1}章大纲。"
    elif summary:
        json_store.update_outline_summary(book_id, summary)
        return "已更新全书总纲。"
    else:
        return "错误: 需要指定 chapter_index + (synopsis/notes)，或提供 summary 更新总纲。"

WORLDBUILDING_SYSTEM = """你是小说世界观架构师。分析小说内容，提取世界观设定并按分类组织。
注意：角色只关注其在世界观中的地位、影响力和能力体系，不写性格；地点只关注其战略意义、功能和与其他地点的关系。
每个条目用2-4句连贯的中文描述，条目中可用 @其他条目名 来交叉引用。

输出严格JSON:
{
  "categories": [{"name": "分类名", "icon": "emoji图标",
    "children": [{"name": "子分类名", "icon": "", "entries": [...]}],
    "entries": [{"title": "条目名", "content": "人类可读的段落描述。可引用 @其他条目名。", "tags": ["标签"], "chapter_refs": ["#1"]}]
  }]
}
分类命名应贴合小说类型（如奇幻用"魔法体系"，仙侠用"修炼体系"，科幻用"技术体系"）。"""

async def _generate_worldbuilding(loop, args: dict, kb, book_id: str, msg: str = "", queue=None) -> str:
    if queue:
        await queue.put({"_progress": "分析小说世界观维度..."})
    entities = kb.list_entities()
    outline = json_store.get_outline(book_id)
    chapters = json_store.load_chapters(book_id)
    budget = config.storage.max_extraction_chars
    source_parts = []
    used = 0
    if entities:
        by_type = {}
        for e in entities:
            by_type.setdefault(e.type, []).append(e)
        for t, elist in by_type.items():
            header = f"\n[{t}]\n"
            if used + len(header) > budget:
                break
            source_parts.append(header)
            used += len(header)
            for e in elist[:15]:
                vals = ", ".join(f"{k}: {v}" for k, v in list(e.data.items())[:5] if v)
                line = f"  {e.name}: {vals}\n"
                if used + len(line) > budget:
                    break
                source_parts.append(line)
                used += len(line)
    if outline.get("chapters") and used < budget:
        source_parts.append("\n[大纲]\n")
        used += len("\n[大纲]\n")
        for c in outline["chapters"]:
            if c and c.get("synopsis"):
                line = f"  {c.get('title', '')}: {c['synopsis']}\n"
                if used + len(line) > budget:
                    break
                source_parts.append(line)
                used += len(line)
    source = "".join(source_parts)
    if not source:
        for ch in chapters[:10]:
            view = json_store._chapter_view(ch) if "versions" in ch else ch
            if view.get("content"):
                line = f"\n{view.get('title', '')}: {view['content'][:400]}\n"
                if used + len(line) > budget:
                    break
                source_parts.append(line)
                used += len(line)
        source = "".join(source_parts)
    if not source:
        return "没有可分析的内容。请先导入章节或提取知识。"

    if queue:
        await queue.put({"_progress": "LLM 生成世界观设定..."})
    prompt = f"## 小说已有内容\n{source}\n\n请分析世界观并生成分类+条目，输出JSON:"
    try:
        response = await asyncio.wait_for(
            loop.run_in_executor(_ai_executor, llm_chat, prompt, WORLDBUILDING_SYSTEM, 0.15, "extraction"),
            timeout=180)
    except Exception as e:
        return f"生成失败: {str(e)[:60]}"

    result = _parse_progressive_result(response)
    categories = result.get("categories", [])
    import uuid

    def assign_ids(cats):
        for cat in cats:
            cat["id"] = f"cat_{uuid.uuid4().hex[:6]}"
            cat.setdefault("entries", [])
            cat.setdefault("children", [])
            for e in cat["entries"]:
                e["id"] = f"ent_{uuid.uuid4().hex[:6]}"
            assign_ids(cat["children"])
    assign_ids(categories)
    json_store.save_worldbuilding(book_id, {"categories": categories})
    return f"世界观生成完成: {len(categories)} 个分类"

def _get_worldbuilding_tool(book_id: str) -> str:
    wb = json_store.get_worldbuilding(book_id)
    cats = wb.get("categories", [])
    if not cats:
        return "尚未生成世界观设定。请使用 generate_worldbuilding 工具。"
    parts = ["世界观设定:\n"]
    def render(cats, depth=0):
        indent = "  " * depth
        for cat in cats:
            parts.append(f"{indent}{cat.get('icon', '')} {cat['name']}")
            for e in cat.get("entries", []):
                parts.append(f"{indent}  ▸ {e['title']}")
                parts.append(f"{indent}    {e.get('content', '')[:80]}")
            render(cat.get("children", []), depth + 1)
    render(cats)
    return "\n".join(parts)

def _add_worldbuilding_entry_tool(args: dict, book_id: str) -> str:
    cat_name = args.get("category", "")
    title = args.get("title", "")
    if not cat_name or not title:
        return "错误: 需要 category 和 title"
    wb = json_store.get_worldbuilding(book_id)
    cats = wb.get("categories", [])
    target_cat = None
    def find_cat(categories):
        nonlocal target_cat
        for c in categories:
            if c["name"] == cat_name:
                target_cat = c
                return
            find_cat(c.get("children", []))
    find_cat(cats)
    if not target_cat:
        target_cat = json_store.add_worldbuilding_category(book_id, cat_name)
    import uuid
    entry = {"id": f"ent_{uuid.uuid4().hex[:6]}", "title": title, "content": args.get("content", ""),
             "tags": args.get("tags", []), "chapter_refs": args.get("chapter_refs", [])}
    json_store.add_worldbuilding_entry(book_id, target_cat["id"], entry)
    return f"已添加条目「{title}」到 [{cat_name}]"

async def _generate_location_map(loop, args: dict, kb, book_id: str, msg: str = "", queue=None) -> str:
    """Read location map from Neo4j; auto-create and supplement connections.

    Knowledge extraction creates Location entities but may not create
    relationships between them. This tool:
    1. Backfills BELONGS_TO/LOCATED_IN from parent_location in entity data
    2. Infers containment from name patterns (e.g. "格兰芬多休息室" contains "格兰芬多")
    3. If connections are sparse (< n-1), uses LLM to analyze chapter content
       and supplement missing location relationships.
    """
    if queue:
        await queue.put({"_progress": "从知识图谱读取地点数据..."})

    # ── Backfill: create BELONGS_TO from parent_location ──
    if kb is not None:
        locs = kb.list_entities(entity_type="location")
        name_to_id = {e.name: e.id for e in locs}
        synced = 0
        for loc in locs:
            parent_name = loc.data.get("parent_location", "") or loc.data.get("parent", "")
            if parent_name and parent_name in name_to_id:
                parent_id = name_to_id[parent_name]
                from core.knowledge import Relation, RelationType
                kb.add_relation(Relation(
                    id=f"rel_loc_{loc.id}",
                    from_entity=loc.id,
                    to_entity=parent_id,
                    type=RelationType.BELONGS_TO,
                    data={"label": "属于"},
                ))
                synced += 1
        if synced > 0 and queue:
            await queue.put({"_progress": f"回溯创建 {synced} 条地点连接"})

        # ── Name pattern inference: if location A's name contains location B's name → A LOCATED_IN B ──
        pattern_added = 0
        for loc_a in locs:
            for loc_b in locs:
                if loc_a.id == loc_b.id:
                    continue
                # Skip if A's name is shorter or equal to B's (B can't contain A)
                if len(loc_a.name) <= len(loc_b.name):
                    continue
                # Check if B's name is a substring of A's name (A contains B → A is inside B)
                if loc_b.name in loc_a.name and len(loc_b.name) >= 2:
                    # Only add if no existing LOCATED_IN/BELONGS_TO edge
                    existing = kb._run("""
                        MATCH (a:Entity {id: $aid, project_id: $pid})-[r:LOCATED_IN|BELONGS_TO]->(b:Entity {id: $bid, project_id: $pid})
                        RETURN count(r) as cnt
                    """, {"aid": loc_a.id, "bid": loc_b.id, "pid": kb.project_id})
                    if existing and existing[0]["cnt"] == 0:
                        from core.knowledge import Relation, RelationType
                        kb.add_relation(Relation(
                            id=f"rel_pattern_{loc_a.id}_{loc_b.id}",
                            from_entity=loc_a.id,
                            to_entity=loc_b.id,
                            type=RelationType.LOCATED_IN,
                            data={"label": "名称推断包含", "inferred": True},
                        ))
                        pattern_added += 1
        if pattern_added > 0 and queue:
            await queue.put({"_progress": f"名称模式推断 {pattern_added} 条包含关系"})

    map_data = kb.get_location_map_for_view() if kb is not None else {"nodes": [], "connections": []}
    nodes = map_data.get("nodes", [])
    connections = map_data.get("connections", [])

    # ── LLM-based connection analysis: trigger when connections are sparse (< n-1) ──
    # At least n-1 edges are needed to connect n nodes; below that, the graph is fragmented
    if nodes and kb is not None and len(connections) < max(len(nodes) - 1, 1):
        chapters = json_store.load_chapters(book_id)
        if chapters:
            if queue:
                await queue.put({"_progress": "增量分析地点间空间关系..."})
            loc_names = [n["name"] for n in nodes]
            # Build set of already-connected pairs to avoid re-analyzing
            connected_pairs = set()
            for c in connections:
                connected_pairs.add((c["from"], c["to"]))
                connected_pairs.add((c["to"], c["from"]))
            source_text = ""
            for i, ch in enumerate(chapters[:20]):
                view = json_store._chapter_view(ch) if "versions" in ch else ch
                content = view.get("content", "")
                if content:
                    source_text += f"\n第{i + 1}章 {view.get('title', '')}: {content[:400]}"
            prompt = f"## 已知地点\n{', '.join(loc_names)}\n\n## 章节内容\n{source_text[:config.storage.max_extraction_chars]}\n\n请分析这些地点之间的空间关系（包含、相邻、路径等），输出JSON:\n{{\"connections\": [{{\"from\": \"地点A\", \"to\": \"地点B\", \"label\": \"连接方式\", \"type\": \"path/portal/contains/near\"}}]}}"
            try:
                response = await asyncio.wait_for(
                    loop.run_in_executor(_ai_executor, llm_chat, prompt, LOCATION_CONN_SYSTEM, 0.1, "extraction"),
                    timeout=120)
                result = _parse_progressive_result(response)
                llm_connections = result.get("connections", [])
                if llm_connections:
                    from core.knowledge import Relation, RelationType
                    new_count = 0
                    for c in llm_connections:
                        from_name = c.get("from", "")
                        to_name = c.get("to", "")
                        from_id = name_to_id.get(from_name)
                        to_id = name_to_id.get(to_name)
                        if from_id and to_id:
                            # Skip already-connected pairs
                            pair_key = (from_name, to_name)
                            if pair_key in connected_pairs or (to_name, from_name) in connected_pairs:
                                continue
                            conn_type = c.get("type", "near")
                            type_map = {"contains": RelationType.LOCATED_IN, "near": RelationType.ADJACENT_TO,
                                       "path": RelationType.ADJACENT_TO, "portal": RelationType.ADJACENT_TO}
                            rel_type = type_map.get(conn_type, RelationType.ADJACENT_TO)
                            import uuid
                            kb.add_relation(Relation(
                                id=f"rel_conn_{uuid.uuid4().hex[:8]}",
                                from_entity=from_id,
                                to_entity=to_id,
                                type=rel_type,
                                data={"label": c.get("label", ""), "original_type": conn_type},
                            ))
                            new_count += 1
                    if queue and new_count > 0:
                        await queue.put({"_progress": f"LLM 增量分析创建 {new_count} 条地点连接"})
                    map_data = kb.get_location_map_for_view()
                    nodes = map_data.get("nodes", [])
                    connections = map_data.get("connections", [])
            except Exception as e:
                if queue:
                    await queue.put({"_progress": f"地点关系分析跳过: {str(e)[:40]}"})

    if not nodes:
        return "知识库中暂无地点数据。请先运行知识提取（/s 或 extract_all_chapters）。"

    json_store.save_location_map(book_id, {"nodes": nodes, "connections": connections})

    if queue:
        await queue.put({"_progress": f"✅ {len(nodes)} 个地点, {len(connections)} 条连接"})
    return f"地点图生成完成: {len(nodes)} 个地点, {len(connections)} 条连接"

LOCATION_CONN_SYSTEM = """你是小说地点关系分析专家。根据章节内容，分析已知地点之间的空间关系。
输出严格JSON: {"connections": [{"from": "地点A", "to": "地点B", "label": "连接方式描述", "type": "path/portal/contains/near"}]}
连接类型: path=物理路径, portal=魔法/传送, contains=包含关系, near=相邻/附近
只分析明确有空间关系的地点对，不要凭空编造。"""

DETAILED_OUTLINE_SYSTEM = """你是小说剧情骨架提取专家。从章节原文中去掉所有描写、对话、心理活动、环境渲染，只提取纯粹的事件链。
输出格式（严格JSON）: {"plot_chain": ["事件1: 谁做了什么 → 导致什么结果", ...], "chapter_function": "本章在全书中的叙事功能"}
规则：只写"谁→做了什么→结果"，每个事件一行用→连接因果，一章通常5-15个事件。"""

async def _generate_detailed_outline(loop, args: dict, kb, book_id: str, msg: str = "", queue=None) -> str:
    chapters_range = args.get("chapters", "all").strip()
    all_chapters = json_store.load_chapters(book_id)
    if not all_chapters:
        return "当前书籍没有章节。"
    target_indices = _parse_chapter_range(chapters_range, len(all_chapters))
    if not target_indices:
        return f"无法解析章节范围: {chapters_range}"
    detailed_outline = json_store.get_detailed_outline(book_id)
    existing = detailed_outline.get("chapters", [])
    existing_extras = detailed_outline.get("extras", [])
    while len(existing) < len(all_chapters):
        existing.append(None)
    regular_indices = [i for i in target_indices if not all_chapters[i].get("is_extra")]
    total_extra_count = sum(1 for c in all_chapters if c.get("is_extra"))
    while len(existing_extras) < total_extra_count:
        existing_extras.append(None)
    generated = 0
    failed = 0
    for idx in regular_indices:
        ch = all_chapters[idx]
        view = json_store._chapter_view(ch) if "versions" in ch else ch
        content = view.get("content", "")
        title = view.get("title", "")
        if not content or len(content) < 50:
            continue
        if queue:
            await queue.put({"_progress": f"提取第{idx + 1}/{len(all_chapters)}章细纲: {title[:15]}..."})
        prompt = f"## {title}\n{content[:config.storage.max_extraction_chars]}\n\n请提取纯剧情骨架，输出JSON:"
        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(_ai_executor, llm_chat, prompt, DETAILED_OUTLINE_SYSTEM, 0.1, "extraction"),
                timeout=120)
            data = _parse_progressive_result(response)
            existing[idx] = {"chapter_id": ch["id"], "title": title,
                             "plot_chain": data.get("plot_chain", []),
                             "chapter_function": data.get("chapter_function", "")}
            generated += 1
            if queue:
                await queue.put({"_progress": f"✅ 第{idx + 1}章: {len(data.get('plot_chain', []))} 个事件"})
        except Exception as e:
            failed += 1
            if queue:
                await queue.put({"_progress": f"❌ 第{idx + 1}章: {str(e)[:40]}"})
    json_store.save_detailed_outline(book_id, {"chapters": existing, "extras": existing_extras})
    return f"细纲生成完成: {generated} 章, {failed} 章失败"

def _get_detailed_outline_tool(book_id: str) -> str:
    d = json_store.get_detailed_outline(book_id)
    chapters = d.get("chapters", [])
    valid = [c for c in chapters if c and c.get("plot_chain")]
    if not valid:
        return "尚未生成细纲。可使用 generate_detailed_outline（从章节提取）或 update_detailed_outline（直接写入）。"
    parts = [f"细纲 ({len(valid)} 章):\n"]
    for i, c in enumerate(chapters):
        if not c or not c.get("plot_chain"):
            continue
        parts.append(f"#{i + 1} {c.get('title', '')} [{c.get('chapter_function', '')}]")
        for ev in c["plot_chain"][:5]:
            parts.append(f"  • {ev}")
    return "\n".join(parts)

def _update_detailed_outline(args: dict, book_id: str) -> str:
    chapter_index = args.get("chapter_index")
    if chapter_index is None:
        return "错误: 需要提供 chapter_index（从1开始）"
    idx = int(chapter_index) - 1
    update = {}
    title = args.get("title")
    plot_chain = args.get("plot_chain")
    chapter_function = args.get("chapter_function")
    if title:
        update["title"] = title
    if plot_chain is not None:
        if isinstance(plot_chain, str):
            import json as _json
            try:
                plot_chain = _json.loads(plot_chain)
            except Exception:
                plot_chain = [line.strip() for line in plot_chain.split("\n") if line.strip()]
        update["plot_chain"] = plot_chain
    if chapter_function:
        update["chapter_function"] = chapter_function
    if not update:
        return "错误: 需要提供 plot_chain 或 chapter_function"
    is_extra = bool(args.get("is_extra", False))
    if is_extra:
        json_store.update_detailed_outline_extra(book_id, idx, update)
        events_count = len(update.get("plot_chain", []))
        return f"已更新番外{idx + 1}细纲。" + (f" ({events_count} 个事件)" if events_count else "")
    else:
        json_store.update_detailed_outline_chapter(book_id, idx, update)
        events_count = len(update.get("plot_chain", []))
        return f"已更新第{idx + 1}章细纲。" + (f" ({events_count} 个事件)" if events_count else "")

async def _generate_timeline(loop, args: dict, kb, book_id: str, msg: str = "", queue=None) -> str:
    """Read timeline from Neo4j. Timeline events are auto-created during knowledge extraction.

    This is a pure read tool — no backfill or chapter scanning.
    """
    if queue:
        await queue.put({"_progress": "从知识图谱读取时间线数据..."})

    tl_data = kb.get_timeline_for_view() if kb is not None else {"tracks": [], "events": []}
    events = tl_data.get("events", [])

    if not events:
        return "知识库中暂无时间线数据。请先运行知识提取（/s 或 extract_all_chapters）。"

    tracks = tl_data.get("tracks", [])
    json_store.save_timeline(book_id, {"tracks": tracks, "events": events})

    if queue:
        await queue.put({"_progress": f"\u2705 {len(tracks)} 条轨道, {len(events)} 个事件"})
    return f"时间线: {len(tracks)} 条轨道, {len(events)} 个事件"

def _get_timeline_tool(book_id: str) -> str:
    tl = json_store.load_timeline(book_id)
    events = tl.get("events", [])
    if not events:
        return "尚未生成时间线数据。请先运行知识提取（/s 或 extract_all_chapters）来从章节中自动创建时间线事件。"
    return f"时间线: {len(tl.get('tracks', []))} 条轨道, {len(events)} 个事件"

def _add_timeline_event_tool(args: dict, book_id: str) -> str:
    return "时间线事件添加功能暂未实现。"


def _build_char_match_map(kb) -> dict:
    """Build a character match map with multiple keys per character.

    Returns dict where keys are matchable name fragments and values are entity_ids.
    Each character generates multiple keys: full name, dot-free name, surname, given name, aliases.
    """
    import re
    char_map: dict[str, str] = {}
    for e in kb.list_entities(entity_type="character"):
        eid = e.id
        name = e.name
        name_lower = name.lower()
        # Key 1: full name
        char_map[name_lower] = eid
        # Key 2: dot-free name (e.g. "哈利·波特" -> "哈利波特")
        dot_free = re.sub(r'[·\u2022\u00b7\u2027\u30fb]', '', name_lower)
        if dot_free != name_lower:
            char_map[dot_free] = eid
        # Key 3: split into parts, keep only given name (first part), exclude surname (last part)
        # to prevent ambiguous matching like '波特' matching both Harry and James
        parts = re.split(r'[·\u2022\u00b7\u2027\u30fb·\-\s—–]+', name_lower)
        for i, part in enumerate(parts):
            part = part.strip()
            if len(part) >= 2 and not (len(parts) >= 2 and i == len(parts) - 1):
                char_map[part] = eid
        # Key 4: remove parenthetical suffixes (e.g. "差点没头的尼克（尼古拉斯·德·敏西-波平顿）" -> "差点没头的尼克")
        simple = re.sub(r'[（(][^）)]*[）)]', '', name_lower).strip()
        if simple != name_lower and len(simple) >= 2:
            char_map[simple] = eid
        # Key 5: aliases
        for alias in e.aliases or []:
            alias_lower = alias.lower()
            if len(alias_lower) >= 2:
                char_map[alias_lower] = eid
    return char_map


def _match_characters_in_content(content_lower: str, char_map: dict[str, str]) -> list[str]:
    """Match characters in content using multi-key matching.

    Returns list of unique entity_ids found in the content.
    """
    seen: set[str] = set()
    matched: list[str] = []
    # Sort keys by length descending so longer matches take priority
    for key in sorted(char_map, key=len, reverse=True):
        if key in content_lower and char_map[key] not in seen:
            seen.add(char_map[key])
            matched.append(char_map[key])
    return matched


# ── Manual entity/relation tools ──

def _add_entity_tool(args: dict, book_id: str) -> str:
    """Manually add a single entity to the knowledge graph."""
    name = args.get("name", "")
    etype = args.get("type", "character")
    aliases = args.get("aliases", [])
    data = args.get("data", {})
    if not name:
        return "错误: 需要提供 name"
    import uuid

    from core.graph_store import get_store
    from core.knowledge import Entity
    store = get_store(book_id)
    # Check existing
    existing = store._run(
        "MATCH (e:Entity {name: $name, project_id: $pid}) RETURN e.id AS id",
        {"name": name, "pid": book_id}
    )
    if existing:
        store.update_entity(existing[0]["id"], data)
        return f"已更新实体: [{etype}] {name}"
    entity = Entity(id=str(uuid.uuid4())[:8], type=etype, name=name, aliases=aliases, data=data)
    store.add_entity(entity)
    return f"已添加实体: [{etype}] {name}"


def _add_relation_tool(args: dict, book_id: str) -> str:
    """Manually add a single relation between two entities."""
    from_entity = args.get("from", "")
    to_entity = args.get("to", "")
    rtype = args.get("type", "knows")
    if not from_entity or not to_entity:
        return "错误: 需要提供 from 和 to（实体名或ID）"
    import uuid

    from core.graph_store import get_store
    from core.knowledge import Relation, RelationType
    store = get_store(book_id)
    # Resolve names to IDs
    def resolve(name_or_id):
        r = store._run("MATCH (e:Entity {project_id: $pid}) WHERE e.id = $v OR e.name = $v RETURN e.id AS id LIMIT 1",
                       {"v": name_or_id, "pid": book_id})
        return r[0]["id"] if r else name_or_id
    fid = resolve(from_entity)
    tid = resolve(to_entity)
    try:
        rt = RelationType(rtype.lower())
    except ValueError:
        return f"错误: 不支持的关系类型 '{rtype}'，支持: {[r.value for r in RelationType]}"
    rel = Relation(id=str(uuid.uuid4())[:8], from_entity=fid, to_entity=tid, type=rt)
    store.add_relation(rel)
    return f"已添加关系: {from_entity} -[{rtype}]-> {to_entity}"
