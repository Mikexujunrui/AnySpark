import asyncio
import json

from fastapi import APIRouter, HTTPException
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
def list_entities(book_id: str, entity_type: str = None):
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
             "resolution": f.resolution_text} for f in foreshadows
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


@router.delete("/books/{book_id}/foreshadows/{fs_id}")
def delete_foreshadow(book_id: str, fs_id: str):
    kb = get_store(book_id)
    kb._run("MATCH (f:Fore {id: $id, project_id: $pid}) DETACH DELETE f", {"id": fs_id, "pid": book_id})
    return {"ok": True}
