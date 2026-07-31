"""SQLite store — search, views, and auto-completion.

Part of the ``core.sqlite_store`` package.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from ..graph_schema import get_symmetric_types
from .analytics import AnalyticsMixin
from .base import _SQLiteBase

logger = logging.getLogger(__name__)


class SearchMixin(AnalyticsMixin):
    """Text search, timeline/location views, and relation auto-completion."""

    def text_search(self, query: str, limit: int = 20) -> list[dict]:
        """Full-text search using FTS5 index."""
        if not query.strip():
            return []
        try:
            rows = self._run(
                """
                SELECT e.id, e.name, e.entity_type, e.aliases
                FROM entities_fts f JOIN entities e ON f.rowid = e.rowid
                WHERE entities_fts MATCH ? AND e.project_id = ?
                LIMIT ?
            """,
                (query, self.project_id, limit),
            )
            return [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "type": r["entity_type"],
                    "aliases": json.loads(r["aliases"]) if isinstance(r["aliases"], str) else [],
                }
                for r in rows
            ]
        except Exception:
            # FTS5 may fail on syntax; fall back to LIKE
            rows = self._run(
                """
                SELECT id, name, entity_type, aliases FROM entities
                WHERE project_id=? AND (name LIKE ? OR aliases LIKE ?)
                LIMIT ?
            """,
                (self.project_id, f"%{query}%", f"%{query}%", limit),
            )
            return [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "type": r["entity_type"],
                    "aliases": json.loads(r["aliases"]) if isinstance(r["aliases"], str) else [],
                }
                for r in rows
            ]

    # ════════════════════════════════════════════════════════════════
    # Timeline / Location view helpers (frontend rendering)
    # ════════════════════════════════════════════════════════════════

    def get_timeline_for_view(self) -> dict:
        """Return timeline data formatted for TimelineView frontend.

        Format: {tracks: [{id, name, color}], events: [{id, track_id, label, time_label, description, chapter_ref, order, characters}]}
        """
        events = self.list_timeline_events()
        if not events:
            return {"tracks": [{"id": "main", "name": "主线", "color": "#22d3ee"}], "events": []}

        tracks: dict[str, dict] = {}
        result_events = []
        for evt in events:
            tid = evt.track_id or "main"
            if tid not in tracks:
                tracks[tid] = {"id": tid, "name": evt.track_name or "主线", "color": evt.track_color or "#22d3ee"}
            # Get involved character names
            involved = self.get_timeline_involved_entities(evt.id)
            char_names = []
            for eid in involved:
                ent = self.get_entity(eid)
                if ent:
                    char_names.append(ent.name)
            result_events.append(
                {
                    "id": evt.id,
                    "track_id": tid,
                    "label": evt.label,
                    "time_label": evt.time_label or evt.time_point,
                    "description": evt.description,
                    "chapter_ref": evt.chapter_ref,
                    "order": evt.time_order,
                    "characters": char_names,
                }
            )

        return {
            "tracks": list(tracks.values()),
            "events": result_events,
        }

    def get_location_map_for_view(self) -> dict:
        """Return location map data formatted for WorldMap frontend.

        Format: {nodes: [{id, name, type, description, parent}], connections: [{from, to, type, label}]}
        """
        locations = self.list_entities(entity_type="location")
        if not locations:
            return {"nodes": [], "connections": []}

        nodes = []
        for loc in locations:
            nodes.append(
                {
                    "id": loc.id,
                    "name": loc.name,
                    "type": "location",
                    "description": loc.data.get("description", ""),
                    "parent": loc.data.get("parent", ""),
                }
            )

        # Get LOCATED_IN and ADJACENT_TO relations between locations
        loc_ids = [loc.id for loc in locations]
        if len(loc_ids) < 2:
            return {"nodes": nodes, "connections": []}

        placeholders = ",".join("?" for _ in loc_ids)
        conn_rows = self._run(
            f"""
            SELECT r.from_entity AS "from", r.to_entity AS "to", r.type
            FROM relations r
            WHERE r.type IN ('LOCATED_IN','ADJACENT_TO') AND r.project_id=?
              AND r.from_entity IN ({placeholders}) AND r.to_entity IN ({placeholders})
        """,
            (self.project_id, *loc_ids, *loc_ids),
        )
        label_map = {"LOCATED_IN": "位于", "ADJACENT_TO": "相邻"}
        connections = [
            {"from": r["from"], "to": r["to"], "type": r["type"].lower(), "label": label_map.get(r["type"], r["type"])}
            for r in conn_rows
        ]

        return {"nodes": nodes, "connections": connections}

    # ════════════════════════════════════════════════════════════════
    # Auto-complete relations (graph reasoning)
    # ════════════════════════════════════════════════════════════════

    def auto_complete_relations(self) -> dict[str, Any]:
        """Auto-complete missing relationships via graph reasoning.

        Returns a dict with counts of each type of completion:
        symmetry_added, paired_added, unidirectional_cleaned,
        cooccur_added, transitive_added, structural_added,
        llm_suggested, multihop_added, jaccard_added.
        """
        now = datetime.now().isoformat()
        stats: dict[str, int] = {
            "symmetry_added": 0,
            "paired_added": 0,
            "unidirectional_cleaned": 0,
            "cooccur_added": 0,
            "transitive_added": 0,
            "structural_added": 0,
            "llm_suggested": 0,
            "multihop_added": 0,
            "jaccard_added": 0,
        }
        pid = self.project_id

        # 1a. Symmetry completion: if A-KNOWS->B exists but B-KNOWS->A missing, add it
        symmetric_types = get_symmetric_types()
        for rtype in symmetric_types:
            rows = self._run(
                """
                SELECT r1.from_entity AS aid, r1.to_entity AS bid
                FROM relations r1
                WHERE r1.type=? AND r1.project_id=?
                  AND NOT EXISTS (
                    SELECT 1 FROM relations r2
                    WHERE r2.from_entity=r1.to_entity AND r2.to_entity=r1.from_entity
                      AND r2.type=r1.type AND r2.project_id=?
                  )
                  AND r1.from_entity <> r1.to_entity
                LIMIT 100
            """,
                (rtype, pid, pid),
            )
            for r in rows:
                self._execute(
                    "INSERT OR IGNORE INTO relations (id, from_entity, to_entity, type, data, project_id, created_at, updated_at) VALUES (?, ?, ?, ?, '{}', ?, ?, ?)",
                    (str(uuid.uuid4())[:8], r["bid"], r["aid"], rtype, pid, now, now),
                )
                stats["symmetry_added"] += 1

        # 1b. Paired completion: A PARENT_OF B → B CHILD_OF A
        from ..graph_schema import RELATIONSHIP_DIRECTION

        for rtype, direction in RELATIONSHIP_DIRECTION.items():
            if not direction.startswith("paired:"):
                continue
            reverse_type = direction[7:]
            rows = self._run(
                """
                SELECT r1.from_entity AS aid, r1.to_entity AS bid
                FROM relations r1
                WHERE r1.type=? AND r1.project_id=?
                  AND NOT EXISTS (
                    SELECT 1 FROM relations r2
                    WHERE r2.from_entity=r1.to_entity AND r2.to_entity=r1.from_entity
                      AND r2.type=? AND r2.project_id=?
                  )
                LIMIT 100
            """,
                (rtype, pid, reverse_type, pid),
            )
            for r in rows:
                self._execute(
                    "INSERT OR IGNORE INTO relations (id, from_entity, to_entity, type, data, project_id, created_at, updated_at) VALUES (?, ?, ?, ?, '{}', ?, ?, ?)",
                    (str(uuid.uuid4())[:8], r["bid"], r["aid"], reverse_type, pid, now, now),
                )
                stats["paired_added"] += 1

        # 1c. Unidirectional cleanup: remove reverse edges for unidirectional types
        uni_types = [rt for rt, d in RELATIONSHIP_DIRECTION.items() if d == "unidirectional"]
        for rtype in uni_types[:5]:  # Limit to common types
            self._execute(
                """
                DELETE FROM relations
                WHERE rowid IN (
                    SELECT r1.rowid FROM relations r1
                    JOIN relations r2 ON r1.from_entity=r2.to_entity
                      AND r1.to_entity=r2.from_entity AND r1.type=r2.type
                    WHERE r1.type=? AND r1.project_id=?
                      AND r1.from_entity < r1.to_entity
                )
            """,
                (rtype, pid),
            )

        # 2. Co-occurrence inference (via timeline events)
        # Characters that appear in multiple events together → KNOWS
        co_rows = self._run(
            """
            SELECT te1.data AS data1, te2.data AS data2
            FROM timeline_events te1
            JOIN timeline_events te2 ON te1.project_id=te2.project_id
            WHERE te1.id < te2.id AND te1.project_id=?
            LIMIT 500
        """,
            (pid,),
        )
        from collections import Counter

        co_pairs: Counter = Counter()
        for r in co_rows:
            try:
                ents1 = set(json.loads(r["data1"]).get("involved_entities", []))
                ents2 = set(json.loads(r["data2"]).get("involved_entities", []))
                for eid in ents1 & ents2:
                    for other in ents1 | ents2:
                        if eid != other:
                            co_pairs[tuple(sorted([eid, other]))] += 1
            except (json.JSONDecodeError, TypeError, AttributeError):
                pass
        for (a, b), count in co_pairs.most_common(50):
            if count >= 3:
                # Check not already connected
                existing = self._run_single(
                    "SELECT 1 FROM relations WHERE ((from_entity=? AND to_entity=?) OR (from_entity=? AND to_entity=?)) AND project_id=? AND type IN ('KNOWS','ALLY','FAMILY','ANTAGONIST','ROMANTIC') LIMIT 1",
                    (a, b, b, a, pid),
                )
                if not existing:
                    self._execute(
                        "INSERT OR IGNORE INTO relations (id, from_entity, to_entity, type, data, project_id, created_at, updated_at) VALUES (?, ?, ?, ?, '{}', ?, ?, ?)",
                        (str(uuid.uuid4())[:8], a, b, "KNOWS", pid, now, now),
                    )
                    stats["cooccur_added"] += 1

        # 3. Transitive closure: A-FAMILY->B, B-FAMILY->C => A-FAMILY->C
        transitive_types = ["FAMILY"]
        for rtype in transitive_types:
            tri_rows = self._run(
                """
                SELECT r1.from_entity AS aid, r2.to_entity AS bid
                FROM relations r1
                JOIN relations r2 ON r1.to_entity=r2.from_entity AND r1.project_id=r2.project_id
                WHERE r1.type=? AND r2.type=? AND r1.project_id=?
                  AND r1.from_entity <> r2.to_entity
                  AND NOT EXISTS (
                    SELECT 1 FROM relations r3
                    WHERE ((r3.from_entity=r1.from_entity AND r3.to_entity=r2.to_entity)
                           OR (r3.from_entity=r2.to_entity AND r3.to_entity=r1.from_entity))
                      AND r3.type=? AND r3.project_id=?
                  )
                LIMIT 100
            """,
                (rtype, rtype, pid, rtype, pid),
            )
            for r in tri_rows:
                self._execute(
                    "INSERT OR IGNORE INTO relations (id, from_entity, to_entity, type, data, project_id, created_at, updated_at) VALUES (?, ?, ?, ?, '{}', ?, ?, ?)",
                    (str(uuid.uuid4())[:8], r["aid"], r["bid"], rtype, pid, now, now),
                )
                stats["transitive_added"] += 1

        # 4. Structural equivalence: characters sharing the same non-character entity
        chars = self.list_entities(entity_type="character")
        if len(chars) >= 2:
            char_ids = [c.id for c in chars]
            placeholders = ",".join("?" for _ in char_ids)
            org_rows = self._run(
                f"""
                SELECT r.from_entity AS char_id, r.to_entity AS org_id, r.type
                FROM relations r
                WHERE r.from_entity IN ({placeholders}) AND r.project_id=?
                  AND r.to_entity NOT IN ({placeholders})
                LIMIT 500
            """,
                (*char_ids, pid, *char_ids),
            )
            from collections import defaultdict

            org_members: dict[str, list[str]] = defaultdict(list)
            for r in org_rows:
                org_members[r["org_id"]].append(r["char_id"])
            for org_id, members in org_members.items():
                if len(members) < 2:
                    continue
                for i, a in enumerate(members):
                    for b in members[i + 1 :]:
                        existing = self._run_single(
                            "SELECT 1 FROM relations WHERE ((from_entity=? AND to_entity=?) OR (from_entity=? AND to_entity=?)) AND project_id=? AND type='ALLY' LIMIT 1",
                            (a, b, b, a, pid),
                        )
                        if not existing:
                            self._execute(
                                "INSERT OR IGNORE INTO relations (id, from_entity, to_entity, type, data, project_id, created_at, updated_at) VALUES (?, ?, ?, ?, '{}', ?, ?, ?)",
                                (str(uuid.uuid4())[:8], a, b, "ALLY", pid, now, now),
                            )
                            stats["structural_added"] += 1

        self._invalidate_cache(pid)
        logger.info(
            "auto_complete_relations: symmetry=%d paired=%d unidirectional_clean=%d cooccur=%d transitive=%d structural=%d",
            stats["symmetry_added"],
            stats["paired_added"],
            stats["unidirectional_cleaned"],
            stats["cooccur_added"],
            stats["transitive_added"],
            stats["structural_added"],
        )
        return stats


# ── Module-level helpers ──


def _ensure_store_has_constraint_table(store: _SQLiteBase) -> None:
    """Idempotent DDL for constraints table (also in SCHEMA_SQL)."""
    store._execute("""
        CREATE TABLE IF NOT EXISTS constraints (
            id TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            constraint_type TEXT NOT NULL DEFAULT 'custom',
            target_entity TEXT NOT NULL DEFAULT '',
            condition TEXT NOT NULL DEFAULT '{}',
            violation_query TEXT NOT NULL DEFAULT '',
            severity TEXT NOT NULL DEFAULT 'hard',
            active INTEGER NOT NULL DEFAULT 1,
            project_id TEXT NOT NULL REFERENCES projects(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)


# ── Factory function ──
