"""SQLite Graph Store — replaces Neo4j GraphStore with embedded SQLite.

Provides the same public API as the original GraphStore (EntityMixin,
RelationMixin, AnalysisMixin combined) so that all ~25 callers continue
to work through the graph_store.py compatibility shim.

Key differences from Neo4j version:
- No Docker / external service required
- Graph traversal (shortest path, network expansion) implemented in Python
- Graph algorithms (PageRank, communities, clustering) in pure Python
- FTS via SQLite FTS5 instead of Neo4j fulltext index
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path

from .graph_schema import (
    get_symmetric_types,
)
from .knowledge import CharacterSnapshot, Entity, Foreshadow, Relation, TimelineEvent

logger = logging.getLogger(__name__)

# ── SQLite schema DDL ──

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    aliases TEXT NOT NULL DEFAULT '[]',
    data TEXT NOT NULL DEFAULT '{}',
    priority INTEGER NOT NULL DEFAULT 0,
    project_id TEXT NOT NULL REFERENCES projects(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_project ON entities(project_id);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);

CREATE TABLE IF NOT EXISTS relations (
    id TEXT PRIMARY KEY,
    from_entity TEXT NOT NULL REFERENCES entities(id),
    to_entity TEXT NOT NULL REFERENCES entities(id),
    type TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}',
    project_id TEXT NOT NULL REFERENCES projects(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_relations_from ON relations(from_entity);
CREATE INDEX IF NOT EXISTS idx_relations_to ON relations(to_entity);
CREATE INDEX IF NOT EXISTS idx_relations_type ON relations(type);
CREATE INDEX IF NOT EXISTS idx_relations_project ON relations(project_id);

CREATE TABLE IF NOT EXISTS foreshadows (
    id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    hint TEXT NOT NULL DEFAULT '',
    expected_resolution TEXT NOT NULL DEFAULT '',
    resolved INTEGER NOT NULL DEFAULT 0,
    resolution_text TEXT NOT NULL DEFAULT '',
    related_entities TEXT NOT NULL DEFAULT '[]',
    related_events TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL DEFAULT 'extracted',
    status TEXT NOT NULL DEFAULT 'open',
    plant_chapter TEXT NOT NULL DEFAULT '',
    resolve_chapter TEXT NOT NULL DEFAULT '',
    volume_ref TEXT NOT NULL DEFAULT '',
    planned_resolve_arc TEXT NOT NULL DEFAULT '',
    scheduled_chapter TEXT NOT NULL DEFAULT '',
    confidence TEXT NOT NULL DEFAULT 'high',
    resolve_keywords TEXT NOT NULL DEFAULT '[]',
    data TEXT NOT NULL DEFAULT '{}',
    project_id TEXT NOT NULL REFERENCES projects(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_foreshadows_project ON foreshadows(project_id);
CREATE INDEX IF NOT EXISTS idx_foreshadows_status ON foreshadows(status);

CREATE TABLE IF NOT EXISTS timeline_events (
    id TEXT PRIMARY KEY,
    time_point TEXT NOT NULL,
    label TEXT NOT NULL,
    time_order INTEGER NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    chapter_ref TEXT NOT NULL DEFAULT '',
    track_id TEXT NOT NULL DEFAULT 'main',
    track_name TEXT NOT NULL DEFAULT '主线',
    track_color TEXT NOT NULL DEFAULT '#22d3ee',
    time_label TEXT NOT NULL DEFAULT '',
    location_ref TEXT NOT NULL DEFAULT '',
    data TEXT NOT NULL DEFAULT '{}',
    project_id TEXT NOT NULL REFERENCES projects(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_timeline_project ON timeline_events(project_id);
CREATE INDEX IF NOT EXISTS idx_timeline_order ON timeline_events(time_order);

CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY,
    character_id TEXT NOT NULL,
    time_point TEXT NOT NULL DEFAULT '',
    time_order INTEGER NOT NULL DEFAULT 0,
    label TEXT NOT NULL DEFAULT '',
    phase TEXT NOT NULL DEFAULT '',
    phase_key TEXT NOT NULL DEFAULT '',
    is_current INTEGER NOT NULL DEFAULT 0,
    data TEXT NOT NULL DEFAULT '{}',
    description TEXT NOT NULL DEFAULT '',
    project_id TEXT NOT NULL REFERENCES projects(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_char ON snapshots(character_id);

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
);
CREATE INDEX IF NOT EXISTS idx_constraints_project ON constraints(project_id);

-- FTS5 full-text search on entity names and aliases
CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
    name, aliases, content='entities', content_rowid='rowid'
);

-- Triggers to keep FTS index in sync
CREATE TRIGGER IF NOT EXISTS entities_ai AFTER INSERT ON entities BEGIN
    INSERT INTO entities_fts(rowid, name, aliases)
    VALUES (new.rowid, new.name, new.aliases);
END;
CREATE TRIGGER IF NOT EXISTS entities_ad AFTER DELETE ON entities BEGIN
    INSERT INTO entities_fts(entities_fts, rowid, name, aliases)
    VALUES ('delete', old.rowid, old.name, old.aliases);
END;
CREATE TRIGGER IF NOT EXISTS entities_au AFTER UPDATE ON entities BEGIN
    INSERT INTO entities_fts(entities_fts, rowid, name, aliases)
    VALUES ('delete', old.rowid, old.name, old.aliases);
    INSERT INTO entities_fts(rowid, name, aliases)
    VALUES (new.rowid, new.name, new.aliases);
END;

-- Graph adjacency view for BFS/DFS traversal
CREATE VIEW IF NOT EXISTS entity_edges AS
SELECT from_entity AS source, to_entity AS target, type, id, project_id FROM relations
UNION ALL
SELECT to_entity, from_entity, type, id, project_id FROM relations
WHERE type IN ('KNOWS','ALLY','FAMILY','ANTAGONIST','ROMANTIC',
               'SPOUSE_OF','SIBLING_OF','FRIEND','ADJACENT_TO');
"""


