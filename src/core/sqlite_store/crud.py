"""SQLite store — entity / relation / foreshadow / timeline / snapshot CRUD.

Part of the ``core.sqlite_store`` package.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from ..knowledge import CharacterSnapshot, Entity, Foreshadow, Relation, TimelineEvent
from .base import _SQLiteBase

logger = logging.getLogger(__name__)


class CrudMixin(_SQLiteBase):
    """Entity / relation / foreshadow / timeline / snapshot CRUD operations."""

    def batch_write(self, operations: list[dict]) -> None:
        """Execute a list of write operations in a transaction.

        Each operation dict:
            {"type": "entity"|"relation"|"foreshadow", "action": "add"|"update"|"delete", ...}
        """
        self._ensure_project()
        now = datetime.now().isoformat()

        # Sort: entities first, then relations/foreshadows (avoid FK violations)
        def _sort_key(op):
            t = op.get("type", "")
            return 0 if t == "entity" else 1

        for op in sorted(operations, key=_sort_key):
            try:
                if op.get("type") == "entity":
                    if op.get("action") == "add":
                        e = op["entity"]
                        self._execute(
                            """
                            INSERT OR REPLACE INTO entities
                                (id, entity_type, name, aliases, data, priority, project_id, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                            (
                                e.id,
                                e.type,
                                e.name,
                                json.dumps(e.aliases, ensure_ascii=False),
                                json.dumps(e.data, ensure_ascii=False),
                                e.priority,
                                self.project_id,
                                now,
                                now,
                            ),
                        )
                    elif op.get("action") == "delete":
                        self._execute(
                            "DELETE FROM entities WHERE id=? AND project_id=?", (op["entity_id"], self.project_id)
                        )
                elif op.get("type") == "relation":
                    if op.get("action") == "add":
                        r = op["relation"]
                        self._execute(
                            """
                            INSERT OR REPLACE INTO relations
                                (id, from_entity, to_entity, type, data, project_id, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                            (
                                r.id,
                                r.from_entity,
                                r.to_entity,
                                r.type.upper() if hasattr(r.type, "upper") else str(r.type).upper(),
                                json.dumps(r.data, ensure_ascii=False),
                                self.project_id,
                                now,
                                now,
                            ),
                        )
                    elif op.get("action") == "delete":
                        self._execute(
                            "DELETE FROM relations WHERE id=? AND project_id=?", (op["relation_id"], self.project_id)
                        )
                elif op.get("type") == "foreshadow":
                    if op.get("action") == "add":
                        f = op["foreshadow"]
                        self._execute(
                            """
                            INSERT OR REPLACE INTO foreshadows
                                (id, text, hint, expected_resolution, resolved, resolution_text,
                                 related_entities, related_events, source, status,
                                 plant_chapter, resolve_chapter, volume_ref,
                                 planned_resolve_arc, scheduled_chapter, confidence,
                                 resolve_keywords, data, project_id, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                            (
                                f.id,
                                f.text,
                                f.hint,
                                f.expected_resolution,
                                int(f.resolved),
                                f.resolution_text,
                                json.dumps(f.related_entities, ensure_ascii=False),
                                json.dumps(f.related_events, ensure_ascii=False),
                                f.source,
                                f.status,
                                f.plant_chapter,
                                f.resolve_chapter,
                                f.volume_ref,
                                f.planned_resolve_arc,
                                f.scheduled_chapter,
                                f.confidence,
                                json.dumps(f.resolve_keywords, ensure_ascii=False),
                                json.dumps({"text": f.text, "hint": f.hint}, ensure_ascii=False),
                                self.project_id,
                                now,
                                now,
                            ),
                        )
                    elif op.get("action") == "delete":
                        self._execute(
                            "DELETE FROM foreshadows WHERE id=? AND project_id=?",
                            (op["foreshadow_id"], self.project_id),
                        )
            except Exception as e:
                logger.warning("batch_write operation failed: %s", e)
        self._invalidate_cache(self.project_id)

    def batch_add_entities(self, entities: list[Entity]) -> None:
        """Add multiple entities in a single transaction."""
        self._ensure_project()
        now = datetime.now().isoformat()
        for e in entities:
            self._execute(
                """
                INSERT OR REPLACE INTO entities
                    (id, entity_type, name, aliases, data, priority, project_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    e.id,
                    e.type,
                    e.name,
                    json.dumps(e.aliases, ensure_ascii=False),
                    json.dumps(e.data, ensure_ascii=False),
                    e.priority,
                    self.project_id,
                    now,
                    now,
                ),
            )

    def batch_add_relations(self, relations: list[Relation]) -> None:
        """Add multiple relations in a single transaction."""
        self._ensure_project()
        now = datetime.now().isoformat()
        for r in relations:
            rel_type = r.type.upper() if hasattr(r.type, "upper") else str(r.type).upper()
            self._execute(
                """
                INSERT OR REPLACE INTO relations
                    (id, from_entity, to_entity, type, data, project_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    r.id,
                    r.from_entity,
                    r.to_entity,
                    rel_type,
                    json.dumps(r.data, ensure_ascii=False),
                    self.project_id,
                    now,
                    now,
                ),
            )

    def batch_add_foreshadows(self, foreshadows: list[Foreshadow]) -> None:
        """Add multiple foreshadows in a single transaction."""
        self._ensure_project()
        now = datetime.now().isoformat()
        for fs in foreshadows:
            self._execute(
                """
                INSERT OR REPLACE INTO foreshadows
                    (id, text, hint, expected_resolution, resolved, resolution_text,
                     related_entities, related_events, source, status,
                     plant_chapter, resolve_chapter, volume_ref,
                     planned_resolve_arc, scheduled_chapter, confidence,
                     resolve_keywords, data, project_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    fs.id,
                    fs.text,
                    fs.hint,
                    fs.expected_resolution,
                    int(fs.resolved),
                    fs.resolution_text,
                    json.dumps(fs.related_entities, ensure_ascii=False),
                    json.dumps(fs.related_events, ensure_ascii=False),
                    fs.source,
                    fs.status,
                    fs.plant_chapter,
                    fs.resolve_chapter,
                    fs.volume_ref,
                    fs.planned_resolve_arc,
                    fs.scheduled_chapter,
                    fs.confidence,
                    json.dumps(fs.resolve_keywords, ensure_ascii=False),
                    json.dumps({"text": fs.text, "hint": fs.hint}, ensure_ascii=False),
                    self.project_id,
                    now,
                    now,
                ),
            )

    # ════════════════════════════════════════════════════════════════
    # Entity CRUD
    # ════════════════════════════════════════════════════════════════

    def add_entity(self, entity: Entity) -> Entity:
        self._ensure_project()
        now = datetime.now().isoformat()
        self._execute(
            """
            INSERT OR REPLACE INTO entities
                (id, entity_type, name, aliases, data, priority, project_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM entities WHERE id=? AND project_id=?), ?), ?)
        """,
            (
                entity.id,
                entity.type,
                entity.name,
                json.dumps(entity.aliases, ensure_ascii=False),
                json.dumps(entity.data, ensure_ascii=False),
                entity.priority,
                self.project_id,
                entity.id,
                self.project_id,
                now,
                now,
            ),
        )
        self._invalidate_cache(self.project_id)
        return entity

    def get_entity(self, entity_id: str) -> Entity | None:
        row = self._run_single(
            "SELECT * FROM entities WHERE id=? AND project_id=?",
            (entity_id, self.project_id),
        )
        return self._row_to_entity(row) if row else None

    def get_entity_by_name(self, name: str) -> Entity | None:
        row = self._run_single(
            "SELECT * FROM entities WHERE name=? AND project_id=? LIMIT 1",
            (name, self.project_id),
        )
        if row:
            return self._row_to_entity(row)
        # Try aliases match
        rows = self._run(
            "SELECT * FROM entities WHERE project_id=?",
            (self.project_id,),
        )
        for r in rows:
            aliases = json.loads(r["aliases"]) if isinstance(r["aliases"], str) else []
            if name in aliases:
                return self._row_to_entity(r)
        # Try case-insensitive name match
        row = self._run_single(
            "SELECT * FROM entities WHERE LOWER(name)=LOWER(?) AND project_id=? LIMIT 1",
            (name, self.project_id),
        )
        return self._row_to_entity(row) if row else None

    def list_entities(self, entity_type: str | None = None) -> list[Entity]:
        if entity_type:
            rows = self._run(
                "SELECT * FROM entities WHERE entity_type=? AND project_id=? ORDER BY name",
                (entity_type, self.project_id),
            )
        else:
            rows = self._run(
                "SELECT * FROM entities WHERE project_id=? ORDER BY entity_type, name",
                (self.project_id,),
            )
        return [self._row_to_entity(r) for r in rows]

    def update_entity(
        self, entity_id: str, data: dict, name: str | None = None, aliases: list[str] | None = None
    ) -> bool:
        now = datetime.now().isoformat()
        sets = ["data=?", "updated_at=?"]
        params = [json.dumps(data, ensure_ascii=False), now]
        if name is not None:
            sets.append("name=?")
            params.append(name)
        if aliases is not None:
            sets.append("aliases=?")
            params.append(json.dumps(aliases, ensure_ascii=False))
        params.extend([entity_id, self.project_id])
        sql = f"UPDATE entities SET {', '.join(sets)} WHERE id=? AND project_id=?"
        count = self._execute(sql, tuple(params))
        self._invalidate_cache(self.project_id)
        return count > 0

    def delete_entity(self, entity_id: str) -> bool:
        self._execute(
            "DELETE FROM relations WHERE (from_entity=? OR to_entity=?) AND project_id=?",
            (entity_id, entity_id, self.project_id),
        )
        self._execute("DELETE FROM entities WHERE id=? AND project_id=?", (entity_id, self.project_id))
        self._invalidate_cache(self.project_id)
        return True

    # ════════════════════════════════════════════════════════════════
    # Relation CRUD
    # ════════════════════════════════════════════════════════════════

    def add_relation(self, relation: Relation) -> Relation:
        self._ensure_project()
        now = datetime.now().isoformat()
        rel_type = relation.type.upper() if hasattr(relation.type, "upper") else str(relation.type).upper()
        self._execute(
            """
            INSERT OR REPLACE INTO relations
                (id, from_entity, to_entity, type, data, project_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                relation.id,
                relation.from_entity,
                relation.to_entity,
                rel_type,
                json.dumps(relation.data, ensure_ascii=False),
                self.project_id,
                now,
                now,
            ),
        )
        self._invalidate_cache(self.project_id)
        return relation

    def list_relations(self, entity_id: str | None = None) -> list[Relation]:
        if entity_id:
            rows = self._run(
                """
                SELECT * FROM relations
                WHERE (from_entity=? OR to_entity=?) AND project_id=?
            """,
                (entity_id, entity_id, self.project_id),
            )
        else:
            rows = self._run(
                "SELECT * FROM relations WHERE project_id=?",
                (self.project_id,),
            )
        return [self._row_to_relation(r) for r in rows]

    def find_share_connections(self, entity_ids: list[str]) -> list[dict]:
        if len(entity_ids) < 2:
            return []
        placeholders = ",".join("?" for _ in entity_ids)
        rows = self._run(
            f"""
            SELECT r.from_entity AS "from", r.type, r.to_entity AS "to"
            FROM relations r
            WHERE r.project_id=?
              AND ((r.from_entity IN ({placeholders}) AND r.to_entity IN ({placeholders}))
                   OR (r.to_entity IN ({placeholders}) AND r.from_entity IN ({placeholders})))
              AND r.from_entity <> r.to_entity
        """,
            (self.project_id, *entity_ids, *entity_ids, *entity_ids, *entity_ids),
        )
        seen = set()
        result = []
        for r in rows:
            key = (r["from"], r["type"], r["to"])
            if key not in seen:
                seen.add(key)
                result.append({"from": r["from"], "type": r["type"].lower(), "to": r["to"]})
        return result

    def delete_relation(self, relation_id: str) -> bool:
        self._execute("DELETE FROM relations WHERE id=? AND project_id=?", (relation_id, self.project_id))
        self._invalidate_cache(self.project_id)
        return True

    # ════════════════════════════════════════════════════════════════
    # Foreshadow CRUD
    # ════════════════════════════════════════════════════════════════

    def add_foreshadow(self, fs: Foreshadow) -> Foreshadow:
        self._ensure_project()
        now = datetime.now().isoformat()
        self._execute(
            """
            INSERT OR REPLACE INTO foreshadows
                (id, text, hint, expected_resolution, resolved, resolution_text,
                 related_entities, related_events, source, status,
                 plant_chapter, resolve_chapter, volume_ref,
                 planned_resolve_arc, scheduled_chapter, confidence,
                 resolve_keywords, data, project_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                fs.id,
                fs.text,
                fs.hint,
                fs.expected_resolution,
                int(fs.resolved),
                fs.resolution_text,
                json.dumps(fs.related_entities, ensure_ascii=False),
                json.dumps(fs.related_events, ensure_ascii=False),
                fs.source,
                fs.status,
                fs.plant_chapter,
                fs.resolve_chapter,
                fs.volume_ref,
                fs.planned_resolve_arc,
                fs.scheduled_chapter,
                fs.confidence,
                json.dumps(fs.resolve_keywords, ensure_ascii=False),
                json.dumps(
                    {
                        "text": fs.text,
                        "hint": fs.hint,
                        "expected_resolution": fs.expected_resolution,
                        "resolved": fs.resolved,
                        "resolution_text": fs.resolution_text,
                        "related_entities": fs.related_entities,
                        "related_events": fs.related_events,
                        "source": fs.source,
                        "status": fs.status,
                        "plant_chapter": fs.plant_chapter,
                        "resolve_chapter": fs.resolve_chapter,
                        "volume_ref": fs.volume_ref,
                        "planned_resolve_arc": fs.planned_resolve_arc,
                        "scheduled_chapter": fs.scheduled_chapter,
                        "confidence": fs.confidence,
                        "resolve_keywords": fs.resolve_keywords,
                    },
                    ensure_ascii=False,
                ),
                self.project_id,
                now,
                now,
            ),
        )
        self._invalidate_cache(self.project_id)
        return fs

    def list_foreshadows(self, resolved: bool | None = None, status: str | None = None) -> list[Foreshadow]:
        parts = ["SELECT * FROM foreshadows WHERE project_id=?"]
        params: list = [self.project_id]
        if resolved is not None:
            parts.append("AND resolved=?")
            params.append(int(resolved))
        if status:
            parts.append("AND status=?")
            params.append(status)
        rows = self._run(" ".join(parts), tuple(params))
        return [self._row_to_foreshadow(r) for r in rows]

    def get_foreshadow(self, fs_id: str) -> Foreshadow | None:
        row = self._run_single(
            "SELECT * FROM foreshadows WHERE id=? AND project_id=?",
            (fs_id, self.project_id),
        )
        return self._row_to_foreshadow(row) if row else None

    def resolve_foreshadow(self, fs_id: str, resolution_text: str, resolve_chapter: str = "") -> bool:
        now = datetime.now().isoformat()
        count = self._execute(
            "UPDATE foreshadows SET resolved=1, resolution_text=?, resolve_chapter=?, "
            "status='resolved', updated_at=? WHERE id=? AND project_id=?",
            (resolution_text, resolve_chapter, now, fs_id, self.project_id),
        )
        self._invalidate_cache(self.project_id)
        return count > 0

    def set_foreshadow_planned(self, fs_id: str, planned_arc: str) -> bool:
        now = datetime.now().isoformat()
        count = self._execute(
            "UPDATE foreshadows SET planned_resolve_arc=?, status='planned', updated_at=? WHERE id=? AND project_id=?",
            (planned_arc, now, fs_id, self.project_id),
        )
        self._invalidate_cache(self.project_id)
        return count > 0

    def mark_foreshadow_due(self, fs_id: str) -> bool:
        now = datetime.now().isoformat()
        count = self._execute(
            "UPDATE foreshadows SET status='due', updated_at=? WHERE id=? AND project_id=?",
            (now, fs_id, self.project_id),
        )
        self._invalidate_cache(self.project_id)
        return count > 0

    def delete_foreshadow(self, fs_id: str) -> bool:
        self._execute("DELETE FROM foreshadows WHERE id=? AND project_id=?", (fs_id, self.project_id))
        self._invalidate_cache(self.project_id)
        return True

    # ════════════════════════════════════════════════════════════════
    # Timeline Event CRUD
    # ════════════════════════════════════════════════════════════════

    def add_timeline_event(self, event: TimelineEvent) -> TimelineEvent:
        self._ensure_project()
        now = datetime.now().isoformat()
        timeline_data = {
            "arc_id": event.arc_id,
            "narrative_time": event.narrative_time,
            "temporal_layer": event.temporal_layer,
            "absolute_start": event.absolute_start,
            "absolute_end": event.absolute_end,
            "relative_to": event.relative_to,
            "source_evidence": event.source_evidence,
            "confidence": event.confidence,
        }
        self._execute(
            """
            INSERT OR REPLACE INTO timeline_events
                (id, time_point, label, time_order, description, chapter_ref,
                 track_id, track_name, track_color, time_label, location_ref,
                 data, project_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                event.id,
                event.time_point,
                event.label,
                event.time_order,
                event.description,
                event.chapter_ref,
                event.track_id,
                event.track_name,
                event.track_color,
                event.time_label,
                event.location_ref,
                json.dumps(timeline_data, ensure_ascii=False),
                self.project_id,
                now,
                now,
            ),
        )
        self._invalidate_cache(self.project_id)
        return event

    def list_timeline_events(self) -> list[TimelineEvent]:
        rows = self._run(
            "SELECT * FROM timeline_events WHERE project_id=? ORDER BY time_order",
            (self.project_id,),
        )
        return [self._row_to_timeline_event(r) for r in rows]

    def get_timeline_event(self, event_id: str) -> TimelineEvent | None:
        row = self._run_single(
            "SELECT * FROM timeline_events WHERE id=? AND project_id=?",
            (event_id, self.project_id),
        )
        return self._row_to_timeline_event(row) if row else None

    def delete_timeline_event(self, event_id: str) -> bool:
        self._execute("DELETE FROM timeline_events WHERE id=? AND project_id=?", (event_id, self.project_id))
        self._invalidate_cache(self.project_id)
        return True

    # ════════════════════════════════════════════════════════════════
    # Snapshot CRUD
    # ════════════════════════════════════════════════════════════════

    def add_snapshot(self, snapshot: CharacterSnapshot) -> CharacterSnapshot:
        self._ensure_project()
        now = datetime.now().isoformat()
        self._execute(
            """
            INSERT OR REPLACE INTO snapshots
                (id, character_id, time_point, time_order, label, phase, phase_key,
                 is_current, data, description, project_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                snapshot.id,
                snapshot.character_entity_id,
                snapshot.time_point,
                snapshot.time_order,
                snapshot.label,
                snapshot.phase or "",
                snapshot.phase_key or "",
                int(bool(snapshot.is_current)),
                json.dumps(snapshot.data, ensure_ascii=False),
                snapshot.description,
                self.project_id,
                now,
                now,
            ),
        )
        self._invalidate_cache(self.project_id)
        return snapshot

    def list_snapshots(self, character_id: str | None = None) -> list[CharacterSnapshot]:
        if character_id:
            rows = self._run(
                "SELECT * FROM snapshots WHERE character_id=? AND project_id=? ORDER BY time_order",
                (character_id, self.project_id),
            )
        else:
            rows = self._run(
                "SELECT * FROM snapshots WHERE project_id=? ORDER BY time_order",
                (self.project_id,),
            )
        return [self._row_to_character_snapshot(r) for r in rows]

    def delete_snapshot(self, snapshot_id: str) -> bool:
        self._execute("DELETE FROM snapshots WHERE id=? AND project_id=?", (snapshot_id, self.project_id))
        self._invalidate_cache(self.project_id)
        return True

    def get_current_phase(self, character_id: str) -> CharacterSnapshot | None:
        """Get the latest snapshot for a character (marked current or newest).

        Returns None if no snapshots exist.
        """
        # Prefer the one marked is_current=1
        row = self._run_single(
            """
            SELECT * FROM snapshots
            WHERE character_id=? AND project_id=? AND is_current=1
            ORDER BY time_order DESC LIMIT 1
        """,
            (character_id, self.project_id),
        )
        if row:
            return self._row_to_character_snapshot(row)
        # Fall back to the latest by time_order
        row = self._run_single(
            """
            SELECT * FROM snapshots
            WHERE character_id=? AND project_id=?
            ORDER BY time_order DESC LIMIT 1
        """,
            (character_id, self.project_id),
        )
        return self._row_to_character_snapshot(row) if row else None
