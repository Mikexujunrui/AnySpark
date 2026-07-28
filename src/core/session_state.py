# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Session State Machine — explicit state tracking with input queuing.

Replaces the binary ``busy`` / ``free`` model with a proper state machine:

    IDLE → RUNNING → (WAITING_USER) → RUNNING → IDLE

States:
    IDLE          No active agent loop. New messages start a fresh run.
    RUNNING       Agent loop is active. New messages are queued as steering.
    WAITING_USER  Agent is blocked on ``ask_user`` / question. New messages
                  are queued and will be injected when the loop resumes.

Input queuing:
    When ``RUNNING`` or ``WAITING_USER``, incoming messages go into a
    per-session queue instead of being rejected with ``BusyError``.
    The agent loop drains the queue between rounds, injecting queued
    messages as steering hints.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class SessionState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_USER = "waiting_user"


class BusyError(Exception):
    """Legacy compatibility — raised when an operation requires IDLE state
    but the session is in another state. New code should use queuing instead."""

    def __init__(self, session_id: str, state: SessionState):
        super().__init__(f"Session {session_id} is {state.value}")
        self.session_id = session_id
        self.state = state


class CancelledError(Exception):
    def __init__(self, session_id: str):
        super().__init__(f"Session {session_id} was cancelled")
        self.session_id = session_id


@dataclass
class QueuedInput:
    """A message that arrived while the agent loop was busy."""

    text: str
    mode: str = "write"


@dataclass
class RunHandle:
    """Handle for the agent loop to interact with the state machine."""

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


class SessionStateMachine:
    """Manages session lifecycle with explicit states and input queuing."""

    def __init__(self):
        self._states: dict[str, SessionState] = {}
        self._queues: dict[str, asyncio.Queue[QueuedInput]] = {}
        self._handles: dict[str, RunHandle] = {}
        self._last_active: dict[str, float] = {}  # session_id → timestamp
        self._lock = asyncio.Lock()

    # ── Stale session timeout (seconds) ──
    STALE_TIMEOUT = 300  # 5 minutes

    # ── State queries ──

    def get_state(self, session_id: str) -> SessionState:
        return self._states.get(session_id, SessionState.IDLE)

    def is_busy(self, session_id: str) -> bool:
        return self.get_state(session_id) != SessionState.IDLE

    def get_handle(self, session_id: str) -> RunHandle | None:
        """Get the active handle for a session, or None if not running."""
        return self._handles.get(session_id)

    def has_queued_input(self, session_id: str) -> bool:
        q = self._queues.get(session_id)
        return q is not None and not q.empty()

    # ── Lifecycle ──

    async def start(self, session_id: str) -> RunHandle:
        """Transition to RUNNING and return a handle for the agent loop.

        Raises BusyError if the session is already RUNNING (not WAITING_USER).
        Callers should use ``start_or_queue`` instead unless they need the
        legacy behaviour."""
        async with self._lock:
            state = self._states.get(session_id, SessionState.IDLE)
            if state == SessionState.RUNNING:
                raise BusyError(session_id, state)
            self._states[session_id] = SessionState.RUNNING
            handle = RunHandle(session_id=session_id)
            self._handles[session_id] = handle
            if session_id not in self._queues:
                self._queues[session_id] = asyncio.Queue()
            return handle

    async def ensure_running(self, session_id: str) -> RunHandle:
        """Backward-compatible alias for ``start``."""
        return await self.start(session_id)

    async def start_or_queue(self, session_id: str, msg: str, mode: str = "write") -> RunHandle | None:
        """Start a new run if IDLE, otherwise queue the message.

        Returns a RunHandle if a new run was started, None if the message
        was queued (caller should NOT start a new agent loop)."""
        async with self._lock:
            state = self._states.get(session_id, SessionState.IDLE)
            if state == SessionState.IDLE:
                self._states[session_id] = SessionState.RUNNING
                handle = RunHandle(session_id=session_id)
                self._handles[session_id] = handle
                if session_id not in self._queues:
                    self._queues[session_id] = asyncio.Queue()
                return handle
            else:
                # Queue the message for the running loop
                q = self._queues.get(session_id)
                if q is None:
                    q = asyncio.Queue()
                    self._queues[session_id] = q
                await q.put(QueuedInput(text=msg, mode=mode))
                return None

    async def set_waiting_user(self, session_id: str):
        """Mark the session as waiting for user input."""
        async with self._lock:
            if self._states.get(session_id) == SessionState.RUNNING:
                self._states[session_id] = SessionState.WAITING_USER

    async def set_running(self, session_id: str):
        """Mark the session as running again (e.g. after user replied)."""
        async with self._lock:
            self._states[session_id] = SessionState.RUNNING

    async def release(self, session_id: str, handle: RunHandle):
        """Release the session back to IDLE. Called when the agent loop ends."""
        async with self._lock:
            if self._handles.get(session_id) is handle:
                self._handles.pop(session_id, None)
            self._states[session_id] = SessionState.IDLE

    async def drain_queued(self, session_id: str) -> list[QueuedInput]:
        """Drain all queued inputs for a session. Called by the agent loop
        between rounds to pick up steering messages."""
        q = self._queues.get(session_id)
        if q is None:
            return []
        items: list[QueuedInput] = []
        while not q.empty():
            try:
                items.append(q.get_nowait())
            except asyncio.QueueEmpty:
                break
        return items

    async def cancel(self, session_id: str) -> bool:
        """Cancel the active run for a session."""
        async with self._lock:
            handle = self._handles.get(session_id)
            if handle and not handle.cancelled:
                handle.cancel()
                return True
            return False

    def touch(self, session_id: str):
        """Update the last-active timestamp for a session."""
        self._last_active[session_id] = time.time()

    def release_stale(self) -> list[str]:
        """Release sessions that have been RUNNING or WAITING_USER for
        longer than STALE_TIMEOUT without any activity. Returns list of
        released session IDs."""
        now = time.time()
        released: list[str] = []
        for sid, state in list(self._states.items()):
            if state == SessionState.IDLE:
                continue
            last = self._last_active.get(sid, 0)
            if now - last > self.STALE_TIMEOUT:
                handle = self._handles.get(sid)
                if handle and not handle.cancelled:
                    handle.cancel()
                self._states[sid] = SessionState.IDLE
                self._handles.pop(sid, None)
                released.append(sid)
                logger.warning("Released stale session %s (state was %s, inactive %.0fs)", sid, state.value, now - last)
        return released


# Module-level singleton
run_state = SessionStateMachine()
