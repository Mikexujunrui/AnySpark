"""Structured Part system for conversation history.

Replaces the flat ``{role, text}`` persistence with a structured record of
*what actually happened* in each agent turn: which tools were called (with
arguments), what they returned, which chapters changed, the model's visible
reply, and (when the provider emits it) the reasoning chain.

Design notes
------------
* **Reasoning is captured but NOT injected back into LLM context.** For a
  writing assistant the model's *explicit* creative rationale (surfaced in its
  visible output) matters more than internal chain-of-thought tokens. Keeping
  reasoning out of the replayed messages saves tokens and avoids the model
  anchoring on its own past deliberation. It is still persisted so a curious
  author can expand the thinking trace in the UI.
* **Chapter diffs are metadata parts**, not sent to the LLM (the tool result
  already conveyed the outcome). They exist so the UI can render
  "📄 第3章 已修改 v2→v3" cards and the author can track creative progress at
  a glance without re-querying chapter history.
* **Backward compatible**: legacy messages lacking ``parts`` load as minimal
  ``Turn`` objects so old sessions keep working.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── Part types ───────────────────────────────────────────────────────────────


@dataclass
class _Part:
    """Base. Subclasses set ``type`` via default."""

    type: str = ""

    def to_dict(self) -> dict:
        d = {"type": self.type}
        for k, v in self.__dict__.items():
            if k == "type":
                continue
            d[k] = v
        return d


@dataclass
class TextPart(_Part):
    """A chunk of visible text the model emitted before/while calling tools."""

    type: str = "text"
    text: str = ""


@dataclass
class ToolCallPart(_Part):
    """A tool the model invoked. Mirrors the OpenAI tool_calls shape."""

    type: str = "tool_call"
    tool_call_id: str = ""
    name: str = ""
    arguments: str = ""  # raw JSON string, as the model produced it


@dataclass
class ToolResultPart(_Part):
    """The stringified result returned by a tool call."""

    type: str = "tool_result"
    tool_call_id: str = ""
    result: str = ""  # string content appended to messages as role:tool
    result_type: str = ""  # semantic tag: "writing_result", "patch_result", "plot_cards", ...
    tool_name: str = ""  # denormalised for UI display without a join


@dataclass
class ChapterDiffPart(_Part):
    """Metadata: a chapter was created/edited/patched/deleted this turn.

    Not sent to the LLM (the tool result already carried the outcome). Exists
    so the UI can surface creative progress cards.
    """

    type: str = "chapter_diff"
    chapter_id: str = ""
    chapter_title: str = ""
    operation: str = ""  # created / edited / patched / deleted / reverted / imported
    version: str = ""  # new version id
    prev_version: str = ""
    word_count: int = 0
    patch_count: int = 0  # number of patch ops applied (patch_chapter only)


@dataclass
class ReasoningPart(_Part):
    """The model's internal chain-of-thought (DeepSeek ``reasoning_content``).

    Persisted for optional UI viewing but deliberately excluded from the
    messages replayed to the LLM (see ``Turn.to_llm_messages``).
    """

    type: str = "reasoning"
    text: str = ""


Part = TextPart | ToolCallPart | ToolResultPart | ChapterDiffPart | ReasoningPart

_PART_CLASSES = {
    "text": TextPart,
    "tool_call": ToolCallPart,
    "tool_result": ToolResultPart,
    "chapter_diff": ChapterDiffPart,
    "reasoning": ReasoningPart,
}


def part_from_dict(d: dict) -> Part:
    cls = _PART_CLASSES.get(d.get("type", ""), TextPart)
    return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ── Turn: one complete agent turn ────────────────────────────────────────────


@dataclass
class Turn:
    """Everything that happened in one agent invocation.

    A turn = user input + an ordered list of Parts (tool calls, results,
    chapter diffs, reasoning, text chunks) + the agent's final visible reply.
    Persisted as one element of the session's message list.
    """

    user_text: str = ""
    mode: str = ""
    parts: list[Part] = field(default_factory=list)
    final_text: str = ""
    timestamp: str = ""
    # Optional: ID for referencing this turn (e.g. revert-to-here).
    turn_id: str = ""

    # ── serialization ──

    def to_dict(self) -> dict:
        return {
            "role": "agent",  # keep role for legacy readers
            "text": self.final_text,  # legacy field: final visible reply
            "mode": self.mode,
            "ts": self.timestamp,
            "parts": [p.to_dict() for p in self.parts],
            "user_text": self.user_text,
            "final_text": self.final_text,
            "turn_id": self.turn_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Turn:
        """Reconstruct a Turn from a persisted dict.

        Falls back gracefully for legacy messages that only have ``role`` and
        ``text`` (no ``parts``): such a record becomes a Turn with an empty
        parts list and ``final_text`` = the legacy text.
        """
        raw_parts = d.get("parts") or []
        parts = [part_from_dict(p) for p in raw_parts if isinstance(p, dict)]
        return cls(
            user_text=d.get("user_text", ""),
            mode=d.get("mode", ""),
            parts=parts,
            final_text=d.get("final_text") or d.get("text", ""),
            timestamp=d.get("ts", ""),
            turn_id=d.get("turn_id", ""),
        )

    # ── reconstruction to flat LLM messages ──

    def to_llm_messages(self) -> list[dict]:
        """Rebuild the flat OpenAI-format messages for THIS turn.

        Ordering follows the agent loop's actual flow:
        ``user`` → (``assistant`` with tool_calls / text) → ``tool`` results
        → final ``assistant`` reply.

        Reasoning parts are deliberately omitted — see module docstring.
        Chapter-diff parts are metadata and also omitted (the tool result
        already carried the information to the LLM).
        """
        msgs: list[dict] = []
        if self.user_text:
            marker = f"[模式: {self.mode}] " if self.mode else ""
            msgs.append({"role": "user", "content": marker + self.user_text})

        # Group consecutive tool_call + their tool_result parts. The agent loop
        # appends them in execution order, so a simple pass preserving order
        # reconstructs the correct sequence.
        pending_tool_calls: list[dict] = []
        pending_text: str = ""

        def _flush_assistant():
            nonlocal pending_tool_calls, pending_text
            if not pending_tool_calls and not pending_text:
                return
            msg = {"role": "assistant"}
            if pending_text:
                msg["content"] = pending_text
            if pending_tool_calls:
                msg["tool_calls"] = pending_tool_calls
            msgs.append(msg)
            pending_tool_calls = []
            pending_text = ""

        for p in self.parts:
            if isinstance(p, TextPart):
                pending_text += p.text
            elif isinstance(p, ToolCallPart):
                if pending_text:
                    _flush_assistant()
                pending_tool_calls.append(
                    {
                        "id": p.tool_call_id,
                        "type": "function",
                        "function": {"name": p.name, "arguments": p.arguments},
                    }
                )
            elif isinstance(p, ToolResultPart):
                # A tool result implies the preceding assistant tool_calls
                # message is complete; flush it first.
                if pending_tool_calls or pending_text:
                    _flush_assistant()
                msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": p.tool_call_id,
                        "content": p.result,
                    }
                )
            # ReasoningPart and ChapterDiffPart are intentionally skipped here.

        _flush_assistant()

        # Final visible reply (may be empty if the turn ended via tool flow).
        if self.final_text and self.final_text != pending_text:
            msgs.append({"role": "assistant", "content": self.final_text})
        elif self.final_text and not msgs:
            msgs.append({"role": "assistant", "content": self.final_text})

        return msgs

    # ── accessors ──

    def chapter_diffs(self) -> list[ChapterDiffPart]:
        return [p for p in self.parts if isinstance(p, ChapterDiffPart)]

    def tool_calls(self) -> list[ToolCallPart]:
        return [p for p in self.parts if isinstance(p, ToolCallPart)]

    def reasoning(self) -> str:
        return "".join(p.text for p in self.parts if isinstance(p, ReasoningPart))


# ── Helpers for loading a full session ──────────────────────────────────────


def turns_from_history(raw_messages: list[dict]) -> list[Turn]:
    """Convert a raw persisted message list into Turns.

    The store holds an interleaved list of legacy ``{role, text}`` records and
    structured ``Turn`` dicts (role=agent with ``parts``). We pair each user
    record with the following agent record/Turn.

    For legacy rows without ``parts`` we synthesise a minimal Turn so the rest
    of the system only ever deals with ``Turn`` objects.
    """
    turns: list[Turn] = []
    i = 0
    n = len(raw_messages)
    while i < n:
        m = raw_messages[i]
        role = m.get("role", "")
        if role == "user":
            user_text = m.get("text", "")
            mode = m.get("mode", "")
            ts = m.get("ts", "")
            # Look ahead for the agent reply.
            agent_turn = None
            if i + 1 < n and raw_messages[i + 1].get("role") == "agent":
                agent_rec = raw_messages[i + 1]
                if agent_rec.get("parts"):
                    agent_turn = Turn.from_dict(agent_rec)
                    agent_turn.user_text = user_text
                    if not agent_turn.mode:
                        agent_turn.mode = mode
                    agent_turn.timestamp = ts or agent_turn.timestamp
                else:
                    # Legacy: only final text.
                    agent_turn = Turn(
                        user_text=user_text,
                        mode=mode,
                        final_text=agent_rec.get("text", ""),
                        timestamp=agent_rec.get("ts", ts),
                    )
                i += 2
            else:
                # User message with no agent reply yet (in-flight).
                agent_turn = Turn(user_text=user_text, mode=mode, timestamp=ts)
                i += 1
            turns.append(agent_turn)
        elif role == "agent":
            # Orphan agent record (shouldn't normally happen); record as-is.
            t = Turn.from_dict(m) if m.get("parts") else Turn(final_text=m.get("text", ""), timestamp=m.get("ts", ""))
            turns.append(t)
            i += 1
        else:
            i += 1
    return turns


def turns_to_llm_messages(turns: list[Turn]) -> list[dict]:
    """Flatten an ordered list of Turns into the OpenAI message format.

    Reasoning is excluded (see module docstring). This is what gets sent to
    the LLM when loading history.
    """
    msgs: list[dict] = []
    for t in turns:
        msgs.extend(t.to_llm_messages())
    return msgs
