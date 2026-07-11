import asyncio
import json

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from core.graph_store import get_store
from data.json_store import json_store

router = APIRouter(tags=["knowledge"])


class ValidateRequest(BaseModel):
    text: str = ""


class ExtractRequest(BaseModel):
    text: str = ""
    book_id: str = ""


class ResolveForeshadowRequest(BaseModel):
    resolution_text: str = ""


@router.get("/books/{book_id}/knowledge/entities")
def list_entities(book_id: str, entity_type: str | None = None):
    """List all knowledge entities, optionally filtered by type."""
    kb = get_store(book_id)
    entities = kb.list_entities(entity_type=entity_type) if entity_type else kb.list_entities()
    return [
        {"id": e.id, "name": e.name, "type": e.type, "aliases": e.aliases, "data": e.data}
        for e in entities
    ]


@router.get("/books/{book_id}/knowledge/summary")
def get_knowledge_summary(book_id: str):
    kb = get_store(book_id)
    entities = kb.list_entities()
    relations = kb.list_relations()
    foreshadows = kb.list_foreshadows()

    by_type = {}
    for e in entities:
        by_type.setdefault(e.type, []).append({
            "id": e.id, "name": e.name, "aliases": e.aliases, "data": e.data
        })

    return {
        "entities": dict(sorted(by_type.items())),
        "relations": [{"id": r.id, "from": r.from_entity, "to": r.to_entity, "type": r.type} for r in relations],
        "foreshadows": [
            {"id": f.id, "text": f.text, "hint": f.hint, "resolved": f.resolved,
             "resolution": f.resolution_text, "status": f.status,
             "plant_chapter": f.plant_chapter,
             "planned_resolve_arc": f.planned_resolve_arc,
             "scheduled_chapter": f.scheduled_chapter} for f in foreshadows
        ],
        "totalEntities": len(entities),
        "totalRelations": len(relations),
        "totalForeshadows": len(foreshadows),
    }


@router.get("/books/{book_id}/knowledge/entity/{entity_id}")
def get_entity(book_id: str, entity_id: str):
    kb = get_store(book_id)
    entity = kb.get_entity(entity_id)
    if not entity:
        raise HTTPException(404, "实体不存在")
    relations = kb.list_relations(entity_id)
    return {
        "id": entity.id,
        "type": entity.type,
        "name": entity.name,
        "aliases": entity.aliases,
        "data": entity.data,
        "relations": [{"id": r.id, "from": r.from_entity, "to": r.to_entity, "type": r.type} for r in relations],
    }


@router.delete("/books/{book_id}/knowledge/entity/{entity_id}")
def delete_entity(book_id: str, entity_id: str):
    kb = get_store(book_id)
    kb.delete_entity(entity_id)
    entities = kb.list_entities()
    json_store.update_book_stats(book_id, entity_count=len(entities))
    return {"ok": True}


class EntityUpdateRequest(BaseModel):
    """Payload for PUT /knowledge/entity/{entity_id}.

    ``data`` replaces the entity's data dict entirely; pass the full merged
    dict. ``name`` / ``aliases`` are optional — only the fields you provide
    are modified. Missing fields mean "don't change".
    """
    data: dict = {}
    name: str | None = None
    aliases: list[str] | None = None


@router.put("/books/{book_id}/knowledge/entity/{entity_id}")
def update_entity(book_id: str, entity_id: str, data: EntityUpdateRequest):
    """Manual edit of a knowledge-base entity (character / location / item / etc).

    Front-end edits typically need to change the name, aliases, and/or the
    arbitrary ``data`` dict. This endpoint supports all three in one call.

    FTS index is refreshed when the entity is a character so search stays
    consistent. Other entity types don't index individual fields.
    """
    kb = get_store(book_id)
    existing = kb.get_entity(entity_id)
    if not existing:
        raise HTTPException(404, "实体不存在")
    # Merge with existing data so the front-end can pass a partial dict; this
    # also lets older front-ends that only pass partial updates keep working.
    merged_data = dict(existing.data)
    merged_data.update(data.data or {})
    ok = kb.update_entity(
        entity_id,
        merged_data,
        name=data.name,
        aliases=data.aliases,
    )
    if not ok:
        raise HTTPException(500, f"更新实体 {entity_id} 失败")
    # Refresh FTS index whenever name/aliases changed, so search stays
    # consistent. Other entity types don't index individual fields.
    name_changed = data.name is not None and data.name != existing.name
    aliases_changed = data.aliases is not None and sorted(data.aliases or []) != sorted(existing.aliases or [])
    if name_changed or aliases_changed:
        try:
            from core.search import fts as fts_engine
            fts_engine.remove_entity(entity_id)
            fts_engine.index_entity(
                book_id, entity_id,
                data.name if data.name is not None else existing.name,
                existing.type,
                data.aliases if data.aliases is not None else existing.aliases,
                merged_data,
            )
        except Exception:
            pass
    return {"ok": True}


