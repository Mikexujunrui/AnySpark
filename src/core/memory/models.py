# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Data models for memory entries."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum


class ConfidenceLevel(StrEnum):
    """Confidence level of a memory entry, determining its visibility."""

    CONFIRMED = "confirmed"  # User explicitly confirmed
    PENDING = "pending"  # Auto-detected, waiting for user confirmation
    SUGGESTED = "suggested"  # Offline analysis suggestion


class MemorySource(StrEnum):
    """Source of a memory entry."""

    MANUAL = "manual"  # User explicitly added via UI or "remember"
    CONVERSATION = "conversation"  # Auto-detected from conversation
    ANALYSIS = "analysis"  # Offline analysis / batch processing


# ── Category path constants ──

CATEGORY_PROJECT = "project"
CATEGORY_PREFERENCE = "user_preference"

CATEGORY_PREFERENCE_XP = "user_preference.xp"
CATEGORY_PREFERENCE_XP_RELATIONSHIP = "user_preference.xp.relationship"
CATEGORY_PREFERENCE_XP_ARCHETYPE = "user_preference.xp.archetype"
CATEGORY_PREFERENCE_XP_EXCLUDED = "user_preference.xp.excluded"

CATEGORY_PREFERENCE_NARRATIVE = "user_preference.narrative"
CATEGORY_PREFERENCE_NARRATIVE_PLOTS = "user_preference.narrative.plots"
CATEGORY_PREFERENCE_NARRATIVE_EMOTION = "user_preference.narrative.emotion"

CATEGORY_PREFERENCE_WRITING = "user_preference.writing"
CATEGORY_PREFERENCE_WRITING_PACING = "user_preference.writing.pacing"
CATEGORY_PREFERENCE_WRITING_WORD_COUNT = "user_preference.writing.word_count"


@dataclass
class MemoryEntry:
    """A single memory entry stored in the memory system.

    Each entry represents a discrete piece of knowledge about the project
    or the user's narrative preferences. Entries are stored in flat JSON
    files and indexed by category + keywords for progressive disclosure.
    """

    id: str = ""
    category: str = ""  # dot-path category, e.g. "user_preference.xp.relationship"
    content: str = ""  # Full content (Tier 2 disclosure)
    summary: str = ""  # One-line summary (Tier 1 index)
    keywords: list[str] = field(default_factory=list)  # Trigger keywords for auto-promotion
    confidence: str = "pending"  # "confirmed" | "pending" | "suggested"
    source: str = "manual"  # "manual" | "conversation" | "analysis"
    source_ref: str = ""  # Source session ID for traceability
    created_at: str = ""
    hit_count: int = 0  # Times auto-promoted to Tier 2
    active: bool = True  # Soft delete

    def __post_init__(self):
        if not self.id:
            self.id = _generate_id()
        if not self.created_at:
            self.created_at = datetime.now().isoformat(timespec="seconds")

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if k != "active"}

    @staticmethod
    def from_dict(d: dict) -> MemoryEntry:
        return MemoryEntry(**d)


def _generate_id() -> str:
    """Generate a short unique ID for memory entries."""
    return uuid.uuid4().hex[:12]
