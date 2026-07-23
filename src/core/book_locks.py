"""Book-level write lock — prevents data races when multiple sessions write to the same book.

Problem: json_store compound operations (read→modify→write) are not atomic across sessions.
Two parallel sessions on the same book can step on each other, causing lost writes.

Solution: Per-book threading.Lock for compound write operations, keeping existing
json_store._lock (threading.RLock) for individual file I/O thread safety.

Usage:
    from core.book_locks import book_lock
    with book_lock(book_id):
        # compound read-modify-write safe from other sessions
"""

import logging
import threading
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_book_locks: dict[str, threading.RLock] = {}
_guard = threading.Lock()


@contextmanager
def book_lock(book_id: str):
    """Acquire exclusive write lock for a book_id (reentrant-safe).

    All compound write operations on the same book_id are serialized.
    Operations on different book_ids run concurrently.
    Reentrant: nested acquisitions by the same thread are fine.
    """
    with _guard:
        if book_id not in _book_locks:
            _book_locks[book_id] = threading.RLock()
        lock = _book_locks[book_id]

    lock.acquire()
    try:
        yield
    finally:
        lock.release()


def cleanup_book_lock(book_id: str):
    """Remove a book's lock entry (e.g. after book deletion)."""
    with _guard:
        _book_locks.pop(book_id, None)
        logger.debug(f"Cleaned up lock for book: {book_id}")
