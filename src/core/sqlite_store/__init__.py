"""SQLite Graph Store — the former ``core/sqlite_store.py`` split by domain.

Composes :class:`SQLiteStore` from domain mixins and re-exports the
module-level factory ``get_store`` / ``close_shared_driver`` so the
``graph_store`` compatibility shim keeps working unchanged.
"""

from __future__ import annotations

from pathlib import Path

from .search import SearchMixin


class SQLiteStore(SearchMixin):
    """SQLite-backed store providing the same public API as Neo4j GraphStore.

    Uses a single database file (data/novel.db) with per-project isolation
    via project_id foreign keys.  Graph algorithms run in Python.
    """


def get_store(book_id: str, db_path: str | Path | None = None) -> SQLiteStore:
    """Get or create a SQLiteStore for the given project.

    Matches the original ``get_store()`` API from ``graph_store.py``.
    Uses an instance cache so all callers share the same connection.
    """
    if book_id not in SQLiteStore._instances:
        store = SQLiteStore(book_id, db_path=db_path)
        store._ensure_project()
        store.init_schema()
        SQLiteStore._instances[book_id] = store
    return SQLiteStore._instances[book_id]


def close_shared_driver() -> None:
    """Compatibility shim — closes all cached store connections."""
    for store in SQLiteStore._instances.values():
        try:
            store.close()
        except Exception:
            pass
    SQLiteStore._instances.clear()


__all__ = ["SQLiteStore", "get_store", "close_shared_driver"]
