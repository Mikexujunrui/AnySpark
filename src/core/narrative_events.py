# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Event-driven auto-check — hooks into the event bus to run constraint
checking automatically after chapters are written or stored.

This module is intentionally lightweight.  It subscribes to the global
EventBus on first import and fires constraint checks in a background
thread so the main loop is never blocked.
"""

from __future__ import annotations

import logging
import threading

from core.event_bus import EventType, bus
from core.graph_store import get_store

logger = logging.getLogger(__name__)

# Set of tool names that trigger an auto-check after execution.
_AUTO_CHECK_TOOLS = frozenset(
    {
        "write_chapter",
        "store_chapter",
        "rewrite_by_chain",
        "delegate_writing",
        "edit_chapter",
        "patch_chapter",
    }
)


def _on_tool_executed(event) -> None:
    """Handler for TOOL_EXECUTED events.  Runs constraint check in a
    background thread for chapter-touching tools."""
    data = event.data or {}
    tool_name = data.get("tool", "")
    if tool_name not in _AUTO_CHECK_TOOLS:
        return

    book_id = data.get("book_id", "")
    if not book_id:
        return

    # Fire-and-forget in a daemon thread — never block the agent loop.
    t = threading.Thread(
        target=_auto_check,
        args=(book_id, tool_name),
        daemon=True,
        name=f"auto-constraint-{book_id[:8]}",
    )
    t.start()


def _auto_check(book_id: str, trigger_tool: str) -> None:
    """Run constraint checking and log results.  Non-blocking."""
    try:
        from core.narrative_logic import ConstraintChecker, ConstraintStore

        store = get_store(book_id)
        constraint_store = ConstraintStore(store)
        constraints = constraint_store.list(active_only=True)
        if not constraints:
            return  # No constraints defined — nothing to check.

        checker = ConstraintChecker(store)
        violations = checker.check_all()
        if violations:
            hard_count = sum(1 for v in violations if v.severity == "hard")
            logger.info(
                "Auto-check after %s: %d constraint violations (%d hard) in book %s",
                trigger_tool,
                len(violations),
                hard_count,
                book_id,
            )
            for v in violations:
                logger.info(
                    "  Constraint #%s [%s]: %s",
                    v.constraint_id,
                    v.severity,
                    v.description[:80],
                )
        else:
            logger.debug(
                "Auto-check after %s: all %d constraints OK in book %s",
                trigger_tool,
                len(constraints),
                book_id,
            )
    except Exception:
        logger.exception("Auto-check background thread failed for book %s", book_id)


# ── Subscribe on module load ─────────────────────────────────────────
# The event bus is a module-level singleton; subscribing here hooks into
# every tool execution across the entire process lifetime.
try:
    bus.on(EventType.TOOL_EXECUTED, _on_tool_executed)
    logger.debug("Narrative auto-check hook registered on event bus")
except Exception:
    logger.warning("Failed to register narrative auto-check hook (event bus not ready?)")
