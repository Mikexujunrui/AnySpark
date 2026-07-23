"""Handler route tool implementations — volume, materials, knowledge edit.

Extracted from executor.py to keep module sizes manageable.
"""

import json
import logging
from datetime import datetime

from core.knowledge import Entity
from core.search import fts
from data.json_store import json_store

logger = logging.getLogger(__name__)


def _handle_volume(name: str, args: dict, book_id: str) -> str:
    if name == "create_volume":
        title = args.get("title", "")
        story_line = args.get("story_line") or args.get("storyLine") or args.get("storyline") or ""
        if not title:
            return "错误: 需要 title 参数"
        # Check if same-title volume already exists (dedup)
        existing_volumes = json_store.load_volumes(book_id)
        existing = next((v for v in existing_volumes if v.get("title") == title), None)
        if existing:
            return f"分卷「{existing['title']}」已存在 (id: {existing['id']})，无需重复创建。"
        vol = json_store.add_volume(book_id, title, story_line)
        return f"已创建分卷「{vol['title']}」(id: {vol['id']})"

    elif name == "update_volume":
        vol_id = args.get("volume_id", "")
        if not vol_id:
            return "错误: 需要 volume_id 参数"
        # Map all known field name variants (snake_case, camelCase, common typos)
        # to the canonical camelCase keys used by the storage layer.
        FIELD_MAP = {
            "title": "title",
            "order": "order",
            "story_line": "storyLine",
            "storyLine": "storyLine",
            "storyline": "storyLine",
        }
        data = {}
        skipped = []
        for arg_key, arg_val in args.items():
            if arg_key in ("volume_id", "action"):
                continue
            if arg_val is None:
                continue
            canonical = FIELD_MAP.get(arg_key)
            if canonical:
                data[canonical] = arg_val
            else:
                skipped.append(arg_key)
        if not data:
            return "错误: 至少需要 title/story_line/order 中的一个"
        try:
            vol = json_store.update_volume(book_id, vol_id, data)
            msg = f"已更新分卷「{vol['title']}」"
            if skipped:
                msg += f"（跳过未知字段: {', '.join(skipped)}）"
            return msg
        except Exception as e:
            logger.exception("volume handler failed")
            return str(e)

    elif name == "list_volumes":
        volumes = json_store.load_volumes(book_id)
        chapters = json_store.load_chapters(book_id)
        chapter_map = {c["id"]: json_store._chapter_view(c).get("title", "") for c in chapters}
        grouped_ids = set()
        for v in volumes:
            grouped_ids.update(v.get("chapters", []))

        if not volumes:
            return "当前书籍还没有分卷。使用 create_volume 创建第一个分卷。"

        # Detect duplicate titles
        from collections import Counter
        title_counts = Counter(v.get("title", "") for v in volumes)
        duplicates = {t: c for t, c in title_counts.items() if c > 1}

        lines = [f"# 分卷结构 ({len(volumes)} 卷)\n"]
        if duplicates:
            lines.append("⚠️ 警告: 存在同名分卷，请使用 delete_volume 清理重复项：")
            for t, c in duplicates.items():
                dup_ids = [v["id"] for v in volumes if v.get("title") == t]
                lines.append(f"  - 「{t}」重复 {c} 次 (IDs: {', '.join(dup_ids)})")
            lines.append("")

        for v in sorted(volumes, key=lambda x: x.get("order", 0)):
            lines.append(f"## {v['title']} (id: {v['id']})")
            if v.get("storyLine"):
                lines.append(f"  故事主线: {v['storyLine'][:200]}")
            chapters_in = v.get("chapters", [])
            if chapters_in:
                lines.append(f"  章节 ({len(chapters_in)}):")
                for cid in chapters_in:
                    lines.append(f"    - {chapter_map.get(cid, cid)}")
            else:
                lines.append("  (暂无章节)")
            lines.append("")

        ungrouped = [c for c in chapters if c["id"] not in grouped_ids]
        if ungrouped:
            lines.append(f"## 未分组章节 ({len(ungrouped)})")
            for c in ungrouped:
                view = json_store._chapter_view(c)
                lines.append(f"  - {view.get('title', '')}")
        return "\n".join(lines)

    elif name == "delete_volume":
        vol_id = args.get("volume_id", "")
        if not vol_id:
            return "错误: 需要 volume_id 参数"
        json_store.delete_volume(book_id, vol_id)
        return f"已删除分卷 (id: {vol_id})，章节保留未受影响。"

    elif name == "move_chapter_to_volume":
        chapter_id = args.get("chapter_id", "")
        vol_id = args.get("volume_id", "")
        if not chapter_id or not vol_id:
            return "错误: 需要 chapter_id 和 volume_id"
        # Resolve #N format
        if chapter_id.startswith("#"):
            chapters = json_store.load_chapters(book_id)
            try:
                idx = int(chapter_id[1:]) - 1
                if 0 <= idx < len(chapters):
                    chapter_id = chapters[idx]["id"]
            except ValueError:
                return f"无效的章节序号: {chapter_id}"
        json_store.add_chapter_to_volume(book_id, vol_id, chapter_id)
        return "已将章节移入分卷"

    elif name == "generate_volume_outlines":
        from tools.impl.plot import _generate_volume_outlines
        return _generate_volume_outlines(book_id)

    return f"未知 volume 操作: {name}"


