"""Simulation Store — JSONL append-only 事件流存储.

采用 append-only JSONL 事件流模型，参照 Nova 的 StoryEventEnvelope 设计。
每个推演会话对应一个 JSONL 文件，每行一个 JSON 事件。

事件类型：
    - meta: 会话元信息（含 branches 索引）
    - turn: 回合事件（user+narrative+thinking）
    - state_delta: 结构化状态变化
    - hot_choices: 快捷选项
    - branch: 分支创建
"""

import json as _json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..graph_store import GraphStore

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"

# ── Event types ──

EVENT_TYPE_META = "meta"
EVENT_TYPE_TURN = "turn"
EVENT_TYPE_STATE_DELTA = "state_delta"
EVENT_TYPE_HOT_CHOICES = "hot_choices"
EVENT_TYPE_BRANCH = "branch"

SCHEMA_VERSION = 1


@dataclass
class StateOp:
    """结构化状态操作."""

    op: str  # "set" | "merge" | "push" | "pull" | "inc" | "unset"
    path: str
    value: Any = None

    def to_dict(self) -> dict:
        return {"op": self.op, "path": self.path, "value": self.value}

    @classmethod
    def from_dict(cls, d: dict) -> "StateOp":
        return cls(op=d.get("op", "set"), path=d.get("path", ""), value=d.get("value"))


@dataclass
class TurnEvent:
    """结构化回合事件."""

    v: int = SCHEMA_VERSION
    type: str = EVENT_TYPE_TURN
    id: str = ""
    parent_id: str | None = None
    branch_id: str = ""
    ts: str = ""
    user: str = ""
    narrative: str = ""
    thinking: str = ""
    state_delta: list | None = None
    state_status: str = "pending"  # "pending" | "ready" | "failed"
    hot_choices: list | None = None
    display_events: list | None = None
    turn_number: int = 0

    def to_dict(self) -> dict:
        result = asdict(self)
        if self.state_delta is None:
            del result["state_delta"]
        if self.hot_choices is None:
            del result["hot_choices"]
        if self.display_events is None:
            del result["display_events"]
        if not self.thinking:
            del result["thinking"]
        return result

    @classmethod
    def from_dict(cls, d: dict) -> "TurnEvent":
        return cls(
            v=d.get("v", SCHEMA_VERSION),
            type=d.get("type", EVENT_TYPE_TURN),
            id=d.get("id", ""),
            parent_id=d.get("parent_id"),
            branch_id=d.get("branch_id", ""),
            ts=d.get("ts", ""),
            user=d.get("user", ""),
            narrative=d.get("narrative", ""),
            thinking=d.get("thinking", ""),
            state_delta=d.get("state_delta"),
            state_status=d.get("state_status", "pending"),
            hot_choices=d.get("hot_choices"),
            display_events=d.get("display_events"),
            turn_number=d.get("turn_number", 0),
        )


# ── State operation utilities ──


def _get_path(root: dict, path: str) -> Any:
    """Navigate dotted path into nested dict."""
    parts = path.split(".")
    current = root
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _set_path(root: dict, path: str, value: Any):
    """Set value at dotted path in nested dict."""
    parts = path.split(".")
    current = root
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def _unset_path(root: dict, path: str):
    """Delete key at dotted path."""
    parts = path.split(".")
    current = root
    for part in parts[:-1]:
        if not isinstance(current, dict):
            return
        current = current.get(part, {})
    if isinstance(current, dict):
        current.pop(parts[-1], None)


