# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""JsonStore — facade class inheriting from entity-specific store mixins.

All methods are provided by the mixin classes in the `stores/` sub-package.
This module keeps the module-level helper functions and the singleton instance.
"""

import re

from .stores._base import BaseStore
from .stores.book_store import BookStoreMixin
from .stores.chapter_store import ChapterStoreMixin
from .stores.meta_store import MetaStoreMixin
from .stores.session_store import SessionStoreMixin
from .stores.worldbuilding_store import WorldbuildingStoreMixin


class JsonStore(
    BaseStore,
    BookStoreMixin,
    ChapterStoreMixin,
    SessionStoreMixin,
    WorldbuildingStoreMixin,
    MetaStoreMixin,
):
    """Unified JSON file storage facade.

    All entity CRUD methods are inherited from store mixin classes.
    Direct instantiation is discouraged; use the module-level `json_store` singleton.
    """


# ── Module-level helpers used by patch_chapter ──

def _split_paragraphs(content: str) -> list[dict]:
    """Split content into paragraphs, returning list of {index, text, start, end}."""
    paragraphs = []
    parts = content.split('\n\n')
    pos = 0
    for i, part in enumerate(parts):
        paragraphs.append({"index": i, "text": part, "start": pos, "end": pos + len(part)})
        pos += len(part) + 2  # +2 for '\n\n'
    return paragraphs


def _locate_in_paragraph(paragraphs: list[dict], segment_id: int,
                         confirm: str) -> tuple[int, str] | None:
    """Locate text within a specific paragraph using segment_id + confirm.

    Returns (absolute_position_in_content, matched_text) or None.
    """
    if segment_id < 0 or segment_id >= len(paragraphs):
        return None
    para = paragraphs[segment_id]
    if not confirm:
        # No confirm, return whole paragraph as anchor
        return (para["start"], para["text"])
    # Search within this paragraph
    result = _fuzzy_find(para["text"], confirm)
    if result:
        rel_pos, matched = result
        return (para["start"] + rel_pos, matched)
    return None


def _fuzzy_find(content: str, find: str) -> tuple[int, str] | None:
    """Multi-strategy text locator for patch operations.

    Returns (position_in_content, actual_matched_text) so the caller uses
    the real text for replacement length. Returns None if all strategies fail.

    Strategies: exact → strip → full-width norm → shorter anchor → whitespace norm
    """
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
    half_to_full = str.maketrans(
        ",?!;:()",
        "\uff0c\uff1f\uff01\uff1b\uff1a\uff08\uff09")
    full_to_half = str.maketrans(
        "\uff0c\uff1f\uff01\uff1b\uff1a\uff08\uff09",
        ",?!;:()")
    norm_find = find.translate(full_to_half).translate(half_to_full)
    if norm_find != find:
        pos = content.find(norm_find)
        if pos >= 0:
            return (pos, norm_find)

    # 4. Shorter anchor (first 60%, at least 10 chars)
    short_len = max(10, int(len(find) * 0.6))
    shorter = find[:short_len]
    if shorter != find and shorter.strip():
        pos = content.find(shorter)
        if pos >= 0:
            return (pos, shorter)

    # 5. Whitespace-normalized — safest: returns the actual matched content span
    norm_find = re.sub(r'\s+', '', find)
    norm_content = re.sub(r'\s+', '', content)
    if norm_find and len(norm_find) > 5:
        pos = norm_content.find(norm_find)
        if pos >= 0:
            # Map back: find the actual content span that corresponds to norm_find
            cleaned_len = 0
            orig_start = 0
            for i, c in enumerate(content):
                if cleaned_len >= pos:
                    orig_start = i
                    break
                if not c.isspace():
                    cleaned_len += 1
            # Find the actual end in original content
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


# ── Singleton ──
json_store = JsonStore()
