# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Annotation/Commentary Constraint Engine — load and inject structural
constraints from literary commentaries or critical annotations.

This module provides data models, persistence, and constraint-generation
for structured commentary/annotation entries (e.g. literary commentaries,
critical apparatus, or zhi pi-style annotations for classical works).

The annotation data itself must be prepared externally — this module only
handles storage, loading, querying, and constraint generation.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

logger = logging.getLogger(__name__)


class AnnotationType(StrEnum):
    """Annotation/commentary type classification."""
    PLOT_HINT = "plot_hint"
    CHARACTER_FATE = "character_fate"
    TECHNIQUE_COMMENT = "technique_comment"
    STRUCTURAL_NOTE = "structural_note"
    ELISION_NOTE = "elision_note"
    FUTURE_REFERENCE = "future_reference"


class AnnotationCertainty(StrEnum):
    """Certainty level of an annotation clue."""
    HIGH = "high"
    MEDIUM = "medium"
    SPECULATIVE = "speculative"


@dataclass
class AnnotationEntry:
    """A single annotation/commentary entry."""
    id: str
    critic: str
    target_chapter: int
    target_text: str
    comment_text: str
    comment_type: AnnotationType

    implied_outcome: str
    certainty: AnnotationCertainty
    related_characters: list[str]
    must_fulfill: bool


@dataclass
class AnnotationDatabase:
    """Database of annotation entries for a book."""
    book_id: str = ""
    entries: list[AnnotationEntry] = field(default_factory=list)

    def get_by_chapter(self, chapter: int) -> list[AnnotationEntry]:
        return [e for e in self.entries if e.target_chapter == chapter]

    def get_must_fulfill(self) -> list[AnnotationEntry]:
        return [e for e in self.entries if e.must_fulfill]

    def get_by_type(self, atype: AnnotationType) -> list[AnnotationEntry]:
        return [e for e in self.entries if e.comment_type == atype]

    def get_by_character(self, character_name: str) -> list[AnnotationEntry]:
        return [e for e in self.entries if character_name in e.related_characters]

    def get_by_certainty(self, certainty: AnnotationCertainty) -> list[AnnotationEntry]:
        return [e for e in self.entries if e.certainty == certainty]


# ── Storage ─────────────────────────────────────────────────────────────

ANNOTATION_DIR = Path(__file__).resolve().parents[2] / "data" / "annotations"


def _ensure_dir() -> None:
    ANNOTATION_DIR.mkdir(parents=True, exist_ok=True)


def save_annotation_database(book_id: str, db: AnnotationDatabase) -> None:
    _ensure_dir()
    path = ANNOTATION_DIR / f"{book_id}.json"
    data = {
        "book_id": book_id,
        "entries": [
            {
                "id": e.id,
                "critic": e.critic,
                "target_chapter": e.target_chapter,
                "target_text": e.target_text,
                "comment_text": e.comment_text,
                "comment_type": e.comment_type.value,
                "implied_outcome": e.implied_outcome,
                "certainty": e.certainty.value,
                "related_characters": e.related_characters,
                "must_fulfill": e.must_fulfill,
            }
            for e in db.entries
        ],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_annotation_database(book_id: str) -> AnnotationDatabase | None:
    path = ANNOTATION_DIR / f"{book_id}.json"
    if not path.exists():
        logger.info("Annotation file not found: %s", path)
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        entries = [
            AnnotationEntry(
                id=e["id"],
                critic=e.get("critic", ""),
                target_chapter=e.get("target_chapter", 0),
                target_text=e.get("target_text", ""),
                comment_text=e.get("comment_text", ""),
                comment_type=AnnotationType(e.get("comment_type", "plot_hint")),
                implied_outcome=e.get("implied_outcome", ""),
                certainty=AnnotationCertainty(e.get("certainty", "medium")),
                related_characters=e.get("related_characters", []),
                must_fulfill=e.get("must_fulfill", False),
            )
            for e in raw.get("entries", [])
        ]
        logger.info("Loaded annotation db %s: %d entries", book_id, len(entries))
        return AnnotationDatabase(book_id=book_id, entries=entries)
    except Exception as e:
        logger.warning("Failed to load annotation db %s: %s", book_id, e)
        return None


def build_annotation_constraints(
    book_id: str,
    chapter_number: int | None = None,
    label: str = "批注/评点",
) -> str:
    """Generate annotation constraint text block for writing prompt injection.

    Args:
        book_id: Book/project ID.
        chapter_number: Optional, constrain to a specific chapter.
        label: Label for the constraint section header (e.g. "批注"/"评语").

    Returns:
        Prompt fragment string. Empty string if no data.
    """
    db = load_annotation_database(book_id)
    if not db or not db.entries:
        return ""

    lines: list[str] = [f"## {label}约束"]

    must_fulfill = db.get_must_fulfill()
    if must_fulfill:
        high = [e for e in must_fulfill if e.certainty == AnnotationCertainty.HIGH]
        if high:
            lines.append(f"### 必须遵循的约束 ({len(high)}条):")
            for e in high[:8]:
                lines.append(f"- [{e.certainty}] {e.implied_outcome[:80]}")
                if e.related_characters:
                    lines.append(f"  涉及: {', '.join(e.related_characters[:4])}")
                lines.append(f"  依据: {e.comment_text[:60]}")

    if chapter_number and chapter_number > 0:
        related = db.get_by_chapter(chapter_number)
        if related:
            lines.append(f"\n### 与第{chapter_number}回相关的批注 ({len(related)}条):")
            for e in related[:4]:
                lines.append(f"- [{e.certainty.value}] {e.comment_text[:60]}")
                lines.append(f"  -> {e.implied_outcome[:60]}")

    return "\n".join(lines)


def get_annotation_chapter_summary(book_id: str) -> dict[int, list[str]]:
    db = load_annotation_database(book_id)
    if not db:
        return {}
    result: dict[int, list[str]] = {}
    for e in db.entries:
        if e.target_chapter not in result:
            result[e.target_chapter] = []
        result[e.target_chapter].append(
            f"[{e.certainty.value}] {e.implied_outcome[:80]}"
        )
    return result