def apply_state_op(state: dict, op: StateOp):
    """Apply a single state operation to the state dict."""
    if op.op == "set":
        _set_path(state, op.path, op.value)
    elif op.op == "merge":
        current = _get_path(state, op.path)
        if not isinstance(current, dict):
            current = {}
        if isinstance(op.value, dict):
            current.update(op.value)
        _set_path(state, op.path, current)
    elif op.op == "push":
        current = _get_path(state, op.path)
        if not isinstance(current, list):
            current = []
        current.append(op.value)
        _set_path(state, op.path, current)
    elif op.op == "pull":
        current = _get_path(state, op.path)
        if isinstance(current, list):
            _set_path(state, op.path, [x for x in current if x != op.value])
    elif op.op == "inc":
        current = _get_path(state, op.path)
        if not isinstance(current, (int, float)):
            current = 0
        by = op.value if isinstance(op.value, (int, float)) else 1
        _set_path(state, op.path, current + by)
    elif op.op == "unset":
        _unset_path(state, op.path)


def apply_state_ops(state: dict, ops: list) -> dict:
    """Apply multiple state operations, returning the updated state."""
    for op_dict in ops:
        if isinstance(op_dict, dict):
            op = StateOp.from_dict(op_dict)
        else:
            op = op_dict
        apply_state_op(state, op)
    return state


# ── SimulationStore ──


