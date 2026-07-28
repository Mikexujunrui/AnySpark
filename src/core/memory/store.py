# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""JSON persistence layer for memory entries.

Stores project memory per-book in ``data/project_memory_{bookId}.json`` and
user preference entries globally in ``data/user_preferences.json``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .models import MemoryEntry

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"

USER_PREFERENCES_FILE = DATA_DIR / "user_preferences.json"


# ── Internal helpers ──


def _read_json(path: Path, default: list | dict) -> list | dict:
    """Read JSON file, returning *default* on error."""
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
            if isinstance(data, list):
                return data
        return default
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read %s: %s", path.name, e)
        return default


def _write_json(path: Path, data: list | dict):
    """Write JSON file atomically."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── Project (per-book) memory store ──


def _project_memory_file(book_id: str) -> Path:
    """Get the project memory file path for a given book."""
    return DATA_DIR / f"project_memory_{book_id}.json"


def load_project_memory(book_id: str) -> dict:
    """Load project memory data for a specific book.

    Returns a dict with default fields if the file doesn't exist.
    """
    path = _project_memory_file(book_id)
    default = {
        "premise": "",
        "notes": [],
        "creative_decisions": [],
        "progress_notes": [],
        "custom_tags": [],
        "updated_at": "",
    }
    data = _read_json(path, default)
    if isinstance(data, dict):
        return data
    return default


def save_project_memory(book_id: str, data: dict):
    """Save project memory data for a specific book."""
    data["updated_at"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    _write_json(_project_memory_file(book_id), data)


# ── User preferences store (global) ──


def load_preferences() -> list[MemoryEntry]:
    """Load all user preference entries."""
    raw = _read_json(USER_PREFERENCES_FILE, [])
    if not isinstance(raw, list):
        return []
    return [MemoryEntry.from_dict(e) for e in raw if isinstance(e, dict)]


def save_preferences(entries: list[MemoryEntry]):
    """Save all user preference entries."""
    _write_json(USER_PREFERENCES_FILE, [e.to_dict() for e in entries])
