import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from .graph_store import GraphStore
from .knowledge import Entity, EntityType, Foreshadow, KnowledgeProposal, Relation, RelationType
from .llm_client import chat, get_mode
from .plugin_loader import plugin_manager
from .prompts import load_prompt
from .schemas import ALL_SCHEMAS, build_schema_prompt
from .search import fts as fts_engine
from .utils import extract_json_from_response

BATCH_SIZE = 4

logger = logging.getLogger(__name__)

try:
    import spacy
    _nlp = None
    _NER_AVAILABLE = False
    try:
        _nlp = spacy.load("zh_core_web_sm")
        _NER_AVAILABLE = True
    except OSError:
        try:
            _nlp = spacy.load("zh_core_web_md")
            _NER_AVAILABLE = True
        except OSError:
            try:
                _nlp = spacy.load("en_core_web_sm")
                _NER_AVAILABLE = True
            except OSError:
                logger.info("spaCy model not found, NER pre-pass disabled (install zh_core_web_sm to enable)")
except ImportError:
    _NER_AVAILABLE = False
    logger.info("spaCy not installed, NER pre-pass disabled")


NER_TYPE_MAP = {
    "PERSON": EntityType.CHARACTER,
    "GPE": EntityType.LOCATION,
    "LOC": EntityType.LOCATION,
    "ORG": EntityType.ORGANIZATION,
    "FAC": EntityType.LOCATION,
    "PRODUCT": EntityType.ITEM,
    "EVENT": EntityType.EVENT,
    "WORK_OF_ART": EntityType.ITEM,
    "NORP": EntityType.CONCEPT,
}


def _ner_prescan(text: str, existing_names: set[str]) -> list[dict]:
    """Use spaCy NER to prescan entities, returns candidates for LLM validation."""
    if not _NER_AVAILABLE or _nlp is None:
        return []
    doc = _nlp(text[:80000])
    seen = set()
    candidates = []
    for ent in doc.ents:
        label = ent.label_.upper()
        entity_type = NER_TYPE_MAP.get(label)
        if not entity_type:
            continue
        name = ent.text.strip()
        if not name or len(name) < 2 or len(name) > 30:
            continue
        if name.lower() in existing_names:
            continue
        dedup_key = f"{entity_type.value}:{name}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        candidates.append({"type": entity_type.value, "name": name})
    return candidates

def _get_extraction_system() -> str:
    """Load the main extraction system prompt from the template file."""
    return load_prompt("extraction_system")


def extract_from_text(text: str, existing_knowledge: str = "", book_id: str = "default") -> KnowledgeProposal:
    plugin_manager.call_hook("on_extract_before", text=text, book_id=book_id)
    if get_mode() == "split":
        proposal = _extract_split_mode(text, existing_knowledge, book_id)
    else:
        proposal = _extract_quality_mode(text, existing_knowledge, book_id)
    plugin_manager.call_hook("on_extract_after", proposal=proposal, book_id=book_id)
    return proposal


def extract_stream(text: str, existing_knowledge: str = "", book_id: str = "default"):
    """Generator version: yields progress events, then final result."""
    yield {"event": "progress", "data": {"stage": "开始分析文本", "detail": f"模式: {get_mode()}"}}

    if get_mode() == "split":
        yield from _extract_split_stream(text, existing_knowledge, book_id)
    else:
        yield from _extract_quality_stream(text, existing_knowledge, book_id)


def _extract_quality_mode(text: str, existing_knowledge: str, book_id: str) -> KnowledgeProposal:
    schema_text = build_schema_prompt()
    system = _get_extraction_system().replace("{schemas}", schema_text)

    prompt = ""
    if existing_knowledge:
        kb_summary = _summarize_entities(existing_knowledge, book_id)
        if kb_summary:
            prompt += f"## 已有实体列表（注意避免重复创建）\n{kb_summary}\n\n"
    prompt += f"## 待提取文本\n{text}\n\n请输出 JSON："

    response = chat(prompt, system=system, temperature=0.15, task="extraction")
    return _parse_proposal(response)


