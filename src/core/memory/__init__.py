# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Memory System — per-book project memory & global user narrative preferences.

Two independent, toggleable memory capabilities:

1. **Project Memory (per-book)**: Each book/novel has its own creative memory:
   premise, writing notes, creative decisions, progress tracking, custom tags.

2. **User Preferences (global)**: The user's narrative taste profile — XP,
   favorite plot patterns, emotional mode, pacing preferences, and excluded
   content. Enables deep personalization of writing output.

Architecture
============
- ``MemoryManager``: real implementation
- ``NullMemoryManager``: no-op for zero-presence when disabled
- ``get_memory_manager()``: returns ``NullMemoryManager`` when global switch is off
"""

from __future__ import annotations

from .manager import MemoryManager, NullMemoryManager, get_memory_manager, reset_memory_manager
from .models import (
    CATEGORY_PREFERENCE_NARRATIVE,
    CATEGORY_PREFERENCE_NARRATIVE_EMOTION,
    CATEGORY_PREFERENCE_NARRATIVE_PLOTS,
    CATEGORY_PREFERENCE_WRITING,
    CATEGORY_PREFERENCE_WRITING_PACING,
    CATEGORY_PREFERENCE_WRITING_WORD_COUNT,
    CATEGORY_PREFERENCE_XP,
    CATEGORY_PREFERENCE_XP_ARCHETYPE,
    CATEGORY_PREFERENCE_XP_EXCLUDED,
    CATEGORY_PREFERENCE_XP_RELATIONSHIP,
    CATEGORY_PROJECT,
    ConfidenceLevel,
    MemoryEntry,
    MemorySource,
)
from .project_memory import ProjectMemoryHelper
from .user_prefs import UserPreferenceHelper

__all__ = [
    "MemoryEntry",
    "ConfidenceLevel",
    "MemorySource",
    "MemoryManager",
    "NullMemoryManager",
    "get_memory_manager",
    "reset_memory_manager",
    "ProjectMemoryHelper",
    "UserPreferenceHelper",
    "CATEGORY_PROJECT",
    "CATEGORY_PREFERENCE_XP",
    "CATEGORY_PREFERENCE_XP_RELATIONSHIP",
    "CATEGORY_PREFERENCE_XP_ARCHETYPE",
    "CATEGORY_PREFERENCE_XP_EXCLUDED",
    "CATEGORY_PREFERENCE_NARRATIVE",
    "CATEGORY_PREFERENCE_NARRATIVE_PLOTS",
    "CATEGORY_PREFERENCE_NARRATIVE_EMOTION",
    "CATEGORY_PREFERENCE_WRITING",
    "CATEGORY_PREFERENCE_WRITING_PACING",
    "CATEGORY_PREFERENCE_WRITING_WORD_COUNT",
]
