# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""User preference helper — CRUD and matching for narrative taste preferences.

Manages XP preferences, favorite plot patterns, emotional mode, pacing,
writing preferences, and excluded content. Supports three confidence levels
(confirmed/pending/suggested) and keyword-based auto-promotion matching.
"""

from __future__ import annotations

import logging

from .models import ConfidenceLevel, MemoryEntry
from .store import load_preferences, save_preferences

logger = logging.getLogger(__name__)


class UserPreferenceHelper:
    """Helper for user narrative preference operations."""

    CATEGORY_KEYWORDS = {
        "user_preference.xp.relationship": [
            "关系",
            "cp",
            "配对",
            "宿敌",
            "师徒",
            "年上",
            "年下",
            "养成",
            "救赎",
            "敌对",
            "合作",
            "同盟",
        ],
        "user_preference.xp.archetype": [
            "原型",
            "人格",
            "性格",
            "冰山",
            "阳光",
            "治愈",
            "阴暗",
        ],
        "user_preference.xp.excluded": [
            "雷",
            "雷点",
            "excluded",
            "不要",
            "禁止",
            "避雷",
        ],
        "user_preference.narrative.plots": [
            "套路",
            "情节",
            "桥段",
            "误会",
            "掉马",
            "替身",
            "追妻",
            "火葬场",
            "破镜重圆",
            "先婚后爱",
        ],
        "user_preference.narrative.emotion": [
            "情感",
            "he",
            "be",
            "虐",
            "甜",
            "治愈",
            "致郁",
        ],
        "user_preference.writing.pacing": [
            "节奏",
            "慢热",
            "快节奏",
            "日常",
            "剧情密度",
        ],
    }

    # ── CRUD ──

    @staticmethod
    def list_all() -> list[MemoryEntry]:
        """List all active preference entries."""
        return [e for e in load_preferences() if e.active]

    @staticmethod
    def list_by_category(category: str) -> list[MemoryEntry]:
        """List active entries in a specific category (exact or prefix match)."""
        all_entries = load_preferences()
        return [
            e for e in all_entries if e.active and (e.category == category or e.category.startswith(category + "."))
        ]

    @staticmethod
    def get_by_id(entry_id: str) -> MemoryEntry | None:
        """Get a single entry by ID."""
        for e in load_preferences():
            if e.id == entry_id:
                return e
        return None

    @staticmethod
    def add_entry(
        category: str,
        content: str,
        summary: str = "",
        keywords: list[str] | None = None,
        confidence: str = "pending",
        source: str = "manual",
        source_ref: str = "",
    ) -> MemoryEntry:
        """Add a new preference entry."""
        entry = MemoryEntry(
            category=category,
            content=content,
            summary=summary or _auto_summary(content),
            keywords=keywords or [],
            confidence=confidence,
            source=source,
            source_ref=source_ref,
        )
        all_entries = load_preferences()
        all_entries.append(entry)
        save_preferences(all_entries)
        return entry

    @staticmethod
    def update_entry(entry_id: str, **kwargs) -> bool:
        """Update fields of an existing entry. Returns True if found."""
        all_entries = load_preferences()
        for e in all_entries:
            if e.id == entry_id:
                for k, v in kwargs.items():
                    if hasattr(e, k) and k not in ("id", "created_at"):
                        setattr(e, k, v)
                save_preferences(all_entries)
                return True
        return False

    @staticmethod
    def confirm_entry(entry_id: str) -> bool:
        """Set an entry's confidence to CONFIRMED."""
        return UserPreferenceHelper.update_entry(entry_id, confidence=ConfidenceLevel.CONFIRMED)

    @staticmethod
    def delete_entry(entry_id: str) -> bool:
        """Soft-delete an entry."""
        return UserPreferenceHelper.update_entry(entry_id, active=False)

    @staticmethod
    def hard_delete(entry_id: str) -> bool:
        """Permanently remove an entry."""
        all_entries = load_preferences()
        new_entries = [e for e in all_entries if e.id != entry_id]
        if len(new_entries) < len(all_entries):
            save_preferences(new_entries)
            return True
        return False

    # ── Matching ──

    @staticmethod
    def match_by_keywords(input_keywords: list[str]) -> list[MemoryEntry]:
        """Return active entries whose keywords overlap with input_keywords."""
        all_entries = [
            e
            for e in load_preferences()
            if e.active
            and e.confidence
            in (
                ConfidenceLevel.CONFIRMED,
                ConfidenceLevel.PENDING,
            )
        ]
        if not input_keywords:
            return []

        input_lower = {k.lower() for k in input_keywords}
        matched = []
        for entry in all_entries:
            entry_keywords = {k.lower() for k in entry.keywords}
            if input_lower & entry_keywords:
                entry.hit_count += 1
                matched.append(entry)

        # Persist hit_count updates
        if matched:
            save_preferences(all_entries)

        return matched

    @staticmethod
    def detect_keywords_from_text(text: str) -> list[str]:
        """Extract potential preference-related keywords from free text."""
        text_lower = text.lower()
        detected = set()
        # Check against known category keywords
        for category_keywords in UserPreferenceHelper.CATEGORY_KEYWORDS.values():
            for kw in category_keywords:
                if kw.lower() in text_lower:
                    detected.add(kw)
        return list(detected)

    # ── Formatting for injection ──

    @staticmethod
    def format_tier0() -> str:
        """Format a Tier 0 presence marker for user preferences."""
        all_entries = load_preferences()
        active = [e for e in all_entries if e.active]
        confirmed = sum(1 for e in active if e.confidence == ConfidenceLevel.CONFIRMED)
        pending = sum(1 for e in active if e.confidence == ConfidenceLevel.PENDING)
        parts = []
        if confirmed:
            parts.append(f"{confirmed}条已确认")
        if pending:
            parts.append(f"{pending}条待确认")
        if not parts:
            return ""
        return f"用户偏好 | {' | '.join(parts)}"

    @staticmethod
    def format_tier1() -> str:
        """Format a Tier 1 index of all active user preference entries."""
        all_entries = [e for e in load_preferences() if e.active and e.confidence == ConfidenceLevel.CONFIRMED]
        if not all_entries:
            return ""

        sections = {}
        for e in all_entries:
            top = e.category.split(".")[0] if "." in e.category else e.category
            sections.setdefault(top, []).append(e)

        lines = ["## 用户叙事偏好"]
        for top, entries in sorted(sections.items()):
            for e in entries:
                sub = e.category.replace(f"{top}.", "", 1) if "." in e.category else ""
                tag = f"[{sub}]" if sub else ""
                lines.append(f"- {tag} {e.summary}")
        return "\n".join(lines)

    @staticmethod
    def format_pending_summary() -> str:
        """Format a summary of pending entries for user confirmation prompt."""
        pending = [e for e in load_preferences() if e.active and e.confidence == ConfidenceLevel.PENDING]
        if not pending:
            return ""
        lines = ["📝 待确认的偏好"]
        for e in pending:
            lines.append(f"  - [{e.category}] {e.summary}")
        return "\n".join(lines)


def _auto_summary(content: str, max_len: int = 60) -> str:
    """Generate a summary from content if none provided."""
    if len(content) <= max_len:
        return content
    return content[:max_len] + "…"
