# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Application context — provides testability hooks for module-level singletons.

All module-level singletons (config, registry, bus, run_state, json_store, etc.)
can be reset to a clean state via ``reset_for_testing()``. This is called from
``conftest.py`` fixture teardown to ensure test isolation.

For production use, the singletons are initialized once at import time and
never reset. This module is intentionally lightweight — it does NOT introduce
a full dependency injection framework, but provides the minimal hooks needed
to make tests deterministic.
"""

import logging
import threading

logger = logging.getLogger(__name__)

# Track whether we're in a testing context (thread-safe)
_test_mode: threading.local = threading.local()
_test_mode.active = False


def is_test_mode() -> bool:
    return getattr(_test_mode, "active", False)


def reset_for_testing():
    """Reset all module-level singletons to a clean state.

    Call this from test fixture setup/teardown to ensure each test starts
    with a fresh state. Not for production use.
    """
    _test_mode.active = True
    logger.debug("Resetting application context for testing")

    # Reset config (reload from .env / config.json)
    import core.config as config_mod
    from core.config import _load_config
    new_cfg = _load_config()
    config_mod.config = new_cfg

    # Reset LLM client cache
    from core.llm_client import reload_clients
    reload_clients()

    # Reset event bus
    import core.event_bus as bus_mod
    from core.event_bus import EventBus
    bus_mod.bus = EventBus()

    # Reset run state
    import core.run_state as rs_mod
    from core.run_state import SessionRunState
    rs_mod.run_state = SessionRunState()

    # Reset question manager
    import core.question as q_mod
    from core.question import QuestionManager
    q_mod.manager = QuestionManager()

    # Reset permission manager
    import core.permissions as p_mod
    from core.permissions import PermissionManager
    p_mod.permission_manager = PermissionManager()

    # Reset review panel (reloads reviewers from disk)
    import core.review_panel as rp_mod
    from core.review_panel import ReviewPanel
    rp_mod.panel = ReviewPanel()

    # Reset JSON store (file-based, so naturally isolated per book_id)
    import data.json_store as js_mod
    from data.json_store import JsonStore
    js_mod.json_store = JsonStore()

    # Reset settings
    try:
        from core.settings import get_settings
        settings = get_settings()
        settings.reload()
    except (ImportError, AttributeError):
        pass

    # Reset book locks
    from core.book_locks import _book_locks, _guard
    with _guard:
        _book_locks.clear()

    logger.debug("Application context reset complete")
