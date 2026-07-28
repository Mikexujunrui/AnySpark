# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

""".spark archive format — portable knowledge base export/import.

Archive layout (ZIP container)::

    manifest.json          — format version + book metadata
    graph.db               — SQLite: entities, relations, foreshadows, timeline
    chapters/              — JSON chapter files (one per chapter)
    outline.json           — chapter outline
    detailed_outline.json  — detailed outline (plot chain)
    reviews.json           — review records
    tasks.json             — persistent task data
    worldbuilding.json     — worldbuilding entries
    volumes.json           — volume data (if any)
    location_map.json      — location map data (if any)
    timeline.json          — timeline data (if any)

Usage::

    from core.archive import export_spark, import_spark

    # Export
    path = export_spark("book_123", output_dir="/tmp")

    # Import
    import_spark("book_123", "/tmp/book_123.spark")
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from .graph_store import GraphStore
from .knowledge import Entity, Foreshadow, Relation, RelationType

logger = logging.getLogger(__name__)

ARCHIVE_VERSION = 1
MANIFEST_FILENAME = "manifest.json"
GRAPH_DB_FILENAME = "graph.db"


def export_spark(book_id: str, output_path: str | None = None) -> str:
    """Export a book project to a .spark archive file.

    Args:
        book_id: The book project ID.
        output_path: Optional output file path. If None, saves to
            ``{book_id}.spark`` in the current directory.

    Returns:
        The absolute path to the created .spark file.
    """
    if output_path is None:
        output_path = f"{book_id}.spark"
    output_path = os.path.abspath(output_path)

    store = GraphStore(book_id)
    store.init_schema()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # ── 1. Manifest ──
        manifest = {
            "format_version": ARCHIVE_VERSION,
            "book_id": book_id,
            "exported_at": datetime.now().isoformat(),
            "entity_count": 0,
            "relation_count": 0,
            "foreshadow_count": 0,
            "timeline_event_count": 0,
        }
        (tmp / MANIFEST_FILENAME).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # ── 2. Graph database (SQLite) ──
        _export_graph_to_sqlite(store, book_id, tmp / GRAPH_DB_FILENAME)

        # ── 3. Data files ──
        _copy_json_data(book_id, tmp)

        # ── 4. Zip it all ──
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in sorted(tmp.rglob("*")):
                if file_path.is_file():
                    arcname = str(file_path.relative_to(tmp)).replace("\\", "/")
                    zf.write(file_path, arcname)

    logger.info("Exported .spark archive: %s", output_path)
    return output_path


def import_spark(book_id: str, archive_path: str) -> dict:
    """Import a .spark archive into a book project.

    Args:
        book_id: The target book project ID.
        archive_path: Path to the .spark file.

    Returns:
        A dict with import statistics.
    """
    archive_path = os.path.abspath(archive_path)
    if not os.path.exists(archive_path):
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    stats = {"entities": 0, "relations": 0, "foreshadows": 0, "timeline_events": 0, "chapters": 0, "errors": []}

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(tmp)

        # ── Validate manifest ──
        manifest_path = tmp / MANIFEST_FILENAME
        if not manifest_path.exists():
            raise ValueError("Invalid .spark archive: missing manifest.json")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("format_version", 0) != ARCHIVE_VERSION:
            raise ValueError(
                f"Unsupported archive version: {manifest.get('format_version')}. Expected: {ARCHIVE_VERSION}"
            )

        # ── Import graph ──
        graph_db = tmp / GRAPH_DB_FILENAME
        if graph_db.exists():
            gs = _import_graph_from_sqlite(book_id, graph_db)
            stats["entities"] = gs.get("entities", 0)
            stats["relations"] = gs.get("relations", 0)
            stats["foreshadows"] = gs.get("foreshadows", 0)
            stats["timeline_events"] = gs.get("timeline_events", 0)

        # ── Import data files ──
        stats["chapters"] = _restore_json_data(book_id, tmp)

    logger.info("Imported .spark archive: %s → %s", archive_path, book_id)
    return stats


# ── Internal helpers ─────────────────────────────────────────────────────────


def _export_graph_to_sqlite(store: GraphStore, book_id: str, db_path: Path) -> None:
    """Export Neo4j graph data to a SQLite database."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")

    # Schema
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY, type TEXT, name TEXT,
            aliases TEXT, data TEXT, book_id TEXT
        );
        CREATE TABLE IF NOT EXISTS relations (
            id TEXT PRIMARY KEY, from_entity TEXT, to_entity TEXT,
            type TEXT, data TEXT, book_id TEXT
        );
        CREATE TABLE IF NOT EXISTS foreshadows (
            id TEXT PRIMARY KEY, text TEXT, hint TEXT,
            expected_resolution TEXT, resolved INTEGER,
            resolution_text TEXT, related_entities TEXT,
            related_events TEXT, source TEXT, status TEXT,
            plant_chapter TEXT, resolve_chapter TEXT,
            volume_ref TEXT, planned_resolve_arc TEXT,
            scheduled_chapter TEXT, confidence TEXT,
            resolve_keywords TEXT, book_id TEXT
        );
        CREATE TABLE IF NOT EXISTS timeline_events (
            id TEXT PRIMARY KEY, time_point TEXT, label TEXT,
            time_order REAL, description TEXT, chapter_ref TEXT,
            track_id TEXT, track_name TEXT, track_color TEXT,
            time_label TEXT, location_ref TEXT, arc_id TEXT,
            narrative_time TEXT, book_id TEXT
        );
    """)

    # Entities
    try:
        entities = store.list_entities()
        for e in entities:
            conn.execute(
                "INSERT OR REPLACE INTO entities VALUES (?,?,?,?,?,?)",
                (
                    e.id,
                    e.type,
                    e.name,
                    json.dumps(e.aliases, ensure_ascii=False),
                    json.dumps(e.data, ensure_ascii=False),
                    book_id,
                ),
            )
    except Exception as exc:
        logger.warning("Failed to export entities: %s", exc)

    # Relations
    try:
        for e in entities:
            for r in store.list_relations(e.id):
                conn.execute(
                    "INSERT OR REPLACE INTO relations VALUES (?,?,?,?,?,?)",
                    (r.id, r.from_entity, r.to_entity, r.type.value, json.dumps(r.data, ensure_ascii=False), book_id),
                )
    except Exception as exc:
        logger.warning("Failed to export relations: %s", exc)

    # Foreshadows
    try:
        for status in ("open", "planned", "due", "scheduled", "resolved", "cross_volume", "dangling"):
            for f in store.list_foreshadows(status=status):
                conn.execute(
                    "INSERT OR REPLACE INTO foreshadows VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        f.id,
                        f.text,
                        f.hint,
                        f.expected_resolution,
                        1 if f.resolved else 0,
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
                        book_id,
                    ),
                )
    except Exception as exc:
        logger.warning("Failed to export foreshadows: %s", exc)

    conn.commit()
    conn.close()


def _import_graph_from_sqlite(book_id: str, db_path: Path) -> dict:
    """Import graph data from SQLite into Neo4j."""
    store = GraphStore(book_id)
    store.init_schema()
    stats = {}

    conn = sqlite3.connect(str(db_path))

    # Entities
    rows = conn.execute("SELECT id, type, name, aliases, data FROM entities WHERE book_id=?", (book_id,)).fetchall()
    for row in rows:
        try:
            entity = Entity(
                id=row[0],
                type=row[1],
                name=row[2],
                aliases=json.loads(row[3]) if row[3] else [],
                data=json.loads(row[4]) if row[4] else {},
            )
            store.add_entity(entity)
        except Exception as exc:
            logger.warning("Failed to import entity %s: %s", row[2], exc)
    stats["entities"] = len(rows)

    # Relations
    rows = conn.execute(
        "SELECT id, from_entity, to_entity, type, data FROM relations WHERE book_id=?", (book_id,)
    ).fetchall()
    for row in rows:
        try:
            rtype = RelationType(row[3])
        except ValueError:
            rtype = RelationType.KNOWS
        try:
            relation = Relation(
                id=row[0],
                from_entity=row[1],
                to_entity=row[2],
                type=rtype,
                data=json.loads(row[4]) if row[4] else {},
            )
            store.add_relation(relation)
        except Exception as exc:
            logger.warning("Failed to import relation: %s", exc)
    stats["relations"] = len(rows)

    # Foreshadows
    rows = conn.execute(
        "SELECT id, text, hint, expected_resolution, resolved, resolution_text, "
        "related_entities, related_events, source, status, plant_chapter, "
        "resolve_chapter, volume_ref, planned_resolve_arc, scheduled_chapter, "
        "confidence, resolve_keywords FROM foreshadows WHERE book_id=?",
        (book_id,),
    ).fetchall()
    for row in rows:
        try:
            fs = Foreshadow(
                id=row[0],
                text=row[1],
                hint=row[2],
                expected_resolution=row[3] or "",
                resolved=bool(row[4]),
                resolution_text=row[5] or "",
                related_entities=json.loads(row[6]) if row[6] else [],
                related_events=json.loads(row[7]) if row[7] else [],
                source=row[8] or "extracted",
                status=row[9] or "open",
                plant_chapter=row[10] or "",
                resolve_chapter=row[11] or "",
                volume_ref=row[12] or "",
                planned_resolve_arc=row[13] or "",
                scheduled_chapter=row[14] or "",
                confidence=row[15] or "high",
                resolve_keywords=json.loads(row[16]) if row[16] else [],
            )
            store.add_foreshadow(fs)
        except Exception as exc:
            logger.warning("Failed to import foreshadow: %s", exc)
    stats["foreshadows"] = len(rows)

    conn.close()
    return stats


def _copy_json_data(book_id: str, tmp: Path) -> None:
    """Copy JSON data files from the project data directory into the archive."""
    from data.json_store import json_store

    chapters_dir = tmp / "chapters"
    chapters_dir.mkdir(exist_ok=True)

    # Chapters
    try:
        chapters = json_store.load_chapters(book_id)
        for i, ch in enumerate(chapters):
            (chapters_dir / f"{i}.json").write_text(
                json.dumps(ch, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    except Exception as exc:
        logger.warning("Failed to copy chapters: %s", exc)

    # Outline
    try:
        outline = json_store.get_outline(book_id)
        if outline:
            (tmp / "outline.json").write_text(
                json.dumps(outline, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    except Exception as exc:
        logger.warning("Failed to copy outline: %s", exc)

    # Detailed outline
    try:
        detailed = json_store.get_detailed_outline(book_id)
        if detailed:
            (tmp / "detailed_outline.json").write_text(
                json.dumps(detailed, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    except Exception as exc:
        logger.warning("Failed to copy detailed outline: %s", exc)

    # Reviews
    try:
        reviews = json_store.load_reviews(book_id)
        if reviews:
            (tmp / "reviews.json").write_text(
                json.dumps(reviews, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    except Exception as exc:
        logger.warning("Failed to copy reviews: %s", exc)

    # Tasks
    try:
        tasks = json_store.load_tasks(book_id)
        if tasks:
            (tmp / "tasks.json").write_text(
                json.dumps(tasks, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    except Exception as exc:
        logger.warning("Failed to copy tasks: %s", exc)

    # Worldbuilding
    try:
        wb = json_store.load_worldbuilding(book_id)
        if wb:
            (tmp / "worldbuilding.json").write_text(
                json.dumps(wb, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    except Exception as exc:
        logger.warning("Failed to copy worldbuilding: %s", exc)

    # Volumes
    try:
        volumes = json_store.load_volumes(book_id)
        if volumes:
            (tmp / "volumes.json").write_text(
                json.dumps(volumes, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    except Exception as exc:
        logger.warning("Failed to copy volumes: %s", exc)

    # Timeline
    try:
        timeline = json_store.load_timeline(book_id)
        if timeline:
            (tmp / "timeline.json").write_text(
                json.dumps(timeline, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    except Exception as exc:
        logger.warning("Failed to copy timeline: %s", exc)

    # Location map
    try:
        loc_map = json_store.load_location_map(book_id)
        if loc_map:
            (tmp / "location_map.json").write_text(
                json.dumps(loc_map, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    except Exception as exc:
        logger.warning("Failed to copy location map: %s", exc)


def _restore_json_data(book_id: str, tmp: Path) -> int:
    """Restore JSON data files from the archive into the project data directory."""
    from data.json_store import json_store

    chapter_count = 0

    # Chapters
    chapters_dir = tmp / "chapters"
    if chapters_dir.exists():
        try:
            chapter_files = sorted(
                chapters_dir.glob("*.json"),
                key=lambda p: int(p.stem) if p.stem.isdigit() else 0,
            )
            chapters = []
            for cf in chapter_files:
                chapters.append(json.loads(cf.read_text(encoding="utf-8")))
            if chapters:
                json_store.save_chapters(book_id, chapters)
                chapter_count = len(chapters)
        except Exception as exc:
            logger.warning("Failed to restore chapters: %s", exc)

    # Outline
    outline_file = tmp / "outline.json"
    if outline_file.exists():
        try:
            outline = json.loads(outline_file.read_text(encoding="utf-8"))
            json_store.save_outline(book_id, outline)
        except Exception as exc:
            logger.warning("Failed to restore outline: %s", exc)

    # Detailed outline
    detailed_file = tmp / "detailed_outline.json"
    if detailed_file.exists():
        try:
            detailed = json.loads(detailed_file.read_text(encoding="utf-8"))
            json_store.save_detailed_outline(book_id, detailed)
        except Exception as exc:
            logger.warning("Failed to restore detailed outline: %s", exc)

    # Reviews
    reviews_file = tmp / "reviews.json"
    if reviews_file.exists():
        try:
            reviews = json.loads(reviews_file.read_text(encoding="utf-8"))
            json_store.save_reviews(book_id, reviews)
        except Exception as exc:
            logger.warning("Failed to restore reviews: %s", exc)

    # Tasks
    tasks_file = tmp / "tasks.json"
    if tasks_file.exists():
        try:
            tasks = json.loads(tasks_file.read_text(encoding="utf-8"))
            json_store.save_tasks(book_id, tasks)
        except Exception as exc:
            logger.warning("Failed to restore tasks: %s", exc)

    # Worldbuilding
    wb_file = tmp / "worldbuilding.json"
    if wb_file.exists():
        try:
            wb = json.loads(wb_file.read_text(encoding="utf-8"))
            json_store.save_worldbuilding(book_id, wb)
        except Exception as exc:
            logger.warning("Failed to restore worldbuilding: %s", exc)

    # Volumes
    volumes_file = tmp / "volumes.json"
    if volumes_file.exists():
        try:
            volumes = json.loads(volumes_file.read_text(encoding="utf-8"))
            json_store.save_volumes(book_id, volumes)
        except Exception as exc:
            logger.warning("Failed to restore volumes: %s", exc)

    # Timeline
    timeline_file = tmp / "timeline.json"
    if timeline_file.exists():
        try:
            timeline = json.loads(timeline_file.read_text(encoding="utf-8"))
            json_store.save_timeline(book_id, timeline)
        except Exception as exc:
            logger.warning("Failed to restore timeline: %s", exc)

    # Location map
    loc_map_file = tmp / "location_map.json"
    if loc_map_file.exists():
        try:
            loc_map = json.loads(loc_map_file.read_text(encoding="utf-8"))
            json_store.save_location_map(book_id, loc_map)
        except Exception as exc:
            logger.warning("Failed to restore location map: %s", exc)

    return chapter_count