def _handle_materials(name: str, args: dict, book_id: str) -> str:
    if name == "add_material":
        title = args.get("title", "")
        content = args.get("content", "")
        if not title:
            return "错误: 需要 title 参数"
        mat = json_store.add_material(
            title=title,
            content=content,
            tags=args.get("tags", []),
            source=args.get("source", "manual"),
            source_url=args.get("source_url", ""),
        )
        fts.index_material(mat)
        return f"已添加资料「{title}」(id: {mat['id']})"

    elif name == "search_materials":
        query = args.get("query", "")
        if not query:
            return "错误: 需要 query 参数"
        subs = json_store.load_material_subs(book_id)
        results = fts.search_materials(query, subs)
        if not results:
            return f"订阅的资料中未找到与「{query}」相关的内容。使用 browse_materials 浏览全局资料池。"
        lines = [f"# 资料搜索结果: {query}\n"]
        for r in results:
            lines.append(f"- **{r['title']}** (id: {r['id']})")
            if r.get("snippet"):
                lines.append(f"  {r['snippet']}")
        return "\n".join(lines)

    elif name == "browse_materials":
        query = args.get("query", "")
        tags = args.get("tags", [])
        if query:
            results = fts.search_materials(query, None)  # No subscription filter
        else:
            mats = json_store.load_materials()
            if tags:
                mats = [m for m in mats if set(tags) & set(m.get("tags", []))]
            results = [{"id": m["id"], "title": m["title"],
                        "tags": m.get("tags", []),
                        "snippet": m.get("content", "")[:80]}
                       for m in mats[-20:]]
        if not results:
            return "资料库为空或未找到匹配结果。"
        lines = ["# 全局资料库" + (f" 搜索: {query}" if query else " (最近20条)") + "\n"]
        for r in results:
            tags_str = f" [{', '.join(r.get('tags', []))}]" if r.get("tags") else ""
            lines.append(f"- **{r['title']}**{tags_str} (id: {r['id']})")
            if r.get("snippet"):
                lines.append(f"  {r['snippet']}")
        return "\n".join(lines)

    elif name == "subscribe_material":
        mid = args.get("material_id", "")
        if not mid:
            return "错误: 需要 material_id"
        try:
            mat = json_store.get_material(mid)
        except Exception:
            return f"资料不存在: {mid}"
        json_store.subscribe_material(book_id, mid)
        return f"已订阅资料「{mat['title']}」"

    elif name == "unsubscribe_material":
        mid = args.get("material_id", "")
        if not mid:
            return "错误: 需要 material_id"
        json_store.unsubscribe_material(book_id, mid)
        return f"已取消订阅资料 (id: {mid})"

    elif name == "delete_material":
        mid = args.get("material_id", "")
        if not mid:
            return "错误: 需要 material_id"
        json_store.delete_material(mid)
        fts.remove_material(mid)
        return f"已永久删除资料 (id: {mid})"

    elif name == "set_reference_books":
        ref_ids = args.get("book_ids", [])
        if not ref_ids:
            json_store.set_reference_books(book_id, [])
            return "已清除所有参考书。"
        books = json_store.load_books()
        valid_ids = []
        names = []
        invalid_ids = []
        for ref_id in ref_ids:
            b = next((b for b in books if b["id"] == ref_id), None)
            if b:
                valid_ids.append(ref_id)
                names.append(b["title"])
            else:
                invalid_ids.append(ref_id)
        if invalid_ids:
            return f"❌ 以下ID不存在，无法设为参考书: {', '.join(invalid_ids)}\n使用 list_books 查看可用的项目ID。"
        json_store.set_reference_books(book_id, valid_ids)
        return f"已设置参考书: {', '.join(names)}"

    elif name == "list_books":
        books = json_store.load_books()
        if not books:
            return "系统中没有项目。"
        lines = ["# 可用项目\n"]
        for b in books:
            if b["id"] == book_id:
                continue  # Skip current book
            entity_count = b.get("stats", {}).get("entity_count", 0)
            chapter_count = b.get("stats", {}).get("chapter_count", 0)
            lines.append(f"- **{b['title']}** (id: {b['id']})")
            lines.append(f"  实体: {entity_count} | 章节: {chapter_count}")
        if len(lines) == 1:
            return "没有其他项目可设为参考书。"
        return "\n".join(lines)

    elif name == "list_references":
        ref_ids = json_store.get_reference_books(book_id)
        if not ref_ids:
            return "当前项目未设置参考书。使用 set_reference_books 指定。"
        books = json_store.load_books()
        lines = ["# 参考书\n"]
        for ref_id in ref_ids:
            b = next((b for b in books if b["id"] == ref_id), None)
            if b:
                lines.append(f"- **{b['title']}**")
                lines.append(f"  实体: {b.get('entityCount', 0)} | 章节: {b.get('chapterCount', 0)}")
            else:
                lines.append(f"- {ref_id} (项目已删除)")
        return "\n".join(lines)

    elif name == "list_reference_chapters":
        ref_ids = json_store.get_reference_books(book_id)
        if not ref_ids:
            return "当前项目未设置参考书。使用 set_reference_books 指定。"
        ref_book_id = args.get("ref_book_id", "")
        if ref_book_id:
            # Filter to specific reference book
            ref_ids = [r for r in ref_ids if r == ref_book_id or r.startswith(ref_book_id)]
            if not ref_ids:
                return f"参考书 {ref_book_id} 不存在或未设置。"
        lines = ["# 参考书章节列表\n"]
        lines.append("使用 write_chapter/delegate_writing 的 ref_chapters 参数可注入原著章节原文。\n")
        for ref_id in ref_ids:
            try:
                ref_book = json_store.get_book(ref_id)
                ref_chapters = json_store.load_chapters(ref_id)
                lines.append(f"\n## {ref_book.get('title', ref_id)} (id: {ref_id})")
                lines.append(f"共 {len(ref_chapters)} 章\n")
                for i, ch in enumerate(ref_chapters[:30]):
                    view = json_store._chapter_view(ch)
                    chars = len(view.get("content", ""))
                    lines.append(f"- #{i+1} {view.get('title', '?')} ({chars}字) id: {view['id']}")
                if len(ref_chapters) > 30:
                    lines.append(f"... (还有 {len(ref_chapters) - 30} 章)")
            except Exception as e:
                logger.exception("volume handler failed")
                lines.append(f"\n## {ref_id} (加载失败: {str(e)[:50]})")
        return "\n".join(lines)

    elif name == "search_reference":
        query = args.get("query", "")
        if not query:
            return "错误: 需要 query 参数"
        ref_ids = json_store.get_reference_books(book_id)
        if not ref_ids:
            return "当前项目未设置参考书。使用 set_reference_books 指定。"
        from core.graph_store import GraphStore
        lines = [f"# 参考书搜索: {query}\n"]
        found = 0
        for ref_id in ref_ids:
            try:
                ref_book = json_store.get_book(ref_id)
                ref_kb = GraphStore(ref_id)
                ref_kb.init_schema()
                entities = ref_kb.list_entities()
                matching = [e for e in entities if query.lower() in e.name.lower() or
                           query.lower() in str(e.data).lower()]
                if matching:
                    lines.append(f"## {ref_book.get('title', ref_id)}")
                    for e in matching[:10]:
                        data_preview = ", ".join(f"{k}: {str(v)[:30]}" for k, v in
                            list(e.data.items())[:4] if v)
                        lines.append(f"- **{e.name}** [{e.type}]")
                        if data_preview:
                            lines.append(f"  {data_preview}")
                    found += len(matching)
                ref_kb.close()
            except Exception:
                lines.append(f"\n## {ref_id} (查询失败)")
        if found == 0:
            lines.append("未找到匹配的实体。")
        return "\n".join(lines)

    elif name == "migrate_reference_knowledge":
        ref_book_id = args.get("ref_book_id", "")
        entity_name = args.get("entity_name", "")
        new_name = args.get("new_name", "")
        new_data = args.get("new_data", {})
        if not ref_book_id or not entity_name:
            return "错误: 需要 ref_book_id 和 entity_name 参数"
        ref_ids = json_store.get_reference_books(book_id)
        if ref_book_id not in ref_ids:
            return f"错误: {ref_book_id} 不是当前书的参考书（当前参考书: {ref_ids}）"
        from core.graph_store import GraphStore
        try:
            ref_book = json_store.get_book(ref_book_id)
        except Exception:
            return f"错误: 参考书 {ref_book_id} 不存在"
        ref_kb = GraphStore(ref_book_id)
        ref_kb.init_schema()
        entity = ref_kb.get_entity_by_name(entity_name)
        if not entity:
            # Try by partial match
            entities = ref_kb.list_entities()
            matching = [e for e in entities if entity_name.lower() in e.name.lower()]
            ref_kb.close()
            if matching:
                names = ", ".join(e.name for e in matching[:10])
                return f"未找到精确匹配 '{entity_name}'。可能的匹配: {names}"
            return f"参考书「{ref_book.get('title', ref_book_id)}」中未找到实体: {entity_name}"

        # Build the new entity (copy with new ID, optionally modified)
        import uuid as _uuid
        final_name = new_name or entity.name
        final_data = dict(entity.data)
        if new_data:
            final_data.update(new_data)

        new_entity_id = _uuid.uuid4().hex[:16]
        new_entity = Entity(
            id=new_entity_id,
            type=entity.type,
            name=final_name,
            aliases=list(entity.aliases),
            data=final_data,
        )

        ref_kb.close()

        # Write to current book's graph
        curr_kb = GraphStore(book_id)
        curr_kb.init_schema()
        curr_kb.add_entity(new_entity)
        entities = curr_kb.list_entities()
        curr_kb.close()

        json_store.update_book_stats(book_id, entity_count=len(entities))

        mod_desc = ""
        if new_name and new_name != entity.name:
            mod_desc += f"，更名为「{new_name}」"
        if new_data:
            changed_keys = list(new_data.keys())
            mod_desc += f"，修改字段: {', '.join(changed_keys)}"

        return f"已从参考书「{ref_book.get('title', ref_book_id)}」迁移实体「{entity.name}」[{entity.type}]到本书(mod_desc)。新实体ID: {new_entity_id}\n\n⚠️ 参考书中的原实体未被修改。"

    return f"未知 materials 操作: {name}"


