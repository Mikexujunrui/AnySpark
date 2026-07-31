"""SQLite store shared infrastructure: connection, schema, low-level query
I/O, row converters, and cross-instance caches.

Part of the ``core.sqlite_store`` package split from the former
monolithic ``core/sqlite_store.py``.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar, cast

from ..config import DATA_DIR
from ..knowledge import CharacterSnapshot, Entity, Foreshadow, Relation, TimelineEvent

if TYPE_CHECKING:
    from . import SQLiteStore  # noqa: F401

logger = logging.getLogger(__name__)

_T = TypeVar("_T")

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


class _SQLiteBase:
    """Shared SQLite infrastructure for the domain mixins.

    Holds the connection, schema init, low-level query helpers, row
    converters and cross-instance caches.  The composed :class:`SQLiteStore`
    builds its public API from this base plus the domain mixins.
    """

    _db_dir: Path = DATA_DIR
    _instances: dict[str, SQLiteStore] = {}

    @classmethod
    def _resolve_db_dir(cls) -> Path:
        """Return a writable directory for the SQLite database.

        DATA_DIR already resolves to a persistent writable location in both
        packaged and development modes.
        """
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
        graph-store callers (e.g. impact_propagator.py).
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

    def _cached(self, cache_key: str, compute_fn: Callable[[], _T]) -> _T:
        pid = self.project_id
        version = self._cache_version.get(pid, 0)
        entry = self._insights_cache.get(pid, {})
        if cache_key in entry and entry[cache_key][0] == version:
            return cast(_T, entry[cache_key][1])
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
        from ..knowledge import RelationType

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