def _ner_augmented_scan(text: str, existing_knowledge: str, book_id: str) -> KnowledgeProposal:
    """NER-enhanced extraction: spaCy prescans candidates → LLM validates + fills attributes.

    Falls back to pure LLM Pass 1 if NER is not available.
    """
    merged = KnowledgeProposal()

    existing_names = set()
    if existing_knowledge:
        store = GraphStore(book_id)
        for e in store.list_entities():
            existing_names.add(e.name.lower())
            for a in e.aliases:
                existing_names.add(a.lower())

    # Pre-scan with NER
    ner_candidates = _ner_prescan(text, existing_names)
    ner_hint = ""
    if ner_candidates:
        by_type = {}
        for c in ner_candidates:
            by_type.setdefault(c["type"], []).append(c["name"])
        ner_lines = ["NER预扫描发现的候选实体:"]
        for t, names in by_type.items():
            ner_lines.append(f"  [{t}] {', '.join(names[:8])}")
        ner_hint = "\n".join(ner_lines)

    # Pass 1: LLM scan with NER hints
    pass1_system = load_prompt("extraction_pass1")

    pass1_prompt = ""
    if existing_knowledge:
        kb_summary = _summarize_entities(existing_knowledge, book_id)
        if kb_summary:
            pass1_prompt += f"## 已有实体（避免重复）\n{kb_summary}\n\n"
    if ner_hint:
        pass1_prompt += f"## 来自NER的候选实体（请验证确认，排除误报）\n{ner_hint}\n\n"
    pass1_prompt += f"## 文本\n{text}\n\n输出 JSON："

    r1 = chat(pass1_prompt, system=pass1_system, temperature=0.1, task="extraction")
    rough = _parse_proposal(r1)

    if not rough.entities:
        return merged

    merged.relations = rough.relations
    merged.foreshadows = rough.foreshadows

    # Pass 2: Parallel batch deep fill (4 entities per LLM call, all batches in parallel)
    all_entities = []
    batches = []
    for batch_start in range(0, len(rough.entities), BATCH_SIZE):
        batches.append(rough.entities[batch_start:batch_start + BATCH_SIZE])

    if batches:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=min(len(batches), 6)) as executor:
            futures = {executor.submit(_extract_batch, batch, text): i for i, batch in enumerate(batches)}
            for future in as_completed(futures):
                try:
                    all_entities.extend(future.result())
                except (RuntimeError, ValueError, OSError) as e:
                    logger.warning(f"Entity extraction task failed: {e}")

    merged.entities = all_entities
    return merged


def _extract_split_mode(text: str, existing_knowledge: str, book_id: str) -> KnowledgeProposal:
    """2-pass extraction using Flash (or NER+LLM if spaCy available)."""
    if _NER_AVAILABLE:
        return _ner_augmented_scan(text, existing_knowledge, book_id)
    return _legacy_extract_split_mode(text, existing_knowledge, book_id)


def _legacy_extract_split_mode(text: str, existing_knowledge: str, book_id: str) -> KnowledgeProposal:
    """Original 2-pass extraction (fallback when NER unavailable)."""
    merged = KnowledgeProposal()

    # --- Pass 1: Quick sweep to identify all entities ---
    pass1_system = load_prompt("extraction_pass1")

    pass1_prompt = ""
    if existing_knowledge:
        kb_summary = _summarize_entities(existing_knowledge, book_id)
        if kb_summary:
            pass1_prompt += f"## 已有实体（避免重复）\n{kb_summary}\n\n"
    pass1_prompt += f"## 文本\n{text}\n\n输出 JSON："

    r1 = chat(pass1_prompt, system=pass1_system, temperature=0.1, task="extraction")
    rough = _parse_proposal(r1)

    if not rough.entities:
        return merged

    merged.relations = rough.relations
    merged.foreshadows = rough.foreshadows

    # --- Pass 2: Parallel batch deep fill (all batches in parallel) ---
    all_entities = []
    batches = []
    for batch_start in range(0, len(rough.entities), BATCH_SIZE):
        batches.append(rough.entities[batch_start:batch_start + BATCH_SIZE])

    if batches:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=min(len(batches), 6)) as executor:
            futures = {executor.submit(_extract_batch, batch, text): i for i, batch in enumerate(batches)}
            for future in as_completed(futures):
                try:
                    all_entities.extend(future.result())
                except (RuntimeError, ValueError, OSError) as e:
                    logger.warning(f"Relation extraction task failed: {e}")

    merged.entities = all_entities
    return merged


