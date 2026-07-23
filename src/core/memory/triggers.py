# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Memory trigger engine — keyword-based auto-promotion for Tier 2.

Detects when a writing scope's entities/outline/keywords match user preference
keywords and returns the relevant entries for automatic injection.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .manager import MemoryManager

logger = logging.getLogger(__name__)

# Default keywords that trigger preference auto-promotion
_SCOPE_KEYWORD_MAP: dict[str, list[str]] = {
    "character": [
        "宿敌", "师徒", "年上", "年下", "养成", "救赎",
        "敌人", "恋人", "伴侣", "搭档", "对手",
    ],
    "outline": [
        "误会", "误解", "掉马", "暴露", "替身",
        "追妻", "追夫", "火葬场", "破镜重圆",
        "先婚后爱", "协议", "契约", "重逢", "失忆",
    ],
    "emotion": [
        "虐", "甜", "治愈", "致郁", "温暖", "悲伤",
    ],
    "pacing": [
        "慢热", "快节奏", "日常", "悠闲", "紧凑",
    ],
}


class MemoryTriggerEngine:
    """Detects potential preference matches and triggers Tier 2 injection."""

    def __init__(self, manager: MemoryManager):
        self._manager = manager

    def check_tier2_promotion(
        self,
        entity_names: list[str] | None = None,
        outline_text: str | None = None,
        extra_keywords: list[str] | None = None,
    ) -> str:
        """Check if any user preference entries should be auto-promoted.

        Args:
            entity_names: Character/location/concept names in current scope.
            outline_text: Chapter outline or synopsis text.
            extra_keywords: Additional keywords from writing instructions.

        Returns:
            Formatted Tier 2 injection text, or empty string if no match.
        """
        if not self._manager.enabled:
            return ""

        keywords = set()

        # Extract from entity names (split into meaningful parts)
        if entity_names:
            for name in entity_names:
                for key_type, kw_list in _SCOPE_KEYWORD_MAP.items():
                    for kw in kw_list:
                        if kw in name:
                            keywords.add(kw)

        # Extract from outline text
        if outline_text:
            text_lower = outline_text.lower()
            for key_type, kw_list in _SCOPE_KEYWORD_MAP.items():
                for kw in kw_list:
                    if kw.lower() in text_lower:
                        keywords.add(kw)

        # Add extra keywords directly
        if extra_keywords:
            keywords.update(k.lower() for k in extra_keywords)

        if not keywords:
            return ""

        return self._manager.inject_tier2(list(keywords))

    def extract_keywords_from_scope(self, scope) -> list[str]:
        """Extract searchable keywords from a WritingKnowledgeScope-like object.

        Works with any object that has ``characters``, ``locations``,
        ``concepts``, ``chapter_outline``, etc. attributes.
        """
        if scope is None:
            return []

        keywords = set()

        # Extract entity names from scope exposure lists
        for attr in ("characters", "locations", "concepts", "items"):
            exposures = getattr(scope, attr, None) or []
            for exp in exposures:
                name = getattr(exp, "entity_name", None) or (exp if isinstance(exp, str) else "")
                if name:
                    keywords.add(name)

        # Extract from chapter outline
        outline = getattr(scope, "chapter_outline", None) or ""
        if outline:
            for kw_list in _SCOPE_KEYWORD_MAP.values():
                for kw in kw_list:
                    if kw.lower() in outline.lower():
                        keywords.add(kw)

        # Extract from style requirements
        style = getattr(scope, "style_requirements", None) or ""
        if style:
            for kw_list in _SCOPE_KEYWORD_MAP.values():
                for kw in kw_list:
                    if kw.lower() in style.lower():
                        keywords.add(kw)

        return list(keywords)