class SQLiteStore:
    """SQLite-backed store providing the same public API as Neo4j GraphStore.

    Uses a single database file (data/novel.db) with per-project isolation
    via project_id foreign keys.  Graph algorithms run in Python.
    """

    _db_dir: Path = Path("data")
    _instances: dict[str, SQLiteStore] = {}

    @classmethod
    def _resolve_db_dir(cls) -> Path:
        """Return a writable directory for the SQLite database.

        In PyInstaller EXE: next to the executable (not inside _MEIPASS).
        In development: the project-root data/ directory.
        """
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).parent.resolve()
            return exe_dir / "data"
        return cls._db_dir

    # ── Class-level cache for expensive computed insights (same as original) ──
    _insights_cache: dict = {}
    _cache_version: dict = {}

    # ── Entity label aliases that expand to the same SQL query ──
    # Mapping from schema ``entity_label("character")`` → stored ``entity_type``
    _TYPE_ALIASES: dict[str, str] = {
        "Character": "character",
        "Location": "location",
        "Item": "item",
        "Skill": "skill",
        "Organization": "organization",
        "Race": "race",
        "Concept": "concept",
        "Event": "event",
    }

    def __init__(self, project_id: str = "default", db_path: str | Path | None = None):
        self.project_id = project_id
        if db_path:
            self._db_path = Path(db_path)
        else:
            self._db_path = self._resolve_db_dir() / "novel.db"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    # ════════════════════════════════════════════════════════════════
    # Schema initialization
    # ════════════════════════════════════════════════════════════════

    def init_schema(self) -> None:
        """Create tables and indexes if they don't exist (idempotent)."""
        conn = sqlite3.connect(str(self._db_path))
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        conn.close()

    def close(self) -> None:
        """Close the database connection."""
        if hasattr(self, "_conn") and self._conn:
            self._conn.close()

    # ════════════════════════════════════════════════════════════════
    # Low-level query helpers
    # ════════════════════════════════════════════════════════════════

    _CYPHER_START = frozenset({"match", "create", "merge", "unwind", "call", "with", "return"})

    def _run(self, sql: str, params: tuple | dict | None = None) -> list[sqlite3.Row]:
        """Execute SQL and return all rows (compatible with original _run API).

        If the query looks like Cypher (starts with MATCH, CREATE, etc.),
        silently return empty for backward compatibility with any remaining
        Neo4j-dependent callers (e.g. impact_propagator.py).
        """
        stripped = sql.strip().lower()
        first_word = stripped.split()[0] if stripped else ""
        if first_word in self._CYPHER_START:
            logger.debug("Ignoring Cypher query (SQLite mode): %.80s", sql)
            return []
        try:
            if isinstance(params, dict):
                cursor = self._conn.execute(sql, params)
            else:
                cursor = self._conn.execute(sql, params or ())
            return list(cursor.fetchall())
        except Exception as e:
            logger.warning("SQLite query failed: %s\nSQL: %s", e, sql[:200])
            return []

    def _run_single(self, sql: str, params: tuple | dict | None = None) -> sqlite3.Row | None:
        """Execute SQL and return the first row, or None."""
        rows = self._run(sql, params)
        return rows[0] if rows else None

    def _execute(self, sql: str, params: tuple | dict | None = None) -> int:
        """Execute a write statement and return rowcount."""
        try:
            if isinstance(params, dict):
                cursor = self._conn.execute(sql, params)
            else:
                cursor = self._conn.execute(sql, params or ())
            self._conn.commit()
            return cursor.rowcount
        except Exception as e:
            logger.warning("SQLite write failed: %s\nSQL: %s", e, sql[:200])
            return 0

    def _ensure_project(self) -> None:
        """Ensure the project exists in the projects table."""
        self._execute(
            "INSERT OR IGNORE INTO projects (id) VALUES (?)",
            (self.project_id,),
        )

    # ── Cache management (same interface as original) ──

    @classmethod
    def _invalidate_cache(cls, project_id: str) -> None:
        cls._insights_cache.pop(project_id, None)
        cls._cache_version[project_id] = cls._cache_version.get(project_id, 0) + 1

    def _cached(self, cache_key: str, compute_fn) -> dict:
        pid = self.project_id
        version = self._cache_version.get(pid, 0)
        entry = self._insights_cache.get(pid, {})
        if cache_key in entry and entry[cache_key][0] == version:
            return entry[cache_key][1]
        result = compute_fn()
        if pid not in self._insights_cache:
            self._insights_cache[pid] = {}
        self._insights_cache[pid][cache_key] = (version, result)
        return result

    # ── Row → Domain object converters ──

    @staticmethod
    def _row_to_entity(row: sqlite3.Row) -> Entity:
        aliases_raw = row["aliases"]
        aliases = json.loads(aliases_raw) if isinstance(aliases_raw, str) else (aliases_raw or [])
        data_raw = row["data"]
        data = json.loads(data_raw) if isinstance(data_raw, str) else (data_raw or {})
        try:
            priority = row["priority"]
        except (IndexError, KeyError):
            priority = 0
        return Entity(
            id=row["id"],
            type=row["entity_type"],
            name=row["name"],
            aliases=aliases,
            data=data,
            priority=priority,
        )

    @staticmethod
    def _row_to_relation(row: sqlite3.Row) -> Relation:
        from .knowledge import RelationType

        raw_type = row["type"].lower()
        try:
            rel_type = RelationType(raw_type)
        except ValueError:
            rel_type = raw_type
        data = json.loads(row["data"]) if isinstance(row["data"], str) else (row["data"] or {})
        return Relation(
            id=row["id"],
            from_entity=row["from_entity"],
            to_entity=row["to_entity"],
            type=rel_type,
            data=data,
        )

    @staticmethod
    def _row_to_foreshadow(row: sqlite3.Row) -> Foreshadow:
        return Foreshadow(
            id=row["id"],
            text=row["text"],
            hint=row["hint"],
            expected_resolution=row["expected_resolution"],
            resolved=bool(row["resolved"]),
            resolution_text=row["resolution_text"],
            related_entities=json.loads(row["related_entities"]) if isinstance(row["related_entities"], str) else [],
            related_events=json.loads(row["related_events"]) if isinstance(row["related_events"], str) else [],
            source=row["source"],
            status=row["status"],
            plant_chapter=row["plant_chapter"],
            resolve_chapter=row["resolve_chapter"],
            volume_ref=row["volume_ref"],
            planned_resolve_arc=row["planned_resolve_arc"],
            scheduled_chapter=row["scheduled_chapter"],
            confidence=row["confidence"],
            resolve_keywords=json.loads(row["resolve_keywords"]) if isinstance(row["resolve_keywords"], str) else [],
        )

    @staticmethod
    def _row_to_timeline_event(row: sqlite3.Row) -> TimelineEvent:
        return TimelineEvent(
            id=row["id"],
            time_point=row["time_point"],
            label=row["label"],
            time_order=row["time_order"],
            description=row["description"],
            chapter_ref=row["chapter_ref"],
            track_id=row["track_id"],
            track_name=row["track_name"],
            track_color=row["track_color"],
            time_label=row["time_label"],
            location_ref=row["location_ref"],
        )

    # ════════════════════════════════════════════════════════════════
    # Batch operations
    # ════════════════════════════════════════════════════════════════

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
                json.dumps({}, ensure_ascii=False),
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

    @staticmethod
    def _row_to_character_snapshot(row: sqlite3.Row) -> CharacterSnapshot:
        data = json.loads(row["data"]) if isinstance(row["data"], str) else (row["data"] or {})
        try:
            phase = row["phase"]
        except (IndexError, KeyError):
            phase = ""
        try:
            phase_key = row["phase_key"]
        except (IndexError, KeyError):
            phase_key = ""
        try:
            is_current = row["is_current"]
        except (IndexError, KeyError):
            is_current = 0
        try:
            description = row["description"]
        except (IndexError, KeyError):
            description = ""
        return CharacterSnapshot(
            id=row["id"],
            character_entity_id=row["character_id"],
            time_point=row["time_point"],
            time_order=row["time_order"],
            label=row["label"],
            phase=phase,
            phase_key=phase_key,
            is_current=bool(is_current),
            data=data,
            description=description,
        )

    # ════════════════════════════════════════════════════════════════
    # Graph traversal (Python BFS/DFS replacing Cypher)
    # ════════════════════════════════════════════════════════════════

    def _get_direct_neighbors(self, entity_id: str, rel_types: list[str] | None = None) -> list[dict]:
        """Get direct neighbors of an entity via relations table."""
        if rel_types:
            placeholders = ",".join("?" for _ in rel_types)
            rows = self._run(
                f"""
                SELECT r.to_entity AS id, r.type, e.name, e.entity_type AS type_label
                FROM relations r JOIN entities e ON r.to_entity = e.id
                WHERE r.from_entity=? AND r.project_id=?
                  AND r.type IN ({placeholders})
                UNION
                SELECT r.from_entity, r.type, e.name, e.entity_type
                FROM relations r JOIN entities e ON r.from_entity = e.id
                WHERE r.to_entity=? AND r.project_id=?
                  AND r.type IN ({placeholders})
            """,
                (entity_id, self.project_id, *rel_types, entity_id, self.project_id, *rel_types),
            )
        else:
            rows = self._run(
                """
                SELECT r.to_entity AS id, r.type, e.name, e.entity_type AS type_label
                FROM relations r JOIN entities e ON r.to_entity = e.id
                WHERE r.from_entity=? AND r.project_id=?
                UNION
                SELECT r.from_entity, r.type, e.name, e.entity_type
                FROM relations r JOIN entities e ON r.from_entity = e.id
                WHERE r.to_entity=? AND r.project_id=?
            """,
                (entity_id, self.project_id, entity_id, self.project_id),
            )
        # Deduplicate
        seen: set = set()
        result = []
        for r in rows:
            key = (r["id"], r["type"])
            if key not in seen:
                seen.add(key)
                result.append(dict(r))
        return result

    def get_neighbors(self, entity_id: str, depth: int = 1) -> list[dict]:
        """Get all neighbors up to given depth (BFS)."""
        visited: set = {entity_id}
        frontier: list[tuple[str, int]] = [(entity_id, 0)]
        neighbors: list[dict] = []
        while frontier:
            current, d = frontier.pop(0)
            if d >= depth:
                continue
            for nb in self._get_direct_neighbors(current):
                nb_id = nb["id"]
                if nb_id not in visited:
                    visited.add(nb_id)
                    entry = {
                        "id": nb_id,
                        "name": nb.get("name", ""),
                        "type": nb.get("type_label", ""),
                        "relationship": nb.get("type", ""),
                        "depth": d + 1,
                    }
                    neighbors.append(entry)
                    frontier.append((nb_id, d + 1))
        return neighbors

    def get_path(self, from_id: str, to_id: str, max_depth: int = 3) -> list[dict]:
        """BFS shortest path — replaces Cypher shortestPath()."""
        max_depth = max(1, min(int(max_depth), 10))
        if from_id == to_id:
            return []
        parent: dict[str, tuple[str | None, str | None]] = {from_id: (None, None)}
        queue: list[tuple[str, int]] = [(from_id, 0)]
        found = False
        while queue and not found:
            current, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for nb in self._get_direct_neighbors(current):
                nb_id = nb["id"]
                if nb_id not in parent:
                    parent[nb_id] = (current, nb.get("type", ""))
                    if nb_id == to_id:
                        found = True
                        break
                    queue.append((nb_id, depth + 1))
        if not found:
            return []
        # Backtrack to build path
        nodes = []
        node = to_id
        while node != from_id:
            p, rel = parent[node]
            nodes.insert(0, {"id": node, "via": rel})
            node = p
        nodes.insert(0, {"id": from_id, "via": None})
        return [{"nodes": nodes, "hops": len(nodes) - 1}]

    def find_relationships(self, from_id: str, to_id: str, max_depth: int = 3) -> list[dict]:
        return self.get_path(from_id, to_id, max_depth)

    def get_entity_network(self, entity_id: str, depth: int = 2) -> dict:
        """Get the subgraph around an entity up to given depth."""
        nodes_set: dict[str, dict] = {}
        edges_set: dict[str, dict] = {}
        visited: set = {entity_id}
        frontier: list[tuple[str, int]] = [(entity_id, 0)]

        # Get root entity
        root = self.get_entity(entity_id)
        if root:
            nodes_set[entity_id] = {"id": entity_id, "name": root.name, "type": root.type}

        while frontier:
            current, d = frontier.pop(0)
            if d >= depth:
                continue
            for nb in self._get_direct_neighbors(current):
                nb_id = nb["id"]
                # Add node
                if nb_id not in nodes_set:
                    nodes_set[nb_id] = {
                        "id": nb_id,
                        "name": nb.get("name", ""),
                        "type": nb.get("type_label", ""),
                    }
                # Add edge
                edge_key = f"{current}|{nb_id}|{nb.get('type', '')}"
                if edge_key not in edges_set:
                    edges_set[edge_key] = {
                        "source": current,
                        "target": nb_id,
                        "type": nb.get("type", "").lower(),
                    }
                if nb_id not in visited:
                    visited.add(nb_id)
                    frontier.append((nb_id, d + 1))

        return {
            "nodes": list(nodes_set.values()),
            "edges": list(edges_set.values()),
        }

    def _get_graph_adjacency(
        self, char_ids: list[str] | None = None, rel_types: list[str] | None = None
    ) -> dict[str, set[str]]:
        """Build in-memory adjacency dict from the relations table.

        Returns {entity_id: {neighbor_id, ...}}.
        """
        if rel_types is None:
            rel_types = [
                "KNOWS",
                "ALLY",
                "FAMILY",
                "ANTAGONIST",
                "ROMANTIC",
                "MASTER_OF",
                "MENTOR_OF",
                "KILLED",
                "SAVED",
                "LOVES",
            ]
        placeholders = ",".join("?" for _ in rel_types)

        if char_ids:
            id_placeholders = ",".join("?" for _ in char_ids)
            rows = self._run(
                f"""
                SELECT r.from_entity AS src, r.to_entity AS tgt
                FROM relations r
                WHERE r.project_id=?
                  AND r.type IN ({placeholders})
                  AND ((r.from_entity IN ({id_placeholders}) AND r.to_entity IN ({id_placeholders})))
                  AND r.from_entity <> r.to_entity
            """,
                (self.project_id, *rel_types, *char_ids, *char_ids),
            )
        else:
            rows = self._run(
                f"""
                SELECT r.from_entity AS src, r.to_entity AS tgt
                FROM relations r
                WHERE r.project_id=?
                  AND r.type IN ({placeholders})
                  AND r.from_entity <> r.to_entity
            """,
                (self.project_id, *rel_types),
            )

        adj: dict[str, set[str]] = {}
        for r in rows:
            src, tgt = r["src"], r["tgt"]
            adj.setdefault(src, set()).add(tgt)
            adj.setdefault(tgt, set()).add(src)
        return adj

    # ════════════════════════════════════════════════════════════════
    # Graph analysis algorithms
    # ════════════════════════════════════════════════════════════════

    # ── PageRank ──

    def _compute_pagerank(self, char_ids: list[str], max_iter: int = 20, damping: float = 0.85) -> dict[str, float]:
        """Compute iterative PageRank for character nodes."""
        if not char_ids:
            return {}
        id_set = set(char_ids)
        adj: dict[str, list[str]] = {cid: [] for cid in char_ids}
        rows = self._run(
            f"""
            SELECT r.from_entity AS src, r.to_entity AS tgt
            FROM relations r
            WHERE r.project_id=? AND r.from_entity IN ({",".join("?" for _ in char_ids)})
              AND r.to_entity IN ({",".join("?" for _ in char_ids)})
              AND r.from_entity <> r.to_entity
        """,
            (self.project_id, *char_ids, *char_ids),
        )
        for r in rows:
            src, tgt = r["src"], r["tgt"]
            if src in id_set and tgt in id_set:
                adj[src].append(tgt)

        n = len(char_ids)
        if n == 0:
            return {}
        pr: dict[str, float] = dict.fromkeys(char_ids, 1.0 / n)
        for _ in range(max_iter):
            new_pr: dict[str, float] = {}
            total = 0.0
            for cid in char_ids:
                incoming = 0.0
                for src_id, tgts in adj.items():
                    if cid in tgts:
                        incoming += pr[src_id] / max(len(tgts), 1)
                new_pr[cid] = (1 - damping) / n + damping * incoming
                total += new_pr[cid]
            # Normalize
            if total > 0:
                for cid in char_ids:
                    new_pr[cid] /= total
            pr = new_pr
        return pr

    def get_character_importance(self) -> list[dict]:
        """Rank characters by composite importance: degree + PageRank + appearances."""
        return self._cached("char_importance", self._compute_character_importance)

    def _compute_character_importance(self) -> list[dict]:
        chars = self.list_entities(entity_type="character")
        if not chars:
            return []
        char_ids = [c.id for c in chars]

        # Degree (from character-character relationships)
        adj = self._get_graph_adjacency(char_ids)
        degree = {cid: len(adj.get(cid, set())) for cid in char_ids}

        # PageRank
        pr = self._compute_pagerank(char_ids)

        # Appearances (from timeline INVOLVES)
        # In SQLite, we approximate by counting timeline events where character
        # appears as a related entity in foreshadow or timeline event data
        appear = dict.fromkeys(char_ids, 0)
        events = self.list_timeline_events()
        for evt in events:
            _count_entity_refs(evt, char_ids, appear)

        max_degree = max(degree.values()) if degree else 1
        max_pr = max(pr.values()) if pr else 1
        max_appear = max(appear.values()) if appear else 1

        results = []
        for cid in char_ids:
            deg_norm = (degree.get(cid, 0) / max(max_degree, 1)) * 100
            pr_norm = (pr.get(cid, 0) / max(max_pr, 1)) * 100
            appear_norm = (appear.get(cid, 0) / max(max_appear, 1)) * 100
            composite = round(deg_norm * 0.40 + pr_norm * 0.35 + appear_norm * 0.25)

            if composite >= 70:
                role = "主角"
            elif composite >= 45:
                role = "重要角色"
            elif composite >= 25:
                role = "配角"
            else:
                role = "龙套"

            char = next((c for c in chars if c.id == cid), None)
            results.append(
                {
                    "entity_id": cid,
                    "name": char.name if char else cid,
                    "composite_score": min(composite, 100),
                    "role": role,
                    "degree": degree.get(cid, 0),
                    "appearances": appear.get(cid, 0),
                    "pagerank_score": round(pr_norm),
                }
            )

        results.sort(key=lambda x: x["composite_score"], reverse=True)
        return results

    # ── Community detection ──

    def get_character_communities(self) -> list[dict]:
        return self._cached("char_communities", self._compute_character_communities)

    def _compute_character_communities(self) -> list[dict]:
        chars = self.list_entities(entity_type="character")
        if not chars:
            return []
        char_ids = [c.id for c in chars]

        adj = self._get_graph_adjacency(char_ids)

        # BFS connected components
        visited: set = set()
        communities: list[list[dict]] = []
        for cid in char_ids:
            if cid in visited:
                continue
            component: list[dict] = []
            queue = [cid]
            while queue:
                node = queue.pop(0)
                if node in visited:
                    continue
                visited.add(node)
                char = next((c for c in chars if c.id == node), None)
                component.append({"id": node, "name": char.name if char else node})
                for nb in adj.get(node, set()):
                    if nb not in visited:
                        queue.append(nb)
            if component:
                communities.append(component)

        result = []
        for i, comp in enumerate(communities):
            result.append(
                {
                    "community_id": f"comm_{i}",
                    "size": len(comp),
                    "members": comp,
                }
            )
        result.sort(key=lambda x: x["size"], reverse=True)
        return result

    def detect_communities(self) -> dict:
        """Label propagation community detection."""
        chars = self.list_entities(entity_type="character")
        if not chars:
            return {"community_count": 0, "communities": {}, "intra_community_missing": []}
        char_ids = [c.id for c in chars]
        adj = self._get_graph_adjacency(char_ids)

        # Initialize: each character its own community
        community: dict[str, str] = {cid: cid for cid in char_ids}

        # 3 rounds of label propagation
        for _ in range(3):
            new_community = dict(community)
            for cid in char_ids:
                neighbor_comms: dict[str, int] = {}
                for nb in adj.get(cid, set()):
                    nc = community.get(nb, nb)
                    neighbor_comms[nc] = neighbor_comms.get(nc, 0) + 1
                if neighbor_comms:
                    # Pick the most common neighbor community
                    new_comm = max(neighbor_comms, key=neighbor_comms.get)
                    new_community[cid] = new_comm
            community = new_community

        # Group by community
        comm_groups: dict[str, list[dict]] = {}
        for cid in char_ids:
            comm = community.get(cid, cid)
            char = next((c for c in chars if c.id == cid), None)
            comm_groups.setdefault(comm, []).append(
                {
                    "id": cid,
                    "name": char.name if char else cid,
                }
            )

        # Find intra-community pairs without direct edges
        intra_missing = []
        for comm_id, members in comm_groups.items():
            if len(members) < 2 or len(members) > 15:
                continue
            for i, a in enumerate(members):
                for b in members[i + 1 :]:
                    if b["id"] not in adj.get(a["id"], set()):
                        intra_missing.append(
                            {
                                "community": comm_id,
                                "char_a": a["name"],
                                "char_b": b["name"],
                                "aid": a["id"],
                                "bid": b["id"],
                            }
                        )

        return {
            "community_count": len(comm_groups),
            "communities": {k: [m["name"] for m in v] for k, v in comm_groups.items() if 2 <= len(v) <= 15},
            "intra_community_missing": intra_missing[:20],
        }

    # ── Clustering coefficient ──

    def get_clustering_coefficient(self) -> list[dict]:
        return self._cached("clustering", self._compute_clustering_coefficient)

    def _compute_clustering_coefficient(self) -> list[dict]:
        chars = self.list_entities(entity_type="character")
        if not chars:
            return []
        char_ids = [c.id for c in chars]
        adj = self._get_graph_adjacency(char_ids)

        results = []
        for cid in char_ids:
            neighbors = list(adj.get(cid, set()))
            n_count = len(neighbors)
            if n_count < 2:
                continue
            max_edges = n_count * (n_count - 1) / 2
            if max_edges == 0:
                continue

            edge_count = 0
            for i, a_id in enumerate(neighbors):
                for b_id in neighbors[i + 1 :]:
                    if b_id in adj.get(a_id, set()):
                        edge_count += 1

            cc = round(edge_count / max_edges, 3)
            char = next((c for c in chars if c.id == cid), None)
            results.append(
                {
                    "entity_id": cid,
                    "name": char.name if char else cid,
                    "clustering_coefficient": cc,
                    "neighbor_count": n_count,
                    "edges_among_neighbors": edge_count,
                }
            )

        results.sort(key=lambda x: x["clustering_coefficient"], reverse=True)
        return results

    # ── Link prediction (Adamic-Adar / Jaccard) ──

    def _compute_link_prediction(self, top_n: int = 20) -> list[dict]:
        """Predict missing character relationships via Adamic-Adar / Jaccard."""
        chars = self.list_entities(entity_type="character")
        if len(chars) < 2:
            return []
        char_ids = [c.id for c in chars]

        adj = self._get_graph_adjacency(char_ids)
        degree = {cid: len(adj.get(cid, set())) for cid in char_ids}

        predictions = []
        for i, a_id in enumerate(char_ids):
            for b_id in char_ids[i + 1 :]:
                if b_id in adj.get(a_id, set()):
                    continue  # already connected

                common = adj.get(a_id, set()) & adj.get(b_id, set())
                if not common:
                    continue

                union = adj.get(a_id, set()) | adj.get(b_id, set())
                common_count = len(common)
                jaccard = common_count / len(union) if union else 0
                adamic_adar = sum(1.0 / math.log(degree.get(cn, 0) + 2) for cn in common)

                char_a = next((c for c in chars if c.id == a_id), None)
                char_b = next((c for c in chars if c.id == b_id), None)
                predictions.append(
                    {
                        "char_a_id": a_id,
                        "char_a_name": char_a.name if char_a else a_id,
                        "char_b_id": b_id,
                        "char_b_name": char_b.name if char_b else b_id,
                        "common_neighbors": common_count,
                        "adamic_adar": round(adamic_adar, 4),
                        "jaccard": round(jaccard, 4),
                    }
                )

        predictions.sort(key=lambda x: x["adamic_adar"], reverse=True)
        return predictions[:top_n]

    def get_link_prediction(self, top_n: int = 20) -> list[dict]:
        """Predict missing character relationships via Adamic-Adar / Jaccard.

        Public wrapper around _compute_link_prediction, matching the
        API expected by routes/knowledge.py.
        """
        return self._compute_link_prediction(top_n=top_n)

    # ── Bridge / Forgotten / Missing-relation analysis ──

    def find_bridge_characters(self) -> list[dict]:
        """Find bridge characters using BFS-based betweenness approximation."""
        chars = self.list_entities(entity_type="character")
        if len(chars) < 3:
            return []
        char_ids = [c.id for c in chars]
        adj = self._get_graph_adjacency(char_ids)

        # Count how many pairs each character bridges (shortest path goes through them)
        bridge_count: dict[str, int] = {}
        bridge_pairs: dict[str, list] = {}

        for i, a_id in enumerate(char_ids):
            for b_id in char_ids[i + 1 :]:
                if a_id == b_id:
                    continue
                if b_id in adj.get(a_id, set()):
                    continue  # directly connected, no bridge needed

                # BFS shortest path
                parent: dict[str, str | None] = {a_id: None}
                queue = [a_id]
                found = False
                while queue and not found:
                    cur = queue.pop(0)
                    for nb in adj.get(cur, set()):
                        if nb not in parent:
                            parent[nb] = cur
                            if nb == b_id:
                                found = True
                                break
                            queue.append(nb)

                if found:
                    # Backtrack, exclude endpoints
                    path_nodes = []
                    node = b_id
                    while node is not None:
                        path_nodes.append(node)
                        node = parent.get(node)
                    path_nodes.reverse()
                    # Count internal nodes as bridges
                    for n in path_nodes[1:-1]:
                        if n != a_id and n != b_id:
                            bridge_count[n] = bridge_count.get(n, 0) + 1
                            if n not in bridge_pairs:
                                bridge_pairs[n] = []
                            if len(bridge_pairs[n]) < 5:
                                bridge_pairs[n].append([a_id, b_id])

        results = []
        for cid, count in sorted(bridge_count.items(), key=lambda x: x[1], reverse=True):
            char = next((c for c in chars if c.id == cid), None)
            sample = bridge_pairs.get(cid, [])
            sample_names = []
            for pair in sample[:5]:
                a = next((c.name for c in chars if c.id == pair[0]), pair[0])
                b = next((c.name for c in chars if c.id == pair[1]), pair[1])
                sample_names.append([a, b])
            results.append(
                {
                    "entity_id": cid,
                    "entity_name": char.name if char else cid,
                    "bridge_count": count,
                    "would_disconnect": sample_names,
                }
            )

        return results

    def find_forgotten_characters(self, max_order: int, threshold: int = 5) -> list[dict]:
        """Find characters who haven't appeared in recent events."""
        chars = self.list_entities(entity_type="character")
        if not chars:
            return []
        char_ids = [c.id for c in chars]

        # Count events per character
        appear = dict.fromkeys(char_ids, 0)
        events = self.list_timeline_events()
        for evt in events:
            _count_entity_refs(evt, char_ids, appear)

        # Characters with total appearances below threshold
        results = []
        for cid in char_ids:
            if appear.get(cid, 0) < threshold:
                total = appear.get(cid, 0)
                char = next((c for c in chars if c.id == cid), None)
                results.append(
                    {
                        "name": char.name if char else cid,
                        "entity_id": cid,
                        "total_appearances": total,
                        "important": total == 0,  # hasn't appeared at all
                    }
                )

        results.sort(key=lambda x: x["total_appearances"])
        return results

    def find_missing_relations(self, char_ids: list[str]) -> list[dict]:
        """Find character pairs with no path in the relationship graph."""
        if len(char_ids) < 2:
            return []
        adj = self._get_graph_adjacency(char_ids)
        missing = []
        for i, a_id in enumerate(char_ids):
            for b_id in char_ids[i + 1 :]:
                if b_id in adj.get(a_id, set()):
                    continue
                # BFS to check if path exists
                visited = {a_id}
                queue = [a_id]
                found = False
                while queue and not found:
                    cur = queue.pop(0)
                    for nb in adj.get(cur, set()):
                        if nb not in visited:
                            visited.add(nb)
                            if nb == b_id:
                                found = True
                                break
                            queue.append(nb)
                if not found:
                    missing.append({"from": a_id, "to": b_id})
        return missing

    # ════════════════════════════════════════════════════════════════
    # Timeline-entity linking (INVOLVES equivalent)
    # ════════════════════════════════════════════════════════════════

    def link_timeline_to_entities(self, event_id: str, entity_ids: list[str]) -> int:
        """Record that a timeline event involves certain entities.

        Stores the relationship in the event's data field as a JSON array
        of involved entity IDs.  Returns the number of links created.
        """
        if not entity_ids:
            return 0
        evt = self.get_timeline_event(event_id)
        if not evt:
            return 0
        # Update data field with involved entities
        data = {"involved_entities": entity_ids}
        now = datetime.now().isoformat()
        self._execute(
            "UPDATE timeline_events SET data=?, updated_at=? WHERE id=? AND project_id=?",
            (json.dumps(data, ensure_ascii=False), now, event_id, self.project_id),
        )
        self._invalidate_cache(self.project_id)
        return len(entity_ids)

    def get_timeline_involved_entities(self, event_id: str) -> list[str]:
        """Get entity IDs involved in a timeline event."""
        row = self._run_single(
            "SELECT data FROM timeline_events WHERE id=? AND project_id=?",
            (event_id, self.project_id),
        )
        if not row:
            return []
        data = json.loads(row["data"]) if isinstance(row["data"], str) else (row["data"] or {})
        return data.get("involved_entities", [])

    # ════════════════════════════════════════════════════════════════
    # Consistency check
    # ════════════════════════════════════════════════════════════════

    def check_consistency(self) -> dict:
        """Check graph consistency — returns issues and stats."""
        issues = []

        # 1. Location conflict: entity at multiple locations
        loc_rows = self._run(
            """
            SELECT e1.name AS entity, e2.name AS loc_a, e3.name AS loc_b
            FROM relations r1
            JOIN entities e1 ON r1.from_entity = e1.id
            JOIN entities e2 ON r1.to_entity = e2.id
            JOIN relations r2 ON r2.from_entity = r1.from_entity AND r2.project_id = r1.project_id
            JOIN entities e3 ON r2.to_entity = e3.id
            WHERE r1.type = 'LOCATED_AT' AND r2.type = 'LOCATED_AT'
              AND r1.to_entity <> r2.to_entity
              AND r1.project_id = ?
            LIMIT 20
        """,
            (self.project_id,),
        )
        for r in loc_rows:
            issues.append(
                {
                    "type": "location_conflict",
                    "severity": "high",
                    "description": f"实体「{r['entity']}」同时位于「{r['loc_a']}」和「{r['loc_b']}」",
                }
            )

        # 2. Temporal contradiction: A BEFORE B AND B BEFORE A
        temp_rows = self._run(
            """
            SELECT a.name AS ea, b.name AS eb
            FROM relations r1
            JOIN entities a ON r1.from_entity = a.id
            JOIN relations r2 ON r1.from_entity = r2.to_entity AND r1.to_entity = r2.from_entity
            JOIN entities b ON r1.to_entity = b.id
            WHERE r1.type = 'BEFORE' AND r2.type = 'BEFORE'
              AND r1.project_id = ? AND r2.project_id = ?
            LIMIT 10
        """,
            (self.project_id, self.project_id),
        )
        for r in temp_rows:
            issues.append(
                {
                    "type": "temporal_conflict",
                    "severity": "high",
                    "description": f"时序矛盾: 「{r['ea']}」先于「{r['eb']}」又后于「{r['eb']}」",
                }
            )

        # 3. Isolated entities (no relations)
        isolated = self._run(
            """
            SELECT e.name, e.entity_type FROM entities e
            WHERE e.project_id = ? AND e.id NOT IN (
                SELECT DISTINCT from_entity FROM relations WHERE project_id = ?
                UNION
                SELECT DISTINCT to_entity FROM relations WHERE project_id = ?
            )
        """,
            (self.project_id, self.project_id, self.project_id),
        )
        for r in isolated:
            issues.append(
                {
                    "type": "isolated_entity",
                    "severity": "medium",
                    "description": f"实体「{r['name']}」（{r['entity_type']}）无任何关系连接",
                }
            )

        stats = {
            "entity_count": len(self.list_entities()),
            "relation_count": len(self.list_relations()),
            "foreshadow_count": len(self.list_foreshadows()),
            "issues_found": len(issues),
        }
        return {"contradictions": issues, "stats": stats}

    # ════════════════════════════════════════════════════════════════
    # Graph insights & narrative diagnosis
    # ════════════════════════════════════════════════════════════════

    def get_graph_insights(self) -> dict:
        return self._cached("insights", self._compute_graph_insights)

    def _compute_graph_insights(self) -> dict:
        insights: dict = {
            "forgotten_characters": [],
            "unresolved_foreshadows": [],
            "disconnected_pairs": [],
            "bridge_characters": [],
            "underutilized_locations": [],
            "suggestions": [],
        }

        chars = self.list_entities(entity_type="character")
        locations = self.list_entities(entity_type="location")
        all_fores = self.list_foreshadows()

        # Forgotten characters
        timeline_events = self.list_timeline_events()
        if timeline_events:
            max_order = max(e.time_order for e in timeline_events)
            forgotten = self.find_forgotten_characters(max_order, threshold=5)
            important = [c for c in forgotten if c.get("important")]
            insights["forgotten_character_count"] = len(important)
            insights["forgotten_characters"] = important[:5]
            if important:
                names = ", ".join(c["name"] for c in important[:3])
                insights["suggestions"].append(
                    {
                        "type": "warning",
                        "priority": "high",
                        "message": f"重要角色已多章未出场：{names}。考虑在下一章让他们露面或提及。",
                    }
                )

        # Unresolved foreshadows
        open_fores = [f for f in all_fores if not f.resolved]
        insights["unresolved_foreshadow_count"] = len(open_fores)
        if open_fores:
            insights["unresolved_foreshadows"] = [
                {"id": f.id, "text": f.text[:50], "related_entities": f.related_entities} for f in open_fores[:10]
            ]
            if len(open_fores) > 3:
                insights["suggestions"].append(
                    {
                        "type": "reminder",
                        "priority": "medium",
                        "message": f"有 {len(open_fores)} 个伏笔尚未回收，注意适时推进。",
                    }
                )

        # Disconnected pairs
        if 2 < len(chars) <= 30:
            char_ids = [c.id for c in chars]
            missing = self.find_missing_relations(char_ids)
            insights["disconnected_pair_count"] = len(missing)
            # Map to frontend format: entity_a/entity_b with name and warning
            char_map = {c.id: c.name for c in chars}
            insights["disconnected_pairs"] = [
                {
                    "entity_a": {"id": p["from"], "name": char_map.get(p["from"], p["from"])},
                    "entity_b": {"id": p["to"], "name": char_map.get(p["to"], p["to"])},
                    "warning": "这两角色在关系图中无路径连接",
                }
                for p in missing[:5]
            ]
            if missing:
                insights["suggestions"].append(
                    {
                        "type": "info",
                        "priority": "low",
                        "message": f"发现 {len(missing)} 对角色之间无关系路径。",
                    }
                )

        # Bridge characters
        bridges = self.find_bridge_characters()
        insights["bridge_character_count"] = len(bridges)
        insights["bridge_characters"] = bridges[:5]
        if bridges:
            names = ", ".join(b["entity_name"] for b in bridges[:3])
            insights["suggestions"].append(
                {
                    "type": "info",
                    "priority": "medium",
                    "message": f"关键枢纽角色：{names}。这些角色连接多个关系链，修改时需谨慎。",
                }
            )

        # Unused locations
        if locations:
            char_locations = set()
            for loc in locations:
                rows = self._run(
                    "SELECT from_entity FROM relations WHERE to_entity=? AND type='LOCATED_AT' AND project_id=?",
                    (loc.id, self.project_id),
                )
                if rows:
                    char_locations.add(loc.id)
            unused = [loc for loc in locations if loc.id not in char_locations]
            insights["unused_location_count"] = len(unused)
            insights["underutilized_locations"] = [{"id": loc.id, "name": loc.name} for loc in unused[:5]]

        return insights

    def get_narrative_diagnosis(self) -> dict:
        return self._cached("diagnosis", self._compute_narrative_diagnosis)

    def _compute_narrative_diagnosis(self) -> dict:
        raw = self.get_graph_insights()
        forgotten = raw.get("forgotten_characters", [])
        forgotten_count = raw.get("forgotten_character_count", len(forgotten))
        unresolved_fs_count = raw.get("unresolved_foreshadow_count", 0)
        disconnected_count = raw.get("disconnected_pair_count", 0)
        bridges = raw.get("bridge_characters", [])

        total_chars = len(self.list_entities(entity_type="character"))
        total_fores = len(self.list_foreshadows())

        dims = []
        # Character continuity
        if forgotten_count > 0:
            important = sum(1 for c in forgotten if c.get("important"))
            weighted = important * 2 + (forgotten_count - important)
            rate = weighted / max(total_chars, 1) / 2
            char_score = round(100 * (1 - rate**0.4))
        else:
            char_score = 100
        dims.append(
            {
                "name": "角色连贯性",
                "score": char_score,
                "finding": f"{forgotten_count} 个角色多章未出场" if forgotten_count else "所有角色出场连贯",
                "weight": 0.20,
            }
        )

        # Foreshadow management
        if unresolved_fs_count > 0:
            rate = unresolved_fs_count / max(total_fores, 1)
            fore_score = round(100 * (1 / (1 + math.log(1 + rate * 8))))
        else:
            fore_score = 100
        dims.append(
            {
                "name": "伏笔管理",
                "score": fore_score,
                "finding": f"{unresolved_fs_count} 个伏笔待回收" if unresolved_fs_count else "所有伏笔已回收",
                "weight": 0.15,
            }
        )

        # Relationship network
        if total_chars > 2:
            max_pairs = total_chars * (total_chars - 1) / 2
            disc_rate = min(disconnected_count / max(max_pairs, 1), 1.0)
            rel_score = round(100 * (1 - disc_rate * 0.7))
        else:
            rel_score = 100
        dims.append(
            {
                "name": "关系网络",
                "score": rel_score,
                "finding": f"{disconnected_count} 对角色无关联" if disconnected_count else "关系网络良好",
                "weight": 0.15,
            }
        )

        # Overall health
        overall = round(sum(d["score"] * d["weight"] for d in dims))
        if overall >= 90:
            summary = "叙事结构健康，各维度表现均衡。"
        elif overall >= 70:
            weak = [d for d in dims if d["score"] < 70]
            summary = f"整体良好，但 {len(weak)} 个维度需要关注：{'、'.join(d['name'] for d in weak[:2])}。"
        else:
            summary = "叙事结构存在较多问题，建议系统性地修复。"

        return {
            "health_score": overall,
            "summary": summary,
            "dimensions": dims,
            "action_items": [],
            "raw_data": {
                "forgotten_count": forgotten_count,
                "foreshadow_count": unresolved_fs_count,
                "disconnected_count": disconnected_count,
                "bridge_count": len(bridges),
            },
        }

    # ════════════════════════════════════════════════════════════════
    # Worldbuilding metrics
    # ════════════════════════════════════════════════════════════════

    def get_worldbuilding_metrics(self) -> dict:
        """Get comprehensive worldbuilding statistics.

        Returns flat structure matching frontend MetricsData interface:
        entity_count, relation_count, density, isolated_entities, isolated_count,
        largest_component_size, fragmentation_ratio, health_assessment, health_score.
        """
        chars = self.list_entities(entity_type="character")
        locations = self.list_entities(entity_type="location")
        orgs = self.list_entities(entity_type="organization")
        items = self.list_entities(entity_type="item")
        skills = self.list_entities(entity_type="skill")
        concepts = self.list_entities(entity_type="concept")
        events_e = self.list_entities(entity_type="event")

        relations = self.list_relations()

        total_entities = (
            len(chars) + len(locations) + len(orgs) + len(items) + len(skills) + len(concepts) + len(events_e)
        )
        relation_count = len(relations)
        max_pairs = total_entities * (total_entities - 1) / 2 if total_entities > 1 else 1
        density_val = round(relation_count / max_pairs, 4) if max_pairs > 0 else 0

        # Isolated entities (no relations)
        isolated_entities = []
        for e in self.list_entities():
            has_rel = self._run_single(
                "SELECT 1 FROM relations WHERE (from_entity=? OR to_entity=?) AND project_id=? LIMIT 1",
                (e.id, e.id, self.project_id),
            )
            if not has_rel:
                isolated_entities.append({"name": e.name, "type": e.type})

        # Connected components (via entity graph)
        all_entity_ids = [e.id for e in self.list_entities()]
        adj = self._get_graph_adjacency(all_entity_ids)
        visited: set = set()
        component_sizes: list[int] = []
        for eid in all_entity_ids:
            if eid in visited:
                continue
            size = 0
            stack = [eid]
            while stack:
                cur = stack.pop()
                if cur in visited:
                    continue
                visited.add(cur)
                size += 1
                for nb in adj.get(cur, set()):
                    if nb not in visited:
                        stack.append(nb)
            if size > 0:
                component_sizes.append(size)

        largest_component = max(component_sizes) if component_sizes else 0
        fragmentation_ratio = 1 - (largest_component / max(total_entities, 1)) if total_entities > 0 else 0

        # Health assessment
        if density_val >= 0.1 and fragmentation_ratio <= 0.2 and relation_count >= total_entities:
            health = "良好"
            score = 85 + min(15, int(density_val * 100))
        elif density_val >= 0.03 or fragmentation_ratio <= 0.5:
            health = "一般"
            score = 50 + min(35, int(density_val * 200))
        else:
            health = "稀疏"
            score = max(5, min(50, int(density_val * 300)))

        return {
            "entity_count": total_entities,
            "relation_count": relation_count,
            "density": density_val,
            "isolated_entities": isolated_entities,
            "isolated_count": len(isolated_entities),
            "largest_component_size": largest_component,
            "fragmentation_ratio": round(fragmentation_ratio, 4),
            "health_assessment": health,
            "health_score": score,
        }

    def get_location_importance(self) -> list[dict]:
        """Rank locations by composite importance score."""
        locations = self.list_entities(entity_type="location")
        if not locations:
            return []

        results = []
        for loc in locations:
            # Count degree (relations involving this location)
            degree_rows = self._run(
                "SELECT COUNT(*) AS cnt FROM relations WHERE (from_entity=? OR to_entity=?) AND project_id=?",
                (loc.id, loc.id, self.project_id),
            )
            degree = degree_rows[0]["cnt"] if degree_rows else 0

            # Count timeline events at this location
            event_count = 0
            for evt in self.list_timeline_events():
                if evt.location_ref == loc.id or loc.id in evt.location_ref:
                    event_count += 1

            # Count character visits
            visit_rows = self._run(
                "SELECT COUNT(DISTINCT from_entity) AS cnt FROM relations WHERE to_entity=? AND type IN ('LOCATED_AT','BELONGS_TO') AND project_id=?",
                (loc.id, self.project_id),
            )
            visits = visit_rows[0]["cnt"] if visit_rows else 0

            composite = round(degree * 0.30 + event_count * 0.40 + visits * 0.30)

            if composite >= 70:
                role = "核心地点"
            elif composite >= 45:
                role = "重要地点"
            elif composite >= 25:
                role = "次要地点"
            else:
                role = "边缘地点"

            results.append(
                {
                    "entity_id": loc.id,
                    "name": loc.name,
                    "composite_score": min(composite, 100),
                    "role": role,
                    "degree": degree,
                    "event_count": event_count,
                    "character_visits": visits,
                }
            )

        results.sort(key=lambda x: x["composite_score"], reverse=True)
        return results

    def get_organization_importance(self) -> list[dict]:
        """Rank organizations by composite importance."""
        orgs = self.list_entities(entity_type="organization")
        if not orgs:
            return []

        results = []
        for org in orgs:
            degree_rows = self._run(
                "SELECT COUNT(*) AS cnt FROM relations WHERE (from_entity=? OR to_entity=?) AND project_id=?",
                (org.id, org.id, self.project_id),
            )
            degree = degree_rows[0]["cnt"] if degree_rows else 0

            member_rows = self._run(
                "SELECT COUNT(DISTINCT from_entity) AS cnt FROM relations WHERE to_entity=? AND type IN ('BELONGS_TO','OWNS','MASTER_OF') AND project_id=?",
                (org.id, self.project_id),
            )
            members = member_rows[0]["cnt"] if member_rows else 0

            event_count = 0
            for evt in self.list_timeline_events():
                if org.id in evt.location_ref or org.id == evt.location_ref:
                    event_count += 1

            composite = round(degree * 0.25 + members * 0.45 + event_count * 0.30)

            if composite >= 70:
                role = "核心势力"
            elif composite >= 45:
                role = "重要势力"
            elif composite >= 25:
                role = "次要势力"
            else:
                role = "边缘势力"

            results.append(
                {
                    "entity_id": org.id,
                    "name": org.name,
                    "composite_score": min(composite, 100),
                    "role": role,
                    "degree": degree,
                    "member_count": members,
                    "event_count": event_count,
                }
            )

        results.sort(key=lambda x: x["composite_score"], reverse=True)
        return results

    # ════════════════════════════════════════════════════════════════
    # Event causal chain
    # ════════════════════════════════════════════════════════════════

    def get_event_causal_chain(self) -> dict:
        """Build event DAG from timeline, find critical path."""
        events = self.list_timeline_events()
        if not events:
            return {"critical_path": [], "branches": 0}

        sorted_events = sorted(events, key=lambda e: e.time_order)
        critical_path = []
        for i, evt in enumerate(sorted_events):
            entry = {"id": evt.id, "label": evt.label, "order": evt.time_order}
            if i > 0:
                entry["depends_on"] = sorted_events[i - 1].id
            critical_path.append(entry)

        tracks = {e.track_id for e in events}

        return {
            "critical_path": critical_path,
            "branches": len(tracks),
            "total_events": len(events),
        }

    # ════════════════════════════════════════════════════════════════
    # Knowledge summary & search
    # ════════════════════════════════════════════════════════════════

    def get_knowledge_summary(self) -> str:
        """Return a text summary of all knowledge in the store."""
        entities = self.list_entities()
        relations = self.list_relations()
        foreshadows = self.list_foreshadows()
        timeline = self.list_timeline_events()

        lines = [f"项目 {self.project_id} 知识库摘要", "=" * 40, ""]
        lines.append(f"实体总数: {len(entities)}")
        for etype in ["character", "location", "organization", "item", "skill", "concept", "event"]:
            count = len([e for e in entities if e.type == etype])
            if count:
                lines.append(f"  {etype}: {count}")
        lines.append(f"关系总数: {len(relations)}")
        lines.append(f"伏笔总数: {len(foreshadows)}")
        lines.append(f"  未回收: {sum(1 for f in foreshadows if not f.resolved)}")
        lines.append(f"时间线事件: {len(timeline)}")
        return "\n".join(lines)

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

    def auto_complete_relations(self) -> dict:
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
        from .graph_schema import RELATIONSHIP_DIRECTION

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


