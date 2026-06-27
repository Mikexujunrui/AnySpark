# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""AgentContext — immutable execution context threaded through the tool call chain.

Created once per agent loop run in ``run_agent_loop` and passed to
``execute_tool_streaming`` / ``execute_tool``. Replaces the ad-hoc tuple of
``(book_id, msg, session_id, mode, agent_type)`` previously threaded through
multiple executor helper signatures.

Adding new execution-context fields here is safe; callers read what they
need without forcing signature churn on helper functions.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentContext:
    """Immutable snapshot of the agent's execution context.

    Attributes:
        mode: Current agent mode — ``"write"`` (full toolset) or ``"plan"``
            (read-only). Governs which sub-agent types can be spawned
            and which tools are exposed.
        book_id: Owning book/project ID. Passed to knowledge store,
            json_store, and most tool implementations.
        session_id: Current session identifier. Sub-agents get
            ``f"sub_{parent_session_id}"`` to mark them as nested.
        agent_type: Active agent type (e.g. ``"write"``, ``"plan"``,
            ``"general"``). Drives toolset selection via
            ``resolve_tools_for_agent``.
        user_message: Original user message for this agent turn. Used by
            tools that need the full user intent (``task``, ``delegate_writing``).
        extra: Open slot for future context data without signature churn.
    """
    mode: str = "write"
    book_id: str = ""
    session_id: str = ""
    agent_type: str = "write"
    user_message: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def is_subagent(self) -> bool:
        """True when this agent was spawned by a parent agent (not user-driven)."""
        return self.session_id.startswith("sub_")

    @property
    def is_plan_mode(self) -> bool:
        """True when running in plan (read-only) mode."""
        return self.mode == "plan" or self.agent_type == "plan"


# Sentinel for "no context provided" — used by legacy call sites that
# haven't been updated yet. Helpers accept ``None`` and fall back to
# legacy signature.
NO_CONTEXT: AgentContext | None = None
