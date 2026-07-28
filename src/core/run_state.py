import asyncio
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class BusyError(Exception):
    def __init__(self, session_id: str):
        super().__init__(f"Session {session_id} is already running")
        self.session_id = session_id


class CancelledError(Exception):
    def __init__(self, session_id: str):
        super().__init__(f"Session {session_id} was cancelled")
        self.session_id = session_id


@dataclass
class RunHandle:
    session_id: str
    cancelled: bool = False
    _cancel_event: asyncio.Event = field(default_factory=asyncio.Event)

    def cancel(self):
        self.cancelled = True
        self._cancel_event.set()

    def check_cancelled(self):
        if self.cancelled:
            raise CancelledError(self.session_id)

    async def wait_cancel(self, timeout: float | None = None) -> bool:
        try:
            await asyncio.wait_for(self._cancel_event.wait(), timeout)
            return True
        except TimeoutError:
            return False


class SessionRunState:
    def __init__(self):
        self._active: dict[str, RunHandle] = {}
        self._lock = asyncio.Lock()

    async def ensure_running(self, session_id: str) -> RunHandle:
        async with self._lock:
            existing = self._active.get(session_id)
            if existing and not existing.cancelled:
                raise BusyError(session_id)
            handle = RunHandle(session_id=session_id)
            self._active[session_id] = handle
            return handle

    async def cancel(self, session_id: str) -> bool:
        async with self._lock:
            handle = self._active.get(session_id)
            if handle and not handle.cancelled:
                handle.cancel()
                logger.info(f"Cancelled session {session_id}")
                return True
            return False

    async def release(self, session_id: str, handle: RunHandle = None):
        async with self._lock:
            current = self._active.get(session_id)
            if current is not None:
                # Only release if no handle specified (backward compat)
                # or if the provided handle matches the current active one.
                # This prevents a stale session's finally block from
                # removing a newer session's handle (race condition).
                if handle is None or current is handle:
                    self._active.pop(session_id, None)

    def is_busy(self, session_id: str) -> bool:
        handle = self._active.get(session_id)
        return handle is not None and not handle.cancelled

    def get_handle(self, session_id: str) -> RunHandle | None:
        return self._active.get(session_id)

    # ── Book-level headless loop mutual exclusion ──
    # Prevents the same book from running two concurrent headless loops
    # (e.g. scheduler + autopilot triggering simultaneously).

    _book_headless: dict[str, str] = {}  # book_id → task_id

    def acquire_book_headless(self, book_id: str, task_id: str) -> bool:
        """Acquire exclusive headless execution for a book. Returns True if acquired."""
        existing = self._book_headless.get(book_id)
        if existing and existing != task_id:
            # Check if the existing task is still actually running
            return False
        self._book_headless[book_id] = task_id
        return True

    def release_book_headless(self, book_id: str, task_id: str = "") -> None:
        """Release headless execution lock for a book."""
        if not task_id or self._book_headless.get(book_id) == task_id:
            self._book_headless.pop(book_id, None)

    def get_book_headless(self, book_id: str) -> str | None:
        """Return the task_id currently holding the book's headless lock, or None."""
        return self._book_headless.get(book_id)


run_state = SessionRunState()
