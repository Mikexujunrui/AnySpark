from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.graph_store import get_store
from core.knowledge import CharacterSnapshot, EntityType, TimelineEvent
from core.voice_fingerprint import get_all_voice_fingerprints, get_character_voice
from data.json_store import json_store

router = APIRouter(tags=["characters"])

# ── Phase card field grouping ──────────────────────────────────────────────
# Maps known field names to display groups so the frontend can render
# structured card sections instead of a flat key-value grid.
PHASE_FIELD_GROUPS = [
    ("基础", ["age", "年龄", "status", "当前状态", "identity", "身份", "role", "角色定位"]),
    ("外貌", ["appearance", "外貌", "hair", "eyes", "height", "build", "clothing", "distinctive_marks"]),
    ("性格", ["personality", "性格", "temperament", "气质", "inner_conflict", "核心冲突"]),
    ("能力", ["abilities", "能力", "powers", "skills"]),
    ("背景", ["background", "背景", "origin", "出身背景", "key_experiences", "童年经历"]),
    (
        "内在",
        [
            "motivation",
            "驱动力",
            "fears",
            "likes",
            "dislikes",
            "goals",
            "secrets",
            "traumas",
            "角色主题",
            "成长弧光起点",
            "growth_note",
            "成长说明",
        ],
    ),
    ("关系", ["relationships", "关系网", "关系状态", "friends", "affiliation"]),
]


def _group_phase_data(data: dict) -> list[dict]:
    """Split a flat phase data dict into grouped sections for card display.

    Unknown fields go into an '其他' group so nothing is lost.
    """
    if not data:
        return []
    grouped = []
    seen_keys = set()
    for group_name, keys in PHASE_FIELD_GROUPS:
        items = []
        for k in keys:
            v = data.get(k)
            if v and k not in seen_keys:
                items.append({"key": k, "label": _field_label(k), "value": v})
                seen_keys.add(k)
        if items:
            grouped.append({"group": group_name, "items": items})
    # Catch-all for unknown fields
    rest = [{"key": k, "label": _field_label(k), "value": v} for k, v in data.items() if k not in seen_keys and v]
    if rest:
        grouped.append({"group": "其他", "items": rest})
    return grouped


def _field_label(key: str) -> str:
    labels = {
        "appearance": "外貌",
        "personality": "性格",
        "abilities": "能力",
        "background": "背景",
        "age": "年龄",
        "status": "状态",
        "motivation": "驱动力",
        "relationships": "关系",
        "growth_note": "成长说明",
        "identity": "身份",
        "role": "角色定位",
        "origin": "出身",
        "temperament": "气质",
        "inner_conflict": "核心冲突",
        "fears": "恐惧",
        "goals": "目标",
        "secrets": "秘密",
        "traumas": "创伤",
        "key_experiences": "关键经历",
        "hair": "头发",
        "eyes": "眼睛",
        "height": "身高",
        "build": "体型",
        "clothing": "穿着",
        "distinctive_marks": "特征标记",
        "powers": "能力",
        "skills": "技能",
        "friends": "朋友",
        "affiliation": "归属",
        "likes": "喜好",
        "dislikes": "厌恶",
    }
    return labels.get(key, key)


@router.get("/books/{book_id}/characters")
def get_character_gallery(book_id: str):
    kb = get_store(book_id)
    all_entities = kb.list_entities()
    chars = [e for e in all_entities if e.type == EntityType.CHARACTER]
    all_relations = kb.list_relations()
    snapshots = kb.list_snapshots()
    timelines = kb.list_timeline_events()

    id_to_entity = {}
    name_to_entity = {}
    for e in all_entities:
        id_to_entity[e.id] = e
        name_to_entity[e.name] = e
        name_to_entity[e.name.lower()] = e
        for alias in e.aliases:
            name_to_entity[alias] = e
            name_to_entity[alias.lower()] = e

    {c.id for c in chars}

    def resolve(ref):
        if ref in id_to_entity:
            return id_to_entity[ref]
        if ref in name_to_entity:
            return name_to_entity[ref]
        if ref.lower() in name_to_entity:
            return name_to_entity[ref.lower()]
        return None

    def is_mine(relation, entity_id):
        src = resolve(relation.from_entity)
        dst = resolve(relation.to_entity)
        src_id = src.id if src else relation.from_entity
        dst_id = dst.id if dst else relation.to_entity
        return src_id == entity_id or dst_id == entity_id

    result = []
    for c in chars:
        char_relations = []
        seen_rel_keys = set()

        for r in all_relations:
            if not is_mine(r, c.id):
                continue
            src = resolve(r.from_entity)
            dst = resolve(r.to_entity)
            src_id = src.id if src else r.from_entity
            dst_id = dst.id if dst else r.to_entity
            other_id = dst_id if src_id == c.id else src_id
            other_entity = resolve(other_id) or resolve(r.to_entity if src_id == c.id else r.from_entity)

            rel_key = f"{min(c.id, other_id)}|{max(c.id, other_id)}|{r.type}"
            if rel_key in seen_rel_keys:
                continue
            seen_rel_keys.add(rel_key)

            char_relations.append(
                {
                    "id": r.id,
                    "targetId": other_entity.id if other_entity else other_id,
                    "targetName": other_entity.name if other_entity else other_id[:12],
                    "targetType": other_entity.type if other_entity else "unknown",
                    "type": r.type,
                    "direction": "out" if src_id == c.id else "in",
                    "timePoint": r.data.get("time_point", ""),
                }
            )

        char_snapshots = [
            {
                "id": s.id,
                "timePoint": s.time_point,
                "timeOrder": s.time_order,
                "label": s.label,
                "data": s.data,
                "description": s.description,
                "phase": s.phase or "",
                "phaseKey": s.phase_key or "",
                "isCurrent": bool(s.is_current),
                "card": _group_phase_data(s.data),  # structured card sections for UI
            }
            for s in snapshots
            if s.character_entity_id == c.id
        ]
        char_snapshots.sort(key=lambda x: x["timeOrder"])

        result.append(
            {
                "id": c.id,
                "name": c.name,
                "aliases": c.aliases,
                "data": c.data,
                "relationCount": len(char_relations),
                "snapshotCount": len(char_snapshots),
                "relations": char_relations,
                "snapshots": char_snapshots,
            }
        )

    return {
        "characters": sorted(result, key=lambda x: x["name"]),
        "timelineEvents": [
            {
                "id": t.id,
                "timePoint": t.time_point,
                "label": t.label,
                "timeOrder": t.time_order,
                "description": t.description,
                "chapterRef": t.chapter_ref,
            }
            for t in timelines
        ],
    }