class SimulationStore:
    """推演会话存储 — JSONL append-only 事件流.

    不再使用 Neo4j 存储推演数据。每个会话一个 JSONL 文件，
    append-only 写入，读取时顺序扫描重建状态。
    """

    def __init__(self, book_id: str):
        self.book_id = book_id
        self.graph = GraphStore(project_id=book_id)  # 保留用于图谱查询
        self._store_dir = DATA_DIR / "simulations" / "jsonl"
        self._store_dir.mkdir(parents=True, exist_ok=True)
        self._choices_cache: dict[str, list[dict]] = {}  # event_id -> choices
        self._char_responses_cache: dict[str, list[dict]] = {}  # event_id -> responses

    # ── JSONL path helpers ──

    def _jsonl_path(self, sim_id: str) -> Path:
        return self._store_dir / f"{sim_id}.jsonl"

    def _sim_id_from_path(self, path: Path) -> str:
        return path.stem

    # ── JSONL I/O ──

    def _append_event(self, sim_id: str, event: dict):
        """Append one event as a JSONL line."""
        path = self._jsonl_path(sim_id)
        event["ts"] = event.get("ts") or datetime.now(UTC).isoformat()
        line = _json.dumps(event, ensure_ascii=False, default=str)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _read_events(self, sim_id: str) -> list[dict]:
        """Read all events for a session in order."""
        path = self._jsonl_path(sim_id)
        if not path.exists():
            return []
        events = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(_json.loads(line))
                    except _json.JSONDecodeError:
                        logger.warning("Skipping invalid JSONL line in %s: %s", sim_id, line[:80])
        return events

    # ── Session CRUD ──

    def create_session(
        self,
        mode: str,
        setting: str = "",
        pov_character_id: str | None = None,
        involved_character_ids: list[str] | None = None,
        condition: str | None = None,
        style_name: str | None = None,
        reference_book_ids: list[str] | None = None,
    ) -> dict:
        """Create a new simulation session.

        Writes a meta event as the first line of the JSONL file.
        """
        sim_id = f"sim_{uuid.uuid4().hex[:16]}"
        now = datetime.now(UTC).isoformat()
        involved_character_ids = involved_character_ids or []

        session = {
            "id": sim_id,
            "book_id": self.book_id,
            "mode": mode,
            "setting": setting,
            "pov_character_id": pov_character_id,
            "involved_character_ids": involved_character_ids,
            "condition": condition,
            "style_name": style_name,
            "reference_book_ids": reference_book_ids or [],
            "status": "active",
            "turn_count": 0,
            "summary": None,
            "created_at": now,
            "updated_at": now,
        }

        # Write meta event
        meta_event = {
            "v": SCHEMA_VERSION,
            "type": EVENT_TYPE_META,
            "id": sim_id,
            "ts": now,
            "book_id": self.book_id,
            "mode": mode,
            "setting": setting,
            "pov_character_id": pov_character_id,
            "involved_character_ids": involved_character_ids,
            "condition": condition,
            "style_name": style_name,
            "reference_book_ids": reference_book_ids or [],
            "status": "active",
            "turn_count": 0,
            "branches": {sim_id: {"id": sim_id, "title": "主线", "created_at": now, "is_main": True}},
            "current_branch": sim_id,
        }
        self._append_event(sim_id, meta_event)

        return session

    def get_session(self, sim_id: str) -> dict | None:
        """Get session metadata from the meta event."""
        events = self._read_events(sim_id)
        if not events:
            return None
        meta = events[0] if events[0].get("type") == EVENT_TYPE_META else None
        if not meta:
            return None
        # Reconstruct current session state from latest meta
        latest_meta = meta
        for ev in events[1:]:
            if ev.get("type") == EVENT_TYPE_META:
                latest_meta = ev
        return {
            "id": sim_id,
            "book_id": latest_meta.get("book_id", self.book_id),
            "mode": latest_meta.get("mode", "character_pov"),
            "setting": latest_meta.get("setting", ""),
            "pov_character_id": latest_meta.get("pov_character_id"),
            "involved_character_ids": latest_meta.get("involved_character_ids", []),
            "condition": latest_meta.get("condition"),
            "style_name": latest_meta.get("style_name"),
            "reference_book_ids": latest_meta.get("reference_book_ids", []),
            "status": latest_meta.get("status", "active"),
            "turn_count": latest_meta.get("turn_count", 0),
            "summary": latest_meta.get("summary"),
            "current_branch": latest_meta.get("current_branch", sim_id),
            "branches": latest_meta.get("branches", {}),
            "created_at": meta.get("ts", ""),
            "updated_at": latest_meta.get("ts", ""),
        }

    def list_sessions(self, status: str | None = None) -> list[dict]:
        """List all sessions by scanning JSONL files."""
        sessions = []
        for f in sorted(self._store_dir.glob("sim_*.jsonl"), reverse=True):
            try:
                # Read ALL events to find the latest meta event
                all_events = []
                with open(f, encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            try:
                                all_events.append(_json.loads(line))
                            except _json.JSONDecodeError:
                                continue

                if not all_events:
                    continue

                # Find latest meta event
                meta = None
                for ev in all_events:
                    if ev.get("type") == EVENT_TYPE_META:
                        meta = ev

                if meta is None:
                    # Fall back to first event
                    meta = all_events[0]

                if meta.get("book_id") != self.book_id:
                    continue
                if status and meta.get("status") != status:
                    continue

                sessions.append(
                    {
                        "id": self._sim_id_from_path(f),
                        "book_id": meta.get("book_id"),
                        "mode": meta.get("mode", "character_pov"),
                        "setting": meta.get("setting", ""),
                        "status": meta.get("status", "active"),
                        "turn_count": meta.get("turn_count", 0),
                        "created_at": meta.get("ts", ""),
                        "current_branch": meta.get("current_branch", ""),
                    }
                )
            except Exception:
                continue
        return sessions

    def update_session(self, sim_id: str, **kwargs) -> dict | None:
        """Update session metadata by appending a new meta event."""
        allowed = {"status", "summary", "turn_count", "setting", "condition", "current_branch"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return self.get_session(sim_id)

        # Read existing events, find latest meta, merge
        events = self._read_events(sim_id)
        if not events:
            return None

        latest_meta = events[0]
        for ev in events:
            if ev.get("type") == EVENT_TYPE_META:
                latest_meta = ev

        merged = {**latest_meta, **updates, "ts": datetime.now(UTC).isoformat()}
        self._append_event(sim_id, merged)
        return self.get_session(sim_id)

    def delete_session(self, sim_id: str) -> bool:
        """Delete a session file."""
        path = self._jsonl_path(sim_id)
        if path.exists():
            path.unlink()
        return True

    # ── Turn Events ──

    def append_turn(self, sim_id: str, turn: TurnEvent) -> dict:
        """Append a turn event to the session."""
        if not turn.id:
            turn.id = str(uuid.uuid4())
        if not turn.ts:
            turn.ts = datetime.now(UTC).isoformat()
        event = turn.to_dict()
        self._append_event(sim_id, event)
        # Update turn_count in meta
        self.update_session(sim_id, turn_count=turn.turn_number + 1)
        return event

    def get_turns(self, sim_id: str, branch_id: str | None = None) -> list[dict]:
        """Get all turn events, optionally filtered by branch."""
        events = self._read_events(sim_id)
        turns = [ev for ev in events if ev.get("type") == EVENT_TYPE_TURN]
        if branch_id:
            turns = [t for t in turns if t.get("branch_id") == branch_id]
        turns.sort(key=lambda t: (t.get("turn_number", 0), t.get("ts", "")))
        return turns

    def get_latest_turn(self, sim_id: str) -> dict | None:
        """Get the most recent turn event."""
        turns = self.get_turns(sim_id)
        return turns[-1] if turns else None

    # ── Choices (旧接口兼容) ──

    def add_choice(
        self, event_id: str, sim_id: str, text: str, description: str = "", choice_type: str = "action"
    ) -> dict:
        """Store a choice option. Legacy compatibility — stores in memory + JSONL."""
        choice = {
            "id": str(uuid.uuid4()),
            "event_id": event_id,
            "simulation_id": sim_id,
            "text": text,
            "description": description,
            "choice_type": choice_type,
            "selected": False,
            "created_at": datetime.now(UTC).isoformat(),
        }
        if event_id not in self._choices_cache:
            self._choices_cache[event_id] = []
        self._choices_cache[event_id].append(choice)
        return choice

    def append_choices(self, sim_id: str, event_id: str, choices: list[dict]) -> dict:
        """Persist choices for a turn event to JSONL."""
        event = {
            "v": SCHEMA_VERSION,
            "type": "choices",
            "id": str(uuid.uuid4()),
            "event_id": event_id,
            "ts": datetime.now(UTC).isoformat(),
            "choices": choices,
        }
        self._append_event(sim_id, event)
        return event

    def get_latest_choices(self, sim_id: str) -> list[dict]:
        """Get the most recent choices for a session from JSONL."""
        events = self._read_events(sim_id)
        for ev in reversed(events):
            if ev.get("type") == "choices":
                return ev.get("choices", [])
        return []

    def get_choices(self, event_id: str) -> list[dict]:
        """Get choices — reads from in-memory cache."""
        return self._choices_cache.get(event_id, [])

    def mark_choice_selected(self, choice_id: str, sim_id: str | None = None) -> bool:
        """Mark a choice as selected by updating the in-memory cache."""
        for event_id, choices in self._choices_cache.items():
            for c in choices:
                if c["id"] == choice_id:
                    c["selected"] = True
                    return True
        return True

    # ── Character Responses (旧接口兼容) ──

    def add_character_response(
        self, sim_id: str, event_id: str, character_id: str, response_text: str, internal_thoughts: str = ""
    ) -> dict:
        response = {
            "id": str(uuid.uuid4()),
            "simulation_id": sim_id,
            "event_id": event_id,
            "character_id": character_id,
            "response_text": response_text,
            "internal_thoughts": internal_thoughts,
            "created_at": datetime.now(UTC).isoformat(),
        }
        if event_id not in self._char_responses_cache:
            self._char_responses_cache[event_id] = []
        self._char_responses_cache[event_id].append(response)
        return response

    def get_character_responses(self, event_id: str) -> list[dict]:
        return self._char_responses_cache.get(event_id, [])

    # ── State Management ──

    def append_state_delta(self, sim_id: str, parent_id: str, ops: list) -> dict:
        """Append a state delta event."""
        event = {
            "v": SCHEMA_VERSION,
            "type": EVENT_TYPE_STATE_DELTA,
            "id": str(uuid.uuid4()),
            "parent_id": parent_id,
            "ts": datetime.now(UTC).isoformat(),
            "ops": [o.to_dict() if isinstance(o, StateOp) else o for o in ops],
        }
        self._append_event(sim_id, event)
        return event

    def get_latest_state(self, sim_id: str) -> dict:
        """Reconstruct state by applying all state deltas."""
        state = {
            "on_stage": [],
            "scene": "",
            "location": "",
            "time": "",
            "characters": {},
            "threads": [],
            "inventory": [],
        }
        events = self._read_events(sim_id)
        for ev in events:
            if ev.get("type") == EVENT_TYPE_STATE_DELTA:
                ops = ev.get("ops", [])
                apply_state_ops(state, ops)
            elif ev.get("type") == EVENT_TYPE_TURN:
                delta = ev.get("state_delta")
                if delta:
                    apply_state_ops(state, delta)
        return state

    # ── Hot Choices ──

    def append_hot_choices(self, sim_id: str, parent_id: str, choices: list[str]) -> dict:
        """Append a hot choices event."""
        event = {
            "v": SCHEMA_VERSION,
            "type": EVENT_TYPE_HOT_CHOICES,
            "id": str(uuid.uuid4()),
            "parent_id": parent_id,
            "ts": datetime.now(UTC).isoformat(),
            "choices": choices,
        }
        self._append_event(sim_id, event)
        return event

    def get_hot_choices(self, sim_id: str, parent_id: str | None = None) -> list[str]:
        """Get the latest hot choices, optionally for a specific parent."""
        events = self._read_events(sim_id)
        choices_events = [ev for ev in events if ev.get("type") == EVENT_TYPE_HOT_CHOICES]
        if parent_id:
            choices_events = [ev for ev in choices_events if ev.get("parent_id") == parent_id]
        if not choices_events:
            return []
        return choices_events[-1].get("choices", [])

    # ── Branch Support ──

    def create_branch(self, sim_id: str, parent_event_id: str, title: str = "") -> dict:
        """Create a new branch from a parent event."""
        session = self.get_session(sim_id)
        if not session:
            return {"error": "Session not found"}

        branch_id = f"br_{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC).isoformat()

        # Record branch event
        branch_event = {
            "v": SCHEMA_VERSION,
            "type": EVENT_TYPE_BRANCH,
            "id": branch_id,
            "parent_id": parent_event_id,
            "branch_id": branch_id,
            "ts": now,
            "title": title or f"分支 {branch_id[:8]}",
            "from_branch": session.get("current_branch", sim_id),
        }
        self._append_event(sim_id, branch_event)

        # Update meta with new branch info
        branches = dict(session.get("branches", {}))
        branches[branch_id] = {
            "id": branch_id,
            "title": title or f"分支 {branch_id[:8]}",
            "created_at": now,
            "parent_event_id": parent_event_id,
            "from_branch": session.get("current_branch", sim_id),
            "is_main": False,
        }
        self.update_session(sim_id, branches=branches)

        return {
            "id": branch_id,
            "title": title or f"分支 {branch_id[:8]}",
            "parent_event_id": parent_event_id,
            "created_at": now,
        }

    def switch_branch(self, sim_id: str, branch_id: str) -> dict | None:
        """Switch the current branch."""
        session = self.get_session(sim_id)
        if not session:
            return None
        branches = session.get("branches", {})
        if branch_id not in branches and branch_id != sim_id:
            return None
        return self.update_session(sim_id, current_branch=branch_id)

    def list_branches(self, sim_id: str) -> list[dict]:
        """List all branches for a session."""
        session = self.get_session(sim_id)
        if not session:
            return []
        branches = session.get("branches", {})
        current = session.get("current_branch", sim_id)
        return [
            {
                "id": bid,
                "title": info.get("title", bid),
                "created_at": info.get("created_at", ""),
                "parent_event_id": info.get("parent_event_id"),
                "from_branch": info.get("from_branch"),
                "is_main": info.get("is_main", False),
                "current": bid == current,
            }
            for bid, info in branches.items()
        ]

    # ── Promote to Timeline ──

    def promote_to_timeline(self, event_id: str, timeline_data: dict) -> dict:
        """Promote a turn event to a canonical Timeline node via Neo4j."""
        tl_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        self.graph._run(
            """
            CREATE (t:Timeline {
                id: $tid, project_id: $pid,
                content: $content,
                time_order: $time_order,
                chapter_index: $ch_idx,
                created_at: $now,
                promoted_from: $sim_event_id
            })
            """,
            {
                "tid": tl_id,
                "pid": self.book_id,
                "content": timeline_data.get("content", ""),
                "time_order": timeline_data.get("time_order", 0),
                "ch_idx": timeline_data.get("chapter_index"),
                "now": now,
                "sim_event_id": event_id,
            },
        )
        return {"timeline_id": tl_id, "promoted_from": event_id}

    # ── Event retrieval (legacy compatibility) ──

    def add_event(
        self,
        sim_id: str,
        content: str,
        event_type: str = "narrative",
        turn_number: int = 0,
        character_id: str | None = None,
    ) -> dict:
        """Legacy compatibility — delegates to append_turn."""
        turn = TurnEvent(
            id=str(uuid.uuid4()),
            branch_id=sim_id,
            ts=datetime.now(UTC).isoformat(),
            narrative=content,
            turn_number=turn_number,
        )
        self.append_turn(sim_id, turn)
        return {
            "id": turn.id,
            "simulation_id": sim_id,
            "content": content,
            "event_type": event_type,
            "turn_number": turn_number,
            "character_id": character_id,
            "created_at": turn.ts,
        }

    def get_events(self, sim_id: str) -> list[dict]:
        """Get all events (legacy compat — returns turn narratives with content key)."""
        turns = self.get_turns(sim_id)
        result = []
        for t in turns:
            result.append(
                {
                    "id": t.get("id", ""),
                    "simulation_id": sim_id,
                    "content": t.get("narrative", ""),
                    "event_type": "narrative",
                    "turn_number": t.get("turn_number", 0),
                    "character_id": None,
                    "created_at": t.get("ts", ""),
                }
            )
        return result

    def get_latest_event(self, sim_id: str) -> dict | None:
        latest = self.get_latest_turn(sim_id)
        if not latest:
            return None
        return {
            "id": latest.get("id", ""),
            "simulation_id": sim_id,
            "content": latest.get("narrative", ""),
            "event_type": "narrative",
            "turn_number": latest.get("turn_number", 0),
            "character_id": None,
            "created_at": latest.get("ts", ""),
        }

    def link_event_to_character(self, event_id: str, character_id: str, role: str = "pov"):
        pass

    def link_event_to_foreshadow(self, event_id: str, fore_id: str, action: str = "advances"):
        pass

    # ── Memory Compaction Helper ──

    def build_memory_context(
        self, sim_id: str, recent_limit: int = 6, summary_max_chars: int = 2000
    ) -> tuple[str, list[dict]]:
        """Build compact memory: recent turns full + earlier turns summary.

        Returns:
            (summary_text, recent_turns)
        """
        turns = self.get_turns(sim_id)
        if len(turns) <= recent_limit:
            return "", turns

        split = len(turns) - recent_limit
        previous = turns[:split]
        recent = turns[split:]

        summary_parts = ["以下为较早回合的压缩记忆（完整原文不再进入本轮上下文）:"]
        for ev in previous:
            tn = ev.get("turn_number", "?")
            content = (ev.get("narrative") or ev.get("content", ""))[:120]
            summary_parts.append(f"- 第{tn}回合: {content}")

        return "\n".join(summary_parts)[:summary_max_chars], recent