def _summarize_entities(knowledge_text: str, book_id: str = "default") -> str:
    """Build a compact existing entity summary from the knowledge base."""
    store = GraphStore(book_id)
    entities = store.list_entities()
    if not entities:
        return ""

    lines = []
    for e in entities:
        aliases_str = f"（{', '.join(e.aliases)}）" if e.aliases else ""
        lines.append(f"- [{e.id}] [{e.type}] {e.name}{aliases_str}")
        for k, v in e.data.items():
            if isinstance(v, dict):
                inner = ", ".join(f"{ik}: {iv}" for ik, iv in v.items() if iv)
                if inner:
                    lines.append(f"  {k}: {inner}")
            elif v:
                lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def _extract_quality_stream(text: str, existing_knowledge: str, book_id: str):
    yield {"event": "progress", "data": {"stage": "正在分析文本...", "detail": "Pro 单次高质量提取"}}
    result = _extract_quality_mode(text, existing_knowledge, book_id)
    yield {"event": "progress", "data": {"stage": "分析完成", "detail": f"识别 {len(result.entities)} 个实体, {len(result.relations)} 条关系"}}
    yield {"event": "result", "data": _proposal_to_dict(result)}


def _extract_one(entity, text):
    e_schema = ALL_SCHEMAS.get(entity.type, {})
    blocks_desc = []
    for bk, bv in e_schema.items():
        blocks_desc.append(f"  {bk}: {', '.join(bv['fields'].keys())}")
    sys = f"Extract one entity's attributes.\nFields:\n{chr(10).join(blocks_desc)}\nOutput: {{\"data\":{{\"basic\":{{...}},\"appearance\":{{...}}}}}}"
    prompt = f"Text:\n{text}\n\nExtract '{entity.name}' ({entity.type}). JSON:"
    r = chat(prompt, system=sys, temperature=0.1, task="extraction")
    detail = _parse_single_entity(r)
    flat = {}
    for block_data in detail.values():
        if isinstance(block_data, dict):
            for fk, fv in block_data.items():
                if fv:
                    flat[fk] = fv
    return Entity(id=str(uuid.uuid4())[:8], type=entity.type, name=entity.name, aliases=entity.aliases, data=flat)


def _extract_batch(entities: list, text: str) -> list[Entity]:
    """Batch extract attributes for multiple entities in a single LLM call."""
    if not entities:
        return []
    if len(entities) == 1:
        return [_extract_one(entities[0], text)]

    entity_list = "\n".join(f"- [{e.type}] {e.name}" for e in entities)

    schemas_needed = {}
    for e in entities:
        if e.type not in schemas_needed:
            blocks = []
            e_schema = ALL_SCHEMAS.get(e.type, {})
            for bk, bv in e_schema.items():
                blocks.append(f"  {bk}（{bv['label']}）: {', '.join(bv['fields'].keys())}")
            schemas_needed[e.type] = "\n".join(blocks)

    schema_text = "\n\n".join(
        f"[{t}] 模板:\n{desc}" for t, desc in schemas_needed.items()
    )

    system = load_prompt("extraction_batch").replace("{schema_text}", schema_text)

    prompt = f"文本：\n{text}\n\n请提取以下实体的全部属性：\n{entity_list}\n\n输出 JSON："

    response = chat(prompt, system=system, temperature=0.1, task="extraction")
    return _parse_batch_result(response, entities)


def _parse_batch_result(response: str, entities: list) -> list[Entity]:
    json_str = extract_json_from_response(response)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return [_extract_one(e, "") for e in entities]

    entity_list = data.get("entities", [])
    name_map = {}
    for e in entities:
        name_map[e.name] = e
        for a in e.aliases:
            name_map[a] = e

    results = []
    for entry in entity_list:
        name = entry.get("name", "")
        etype = entry.get("type", "character")

        original = name_map.get(name)
        if not original:
            original = next((e for e in entities if e.name.lower() == name.lower()), None)
        if not original:
            continue

        raw_data = entry.get("data", {})
        flat = {}
        for block in raw_data.values():
            if isinstance(block, dict):
                for fk, fv in block.items():
                    if fv:
                        flat[fk] = fv

        results.append(Entity(
            id=str(uuid.uuid4())[:8],
            type=etype,
            name=name,
            aliases=original.aliases if original else [],
            data=flat,
        ))

    extracted_names = {r.name for r in results}
    for e in entities:
        if e.name not in extracted_names:
            results.append(Entity(
                id=str(uuid.uuid4())[:8],
                type=e.type, name=e.name,
                aliases=e.aliases, data={},
            ))

    return results


