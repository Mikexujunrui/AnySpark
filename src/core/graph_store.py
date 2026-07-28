"""Compatibility shim — SQLiteStore masquerading as the original GraphStore.

All 25+ callers that import from ``graph_store`` continue to work without
any changes::

    from core.graph_store import GraphStore, get_store

This shim delegates to the real SQLite implementation.
"""

from __future__ import annotations

from .sqlite_store import SQLiteStore as GraphStore
from .sqlite_store import close_shared_driver, get_store

__all__ = ["GraphStore", "get_store", "close_shared_driver"]
