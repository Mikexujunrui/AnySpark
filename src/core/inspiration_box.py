# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Inspiration inbox — lightweight card-based idea management for writers.

Extends the existing store_inspiration tool with a full card management system:
- Inbox → Promoted → Archived lifecycle
- Link inspirations to characters, chapters, foreshadows
- Promote inspirations to formal outline nodes or foreshadows
- Full-text search via FTS5

Data persistence: data/inspirations_{book_id}.json (reuse json_store pattern).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.book_locks import book_lock
from core.config import DATA_DIR
from core.search import fts as fts_engine

logger = logging.getLogger(__name__)

_INSPIRATIONS_DIR = DATA_DIR  # same as other JSON files


def _inspirations_file(book_id: str):
    """File path for a book's inspirations JSON."""
    safe_id = book_id.replace("..", "").replace("/", "").replace("\\", "")
    return _INSPIRATIONS_DIR / f"inspirations_{safe_id}.json"


@dataclass
class Inspiration:
    """A single inspiration card."""

    id: str = ""
    content: str = ""
    tags: list[str] = field(default_factory=list)
    linked_characters: list[str] = field(default_factory=list)
    linked_chapters: list[str] = field(default_factory=list)
    linked_foreshadows: list[str] = field(default_factory=list)
    status: str = "inbox"  # inbox / promoted / archived
    created_at: str = ""
    promoted_to: str = ""  # outline_node / foreshadow / character_note
    promoted_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "tags": self.tags,
            "linked_characters": self.linked_characters,
            "linked_chapters": self.linked_chapters,
            "linked_foreshadows": self.linked_foreshadows,
            "status": self.status,
            "created_at": self.created_at,
            "promoted_to": self.promoted_to,
            "promoted_at": self.promoted_at,
        }


def _load_inspirations(book_id: str) -> list[dict]:
    """Load raw inspiration dicts from JSON file."""
    path = _inspirations_file(book_id)
    if not path.exists():
        return []
    import json
    try:
        result = json.loads(path.read_text(encoding="utf-8-sig"))
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_inspirations(book_id: str, inspirations: list[dict]) -> None:
    """Save inspirations to JSON file with book-level locking."""
    import json
    with book_lock(book_id):
        path = _inspirations_file(book_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(inspirations, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def add_inspiration(
    book_id: str,
    content: str,
    tags: list[str] | None = None,
    linked_characters: list[str] | None = None,
    linked_chapters: list[str] | None = None,
    linked_foreshadows: list[str] | None = None,
) -> dict:
    """Add a new inspiration card to the inbox."""
    insp = {
        "id": f"insp_{uuid.uuid4().hex[:12]}",
        "content": content,
        "tags": tags or [],
        "linked_characters": linked_characters or [],
        "linked_chapters": linked_chapters or [],
        "linked_foreshadows": linked_foreshadows or [],
        "status": "inbox",
        "created_at": datetime.now().isoformat(),
        "promoted_to": "",
        "promoted_at": "",
    }

    with book_lock(book_id):
        inspirations = _load_inspirations(book_id)
        inspirations.append(insp)
        _save_inspirations(book_id, inspirations)

    # Index in FTS
    try:
        fts_engine.index_material(
            book_id,
            insp["id"],
            insp["content"],
            ", ".join(insp["tags"]),
        )
    except Exception:
        pass  # FTS indexing is best-effort

    return insp


def list_inspirations(
    book_id: str,
    status_filter: str | None = None,
) -> list[dict]:
    """List all inspirations, optionally filtered by status."""
    inspirations = _load_inspirations(book_id)
    if status_filter and status_filter != "all":
        inspirations = [i for i in inspirations if i.get("status") == status_filter]
    return inspirations


def get_inspiration(book_id: str, inspiration_id: str) -> dict | None:
    """Get a single inspiration by ID."""
    inspirations = _load_inspirations(book_id)
    return next((i for i in inspirations if i.get("id") == inspiration_id), None)


def update_inspiration(book_id: str, inspiration_id: str, updates: dict) -> dict | None:
    """Update an inspiration card (content, tags, links, status)."""
    with book_lock(book_id):
        inspirations = _load_inspirations(book_id)
        for i, insp in enumerate(inspirations):
            if insp.get("id") == inspiration_id:
                insp.update(updates)
                _save_inspirations(book_id, inspirations)
                return insp
    return None


def link_inspiration(
    book_id: str,
    inspiration_id: str,
    target_type: str,  # character / chapter / foreshadow
    target_id: str,
) -> dict | None:
    """Link an inspiration to a character/chapter/foreshadow."""
    link_map = {
        "character": "linked_characters",
        "chapter": "linked_chapters",
        "foreshadow": "linked_foreshadows",
    }
    field_name = link_map.get(target_type)
    if not field_name:
        return None

    with book_lock(book_id):
        inspirations = _load_inspirations(book_id)
        for insp in inspirations:
            if insp.get("id") == inspiration_id:
                links = insp.setdefault(field_name, [])
                if target_id not in links:
                    links.append(target_id)
                _save_inspirations(book_id, inspirations)
                return insp
    return None


def promote_inspiration(
    book_id: str,
    inspiration_id: str,
    target_type: str,  # outline_node / foreshadow / character_note
) -> dict:
    """Promote an inspiration from inbox to a formal structure.

    This marks the inspiration as 'promoted' and records what it was promoted to.
    The actual creation of the target structure (outline node, foreshadow, etc.)
    is handled by the caller — this function just updates the card status.
    """
    with book_lock(book_id):
        inspirations = _load_inspirations(book_id)
        for insp in inspirations:
            if insp.get("id") == inspiration_id:
                insp["status"] = "promoted"
                insp["promoted_to"] = target_type
                insp["promoted_at"] = datetime.now().isoformat()
                _save_inspirations(book_id, inspirations)
                return insp
    return {"error": "Inspiration not found"}


def archive_inspiration(book_id: str, inspiration_id: str) -> dict | None:
    """Archive an inspiration (move from inbox/promoted to archived)."""
    return update_inspiration(book_id, inspiration_id, {"status": "archived"})


def delete_inspiration(book_id: str, inspiration_id: str) -> bool:
    """Permanently delete an inspiration card."""
    with book_lock(book_id):
        inspirations = _load_inspirations(book_id)
        filtered = [i for i in inspirations if i.get("id") != inspiration_id]
        if len(filtered) < len(inspirations):
            _save_inspirations(book_id, filtered)
            return True
    return False


def search_inspirations(book_id: str, query: str) -> list[dict]:
    """Search inspirations by content/tags using FTS5."""
    try:
        results = fts_engine.search_materials(query, limit=20)
        insp_ids = {r.get("mat_id") for r in results}
        inspirations = _load_inspirations(book_id)
        return [i for i in inspirations if i.get("id") in insp_ids]
    except Exception:
        # Fallback to simple string search
        inspirations = _load_inspirations(book_id)
        q = query.lower()
        return [
            i for i in inspirations
            if q in i.get("content", "").lower()
            or any(q in t.lower() for t in i.get("tags", []))
        ]