def _extract_split_stream(text: str, existing_knowledge: str, book_id: str):
    merged = KnowledgeProposal()

    yield {"event": "progress", "data": {"stage": "Step 0: NER pre-scan", "detail": "Running spaCy NER to pre-identify entities" if _NER_AVAILABLE else "（NER模块未加载，跳过）"}}

    existing_names = set()
    if existing_knowledge:
        store = GraphStore(book_id)
        for e in store.list_entities():
            existing_names.add(e.name.lower())
            for a in e.aliases:
                existing_names.add(a.lower())

    ner_candidates = _ner_prescan(text, existing_names)
    ner_hint = ""
    if ner_candidates:
        by_type = {}
        for c in ner_candidates:
            by_type.setdefault(c["type"], []).append(c["name"])
        ner_lines = ["NER候选实体:"]
        for t, names in by_type.items():
            ner_lines.append(f"  [{t}] {', '.join(names[:8])}")
        ner_hint = "\n".join(ner_lines)
        yield {"event": "progress", "data": {"stage": f"NER完成: {len(ner_candidates)} 个候选", "detail": ner_hint}}

    yield {"event": "progress", "data": {"stage": "Step 1: scanning", "detail": "Identifying entities and relations"}}
    pass1_system = load_prompt("extraction_pass1")
    pass1_prompt = ""
    if existing_knowledge:
        kb_summary = _summarize_entities(existing_knowledge, book_id)
        if kb_summary:
            pass1_prompt += f"Existing entities:\n{kb_summary}\n\n"
    if ner_hint:
        pass1_prompt += f"NER candidates (please validate):\n{ner_hint}\n\n"
    pass1_prompt += f"Text:\n{text}\n\nOutput JSON:"
    r1 = chat(pass1_prompt, system=pass1_system, temperature=0.1, task="extraction")
    rough = _parse_proposal(r1)

    if not rough.entities:
        yield {"event": "progress", "data": {"stage": "Scan complete", "detail": "No entities found"}}
        yield {"event": "result", "data": _proposal_to_dict(merged)}
        return

    total = len(rough.entities)
    yield {"event": "progress", "data": {"stage": f"Step 1 done: {total} 个实体", "detail": f"发现 {len(rough.relations)} 条关系, {len(rough.foreshadows)} 个伏笔 — 开始并行提取属性", "found": total}}
    merged.relations = rough.relations
    merged.foreshadows = rough.foreshadows

    # Parallel Pass 2
    results = {}
    completed = 0

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(_extract_one, e, text): e for e in rough.entities}
        for future in as_completed(futures):
            entity = futures[future]
            try:
                results[entity.name] = future.result()
            except (RuntimeError, ValueError, OSError) as exc:
                logger.warning(f"Entity update task failed for {entity.name}: {exc}")
            completed += 1
            # Yield progress every entity (throttled by executor completion)
            yield {"event": "progress", "data": {"stage": f"Step 2: 提取属性 ({completed}/{total})", "detail": f"已完成 {entity.name}", "done": completed, "total": total}}

    for e in rough.entities:
        if e.name in results:
            merged.entities.append(results[e.name])

    yield {"event": "progress", "data": {"stage": "Extraction complete", "detail": f"{len(merged.entities)} entities, {len(merged.relations)} relations, {len(merged.foreshadows)} foreshadows"}}
    yield {"event": "result", "data": _proposal_to_dict(merged)}


def _proposal_to_dict(p: KnowledgeProposal) -> dict:
    return {
        "entities": [{"id": e.id, "type": e.type, "name": e.name, "aliases": e.aliases, "data": e.data} for e in p.entities],
        "relations": [{"id": r.id, "from": r.from_entity, "to": r.to_entity, "type": r.type} for r in p.relations],
        "foreshadows": [{"id": f.id, "text": f.text, "hint": f.hint} for f in p.foreshadows],
    }


