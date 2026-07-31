#!/usr/bin/env python
"""Rebuild the full-text search index (data/search_fts.db) from source data.

The FTS index is derived data — it can always be rebuilt from the sources of
truth (chapters_*.json, worldbuilding_*.json, novel.db entities, materials.json).
This script is the recovery path for a corrupted/missing index.

Usage:
    python scripts/rebuild_fts.py            # rebuild everything (idempotent)
    python scripts/rebuild_fts.py --dry-run  # report counts only, no writes

Idempotent: clears each FTS table before repopulating it.
"""

import argparse
import json
import sys
from pathlib import Path

# Make `core`/`data` importable the same way pytest does (src layout).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from core.config import DATA_DIR  # noqa: E402
from core.search import FullTextSearch  # noqa: E402


def iter_books() -> list[str]:
    """Return all book IDs that have chapters or worldbuilding JSON files."""
    ids: set[str] = set()
    for pattern in ("chapters_*.json", "worldbuilding_*.json"):
        for p in DATA_DIR.glob(pattern):
            ids.add(p.stem.split("_", 1)[1])
    return sorted(ids)


def rebuild_chapters(fts: FullTextSearch, book_id: str, dry_run: bool) -> int:
    path = DATA_DIR / f"chapters_{book_id}.json"
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    chapters = data if isinstance(data, list) else data.get("chapters", [])
    count = 0
    if not dry_run:
        # Full wipe per book: DELETE+INSERT per chapter only handles updates,
        # not documents removed from the source. Orphan rows must go too.
        fts._get_conn().execute("DELETE FROM chapters_fts WHERE book_id=?", (book_id,))
    for ch in chapters:
        versions = ch.get("versions") or []
        cur = next((v for v in versions if v.get("id") == ch.get("current_version")), None)
        if cur is None and versions:
            cur = versions[-1]
        content = (cur or ch).get("content", "")
        title = ch.get("title", "")
        if not dry_run:
            fts.index_chapter(book_id, {"id": ch["id"], "title": title, "content": content})
        count += 1
    return count


def rebuild_worldbuilding(fts: FullTextSearch, book_id: str, dry_run: bool) -> int:
    path = DATA_DIR / f"worldbuilding_{book_id}.json"
    if not path.exists():
        return 0
    wb = json.loads(path.read_text(encoding="utf-8"))
    if not dry_run:
        fts.index_worldbuilding(book_id, wb)
    return len(wb.get("categories", []))


def rebuild_entities(fts: FullTextSearch, dry_run: bool) -> int:
    """Rebuild entities_fts from ALL projects in novel.db (single pass)."""
    import sqlite3

    db_path = DATA_DIR / "novel.db"
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT project_id, id, entity_type, name, aliases, data FROM entities"
        ).fetchall()
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()
    if not dry_run:
        # Wipe the whole table: orphan rows for deleted books must not survive.
        fts._get_conn().execute("DELETE FROM entities_fts")
    for row in rows:
        project_id, eid, etype, name, aliases, data = row
        aliases_list = json.loads(aliases) if aliases else []
        data_dict = json.loads(data) if data else {}
        if not dry_run:
            fts.index_entity(project_id, eid, name, etype, aliases_list, data_dict)
    return len(rows)


def rebuild_materials(fts: FullTextSearch, dry_run: bool) -> int:
    path = DATA_DIR / "materials.json"
    if not path.exists():
        # No source data — drop any orphan rows left in the index.
        if not dry_run:
            try:
                fts._get_conn().execute("DELETE FROM materials_fts")
                fts._get_conn().commit()
            except Exception:
                pass
        return 0
    mats = json.loads(path.read_text(encoding="utf-8"))
    if not dry_run:
        for m in mats:
            fts.index_material(m)
    return len(mats)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report counts only")
    parser.add_argument("--book", default="", help="rebuild only one book id")
    args = parser.parse_args()

    fts = FullTextSearch()
    books = [args.book] if args.book else iter_books()
    totals = {"chapters": 0, "worldbuilding": 0, "entities": 0, "materials": 0}

    for book_id in books:
        totals["chapters"] += rebuild_chapters(fts, book_id, args.dry_run)
        totals["worldbuilding"] += rebuild_worldbuilding(fts, book_id, args.dry_run)
    totals["entities"] = rebuild_entities(fts, args.dry_run)
    totals["materials"] = rebuild_materials(fts, args.dry_run)

    print(f"{'[dry-run] ' if args.dry_run else ''}rebuild summary:")
    for k, v in totals.items():
        print(f"  {k}: {v}")
    print(f"  books: {len(books)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
