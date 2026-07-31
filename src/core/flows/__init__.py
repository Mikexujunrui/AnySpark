"""Domain result flows — decoupled handlers for special tool result types.

Each flow handles one ``result["type"]`` and returns a ``FlowOutcome``:

    (events, result_str, chapter_updated, terminal)

``events`` are yielded by the caller before the unified tail handling
(message append / chapter_updated event / terminal chunk). The caller
(``agent_loop._process_tool_result``) no longer knows any domain logic —
it just dispatches by result type.

Adding a new interaction type = adding one entry to ``RESULT_FLOWS``,
no edits to the loop.
"""

from collections.abc import Awaitable, Callable

from core.loop_event import LoopEvent

from .engine_signal import flow_autopilot_plan, flow_task_list
from .user_interaction import flow_ask_user, flow_plot_cards
from .work_product import flow_patch_result, flow_review_result, flow_writing_result

FlowOutcome = tuple[list[LoopEvent], str, bool, str | None]
FlowHandler = Callable[[dict, str], Awaitable[FlowOutcome]]

# ── Dispatch table: result type → flow handler ──
# The single place where a result type is bound to its handler.
RESULT_FLOWS: dict[str, FlowHandler] = {
    "plot_cards": flow_plot_cards,
    "autopilot_plan": flow_autopilot_plan,
    "writing_result": flow_writing_result,
    "task_list": flow_task_list,
    "patch_result": flow_patch_result,
    "review_result": flow_review_result,
    "question": flow_ask_user,
}

__all__ = ["RESULT_FLOWS", "FlowOutcome", "FlowHandler", "LoopEvent"]