def _parse_proposal(response: str) -> KnowledgeProposal:
    json_str = extract_json_from_response(response)

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return KnowledgeProposal()

    def make_id() -> str:
        return str(uuid.uuid4())[:8]

    entities = []
    for e in data.get("entities", []):
        etype = e.get("type", "character")

        name = e.get("name", "")
        raw_data = e.get("data", {})
        existing_id = e.get("existing_id", "")

        structured_data = {}
        schema = ALL_SCHEMAS.get(etype, {})
        for block_key in schema:
            block = raw_data.get(block_key, {})
            if isinstance(block, dict) and any(v for v in block.values() if v):
                structured_data[block_key] = {k: v for k, v in block.items() if v}

        flat_props = {}
        for block_key, block_fields in structured_data.items():
            for fk, fv in block_fields.items():
                if fv:
                    flat_props[fk] = fv

        entity = Entity(
            id=existing_id or make_id(),
            type=etype,
            name=name,
            aliases=e.get("aliases", []),
            data=flat_props,
        )
        entities.append(entity)

    relations = []
    for r in data.get("relations", []):
        raw_type = r.get("type", "")
        if not raw_type:
            continue
        try:
            rtype = RelationType(raw_type.lower())
        except ValueError:
            continue
        relations.append(Relation(
            id=make_id(),
            from_entity=r.get("from", ""),
            to_entity=r.get("to", ""),
            type=rtype,
            data=r.get("data", {}),
        ))

    foreshadows = []
    for f in data.get("foreshadows", []):
        resolve_ch = f.get("resolve_chapter", "")
        fs = Foreshadow(
            id=make_id(),
            text=f.get("text", ""),
            hint=f.get("hint", ""),
            expected_resolution=f.get("expected_resolution", ""),
            plant_chapter=f.get("plant_chapter", ""),
            confidence=f.get("confidence", "high"),
            resolve_keywords=f.get("resolve_keywords", []) if isinstance(f.get("resolve_keywords", []), list) else [],
        )
        # If LLM identified this chapter as resolving a previous foreshadow
        if resolve_ch:
            fs.resolve_chapter = resolve_ch
            fs.status = "resolved"
            fs.resolved = True
            fs.resolution_text = f.get("resolution_text", f.get("expected_resolution", ""))
        foreshadows.append(fs)

    timeline_events = []
    for te in data.get("timeline_events", []):
        timeline_events.append({
            "time_order": te.get("time_order", 0),
            "label": te.get("label", ""),
            "chapter_ref": te.get("chapter_ref", ""),
            "characters": te.get("characters", []),
            "location": te.get("location", ""),
            "arc_id": te.get("arc_id", ""),
            "narrative_time": te.get("narrative_time", ""),
        })

    spatial_relations = []
    for sr in data.get("spatial_relations", []):
        spatial_relations.append({
            "from": sr.get("from", ""),
            "to": sr.get("to", ""),
            "type": sr.get("type", "located_in"),
            "label": sr.get("label", ""),
        })

    return KnowledgeProposal(entities=entities, relations=relations, foreshadows=foreshadows, timeline_events=timeline_events, spatial_relations=spatial_relations)


def _parse_single_entity(response: str) -> dict:
    """Parse a single entity detail JSON from a response string."""
    json_str = extract_json_from_response(response)
    try:
        data = json.loads(json_str)
        return data.get("data", data)
    except json.JSONDecodeError:
        return {}