class EntityCreateRequest(BaseModel):
    """Payload for POST /knowledge/entity — manual creation from the UI."""
    type: str
    name: str
    aliases: list[str] = []
    data: dict = {}


@router.post("/books/{book_id}/knowledge/entity")
def create_entity(book_id: str, data: EntityCreateRequest):
    """Create a new knowledge-base entity from the UI.

    Uses the existing ``add_entity`` pathway so the new entity goes through
    the same validation and FTS indexing as extracted entities.
    """
    import uuid

    from core.knowledge import Entity, EntityType
    if not data.name or not data.name.strip():
        raise HTTPException(400, "实体名不能为空")
    try:
        entity_type = EntityType(data.type)
    except ValueError:
        raise HTTPException(400, f"未知的实体类型: {data.type}")
    kb = get_store(book_id)
    entity = Entity(
        id=str(uuid.uuid4())[:8],
        type=entity_type,
        name=data.name.strip(),
        aliases=[a for a in (data.aliases or []) if a and a.strip()],
        data=data.data or {},
    )
    kb.add_entity(entity)
    # Refresh FTS index so the new entity shows up in search
    try:
        from core.search import fts as fts_engine
        fts_engine.index_entity(
            book_id, entity.id, entity.name, entity.type,
            entity.aliases, entity.data,
        )
    except Exception:
        pass
    # Update book stats
    entities = kb.list_entities()
    json_store.update_book_stats(book_id, entity_count=len(entities))
    return {"ok": True, "id": entity.id}