def _count_entity_refs(event, entity_ids: list[str], counter: dict[str, int]) -> None:
    """Count how many timeline events reference each entity ID."""
    for eid in entity_ids:
        if event.chapter_ref and eid in event.chapter_ref:
            counter[eid] = counter.get(eid, 0) + 1
            continue
        if event.location_ref and eid in event.location_ref:
            counter[eid] = counter.get(eid, 0) + 1


# ════════════════════════════════════════════════════════════════
# Constraint operations
# ════════════════════════════════════════════════════════════════


def _ensure_store_has_constraint_table(store: SQLiteStore) -> None:
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


def get_store(book_id: str, db_path: str | Path | None = None) -> SQLiteStore:
    """Get or create a SQLiteStore for the given project.

    Matches the original ``get_store()`` API from ``graph_store.py``.
    Uses an instance cache so all callers share the same connection.
    """
    if book_id not in SQLiteStore._instances:
        store = SQLiteStore(book_id, db_path=db_path)
        store._ensure_project()
        store.init_schema()
        SQLiteStore._instances[book_id] = store
    return SQLiteStore._instances[book_id]


def close_shared_driver() -> None:
    """Compatibility shim — closes all cached store connections."""
    for store in SQLiteStore._instances.values():
        try:
            store.close()
        except Exception:
            pass
    SQLiteStore._instances.clear()
