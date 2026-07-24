# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Memory injection — formats Tier 0/1/2 context for system prompt injection.

Follows the same progressive disclosure pattern as ``ContextManager``:
- Tier 0: one-line presence marker (~50 tokens)
- Tier 1: full index in ``build_dynamic_context``
- Tier 2: keyword-matched details auto-injected by ``ContextManager.build_scoped_context``
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .manager import MemoryManager

logger = logging.getLogger(__name__)


class MemoryInjector:
    """Formats memory content for progressive disclosure injection."""

    def __init__(self, manager: MemoryManager):
        self._manager = manager

    def format_tier0(self, book_id: str = "") -> str:
        """Generate a one-line presence marker (~50 tokens)."""
        if not self._manager.enabled:
            return ""

        parts = []

        # Per-book project memory
        if book_id:
            pm_tier0 = self._manager.project.format_tier0(book_id)
            if pm_tier0:
                parts.append(pm_tier0)

        # Global user preferences
        counts = self._manager.get_category_counts(book_id)
        pref_parts = []
        if counts["pref_confirmed"] > 0:
            pref_parts.append(f"{counts['pref_confirmed']}条已确认")
        if counts["pref_pending"] > 0:
            pref_parts.append(f"{counts['pref_pending']}条待确认")
        if pref_parts:
            parts.append(f"用户偏好 | {' | '.join(pref_parts)}")

        if not parts:
            return ""
        return " | ".join(parts)

    def format_tier1(self, book_id: str = "", session_mode: str = "normal") -> str:
        """Generate full index for build_dynamic_context injection."""
        if not self._manager.enabled:
            return ""
        if session_mode == "clean_slate":
            return ""

        lines = ["# 记忆系统"]

        # Per-book project memory
        if book_id:
            pm = self._manager.project.format_tier1_index(book_id)
            if pm:
                lines.append(pm)

        # User preferences (skip in experimental mode)
        if session_mode != "experimental":
            prefs = self._manager.preferences.format_tier1()
            if prefs:
                lines.append(prefs)

        if len(lines) <= 1:
            return ""
        return "\n\n".join(lines)

    def format_tier2(self, input_keywords: list[str]) -> str:
        """Generate keyword-matched preference details."""
        if not self._manager.enabled or not input_keywords:
            return ""

        matches = self._manager.preferences.match_by_keywords(input_keywords)
        if not matches:
            return ""

        grouped: dict[str, list[str]] = {}
        for m in matches:
            label = m.category.split(".")[-1] if "." in m.category else m.category
            grouped.setdefault(label, []).append(f"- [{m.summary}] {m.content[:120]}")

        lines = ["## 偏好参考（关键词匹配）"]
        for label, entries in grouped.items():
            lines.append(f"\n{label}:")
            lines.extend(entries)

        result = "\n".join(lines)
        return result

    def has_any_content(self, book_id: str = "") -> bool:
        """Check if there's any memory content to inject."""
        if not self._manager.enabled:
            return False
        counts = self._manager.get_category_counts(book_id)
        return (
            counts["notes"] > 0 or counts["decisions"] > 0 or counts["pref_confirmed"] > 0 or counts["pref_pending"] > 0
        )