def _handle_knowledge_edit(name: str, args: dict, book_id: str) -> str:
    from core.graph_store import GraphStore
    if name == "delete_entity":
        eid = args.get("entity_id", "")
        if not eid:
            return "错误: 需要 entity_id 参数"
        kb = GraphStore(book_id)
        kb.init_schema()
        # Try by ID first, then by name
        entity = kb.get_entity(eid)
        if not entity:
            entity = kb.get_entity_by_name(eid)
        if not entity:
            return f"未找到实体: {eid}"
        kb.delete_entity(entity.id)
        from core.search import fts as fts_engine
        try:
            fts_engine.remove_entity(entity.id)
        except Exception:
            logger.warning("Failed to remove entity %s from FTS index", entity.id)
        return f"已删除实体「{entity.name}」(id: {entity.id})"

    elif name == "update_entity":
        eid = args.get("entity_id", "")
        data = args.get("data", {})
        # LLMs sometimes emit data as a JSON string instead of an object.
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                return f"更新失败: data 参数必须是对象，但收到字符串: {data[:80]!r}"
        if not isinstance(data, dict):
            return f"更新失败: data 必须是键值对对象，收到 {type(data).__name__}"
        if not eid or not data:
            return "错误: 需要 entity_id 和 data 参数"
        kb = GraphStore(book_id)
        kb.init_schema()
        entity = kb.get_entity(eid)
        if not entity:
            entity = kb.get_entity_by_name(eid)
        if not entity:
            return f"未找到实体: {eid}"
        merged = dict(entity.data)
        merged.update(data)
        kb.update_entity(entity.id, merged)
        from core.search import fts as fts_engine
        fts_engine.index_entity(kb.project_id, entity.id, entity.name, entity.type, entity.aliases, merged)
        return f"已更新实体「{entity.name}」，修改了 {len(data)} 个字段: {', '.join(data.keys())}"

    elif name == "set_character_phase":
        cid = args.get("character_id", "")
        phase_name = args.get("phase", "")
        if not cid or not phase_name:
            return "错误: 需要 character_id 和 phase 参数"
        kb = GraphStore(book_id)
        kb.init_schema()
        entity = kb.get_entity(cid) or kb.get_entity_by_name(cid)
        if not entity:
            return f"未找到角色: {cid}"
        if entity.type != "character":
            return f"错误: {cid} 不是角色实体 (当前类型: {entity.type})"

        data = args.get("data", {}) or {}
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                return f"错误: data 必须是对象，收到字符串: {data[:80]!r}"
        if not isinstance(data, dict):
            return f"错误: data 必须是键值对对象，收到 {type(data).__name__}"

        # Auto-generate stable phase_key if caller didn't supply one.
        phase_key = args.get("phase_key", "") or (
            f"arc{sum(1 for s in kb.list_snapshots(character_entity_id=entity.id) if s.phase) + 1}"
        )
        # New phases default to "current" — phase selection is order-based
        # (is_current / time_order) and decoupled from chapters, so the latest
        # phase created should normally become the active one for writing.
        is_current = bool(args.get("is_current", True))
        description = args.get("description", "") or ""

        # time_order = previous max + 1, so the new phase sorts after existing ones.
        existing = kb.list_snapshots(character_entity_id=entity.id)
        next_order = (max((s.time_order for s in existing), default=-1) + 1) if existing else 0

        import uuid as _uuid

        from core.knowledge import CharacterSnapshot
        snap = CharacterSnapshot(
            id=str(int(datetime.now().timestamp() * 1000)) + _uuid.uuid4().hex[:4],
            character_entity_id=entity.id,
            time_point=phase_name,
            time_order=next_order,
            label=phase_name,
            data=data,
            description=description,
            phase=phase_name,
            phase_key=phase_key,
            is_current=is_current,
        )
        kb.add_snapshot(snap)
        arc_count = sum(1 for s in kb.list_snapshots(character_entity_id=entity.id) if s.phase)
        suffix = " (当前阶段)" if is_current else ""
        return (
            f"已为角色「{entity.name}」创建阶段「{phase_name}」"
            f"[{phase_key}]，当前共 {arc_count} 个阶段{suffix}。"
            f"写章节时系统会自动注入该角色当前阶段的角色卡，无需绑定具体章节。"
        )

    elif name == "delete_worldbuilding_entry":
        args.get("category", "")
        eid = args.get("entry_id", "")
        if not eid:
            return "错误: 需要 entry_id 参数"
        json_store.delete_worldbuilding_entry(book_id, eid)
        return f"已删除世界观条目 (id: {eid})"

    elif name == "update_worldbuilding_entry":
        eid = args.get("entry_id", "")
        data = args.get("data", {})
        if not eid or not data:
            return "错误: 需要 entry_id 和 data 参数"
        json_store.update_worldbuilding_entry(book_id, eid, data)
        return f"已更新世界观条目 (id: {eid})"

    elif name == "delete_timeline_event":
        eid = args.get("event_id", "")
        if not eid:
            return "错误: 需要 event_id 参数"
        json_store.delete_timeline_event(book_id, eid)
        kb = GraphStore(book_id)
        kb.init_schema()
        try:
            kb.delete_timeline_event(eid)
        except Exception:
            logger.warning("Failed to delete timeline event %s from Neo4j (may already be removed)", eid)
        return f"已删除时间线事件 (id: {eid})"

    elif name == "delete_foreshadow":
        fid = args.get("foreshadow_id", "")
        if not fid:
            return "错误: 需要 foreshadow_id 参数"
        kb = GraphStore(book_id)
        kb.init_schema()
        kb._run("MATCH (f:Fore {id: $id, project_id: $pid}) DETACH DELETE f",
                {"id": fid, "pid": book_id})
        return f"已删除伏笔 (id: {fid})"

    elif name == "plan_foreshadow":
        fid = args.get("foreshadow_id", "")
        arc = args.get("planned_arc", "")
        if not fid or not arc:
            return "错误: 需要 foreshadow_id 和 planned_arc 参数"
        kb = GraphStore(book_id)
        kb.init_schema()
        kb.set_foreshadow_planned(fid, arc)
        return f"伏笔 {fid} 已规划回收弧: 「{arc}」"

    elif name == "schedule_foreshadow":
        fid = args.get("foreshadow_id", "")
        chapter = args.get("chapter", "")
        if not fid or not chapter:
            return "错误: 需要 foreshadow_id 和 chapter 参数"
        kb = GraphStore(book_id)
        kb.init_schema()
        kb.schedule_foreshadow(fid, chapter)
        return f"伏笔 {fid} 已排入 {chapter} 回收"

    elif name == "postpone_foreshadow":
        fid = args.get("foreshadow_id", "")
        if not fid:
            return "错误: 需要 foreshadow_id 参数"
        kb = GraphStore(book_id)
        kb.init_schema()
        kb.postpone_foreshadow(fid)
        return f"伏笔 {fid} 已推迟，状态退回'已规划'"

    elif name == "resolve_foreshadow":
        fid = args.get("foreshadow_id", "")
        resolution = args.get("resolution_text", "")
        if not fid or not resolution:
            return "错误: 需要 foreshadow_id 和 resolution_text 参数"
        kb = GraphStore(book_id)
        kb.init_schema()
        kb.resolve_foreshadow(fid, resolution)
        return f"伏笔 {fid} 已标记为回收: {resolution[:80]}"

    elif name == "list_pending_foreshadows":
        kb = GraphStore(book_id)
        kb.init_schema()
        planned = kb.list_foreshadows(status="planned")
        due = kb.list_foreshadows(status="due")
        if not planned and not due:
            return "没有待处理的伏笔。"
        lines = ["## 待处理伏笔"]
        if due:
            lines.append(f"\n### 到期等待确认 ({len(due)}个)")
            for f in due:
                arc = f" [弧: {f.planned_resolve_arc}]" if f.planned_resolve_arc else ""
                lines.append(f"- 🔴 {f.text[:50]}{arc}")
        if planned:
            lines.append(f"\n### 已规划尚未到期 ({len(planned)}个)")
            for f in planned:
                arc = f" [弧: {f.planned_resolve_arc}]" if f.planned_resolve_arc else ""
                lines.append(f"- 🟡 {f.text[:50]}{arc}")
        return "\n".join(lines)

    return f"未知知识编辑操作: {name}"
