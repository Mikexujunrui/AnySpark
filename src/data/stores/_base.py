# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Base store with file-path helpers, JSON I/O, and ID resolution."""

import json
import logging
import threading
from pathlib import Path

from core.config import DATA_DIR
from core.errors import StorageError

logger = logging.getLogger(__name__)


class BaseStore:
    """Shared foundation: file paths, JSON read/write, ID helpers."""

    def __init__(self):
        self._books_file = DATA_DIR / "books.json"
        self._write_lock = threading.RLock()

    @staticmethod
    def _safe_id(raw: str) -> str:
        """Reject path traversal characters in user-supplied IDs."""
        if not raw or ".." in raw or "/" in raw or "\\" in raw:
            raise ValueError(f"Invalid ID (path traversal detected): {raw!r}")
        return raw.strip()

    @staticmethod
    def _resolve_by_id(items: list[dict], target_id: str, id_key: str = "id") -> dict | None:
        """Find item by exact ID match, then fall back to unique prefix match.

        This handles the common case where IDs are truncated during display
        (e.g. 13-digit timestamps shown as 8 digits) and then fed back by the
        Agent for lookups.

        Returns None if zero or multiple prefix matches are found.
        """
        # Exact match
        exact = next((item for item in items if item.get(id_key) == target_id), None)
        if exact:
            return exact
        # Prefix match (only if unique)
        prefix_matches = [item for item in items if str(item.get(id_key, "")).startswith(target_id)]
        if len(prefix_matches) == 1:
            return prefix_matches[0]
        return None

    @staticmethod
    def _resolve_full_id(items: list[dict], target_id: str, id_key: str = "id") -> str:
        """Like _resolve_by_id but returns the resolved full ID string, or the
        original target_id if no unique match is found."""
        resolved = BaseStore._resolve_by_id(items, target_id, id_key)
        return resolved[id_key] if resolved else target_id

    # ── File path helpers ──

    def _chapters_file(self, book_id: str) -> Path:
        return DATA_DIR / f"chapters_{self._safe_id(book_id)}.json"

    def _sessions_file(self, book_id: str) -> Path:
        return DATA_DIR / f"sessions_{self._safe_id(book_id)}.json"

    def _messages_file(self, session_id: str) -> Path:
        return DATA_DIR / f"messages_{self._safe_id(session_id)}.json"

    def _docs_file(self, session_id: str) -> Path:
        return DATA_DIR / f"docs_{self._safe_id(session_id)}.json"

    def _worldbuilding_file(self, book_id: str) -> Path:
        return DATA_DIR / f"worldbuilding_{self._safe_id(book_id)}.json"

    def _location_map_file(self, book_id: str) -> Path:
        return DATA_DIR / f"location_map_{self._safe_id(book_id)}.json"

    def _detailed_outline_file(self, book_id: str) -> Path:
        return DATA_DIR / f"detailed_outline_{self._safe_id(book_id)}.json"

    def _continuity_cards_file(self, book_id: str) -> Path:
        return DATA_DIR / f"continuity_cards_{self._safe_id(book_id)}.json"

    def _flavor_reports_file(self, book_id: str) -> Path:
        return DATA_DIR / f"flavor_reports_{self._safe_id(book_id)}.json"

    def _timeline_file(self, book_id: str) -> Path:
        return DATA_DIR / f"timeline_{self._safe_id(book_id)}.json"

    def _outline_file(self, book_id: str) -> Path:
        return DATA_DIR / f"outline_{self._safe_id(book_id)}.json"

    def _notes_file(self, book_id: str) -> Path:
        return DATA_DIR / f"notes_{self._safe_id(book_id)}.json"

    def _reviews_file(self, book_id: str) -> Path:
        return DATA_DIR / f"reviews_{self._safe_id(book_id)}.json"

    def _volumes_file(self, book_id: str) -> Path:
        return DATA_DIR / f"volumes_{self._safe_id(book_id)}.json"

    def _material_subs_file(self, book_id: str) -> Path:
        return DATA_DIR / f"material_subs_{self._safe_id(book_id)}.json"

    def _plot_chain_file(self, book_id: str) -> Path:
        return DATA_DIR / f"plot_chain_{self._safe_id(book_id)}.json"

    def _tasks_file(self, book_id: str) -> Path:
        return DATA_DIR / f"tasks_{self._safe_id(book_id)}.json"

    # ── JSON I/O ──

    def _read_json(self, path: Path, default=None):
        if default is None:
            default = []
        if path.exists():
            # read_text is atomic; no lock needed since _write_json uses atomic rename
            try:
                return json.loads(path.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError:
                logger.warning("Corrupted JSON file detected: %s — returning default", path.name)
                return default
            except OSError:
                return default
        return default

    def _write_json(self, path: Path, data):
        with self._write_lock:
            try:
                tmp = path.with_suffix(path.suffix + ".tmp")
                tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                tmp.replace(path)  # atomic rename on same filesystem
            except OSError as e:
                raise StorageError(f"写入失败: {path.name}", str(e))


# ── Module-level helpers used by patch_chapter ──


def _split_paragraphs(content: str) -> list[dict]:
    """Split content into paragraphs, returning list of {index, text, start, end}."""
    paragraphs = []
    parts = content.split("\n\n")
    pos = 0
    for i, part in enumerate(parts):
        paragraphs.append({"index": i, "text": part, "start": pos, "end": pos + len(part)})
        pos += len(part) + 2  # +2 for '\n\n'
    return paragraphs


def _locate_in_paragraph(paragraphs: list[dict], segment_id: int, confirm: str) -> tuple[int, str] | None:
    """Locate text within a specific paragraph using segment_id + confirm."""
    if segment_id < 0 or segment_id >= len(paragraphs):
        return None
    para = paragraphs[segment_id]
    if not confirm:
        return (para["start"], para["text"])
    result = _fuzzy_find(para["text"], confirm)
    if result:
        rel_pos, matched = result
        return (para["start"] + rel_pos, matched)
    return None


def _fuzzy_find(content: str, find: str) -> tuple[int, str] | None:
    """Multi-strategy text locator for patch operations."""
    import re

    # 1. Exact
    pos = content.find(find)
    if pos >= 0:
        return (pos, find)
    # 2. strip
    stripped = find.strip()
    if stripped and stripped != find:
        pos = content.find(stripped)
        if pos >= 0:
            return (pos, stripped)
    # 3. Full-width normalization
    half_to_full = str.maketrans(",?!;:()", "\uff0c\uff1f\uff01\uff1b\uff1a\uff08\uff09")
    full_to_half = str.maketrans("\uff0c\uff1f\uff01\uff1b\uff1a\uff08\uff09", ",?!;:()")
    norm_find = find.translate(full_to_half).translate(half_to_full)
    if norm_find != find:
        pos = content.find(norm_find)
        if pos >= 0:
            return (pos, norm_find)
    # 4. Shorter anchor
    short_len = max(10, int(len(find) * 0.6))
    shorter = find[:short_len]
    if shorter != find and shorter.strip():
        pos = content.find(shorter)
        if pos >= 0:
            return (pos, shorter)
    # 5. Whitespace-normalized
    norm_find = re.sub(r"\s+", "", find)
    norm_content = re.sub(r"\s+", "", content)
    if norm_find and len(norm_find) > 5:
        pos = norm_content.find(norm_find)
        if pos >= 0:
            cleaned_len = 0
            orig_start = 0
            for i, c in enumerate(content):
                if cleaned_len >= pos:
                    orig_start = i
                    break
                if not c.isspace():
                    cleaned_len += 1
            cleaned_end = 0
            orig_end = orig_start
            for i in range(orig_start, len(content)):
                if cleaned_end >= len(norm_find):
                    orig_end = i
                    break
                if not content[i].isspace():
                    cleaned_end += 1
                orig_end = i + 1
            actual = content[orig_start:orig_end]
            return (orig_start, actual)
    return None
