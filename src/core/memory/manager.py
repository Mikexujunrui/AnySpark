# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""MemoryManager + NullMemoryManager — core orchestration layer.

Implements the Null Object pattern for zero-presence when disabled.
When the global ``memory_enabled`` switch is off, ``get_memory_manager()``
returns a ``NullMemoryManager`` whose every method is a no-op.
"""

from __future__ import annotations

import logging

from .injector import MemoryInjector
from .models import MemoryEntry
from .project_memory import ProjectMemoryHelper
from .store import load_preferences
from .triggers import MemoryTriggerEngine
from .user_prefs import UserPreferenceHelper

logger = logging.getLogger(__name__)


class MemoryManager:
    """Real implementation of the memory system.

    Provides unified access to both project memory (per-book) and user
    preferences (global), with progressive disclosure (Tier 0/1/2) and
    keyword-based auto-promotion.
    """

    def __init__(self):
        self._project_helper = ProjectMemoryHelper()
        self._pref_helper = UserPreferenceHelper()
        self._injector = MemoryInjector(self)
        self._triggers = MemoryTriggerEngine(self)

    @property
    def enabled(self) -> bool:
        return True

    def __bool__(self) -> bool:
        return True

    # ── Tiered injection (requires book_id for project memory) ──

    def inject_tier0(self, book_id: str = "") -> str:
        """~50 token presence marker."""
        return self._injector.format_tier0(book_id)

    def inject_tier1(self, book_id: str = "", session_mode: str = "normal") -> str:
        """Full index for build_dynamic_context injection."""
        return self._injector.format_tier1(book_id, session_mode)

    def inject_tier2(self, input_keywords: list[str]) -> str:
        """Keyword-matched preference details for ContextManager injection."""
        return self._injector.format_tier2(input_keywords)

    @property
    def project(self) -> ProjectMemoryHelper:
        return self._project_helper

    @property
    def preferences(self) -> UserPreferenceHelper:
        return self._pref_helper

    @property
    def triggers(self) -> MemoryTriggerEngine:
        return self._triggers

    def get_category_counts(self, book_id: str = "") -> dict:
        """Return {note_count, decision_count, pref_confirmed, pref_pending}."""
        proj_data = self._project_helper.get_full_snapshot(book_id)
        notes = proj_data.get("notes", [])
        decisions = proj_data.get("creative_decisions", [])

        all_prefs = load_preferences()
        active_prefs = [e for e in all_prefs if e.active]
        confirmed = sum(1 for e in active_prefs if e.confidence == "confirmed")
        pending = sum(1 for e in active_prefs if e.confidence == "pending")

        return {
            "notes": len(notes),
            "decisions": len(decisions),
            "pref_confirmed": confirmed,
            "pref_pending": pending,
            "pref_total": len(active_prefs),
        }


class NullMemoryManager:
    """No-op implementation. Agent has zero awareness of the memory system."""

    @property
    def enabled(self) -> bool:
        return False

    def __bool__(self) -> bool:
        return False

    def inject_tier0(self, book_id: str = "") -> str:
        return ""

    def inject_tier1(self, book_id: str = "", session_mode: str = "normal") -> str:
        return ""

    def inject_tier2(self, input_keywords: list[str]) -> str:
        return ""

    @property
    def project(self):
        return _NULL_PROJECT_HELPER

    @property
    def preferences(self):
        return _NULL_PREF_HELPER

    @property
    def triggers(self):
        return _NULL_TRIGGER_ENGINE

    def get_category_counts(self, book_id: str = "") -> dict:
        return {"notes": 0, "decisions": 0, "pref_confirmed": 0, "pref_pending": 0, "pref_total": 0}


# ── Null helpers ──


class _NullProjectHelper:
    def get_premise(self, book_id): return ""
    def set_premise(self, book_id, premise): pass
    def get_notes(self, book_id): return []
    def add_note(self, book_id, title, content): return {"id": ""}
    def delete_note(self, book_id, note_id): return False
    def get_decisions(self, book_id): return []
    def record_decision(self, book_id, title, rationale): return {"id": ""}
    def delete_decision(self, book_id, decision_id): return False
    def get_progress_notes(self, book_id): return []
    def add_progress_note(self, book_id, content): return {"id": ""}
    def delete_progress_note(self, book_id, note_id): return False
    def get_tags(self, book_id): return []
    def set_tags(self, book_id, tags): pass
    def get_full_snapshot(self, book_id): return {}
    def format_tier1_index(self, book_id): return ""
    def format_tier0(self, book_id): return ""


class _NullPrefHelper:
    def list_all(self): return []
    def list_by_category(self, c): return []
    def get_by_id(self, i): return None
    def add_entry(self, *a, **kw): return MemoryEntry(id="null")
    def update_entry(self, *a, **kw): return False
    def confirm_entry(self, *a): return False
    def delete_entry(self, *a): return False
    def hard_delete(self, *a): return False
    def match_by_keywords(self, k): return []
    def detect_keywords_from_text(self, t): return []
    def format_tier0(self): return ""
    def format_tier1(self): return ""
    def format_pending_summary(self): return ""


class _NullTriggerEngine:
    def check_tier2_promotion(self, *a, **kw): return ""
    def extract_keywords_from_scope(self, *a): return []


_NULL_PROJECT_HELPER = _NullProjectHelper()
_NULL_PREF_HELPER = _NullPrefHelper()
_NULL_TRIGGER_ENGINE = _NullTriggerEngine()


# ── Singleton ──

_memory_manager: MemoryManager | NullMemoryManager | None = None


def get_memory_manager() -> MemoryManager | NullMemoryManager:
    """Return the global memory manager singleton.

    Returns ``NullMemoryManager`` when the global ``memory_enabled`` switch
    in ``data/settings.json`` is off.
    """
    global _memory_manager
    if _memory_manager is None:
        try:
            from core.settings import get_settings
            master_enabled = get_settings().memory_enabled
            if not master_enabled:
                _memory_manager = NullMemoryManager()
                return _memory_manager
        except Exception:
            pass
        _memory_manager = MemoryManager()
    return _memory_manager


def reset_memory_manager():
    """Clear the cached singleton (used for tests or settings changes)."""
    global _memory_manager
    _memory_manager = None