def accept_proposal(proposal: KnowledgeProposal, project_id: str = "default") -> str:
    store = GraphStore(project_id)
    store.init_schema()
    existing_entities = {e.name.lower(): e for e in store.list_entities()}
    name_to_id: dict[str, str] = {}
    new_count = 0
    updated_count = 0

    # Same-batch dedupe pools — prevents LLM emittingting "尼尔" and
    # "尼尔·克劳" as two separate new_entities in one pass and ending up
    # with two rows in DB (the root cause of the agent later claiming
    # duplicates exist).
    _seen_lower: dict[str, Entity] = {}
    for e in store.list_entities():
        _seen_lower[e.name.lower()] = e
        for a in e.aliases:
            _seen_lower.setdefault(a.lower(), e)

    def _merge_into(target_entity: Entity, source: Entity):
        for k, v in source.data.items():
            if v:
                target_entity.data[k] = v
        for a in source.aliases:
            if a and a not in target_entity.aliases and a != target_entity.name:
                target_entity.aliases.append(a)

    for entity in proposal.entities:
        has_id = bool(entity.id and entity.id in {e.id for e in store.list_entities()})
        existing = store.get_entity(entity.id) if has_id else existing_entities.get(entity.name.lower())
        if not existing:
            existing = _seen_lower.get(entity.name.lower())

        # Same-batch duplicate: merge into the already-seen proposal entity
        prev = _seen_lower.get(entity.name.lower())
        if prev is not None and prev is not existing:
            _merge_into(prev, entity)
            for a in entity.aliases:
                if a:
                    name_to_id[a] = prev.id
            name_to_id[entity.name] = prev.id
            entity.id = prev.id
            updated_count += 1
            continue

        if existing:
            merged_data = {**existing.data, **entity.data}
            store.update_entity(existing.id, merged_data)
            entity.id = existing.id
            updated_count += 1
        else:
            store.add_entity(entity)
            new_count += 1

        _seen_lower[entity.name.lower()] = entity
        for a in entity.aliases:
            if a:
                _seen_lower.setdefault(a.lower(), entity)

        name_to_id[entity.name] = entity.id
        for alias in entity.aliases:
            name_to_id[alias] = entity.id

    try:
        for entity in proposal.entities:
            if entity.id:
                fts_engine.index_entity(project_id, entity.id, entity.name, entity.type, entity.aliases, entity.data)
    except (OSError, RuntimeError) as exc:
        logger.warning(f"FTS index_entity batch failed: {exc}")

    for relation in proposal.relations:
        from_id = name_to_id.get(relation.from_entity, relation.from_entity)
        to_id = name_to_id.get(relation.to_entity, relation.to_entity)
        store.add_relation(Relation(
            id=relation.id,
            from_entity=from_id,
            to_entity=to_id,
            type=relation.type,
            data=relation.data,
        ))

    for fs in proposal.foreshadows:
        fs.related_entities = [name_to_id.get(n, n) for n in fs.related_entities]
        fs.related_events = [name_to_id.get(n, n) for n in fs.related_events]
        store.add_foreshadow(fs)

    # ── Create timeline events from extraction ──
    tl_created = 0
    tl_linked = 0
    for te in proposal.timeline_events:
        time_order = te.get("time_order", 0)
        label = te.get("label", "")
        chapter_ref = te.get("chapter_ref", "")
        characters = te.get("characters", [])
        if not time_order or not label:
            continue
        # Generate safe event ID from float time_order (e.g. 15.1 -> evt_ch15_1)
        _to_str = str(time_order).replace(".", "_")
        evt_id = f"evt_ch{_to_str}"
        # Check if this timeline event already exists
        existing_tl = store._run(
            "MATCH (t:Timeline {id: $tid, project_id: $pid}) RETURN t",
            {"tid": evt_id, "pid": project_id}
        )
        if not existing_tl:
            from .knowledge import TimelineEvent
            loc_ref = te.get("location", "")
            store.add_timeline_event(TimelineEvent(
                id=evt_id,
                time_point=f"第{time_order}章",
                label=label,
                time_order=time_order,
                description="",
                chapter_ref=chapter_ref,
                track_id="main",
                track_name="主线",
                track_color="#22d3ee",
                time_label=f"第{time_order}章",
                location_ref=loc_ref,
                arc_id=te.get("arc_id", ""),
                narrative_time=te.get("narrative_time", ""),
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
            n = store.link_timeline_to_entities(evt_id, matched_ids[:30])
            tl_linked += n

        # ── Link event to location via OCCURRED_AT ──
        loc_name = te.get("location", "")
        if loc_name:
            loc_id = name_to_id.get(loc_name) or name_to_id.get(loc_name.lower())
            if loc_id:
                try:
                    store._run("""
                        MATCH (t:Timeline {id: $tid, project_id: $pid})
                        MATCH (l:Entity {id: $lid, project_id: $pid})
                        MERGE (t)-[:OCCURRED_AT]->(l)
                    """, {"tid": evt_id, "lid": loc_id, "pid": project_id})
                except Exception:
                    pass

    # ── Process spatial relations (location → location) ──
    spatial_created = 0
    for sr in getattr(proposal, 'spatial_relations', []):
        from_name = sr.get("from", "")
        to_name = sr.get("to", "")
        raw_type = sr.get("type", "located_in")
        try:
            srtype = RelationType(raw_type.lower())
        except ValueError:
            srtype = RelationType.LOCATED_IN
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
            spatial_created += 1

    # ── Fix LOCATED_IN direction errors + transitive containment ──
    if spatial_created > 0:
        try:
            # Fix cycles: if A→B and B→A, keep only correct direction
            store._run("""
                MATCH (a:Entity:Location {project_id: $pid})-[r1:LOCATED_IN]->(b:Entity:Location {project_id: $pid})-[r2:LOCATED_IN]->(a)
                WHERE a.id < b.id
                WITH a, b, r1, r2,
                    CASE
                        WHEN a.data CONTAINS b.name THEN 'a_is_child'
                        WHEN b.data CONTAINS a.name THEN 'b_is_child'
                        WHEN size(a.name) > size(b.name) THEN 'a_is_child'
                        ELSE 'b_is_child'
                    END AS correct_direction
                FOREACH (_ IN CASE WHEN correct_direction = 'a_is_child' THEN [1] ELSE [] END |
                    DELETE r2
                )
                FOREACH (_ IN CASE WHEN correct_direction = 'b_is_child' THEN [1] ELSE [] END |
                    DELETE r1
                )
            """, {"pid": project_id})
            # Transitive closure
            store._run("""
                MATCH (a:Entity:Location {project_id: $pid})-[:LOCATED_IN]->(b:Entity:Location {project_id: $pid})-[:LOCATED_IN]->(c:Entity:Location {project_id: $pid})
                WHERE a.id <> c.id AND NOT (a)-[:LOCATED_IN]->(c)
                MERGE (a)-[:LOCATED_IN]->(c)
            """, {"pid": project_id})
        except Exception:
            pass

    lines = []
    if proposal.entities:
        parts = []
        if new_count > 0:
            parts.append(f"新增 {new_count} 个")
        if updated_count > 0:
            parts.append(f"合并更新 {updated_count} 个")
        lines.append(f"实体: {', '.join(parts)}")
        for e in proposal.entities:
            existing = store.get_entity(e.id)
            tag = "♻️" if (updated_count > 0 and e.id in {ee.id for ee in existing_entities.values()}) else "🆕"
            lines.append(f"  {tag} [{e.type}] {e.name}")
    if proposal.relations:
        lines.append(f"关系: +{len(proposal.relations)} 条")
    if spatial_created > 0:
        lines.append(f"空间关系: +{spatial_created} 条")
    if proposal.foreshadows:
        lines.append(f"伏笔: +{len(proposal.foreshadows)} 个")
    if tl_created > 0:
        lines.append(f"时间线: +{tl_created} 个事件, 关联 {tl_linked} 个角色")

    # ── Auto-complete missing relations via graph reasoning ──
    ac = store.auto_complete_relations()
    if ac.get("symmetry_added") or ac.get("paired_added") or ac.get("unidirectional_cleaned") or ac.get("cooccur_added") or ac.get("transitive_added") or ac.get("structural_added") or ac.get("llm_suggested") or ac.get("multihop_added") or ac.get("jaccard_added"):
        parts = []
        if ac.get("symmetry_added"):
            parts.append(f"对称补全 +{ac['symmetry_added']}")
        if ac.get("paired_added"):
            parts.append(f"配对补全 +{ac['paired_added']}")
        if ac.get("unidirectional_cleaned"):
            parts.append(f"单向清理 +{ac['unidirectional_cleaned']}")
        if ac.get("cooccur_added"):
            parts.append(f"共现推断 +{ac['cooccur_added']}")
        if ac.get("transitive_added"):
            parts.append(f"传递推理 +{ac['transitive_added']}")
        if ac.get("structural_added"):
            parts.append(f"结构等价 +{ac['structural_added']}")
        if ac.get("multihop_added"):
            parts.append(f"多跳等价 +{ac['multihop_added']}")
        if ac.get("jaccard_added"):
            parts.append(f"Jaccard预测 +{ac['jaccard_added']}")
        if ac.get("llm_suggested"):
            parts.append(f"LLM建议 +{ac['llm_suggested']}")
        lines.append(f"关系补全: {', '.join(parts)}")
    if ac.get("anomalies"):
        names = ", ".join(a["name"] for a in ac["anomalies"][:3])
        lines.append(f"⚠ 异常: {names} 等出场多但关系少，可能漏提取")

    from .event_bus import Event, EventType, bus
    bus.emit_sync(Event(type=EventType.KNOWLEDGE_EXTRACTED, data={
        "project_id": project_id,
        "new": new_count, "updated": updated_count,
        "relations": len(proposal.relations), "foreshadows": len(proposal.foreshadows)
    }))
    plugin_manager.call_hook("on_knowledge_update", project_id=project_id, new=new_count, updated=updated_count)

    return "\n".join(lines)