class SnapshotCreate(BaseModel):
    character_entity_id: str
    time_point: str
    time_order: int = 0
    label: str = ""
    data: dict = {}
    description: str = ""
    phase: str = ""
    phase_key: str = ""
    is_current: bool = False


class SnapshotUpdate(BaseModel):
    """Partial update for a snapshot/phase card. All fields optional."""

    label: str | None = None
    description: str | None = None
    time_point: str | None = None
    time_order: int | None = None
    data: dict | None = None
    phase: str | None = None
    phase_key: str | None = None
    is_current: bool | None = None


@router.post("/books/{book_id}/characters/{entity_id}/snapshots")
def add_snapshot(book_id: str, entity_id: str, snap: SnapshotCreate):
    kb = get_store(book_id)
    sid = str(int(datetime.now().timestamp() * 1000))
    s = CharacterSnapshot(
        id=sid,
        character_entity_id=entity_id,
        time_point=snap.time_point,
        time_order=snap.time_order,
        label=snap.label,
        data=snap.data,
        description=snap.description,
        phase=snap.phase,
        phase_key=snap.phase_key,
        is_current=snap.is_current,
    )
    kb.add_snapshot(s)
    return {"id": sid, "ok": True}


@router.put("/books/{book_id}/snapshots/{snapshot_id}")
def update_snapshot(book_id: str, snapshot_id: str, updates: SnapshotUpdate):
    """Update a phase card. Only the fields provided are modified.

    Use this to rename a phase, flip is_current (to switch the active writing
    phase), or rewrite the whole data dict (character attributes at that phase).
    """
    kb = get_store(book_id)
    payload = dict(updates.model_dump(exclude_unset=True, exclude_none=True).items())
    if not payload:
        return {"ok": True, "changed": False}
    kb.update_snapshot(snapshot_id, payload)
    return {"ok": True, "changed": True}


@router.delete("/books/{book_id}/snapshots/{snapshot_id}")
def delete_snapshot(book_id: str, snapshot_id: str):
    kb = get_store(book_id)
    kb.delete_snapshot(snapshot_id)
    return {"ok": True}


class TimelineEventCreate(BaseModel):
    time_point: str
    label: str
    time_order: int = 0
    description: str = ""
    chapter_ref: str = ""


@router.get("/books/{book_id}/timeline")
def list_timeline_events(book_id: str):
    kb = get_store(book_id)
    events = kb.list_timeline_events()
    return [
        {
            "id": e.id,
            "timePoint": e.time_point,
            "label": e.label,
            "timeOrder": e.time_order,
            "description": e.description,
            "chapterRef": e.chapter_ref,
        }
        for e in events
    ]


@router.post("/books/{book_id}/timeline")
def add_timeline_event(book_id: str, event: TimelineEventCreate):
    kb = get_store(book_id)
    eid = str(int(datetime.now().timestamp() * 1000))
    e = TimelineEvent(
        id=eid,
        time_point=event.time_point,
        label=event.label,
        time_order=event.time_order,
        description=event.description,
        chapter_ref=event.chapter_ref,
    )
    kb.add_timeline_event(e)
    return {"id": eid, "ok": True}


@router.delete("/books/{book_id}/timeline/{event_id}")
def delete_timeline_event(book_id: str, event_id: str):
    kb = get_store(book_id)
    kb.delete_timeline_event(event_id)
    return {"ok": True}


@router.get("/books/{book_id}/character-mentions")
def get_character_mentions(book_id: str):
    """Return cached character-mention-per-chapter matrix, or {matrix: null} if stale/missing."""
    data = json_store.get_character_mentions(book_id)
    if data is None:
        return {"matrix": None, "lastUpdatedAt": None, "chaptersCount": 0}
    return data


@router.post("/books/{book_id}/character-mentions/refresh")
def refresh_character_mentions(book_id: str):
    """Force recomputation of the mentions cache. Slow on first call."""
    try:
        return json_store.refresh_character_mentions(book_id)
    except Exception as e:
        raise HTTPException(500, f"计算角色戏份失败: {str(e)[:200]}")


@router.get("/books/{book_id}/characters/voice")
def all_voice_fingerprints(book_id: str):
    """Return voice fingerprints for all characters in the book."""
    fingerprints = get_all_voice_fingerprints(book_id)
    return {
        "book_id": book_id,
        "fingerprints": [fp.to_dict() for fp in fingerprints],
        "total": len(fingerprints),
    }


@router.get("/books/{book_id}/characters/{char_name}/voice")
def character_voice(book_id: str, char_name: str):
    """Return voice fingerprint for a specific character."""
    fp = get_character_voice(book_id, char_name)
    return fp.to_dict()