@router.post("/books/{book_id}/validate")
def validate_text(book_id: str, data: ValidateRequest):
    from core.llm_client import chat
    kb = get_store(book_id)
    entities = kb.list_entities()
    text = data.text

    if not entities:
        return {"valid": True, "conflicts": [], "notes": ["知识库为空，无需校验"]}

    kb_summary = kb.get_knowledge_summary()[:3000]
    v_prompt = f"""你是小说一致性校验员。对比"小说正文"和"知识库设定"，检查以下三类问题：

1. 违规新增：正文中出现了知识库中不存在的新人物/新地点/新事件？
2. 设定冲突：正文中的描述是否与知识库中的设定矛盾？
3. 遗漏伏笔：正文中是否有暗示但未在知识库中标记的内容？

知识库：
{kb_summary}

小说正文：
{text[:2000]}

请以 JSON 格式输出：
{{"valid": true/false, "conflicts": ["冲突描述1", ...], "notes": ["备注1", ...]}}"""

    response = chat(v_prompt, system="你是一位严格的校对员。只输出 JSON，不输出其他内容。", temperature=0.1, task="extraction")

    try:
        json_str = response.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.startswith("```"):
            json_str = json_str[3:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        return json.loads(json_str.strip())
    except json.JSONDecodeError:
        return {"valid": True, "conflicts": [], "notes": ["校验失败，请重试"]}


@router.post("/extract")
async def extract_knowledge_endpoint(data: ExtractRequest):
    from core.extractor import accept_proposal, extract_from_text, extract_stream
    from tools.executor import get_executor

    text = data.text
    book_id = data.book_id

    async def event_generator():
        q = asyncio.Queue()
        loop = asyncio.get_event_loop()
        executor = get_executor()

        def run_extraction():
            try:
                kb = get_store(book_id)
                summary = kb.get_knowledge_summary()
                for evt in extract_stream(text, existing_knowledge=summary, book_id=book_id):
                    q.put_nowait(evt)
            finally:
                q.put_nowait(None)

        loop.run_in_executor(executor, run_extraction)

        while True:
            evt = await q.get()
            if evt is None:
                break
            yield {"event": evt["event"], "data": json.dumps(evt["data"], ensure_ascii=False)}
            if evt["event"] == "result":
                proposal = await loop.run_in_executor(executor, extract_from_text, text, "", book_id)
                result = await loop.run_in_executor(executor, accept_proposal, proposal, book_id)
                kb = get_store(book_id)
                entities = kb.list_entities()
                json_store.update_book_stats(book_id, entity_count=len(entities))
                yield {"event": "done", "data": json.dumps({
                    "message": result,
                    "totalEntities": len(proposal.entities),
                    "totalRelations": len(proposal.relations),
                    "totalForeshadows": len(proposal.foreshadows)
                }, ensure_ascii=False)}
                break

    return EventSourceResponse(event_generator())


class RelationUpdate(BaseModel):
    time_point: str = ""
    label: str = ""


@router.put("/books/{book_id}/relations/{relation_id}")
def update_relation(book_id: str, relation_id: str, update: RelationUpdate):
    kb = get_store(book_id)
    data = {}
    if update.time_point:
        data["time_point"] = update.time_point
    if update.label:
        data["label"] = update.label
    kb._run("""
        MATCH ()-[r {id: $rid, project_id: $pid}]->()
        SET r.data = $data
        RETURN r
    """, {"rid": relation_id, "pid": book_id, "data": json.dumps(data, ensure_ascii=False)})
    return {"ok": True}


@router.put("/books/{book_id}/foreshadows/{fs_id}/resolve")
def resolve_foreshadow(book_id: str, fs_id: str, data: ResolveForeshadowRequest):
    kb = get_store(book_id)
    kb.resolve_foreshadow(fs_id, data.resolution_text)
    return {"ok": True}


# ── Foreshadow lifecycle scheduling endpoints ──

class PlanForeshadowRequest(BaseModel):
    planned_arc: str = ""


@router.put("/books/{book_id}/foreshadows/{fs_id}/plan")
def plan_foreshadow(book_id: str, fs_id: str, data: PlanForeshadowRequest):
    """Mark a foreshadow as 'planned' with a target narrative arc.

    The user decides which arc should resolve this foreshadow. The system
    will later detect when writing enters that arc and prompt for confirmation.
    """
    kb = get_store(book_id)
    kb.set_foreshadow_planned(fs_id, data.planned_arc)
    return {"ok": True}


@router.put("/books/{book_id}/foreshadows/{fs_id}/schedule")
def schedule_foreshadow(book_id: str, fs_id: str, data: PlanForeshadowRequest):
    """User confirms: schedule this foreshadow for resolution in a specific chapter.

    The planned_arc field is reused as the chapter reference (e.g. "#15").
    After this, the ContextManager will inject it as an active resolution task.
    """
    kb = get_store(book_id)
    kb.schedule_foreshadow(fs_id, data.planned_arc)
    return {"ok": True}


@router.put("/books/{book_id}/foreshadows/{fs_id}/postpone")
def postpone_foreshadow(book_id: str, fs_id: str):
    """User defers: move a 'due' foreshadow back to 'planned'.

    The foreshadow keeps its planned_resolve_arc but will not prompt again
    until the next time that arc is detected.
    """
    kb = get_store(book_id)
    kb.postpone_foreshadow(fs_id)
    return {"ok": True}


@router.put("/books/{book_id}/foreshadows/{fs_id}/mark-due")
def mark_foreshadow_due(book_id: str, fs_id: str):
    """Mark a 'planned' foreshadow as 'due' — the planned arc is now active.

    This triggers a user confirmation prompt before the next write.
    """
    kb = get_store(book_id)
    kb.mark_foreshadow_due(fs_id)
    return {"ok": True}


@router.get("/books/{book_id}/foreshadows/pending")
def list_pending_foreshadows(book_id: str):
    """List foreshadows that need user attention: planned + due."""
    kb = get_store(book_id)
    planned = kb.list_foreshadows(status="planned")
    due = kb.list_foreshadows(status="due")
    result = []
    for f in planned + due:
        result.append({
            "id": f.id, "text": f.text, "hint": f.hint,
            "status": f.status,
            "plant_chapter": f.plant_chapter,
            "planned_resolve_arc": f.planned_resolve_arc,
            "expected_resolution": f.expected_resolution,
        })
    return result


@router.post("/books/{book_id}/foreshadows/match-resolutions")
def match_foreshadow_resolutions(book_id: str):
    """Pass 2: Match unresolved foreshadows to their resolutions in later chapters.

    Scans all chapters for resolve_keywords and uses LLM to confirm matches.
    Updates foreshadow status to resolved/dangling.
    """
    from core.llm_client import chat as llm_chat
    kb = get_store(book_id)
    chapters = json_store.load_chapters(book_id)
    result = kb.match_foreshadow_resolutions(chapters, llm_chat=llm_chat)
    return result


@router.delete("/books/{book_id}/foreshadows/{fs_id}")
def delete_foreshadow(book_id: str, fs_id: str):
    kb = get_store(book_id)
    kb._run("MATCH (f:Fore {id: $id, project_id: $pid}) DETACH DELETE f", {"id": fs_id, "pid": book_id})
    return {"ok": True}


@router.post("/books/{book_id}/graph/clear-timeline")
def clear_timeline(book_id: str):
    """Delete all timeline events and their INVOLVES edges. Use before re-extracting with new format."""
    kb = get_store(book_id)
    n = kb.clear_all_timeline_events()
    return {"ok": True, "deleted": n}


@router.post("/books/{book_id}/graph/clear-all")
def clear_all_knowledge(book_id: str):
    """Delete ALL knowledge graph data for this book: entities, relations, timeline, foreshadows, snapshots.

    Use before a full re-extraction.
    """
    kb = get_store(book_id)
    stats = {"entities": 0, "timeline": 0, "foreshadows": 0, "snapshots": 0}
    # Clear timeline first (has INVOLVES edges)
    stats["timeline"] = kb.clear_all_timeline_events()
    # Clear snapshots
    r = kb._run("MATCH (s:Snapshot {project_id: $pid}) DETACH DELETE s RETURN count(s) as cnt", {"pid": book_id})
    stats["snapshots"] = r[0]["cnt"] if r else 0
    # Clear foreshadows
    r = kb._run("MATCH (f:Fore {project_id: $pid}) DETACH DELETE f RETURN count(f) as cnt", {"pid": book_id})
    stats["foreshadows"] = r[0]["cnt"] if r else 0
    # Clear entities (DETACH DELETE also removes all their relations)
    r = kb._run("MATCH (e:Entity {project_id: $pid}) DETACH DELETE e RETURN count(e) as cnt", {"pid": book_id})
    stats["entities"] = r[0]["cnt"] if r else 0
    return {"ok": True, "stats": stats}


@router.post("/books/{book_id}/graph/auto-complete")
def auto_complete_relations(book_id: str):
    """Run graph reasoning to auto-complete missing relations after extraction."""
    kb = get_store(book_id)
    result = kb.auto_complete_relations()
    return {"ok": True, "result": result}


# ── P1-2: Entity network graph (activates get_entity_network) ──
# NOTE: Static path segments must be declared before the dynamic {entity_id}
# route, otherwise FastAPI would match "bridges" as entity_id.

@router.get("/books/{book_id}/graph/bridges")
def get_bridge_characters(book_id: str):
    """P1-3: Find bridge characters whose removal disconnects relationship paths."""
    kb = get_store(book_id)
    return kb.find_bridge_characters()


@router.get("/books/{book_id}/graph/forgotten")
def get_forgotten_characters(book_id: str, current_time_order: int = 0,
                             threshold: int = 5):
    """P1-5: Find characters who haven't appeared in recent timeline events."""
    kb = get_store(book_id)
    return kb.find_forgotten_characters(current_time_order, threshold)


@router.get("/books/{book_id}/graph/impact/{event_id}")
def get_downstream_impact(book_id: str, event_id: str):
    """P1-4: Find all downstream elements affected by modifying a timeline event."""
    kb = get_store(book_id)
    return kb.find_downstream_impact(event_id)


# P2-14: Worldbuilding metrics (must be before {entity_id} route)
@router.get("/books/{book_id}/graph/metrics")
def get_worldbuilding_metrics(book_id: str, response: Response):
    """P2-14: Graph topology metrics for worldbuilding health assessment."""
    response.headers["Cache-Control"] = "private, max-age=60"
    kb = get_store(book_id)
    return kb.get_worldbuilding_metrics()


# ── Static graph routes MUST be before /graph/{entity_id} to avoid interception ──

@router.get("/books/{book_id}/graph/full")
def get_full_graph(book_id: str, at_time_order: int | None = None, include_simulations: bool = False):
    """Full graph: Return ALL nodes and edges for complete book visualization.

    Includes entities, timeline events, foreshadows, snapshots, and all edges.
    This is the master graph view — the '4D book graph'.

    When ``at_time_order`` is provided, the graph is filtered to show only
    timeline nodes ≤ T, relationships established by that time, and
    snapshots up to that time.

    When ``include_simulations`` is True, also includes推演 layer nodes
    (SimulationSession, SimEvent) with their SIM_* edges.
    """
    kb = get_store(book_id)
    return kb.get_full_graph(at_time_order=at_time_order, include_simulations=include_simulations)


@router.get("/books/{book_id}/graph/map-at-time")
def get_map_at_time(book_id: str, time_order: int = 0):
    """4D Map: Get the location map with character positions at a specific time.

    Returns locations, characters_at_locations, and events_at_time.
    """
    kb = get_store(book_id)
    return kb.get_map_at_time(time_order)


# ── P3: Graph insights for Autopilot ──

@router.get("/books/{book_id}/graph/insights")
def get_graph_insights(book_id: str, response: Response):
    """P3: Generate actionable insights from graph analysis for writing decisions.

    Returns forgotten characters, unresolved foreshadows, bridge characters,
    and writing suggestions based on graph topology.
    """
    response.headers["Cache-Control"] = "private, max-age=60"
    kb = get_store(book_id)
    return kb.get_graph_insights()


@router.get("/books/{book_id}/graph/diagnosis")
def get_narrative_diagnosis(book_id: str, response: Response):
    """P3-ext: Narrative diagnosis with causal reasoning chains.

    Returns a structured diagnosis report with:
    - health_score: overall narrative health (0-100)
    - dimensions: 6-dimension scoring with findings
    - causal_chains: cause-effect-suggestion reasoning chains
    - action_items: prioritized actionable items
    """
    response.headers["Cache-Control"] = "private, max-age=60"
    kb = get_store(book_id)
    return kb.get_narrative_diagnosis()
# ── P4: High-order graph analytics ──

@router.get("/books/{book_id}/graph/character-importance")
def get_character_importance(book_id: str, response: Response):
    """P4-1: Rank characters by composite importance score."""
    response.headers["Cache-Control"] = "private, max-age=60"
    kb = get_store(book_id)
    return kb.get_character_importance()


@router.get("/books/{book_id}/graph/character-communities")
def get_character_communities(book_id: str, response: Response):
    """P4-2: Detect character communities via connected components."""
    response.headers["Cache-Control"] = "private, max-age=60"
    kb = get_store(book_id)
    return kb.get_character_communities()


@router.get("/books/{book_id}/graph/network-evolution")
def get_network_evolution(book_id: str, response: Response):
    """P4-3: Analyze network evolution over time."""
    response.headers["Cache-Control"] = "private, max-age=60"
    kb = get_store(book_id)
    return kb.get_network_evolution()


@router.get("/books/{book_id}/graph/pacing-analysis")
def get_pacing_analysis(book_id: str, response: Response):
    """P4-4: Analyze story pacing and climax detection."""
    response.headers["Cache-Control"] = "private, max-age=60"
    kb = get_store(book_id)
    return kb.get_pacing_analysis()


@router.get("/books/{book_id}/graph/foreshadow-dependency")
def get_foreshadow_dependency_analysis(book_id: str, response: Response):
    """P4-5: Analyze foreshadow dependencies and resolution chains."""
    response.headers["Cache-Control"] = "private, max-age=60"
    kb = get_store(book_id)
    return kb.get_foreshadow_dependency_analysis()


@router.get("/books/{book_id}/graph/character-heatmap")
def get_character_heatmap(book_id: str, response: Response):
    """P4-6: Compute character co-occurrence heatmap and triangle detection."""
    response.headers["Cache-Control"] = "private, max-age=60"
    kb = get_store(book_id)
    return kb.get_character_heatmap()




# ── P5: Extended graph analytics (MUST be before /graph/{entity_id}) ──

@router.get("/books/{book_id}/graph/location-importance")
def get_location_importance(book_id: str, response: Response):
    """P5-1: Rank locations by composite importance."""
    response.headers["Cache-Control"] = "private, max-age=60"
    kb = get_store(book_id)
    return kb.get_location_importance()


@router.get("/books/{book_id}/graph/organization-importance")
def get_organization_importance(book_id: str, response: Response):
    """P5-2: Rank organizations by composite importance."""
    response.headers["Cache-Control"] = "private, max-age=60"
    kb = get_store(book_id)
    return kb.get_organization_importance()


@router.get("/books/{book_id}/graph/clustering-coefficient")
def get_clustering_coefficient(book_id: str, response: Response):
    """P5-3: Compute local clustering coefficient for each character."""
    response.headers["Cache-Control"] = "private, max-age=60"
    kb = get_store(book_id)
    return kb.get_clustering_coefficient()


@router.get("/books/{book_id}/graph/event-causal-chain")
def get_event_causal_chain(book_id: str, response: Response):
    """P5-4: Build event DAG, find critical path (story spine)."""
    response.headers["Cache-Control"] = "private, max-age=60"
    kb = get_store(book_id)
    return kb.get_event_causal_chain()


@router.get("/books/{book_id}/graph/link-prediction")
def get_link_prediction(book_id: str, response: Response, top_n: int = 20):
    """P5-5: Predict missing character relationships via Adamic-Adar / Jaccard."""
    response.headers["Cache-Control"] = "private, max-age=60"
    kb = get_store(book_id)
    return kb.get_link_prediction(top_n=top_n)


# ── Timeline & Location Map (MUST be before /graph/{entity_id}) ──

@router.get("/books/{book_id}/graph/timeline")
def get_graph_timeline(book_id: str):
    """Return timeline data from Neo4j for TimelineView.

    Format: {tracks: [{id, name, color}], events: [{id, track_id, label, time_label, description, chapter_ref, order, characters}]}
    """
    kb = get_store(book_id)
    return kb.get_timeline_for_view()


@router.get("/books/{book_id}/graph/location-map")
def get_graph_location_map(book_id: str):
    """Return location map data from Neo4j for WorldMap.

    Format: {nodes: [{id, name, type, description, parent}], connections: [{from, to, type, label}]}
    """
    kb = get_store(book_id)
    return kb.get_location_map_for_view()


@router.get("/books/{book_id}/graph/{entity_id}")
def get_entity_network(book_id: str, entity_id: str, depth: int = 2):
    """P1-2: Return multi-hop subgraph around an entity for D3 rendering.

    Activates the previously dormant get_entity_network() method.
    Returns {nodes: [...], edges: [...]} ready for force-directed graph.
    """
    kb = get_store(book_id)
    return kb.get_entity_network(entity_id, depth=depth)


# ── P2-15: Character perspective subgraph (POV-aware) ──

@router.get("/books/{book_id}/graph/pov/{character_id}")
def get_pov_subgraph(book_id: str, character_id: str):
    """P2-15: Return the subgraph visible from a character's perspective."""
    kb = get_store(book_id)
    return kb.get_pov_subgraph(character_id)


# ── P2-6: Character knowledge horizon ──

@router.get("/books/{book_id}/graph/knowledge/{character_id}")
def get_character_knowledge(book_id: str, character_id: str, at_chapter: int = 1):
    """P2-6: Query what a character knows at a given chapter."""
    kb = get_store(book_id)
    return kb.get_character_knowledge(character_id, at_chapter)


class TemporalRelationRequest(BaseModel):
    """P2-6: Create a time-annotated relationship edge."""
    from_id: str
    to_id: str
    rel_type: str
    since_chapter: int


@router.post("/books/{book_id}/graph/temporal-relation")
def add_temporal_relation(book_id: str, data: TemporalRelationRequest):
    """P2-6: Create a time-annotated relationship edge."""
    kb = get_store(book_id)
    kb.add_temporal_relation(data.from_id, data.to_id, data.rel_type, data.since_chapter)
    return {"ok": True}


class MissingRelationsRequest(BaseModel):
    """P2-13: Check for missing relationships between entities."""
    entity_ids: list[str]


@router.post("/books/{book_id}/graph/missing-relations")
def find_missing_relations(book_id: str, data: MissingRelationsRequest):
    """P2-13: Detect pairs of entities with no relationship path."""
    kb = get_store(book_id)
    return kb.find_missing_relations(data.entity_ids)


# ── P2-11: Foreshadow dependency graph ──

class ForeshadowDependencyRequest(BaseModel):
    from_id: str
    to_id: str


@router.post("/books/{book_id}/foreshadows/dependency")
def add_foreshadow_dependency(book_id: str, data: ForeshadowDependencyRequest):
    """P2-11: Create a DEPENDS_ON edge between foreshadows."""
    kb = get_store(book_id)
    kb.add_foreshadow_dependency(data.from_id, data.to_id)
    return {"ok": True}


@router.get("/books/{book_id}/foreshadows/cycles")
def get_foreshadow_cycles(book_id: str):
    """P2-11: Detect circular dependencies in foreshadow graph."""
    kb = get_store(book_id)
    return kb.detect_foreshadow_cycles()


@router.get("/books/{book_id}/foreshadows/resolution-order")
def get_resolution_order(book_id: str):
    """P2-11: Topological sort of foreshadow resolution order."""
    kb = get_store(book_id)
    return kb.get_foreshadow_resolution_order()


# ── 4D Map: Time-aware queries ──

@router.get("/books/{book_id}/graph/state/{entity_id}")
def get_entity_state_at_time(book_id: str, entity_id: str, time_order: int = 0, track_id: str | None = None):
    """4D Map: Get an entity's complete state at a specific timeline position.

    Returns phase, relationships, location, events, and active foreshadows
    all filtered to the given time_order.

    When ``track_id`` is provided, only events from that track are included.
    When ``track_id`` is None, events are grouped by track (multi-track support).
    """
    kb = get_store(book_id)
    return kb.get_entity_state_at_time(entity_id, time_order, track_id=track_id)


# /graph/full and /graph/map-at-time moved before /graph/{entity_id} to avoid route interception


# ── Ontology generation ──

class OntologyGenerateRequest(BaseModel):
    book_title: str = ""
    book_description: str = ""
    sample_text: str = ""


@router.post("/books/{book_id}/ontology/generate")
def generate_ontology_endpoint(book_id: str, req: OntologyGenerateRequest):
    """Generate domain-specific ontology for a book using LLM analysis."""
    from core.graph_schema import register_dynamic_ontology
    from core.ontology_generator import apply_ontology_to_schema, generate_ontology

    kb = get_store(book_id)
    entities = kb.list_entities()
    existing_names = [e.name for e in entities]

    ontology = generate_ontology(
        book_title=req.book_title,
        book_description=req.book_description,
        sample_text=req.sample_text,
        existing_entity_names=existing_names,
    )

    schema = apply_ontology_to_schema(ontology)
    register_dynamic_ontology(
        entity_labels=schema["entity_labels"],
        relationship_types=schema["relationship_types"],
    )

    return {
        "ok": True,
        "ontology": ontology.to_dict(),
        "schema": schema,
    }


@router.get("/books/{book_id}/ontology")
def get_ontology_endpoint(book_id: str):
    """Get the currently active ontology for this book."""
    from core.graph_schema import get_active_entity_labels, get_active_relationship_types

    entity_labels = get_active_entity_labels()
    relationship_types = get_active_relationship_types()

    return {
        "entity_types": [
            {"name": k, "label": v} for k, v in entity_labels.items()
        ],
        "relationship_types": relationship_types,
    }


# ── Graph semantic search ──

class GraphSearchRequest(BaseModel):
    question: str = ""


@router.post("/books/{book_id}/graph/search")
def graph_search_endpoint(book_id: str, req: GraphSearchRequest):
    """Search the knowledge graph using natural language.

    Decomposes the question into sub-questions, generates Cypher queries,
    executes them, and returns a synthesized answer.
    """
    from core.graph_search import graph_search

    kb = get_store(book_id)
    result = graph_search(kb, req.question)

    return {
        "question": result.original_question,
        "sub_questions": result.sub_questions,
        "results": [
            {
                "sub_question": r.sub_question,
                "cypher": r.cypher,
                "explanation": r.explanation,
                "rows": r.rows[:10],
                "total_rows": len(r.rows),
                "error": r.error,
            }
            for r in result.results
        ],
        "answer": result.answer,
        "error": result.error,
    }


# ── P3: Community detection ──

@router.get("/books/{book_id}/graph/communities")
def detect_communities(book_id: str):
    """Detect character communities using simplified label propagation.

    Returns community assignments and intra-community missing relationships.
    """
    kb = get_store(book_id)
    return kb.detect_communities()


# ── P3: Narrative arc aggregation ──

@router.post("/books/{book_id}/graph/aggregate-arcs")
def aggregate_narrative_arcs(book_id: str):
    """Detect and label multi-event narrative arcs in the timeline.

    Arcs group timeline events that share characters and are close in time.
    """
    kb = get_store(book_id)
    return kb.aggregate_narrative_arcs()

