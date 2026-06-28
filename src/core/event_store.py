# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Event Store — append-only event stream persistence for agent sessions.

Replaces the coarse ``_persist_turn`` approach (append user+agent pair at the end)
with a fine-grained event stream. Every LLM chunk, tool call, tool result, and
completion signal is written as a separate line in a JSONL file. This enables:

- Exact replay to reconstruct any intermediate state
- Crash resilience (no lost progress between turns)
- Incremental persistence (no need to buffer until the end)

File format: ``data/events_{session_id}.jsonl``, one JSON object per line.
"""

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR

logger = logging.getLogger(__name__)


class EventStore:
    """Append-only event log backed by a JSONL file per session.

    Thread-safe: writes are serialised via a per-session lock.
    """

    def __init__(self):
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    # ── File path ──

    def _events_file(self, session_id: str) -> Path:
        return DATA_DIR / f"events_{self._safe_id(session_id)}.jsonl"

    @staticmethod
    def _safe_id(raw: str) -> str:
        if not raw or ".." in raw or "/" in raw or "\\" in raw:
            raise ValueError(f"Invalid session ID: {raw!r}")
        return raw.strip()

    # ── Lock ──

    def _get_lock(self, session_id: str) -> threading.Lock:
        with self._locks_guard:
            if session_id not in self._locks:
                self._locks[session_id] = threading.Lock()
            return self._locks[session_id]

    # ── Core API ──

    def append(self, session_id: str, event_type: str, data: dict) -> None:
        """Append one event to the session's event stream.

        ``event_type`` is one of:
        ``chunk``, ``tool_call``, ``tool_result``, ``done``, ``error``,
        ``progress``, ``user_message``.
        """
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "data": data,
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"
        lock = self._get_lock(session_id)
        with lock:
            try:
                with open(self._events_file(session_id), "a", encoding="utf-8") as f:
                    f.write(line)
            except OSError as e:
                logger.warning("EventStore append failed for %s: %s", session_id, e)

    def replay(self, session_id: str) -> list[dict]:
        """Replay all events for a session, returning a list of raw event dicts.

        Returns an empty list if the events file does not exist or is corrupt.
        """
        path = self._events_file(session_id)
        if not path.exists():
            return []
        events: list[dict] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("EventStore: skipping corrupt line in %s", path.name)
        except OSError as e:
            logger.warning("EventStore replay failed for %s: %s", session_id, e)
            return []
        return events

    def replay_messages(self, session_id: str) -> list[dict]:
        """Replay events and reconstruct a flat message list suitable for
        ``_load_history_as_llm_messages``.

        Events are aggregated into user/agent pairs. Each ``user_message``
        event starts a new turn. ``chunk`` events are accumulated into the
        agent's final text. ``done`` events carry the aggregated ``final_text``
        and ``parts``.
        """
        events = self.replay(session_id)
        if not events:
            return []

        messages: list[dict] = []
        current_user: dict | None = None
        current_agent_text: str = ""
        current_agent_parts: list | None = None
        current_agent_mode: str = ""

        for evt in events:
            etype = evt["type"]
            edata = evt.get("data", {})

            if etype == "user_message":
                # Flush previous turn
                if current_user is not None:
                    messages.append(current_user)
                    agent_record = {"role": "agent", "text": current_agent_text, "mode": current_agent_mode}
                    if current_agent_parts is not None:
                        agent_record["parts"] = current_agent_parts
                        agent_record["user_text"] = current_user.get("text", "")
                        agent_record["final_text"] = current_agent_text
                    messages.append(agent_record)
                # Start new turn
                current_user = {
                    "role": "user",
                    "text": edata.get("text", ""),
                    "ts": evt.get("ts", ""),
                    "mode": edata.get("mode", ""),
                }
                current_agent_text = ""
                current_agent_parts = None
                current_agent_mode = edata.get("mode", "")

            elif etype == "chunk":
                current_agent_text += edata.get("text", "")

            elif etype == "done":
                current_agent_text = edata.get("message", "") or current_agent_text
                current_agent_parts = edata.get("parts")

        # Flush last turn
        if current_user is not None:
            messages.append(current_user)
            agent_record = {"role": "agent", "text": current_agent_text, "mode": current_agent_mode}
            if current_agent_parts is not None:
                agent_record["parts"] = current_agent_parts
                agent_record["user_text"] = current_user.get("text", "")
                agent_record["final_text"] = current_agent_text
            messages.append(agent_record)

        return messages

    def has_events(self, session_id: str) -> bool:
        """Check if the events file exists for this session."""
        return self._events_file(session_id).exists()

    def truncate(self, session_id: str) -> None:
        """Delete the events file for a session.

        Called when the frontend explicitly saves messages (e.g. after
        revert or edit), making the JSON store the canonical source.
        """
        path = self._events_file(session_id)
        if path.exists():
            try:
                path.unlink()
            except OSError as e:
                logger.warning("EventStore truncate failed for %s: %s", session_id, e)


# Module-level singleton
event_store = EventStore()