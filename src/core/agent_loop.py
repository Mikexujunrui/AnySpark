# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Agent loop — autonomous while-true loop for tool-use iteration.

Decomposed into stage helpers built around :class:`LoopState` (see
``loop_state.py``). ``_loop_inner`` remains the single async generator yielding
:class:`LoopEvent` objects, but each phase — context preparation, compaction,
sitrep, LLM call, terminal handling and tool handling — lives in its own
function so they can be tested and reasoned about independently.
"""

import asyncio
import json
import logging
import traceback
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

from .agent_context import AgentContext
from .compaction import handle_context_overflow, needs_compaction, prune_stale_tool_results
from .config import config
from .hallucination import detect_hallucination
from .llm_client import (
    LLMResponse,
    ToolCall,
    chat_with_tools_stream_async,
    model_for,
)
from .loop_state import LoopState
from .parts import ChapterDiffPart, ReasoningPart, TextPart, ToolCallPart, ToolResultPart
from .permissions import permission_manager
from .question import manager as question_manager
from .retry import calculate_delay, is_context_overflow, is_retryable
from .session_state import BusyError, CancelledError, RunHandle, run_state
from .system_prompt import build_dynamic_context, build_system_prompt, resolve_tools_for_agent
from .token_counter import count_message_tokens, get_context_limit
from .tools import DoomLoopDetector, registry, truncate_tool_output, validate_tool_input

logger = logging.getLogger(__name__)

MAX_LLM_ERROR_RETRIES = 2  # Retry LLM errors before giving up

# ── Context overflow recovery ──
# When the LLM reports context overflow, we compact and retry once.
# If it still fails after compaction, we give up (the session needs a reset).
_MAX_OVERFLOW_RETRIES = 1


def _check_incomplete_task_list(book_id: str, state: LoopState) -> tuple[bool, str]:
    """Check if the active task list has incomplete items.

    The task list is treated as a multi-step state machine: if the agent
    created a task list but hasn't completed all items, terminating here is
    a premature termination. Returns (has_incomplete, description) where
    description lists pending task labels for the nudge message.
    """
    if not state.active_task_list_id or not book_id:
        return False, ""
    try:
        from data.json_store import json_store

        tl = json_store.get_task_list(book_id, state.active_task_list_id)
        items = tl.get("items", [])
        pending = [it for it in items if it.get("status") not in ("done", "skipped", "failed")]
        if pending:
            labels = ", ".join(it.get("label", "?") for it in pending[:5])
            return True, f"还有 {len(pending)} 个未完成任务: {labels}"
        return False, ""
    except Exception:
        return False, ""


# Keywords that indicate the model is describing a plan instead of executing.
# When the response contains these AND has no tool_calls, it's an empty plan.
_PLAN_KEYWORDS = ["我先", "我来", "并行", "接下来", "首先", "然后", "让我", "好的，我"]


def _looks_like_plan_without_action(text: str) -> bool:
    """Check if the response describes intentions but doesn't execute.

    Returns True when the text contains planning keywords ("我先...",
    "我来...", "并行...") suggesting the model intends to act but
    produced no tool_calls. This catches the common failure pattern where
    the model writes a plan as text instead of calling tools.
    """
    if not text or len(text) < 5:
        return False
    # Short responses are likely real answers, not plans
    if len(text) < 30:
        return False
    return any(kw in text for kw in _PLAN_KEYWORDS)


# Keywords that indicate the model's final response is a trivial acknowledgment
# rather than a meaningful summary. When the model says "完成" after running
# extract_all_chapters, the frontend trivial-filter swallows it → user sees nothing.
_TRIVIAL_DONE_PHRASES = frozenset({
    "完成", "已完成", "好的", "好", "ok", "OK", "done", "Done",
    "已处理", "处理完成", "已执行", "执行完成",
})


def _is_trivial_done(text: str) -> bool:
    """Check if the model's final text is just a trivial acknowledgment
    with no informative content about what was actually accomplished."""
    cleaned = text.strip().rstrip("。.!！\"")
    return cleaned in _TRIVIAL_DONE_PHRASES or len(cleaned) < 3


def _extract_last_tool_summary(messages: list[dict]) -> str:
    """Extract a summary of the last tool result from the message history,
    used when the model's final text is trivial but tools did real work.

    Skips trivial tool results to find the last meaningful tool output."""
    for msg in reversed(messages):
        if msg.get("role") == "tool":
            content = msg.get("content", "")
            if content and not _is_trivial_done(content):
                return content[:800]
    # Fallback: return last tool message even if trivial
    for msg in reversed(messages):
        if msg.get("role") == "tool":
            content = msg.get("content", "")
            if content:
                return content[:500]
    return ""


@dataclass
class LoopEvent:
    type: str
    data: dict = field(default_factory=dict)

    def to_sse(self) -> dict:
        return {"event": self.type, "data": json.dumps(self.data, ensure_ascii=False)}


@dataclass
class AgentConfig:
    agent_type: str = "write"
    mode: str = "write"
    book_id: str = ""
    session_id: str = ""
    max_rounds: int = 0
    soft_round_limit: int = 0
    temperature: float = 0.0
    token_budget_ratio: float = 0.0  # 0 = disabled; cap cumulative tokens at ratio × context limit
    extra_context: str = ""
    task_description: str = ""
    auto_mode_enabled: bool = True  # 机器人开关，False 时隐藏 start_autopilot
    memory_mode: str = "normal"  # "normal" | "clean_slate" | "experimental"

    def __post_init__(self):
        defaults = config.agent.per_type.get(self.agent_type, {})
        if not self.max_rounds:
            self.max_rounds = defaults.get("max_rounds", config.agent.max_rounds)
        if not self.soft_round_limit:
            self.soft_round_limit = defaults.get("soft_round_limit", config.agent.soft_round_limit)
        if not self.temperature:
            self.temperature = defaults.get("temperature", config.agent.default_temperature)
        if not self.token_budget_ratio:
            self.token_budget_ratio = config.agent.token_budget_ratio

    @property
    def task_label(self) -> str:
        defaults = config.agent.per_type.get(self.agent_type, {})
        return defaults.get("task_label", "general")


async def run_agent_loop(
    user_message: str,
    agent_config: AgentConfig,
    history_messages: list[dict] | None = None,
    handle: RunHandle | None = None,
) -> AsyncGenerator[LoopEvent, None]:

    session_id = agent_config.session_id or agent_config.book_id or "default"

    if handle is None:
        try:
            handle = await run_state.ensure_running(session_id)
        except BusyError:
            yield LoopEvent(type="error", data={"message": f"会话 {session_id} 正在处理中，请等待完成。"})
            return

    did_yield_done = False
    last_error_msg = ""
    try:
        async for event in _loop_inner(user_message, agent_config, history_messages, handle):
            if event.type == "done":
                did_yield_done = True
            elif event.type == "error":
                last_error_msg = event.data.get("message", "")
            yield event
            # Touch session timestamp to prevent stale timeout
            run_state.touch(session_id)
    except CancelledError:
        last_error_msg = "操作已取消"
        yield LoopEvent(type="cancelled", data={"message": last_error_msg})
    except asyncio.CancelledError:
        # asyncio-level cancellation (e.g. SSE client disconnect, task timeout).
        # Must be caught here — otherwise it propagates to the SSE handler and
        # the frontend gets a broken connection instead of a proper done event.
        last_error_msg = "连接已中断（超时或客户端断开）"
        yield LoopEvent(type="cancelled", data={"message": last_error_msg})
    except Exception as e:
        logger.exception(f"Agent loop error: {e}")
        last_error_msg = f"Agent 出错: {str(e)[:200]}"
        yield LoopEvent(type="error", data={"message": last_error_msg})
    finally:
        await run_state.release(session_id, handle)

    # ── Safety net: ensure every consumer receives a done event ──
    # If the loop ended without yielding done (e.g. LLM error, unexpected
    # exception, or _loop_inner returned after an error event), emit a
    # fallback done so the frontend / headless runner / CLI never silently
    # hangs waiting for a termination signal. The message carries the last
    # error so the user knows why it stopped (never a bare placeholder).
    if not did_yield_done:
        fallback = last_error_msg or "Agent 循环异常终止（未捕获到明确原因），请检查后端日志或重试。"
        yield LoopEvent(
            type="done",
            data={
                "message": fallback,
                "rounds": 0,
                "metrics": {},
            },
        )


async def _loop_inner(
    user_message: str,
    agent_config: AgentConfig,
    history_messages: list[dict] | None,
    handle: RunHandle,
) -> AsyncGenerator[LoopEvent, None]:

    messages = _prepare_initial_messages(user_message, agent_config, history_messages)
    # is_subagent: True when this agent was spawned by another agent (not by the user).
    # Sub-agents must NOT see the task tool to prevent recursive spawn chains
    # (Nesting prevention for sub-agents).
    is_subagent = agent_config.session_id.startswith("sub_")
    tool_list = resolve_tools_for_agent(agent_config.agent_type, agent_config.mode, is_subagent=is_subagent)
    # ── Auto-mode gate: start_autopilot requires the robot switch (autoModeEnabled) ──
    # Controlled by the bot-icon toggle in BookDetail. When off, the Agent
    # cannot see or use the Autopilot tool — it must use delegate_writing instead.
    if not agent_config.auto_mode_enabled:
        tool_list = [t for t in tool_list if t.get("name") != "start_autopilot"]
    doom_detector = DoomLoopDetector()

    # Token budget cap (industry-standard dual control with the round cap).
    # 0 ratio = disabled. Otherwise cap cumulative tokens at ratio × context limit.
    token_budget_limit = 0
    if agent_config.token_budget_ratio > 0:
        try:
            ctx_limit = get_context_limit(model_for("general"))
            token_budget_limit = int(ctx_limit * agent_config.token_budget_ratio)
        except Exception:
            token_budget_limit = 0

    state = LoopState(
        max_rounds=agent_config.max_rounds,
        soft_round_limit=agent_config.soft_round_limit,
        base_temperature=agent_config.temperature,
        token_budget_limit=token_budget_limit,
    )

    from .graph_store import GraphStore

    kb = GraphStore(agent_config.book_id)
    kb.init_schema()

    # Build immutable execution context once per loop run. Threaded through
    # _execute_tool_streaming / _execute_tool to the executor.
    # ``extra`` carries mutable shared state (subagent tracker) that the
    # executor mutates — agent_loop reads it back for persistence.
    context = AgentContext(
        mode=agent_config.mode,
        book_id=agent_config.book_id,
        session_id=agent_config.session_id,
        agent_type=agent_config.agent_type,
        user_message=user_message,
        extra={"metrics": state.metrics},
    )

    yield LoopEvent(
        type="start",
        data={
            "agent": agent_config.agent_type,
            "mode": agent_config.mode,
            "tools_count": len(tool_list),
        },
    )

    try:
        while not state.exhausted:
            handle.check_cancelled()
            state.advance_round()

            # ── Stage 0: proactive stale tool result pruning ──
            # Truncates old tool outputs to short previews BEFORE compaction
            # is needed. A read_chapter result of 8K tokens becomes 800 tokens
            # in the next round, preventing linear context growth.
            pruned_msgs, did_prune = prune_stale_tool_results(messages)
            if did_prune:
                messages[:] = pruned_msgs
                state.metrics.tool_prunes += 1

            # ── Stage 1: compaction ──
            async for ev in _maybe_compact(messages, agent_config, state):
                yield ev

            # ── Stage 2: periodic sitrep (state anchor) ──
            if state.round > 1 and state.round % 10 == 0:
                async for ev in _inject_sitrep(messages, agent_config, state):
                    yield ev

            # ── Stage 3.5: message-pair hygiene (defense in depth) ──
            # Ensure every assistant tool_call has a matching tool message, and
            # every tool message has a matching assistant tool_call. Catches
            # orphans from partial tool processing, compaction edge cases, or
            # cancel mid-loop. Without this the next LLM call 400s.
            _sanitize_tool_messages(messages)

            # ── Stage 4: call the LLM (streaming chunks flow straight through) ──
            response = None
            streamed_text = ""
            fatal_error = None
            async for msg_type, data in _stream_llm_with_retry(
                messages,
                tool_list,
                agent_config,
                handle,
                state,
            ):
                if msg_type == "chunk":
                    yield LoopEvent(type="chunk", data={"text": data})
                elif msg_type == "heartbeat":
                    yield LoopEvent(type="progress", data={"stage": data})
                elif msg_type == "progress":
                    yield LoopEvent(type="progress", data={"stage": data})
                elif msg_type == "error":
                    fatal_error = data
                elif msg_type == "result":
                    response, streamed_text = data

            if fatal_error is not None:
                err_msg = f"LLM 错误（已重试{MAX_LLM_ERROR_RETRIES}次）: {str(fatal_error)[:150]}"
                yield LoopEvent(type="error", data={"message": err_msg})
                state.metrics.finish_reason = "llm_error"
                # Deterministic terminal event (industry standard: every exit
                # yields done). The outer safety net is only a last resort.
                yield LoopEvent(
                    type="done",
                    data={
                        "message": err_msg,
                        "rounds": state.round,
                        "parts": [p.to_dict() for p in state.parts],
                        "metrics": _loop_metrics_dict(state.metrics),
                    },
                )
                return
            if response is None:
                err_msg = "LLM 未返回有效响应（已重试）"
                yield LoopEvent(type="error", data={"message": err_msg})
                state.metrics.finish_reason = "llm_empty"
                yield LoopEvent(
                    type="done",
                    data={
                        "message": err_msg,
                        "rounds": state.round,
                        "parts": [p.to_dict() for p in state.parts],
                        "metrics": _loop_metrics_dict(state.metrics),
                    },
                )
                return

            # ── Stage 5: writing-mode / temperature bookkeeping ──
            state.update_writing_mode(streamed_text)
            state.last_text_preview = (streamed_text or "")[:200]

            # ── Stage 5.5: token budget accounting (dual control w/ round cap) ──
            # Estimate per-round tokens: input from messages, output from the
            # streamed assistant text. Industry-standard cumulative cap.
            try:
                in_tok = count_message_tokens(messages)
                out_tok = (
                    count_message_tokens([{"role": "assistant", "content": streamed_text}]) if streamed_text else 0
                )
                state.record_token_usage(in_tok, out_tok)
            except Exception:
                pass
            if state.token_budget_exceeded:
                state.metrics.finish_reason = "token_budget_reached"
                budget_msg = (
                    f"已达 token 预算上限（累计 {state.metrics.total_tokens} tokens），"
                    f"本轮停止。共执行 {state.metrics.tool_calls} 次工具调用、"
                    f"{state.round} 轮。"
                )
                if not streamed_text:
                    yield LoopEvent(type="text", data={"content": budget_msg})
                yield LoopEvent(
                    type="done",
                    data={
                        "message": budget_msg,
                        "rounds": state.round,
                        "parts": [p.to_dict() for p in state.parts],
                        "metrics": _loop_metrics_dict(state.metrics),
                    },
                )
                return

            # ── Stage 6: terminal branch (no tool calls) ──
            if not response.tool_calls:
                # Capture reasoning + streamed text as parts before handling.
                if response.reasoning:
                    state.add_part(ReasoningPart(text=response.reasoning))
                if streamed_text:
                    state.add_part(TextPart(text=streamed_text))

                final_text = (response.content or "").strip()

                # Check 0: plan-detection — if the LLM describes a plan
                # ("我先...", "我来...", "并行...") but makes no tool_calls,
                # it's an empty plan. Nudge it to actually execute tools.
                # This is NOT a general nudge; it targets a specific failure
                # pattern where the model writes intentions instead of actions.
                if _looks_like_plan_without_action(final_text) and state.plan_nudges < 4:
                    state.plan_nudges += 1
                    messages.append({"role": "assistant", "content": final_text or "（无文本输出）"})
                    _append_user_hint(
                        messages,
                        (
                            "[系统提示] 你描述了计划但没有调用工具。"
                            "用户需要的是执行结果，不是计划描述。"
                            "请立即调用工具执行，不要再描述你打算做什么。"
                        ),
                    )
                    yield LoopEvent(type="progress", data={"stage": "检测到空计划，要求执行工具..."})
                    continue
                elif _looks_like_plan_without_action(final_text):
                    # Nudge limit exhausted — model keeps describing plans
                    # without executing. Give a clear termination signal
                    # instead of falling through to abnormal_exit.
                    state.metrics.finish_reason = "plan_exhausted"
                    done_msg = (
                        f"模型多次描述计划但未调用工具执行（已尝试 {state.plan_nudges} 次引导）。"
                        f"最后输出：{final_text[:200]}"
                    )
                    if not streamed_text:
                        yield LoopEvent(type="text", data={"content": done_msg})
                    yield LoopEvent(
                        type="done",
                        data={
                            "message": done_msg,
                            "rounds": state.round,
                            "parts": [p.to_dict() for p in state.parts],
                            "metrics": _loop_metrics_dict(state.metrics),
                        },
                    )
                    return

                # Check 1: fake_tool/fake_write hallucination — warning only,
                # never interrupts the loop. Trust the LLM; if it genuinely
                # hallucinated this will be visible in the final output.
                h = detect_hallucination(final_text) if final_text else None
                if h and h.detected:
                    state.metrics.record_hallucination(h.layer)
                    logger.warning("Hallucination detected (%s) in terminal text, not interrupting", h.layer)

                # Check 2: Task list completeness — warning only, never
                # interrupts. The model decides when it's done; we just note
                # incomplete tasks in the final message.
                has_incomplete, incomplete_desc = _check_incomplete_task_list(agent_config.book_id, state)

                # Accept text-only as done (industry standard: no tool_calls = done).
                # Never emit a bare "完成" placeholder — it gets swallowed by
                # the frontend trivial-filter and leaves the user with no report.
                # When the model produced no summary text, synthesize one from
                # metrics so the user always sees what happened.
                #
                # Also catch trivial acknowledgments like "完成"/"已处理" that
                # the model emits after tool execution. When tools did real work
                # but the model just says "完成", include the last tool result
                # so the user sees the actual outcome.
                if final_text and not _is_trivial_done(final_text):
                    done_msg = final_text
                elif final_text and state.metrics.tool_calls > 0:
                    # Model said "完成" but tools did work — synthesize from
                    # tool results so the user sees what was accomplished.
                    tool_summary = _extract_last_tool_summary(messages)
                    if tool_summary:
                        done_msg = f"{final_text}\n\n{tool_summary}"
                    else:
                        done_msg = (
                            f"{final_text}（本轮共执行 {state.metrics.tool_calls} 次工具调用、"
                            f"{state.round} 轮）"
                        )
                else:
                    done_msg = (
                        f"本轮共执行 {state.metrics.tool_calls} 次工具调用、{state.round} 轮。模型未输出总结文本。"
                    )
                if has_incomplete:
                    done_msg += f"\n\n⚠️ 任务清单{incomplete_desc}，但模型未继续执行。"
                    state.metrics.finish_reason = "task_incomplete_done"
                else:
                    state.metrics.finish_reason = "done"
                if not streamed_text:
                    yield LoopEvent(type="text", data={"content": done_msg})
                yield LoopEvent(
                    type="done",
                    data={
                        "message": done_msg,
                        "rounds": state.round,
                        "parts": [p.to_dict() for p in state.parts],
                        "metrics": _loop_metrics_dict(state.metrics),
                    },
                )
                return

            # ── Stage 7: tool-call branch ──
            state.last_tool_calls = ", ".join(tc.name for tc in response.tool_calls)
            logger.info("Round %d tool calls: %s", state.round, state.last_tool_calls)
            async for ev in _handle_tool_calls(
                response,
                messages,
                agent_config,
                user_message,
                kb,
                handle,
                doom_detector,
                state,
                context,
            ):
                yield ev
            if state.metrics.finish_reason == "review_result":
                return

            # ── Emit real-time agent_metrics after each round for frontend Run Ledger ──
            yield LoopEvent(type="agent_metrics", data=_loop_metrics_dict(state.metrics))

        # ── Loop exited via round cap (while condition became False) ──
        # Inner branches all `return` on done, so reaching here means the
        # hard round cap was hit.
        # "Early stopping generate" pattern (industry standard): append a
        # hint asking the model to synthesize its best answer, then call the
        # LLM one more time without tools so the user gets a useful summary
        # instead of a bare "round limit reached" message.
        if not state.metrics.finish_reason:
            state.metrics.finish_reason = "round_limit_reached"
            yield LoopEvent(type="progress", data={"stage": "已达轮次上限，正在生成总结..."})
            _append_user_hint(
                messages,
                (
                    f"[系统提示] 你已达到最大轮次上限（{state.max_rounds} 轮）。"
                    "请基于已完成的工作给出最佳回答，不要调用任何工具，"
                    "直接输出文本总结。"
                ),
            )
            # Call LLM without tools so it synthesizes a final response
            try:
                final_streamed = ""
                async for msg_type, data in _stream_llm_with_retry(
                    messages, [], agent_config, handle, state,
                ):
                    if msg_type == "chunk":
                        yield LoopEvent(type="chunk", data={"text": data})
                        final_streamed += data
                    elif msg_type == "heartbeat":
                        yield LoopEvent(type="progress", data={"stage": data})
                    elif msg_type == "result":
                        _, final_streamed = data
                done_msg = final_streamed.strip() if final_streamed else (
                    f"已达循环轮次上限（{state.max_rounds} 轮），"
                    f"共执行 {state.metrics.tool_calls} 次工具调用。"
                )
                if not final_streamed:
                    yield LoopEvent(type="text", data={"content": done_msg})
            except Exception:
                done_msg = (
                    f"已达循环轮次上限（{state.max_rounds} 轮），"
                    f"共执行 {state.metrics.tool_calls} 次工具调用。"
                )
                yield LoopEvent(type="text", data={"content": done_msg})
            yield LoopEvent(
                type="done",
                data={
                    "message": done_msg,
                    "rounds": state.round,
                    "parts": [p.to_dict() for p in state.parts],
                    "metrics": _loop_metrics_dict(state.metrics),
                },
            )
    finally:
        # If finish_reason is still empty, the loop exited abnormally
        # (exception, cancellation, or unexpected code path). Tag it so
        # the metrics log and frontend done event carry a meaningful signal.
        if not state.metrics.finish_reason:
            state.metrics.finish_reason = "abnormal_exit"
            # Log diagnostic context so abnormal_exit is analyzable from
            # server.log alone — no need for the user to paste screenshots.
            # AI can read this to pinpoint the root cause.
            logger.error(
                "abnormal_exit: round=%d tool_calls=%d last_tools=%r last_text=%r",
                state.round, state.metrics.tool_calls,
                state.last_tool_calls, state.last_text_preview,
            )
        logger.info("Agent loop metrics: %s", state.metrics.summary())
        _persist_metrics(state.metrics, agent_config, user_message)

    # max_rounds=0 means unlimited — loop only exits via terminal branch,
    # drift force-stop, KB mutation guard, or user cancellation.


# ─────────────────────────────────────────────────────────────────────────────
# Stage: initial message preparation
# ─────────────────────────────────────────────────────────────────────────────


def _prepare_initial_messages(
    user_message: str,
    agent_config: AgentConfig,
    history_messages: list[dict] | None,
) -> list[dict]:
    from .styles import manager as style_manager

    # ── Instruction-level memory override ──
    # /free or /mem:off in the message body skips memory for this turn only.
    # The marker is stripped before sending to the LLM.
    _memory_mode = agent_config.memory_mode
    _clean_msg = user_message
    for marker in ("/free", "/mem:off", "/xp:off"):
        if _clean_msg.startswith(marker):
            _memory_mode = "clean_slate"
            _clean_msg = _clean_msg[len(marker):].strip()
            break

    active_style = style_manager.get_active_style(agent_config.book_id) if agent_config.book_id else ""
    system_prompt = build_system_prompt(
        agent_type=agent_config.agent_type, style_name=active_style, auto_mode_enabled=agent_config.auto_mode_enabled
    )

    messages = [{"role": "system", "content": system_prompt}]

    dynamic_ctx = build_dynamic_context(
        book_id=agent_config.book_id,
        session_id=agent_config.session_id,
        extra_context=agent_config.extra_context,
        memory_mode=_memory_mode,
    )
    if dynamic_ctx:
        messages.append({"role": "user", "content": f"[当前项目上下文]\n{dynamic_ctx}"})
        messages.append({"role": "assistant", "content": "好的，我已了解当前项目状态。请问有什么需要我帮忙的？"})

    if history_messages:
        messages.extend(history_messages)

    # Tag the current turn with its mode so the LLM can see mode switches
    # consistently across history (each history user turn carries the same
    # marker — see _load_history_as_llm_messages) and the current turn.
    mode_marker = f"[模式: {agent_config.mode}] " if agent_config.mode else ""
    messages.append({"role": "user", "content": mode_marker + _clean_msg})
    return messages


# ─────────────────────────────────────────────────────────────────────────────
# Stage: compaction
# ─────────────────────────────────────────────────────────────────────────────


async def _maybe_compact(
    messages: list[dict],
    agent_config: AgentConfig,
    state: LoopState,
) -> AsyncGenerator[LoopEvent, None]:
    if not needs_compaction(messages):
        return
    yield LoopEvent(type="compaction", data={"stage": "上下文压缩中..."})
    messages_replace, ok = await handle_context_overflow(messages)
    if not ok:
        yield LoopEvent(type="error", data={"message": "上下文过长，压缩后仍超限。请开启新对话。"})
        return
    messages[:] = messages_replace
    state.metrics.compactions += 1
    # Re-inject project state anchor after compaction to prevent state loss
    sitrep = await _build_sitrep_async(agent_config)
    if sitrep:
        _append_user_hint(messages, f"[压缩后状态锚定]\n{sitrep}")
    yield LoopEvent(type="compaction", data={"stage": "压缩完成", "tokens": count_message_tokens(messages)})


# ─────────────────────────────────────────────────────────────────────────────
# Stage: periodic sitrep injection
# ─────────────────────────────────────────────────────────────────────────────


async def _inject_sitrep(
    messages: list[dict],
    agent_config: AgentConfig,
    state: LoopState,
) -> AsyncGenerator[LoopEvent, None]:
    sitrep = await _build_sitrep_async(agent_config)
    if not sitrep:
        return
    _append_user_hint(messages, sitrep)
    state.metrics.sitreps += 1
    yield LoopEvent(type="compaction", data={"stage": "状态刷新", "tokens": count_message_tokens(messages)})


# ─────────────────────────────────────────────────────────────────────────────
# Stage: LLM call (streaming + retry on transient errors)
# ─────────────────────────────────────────────────────────────────────────────


async def _stream_llm_with_retry(
    messages: list[dict],
    tools: list[dict],
    agent_config: AgentConfig,
    handle: RunHandle,
    state: LoopState,
) -> AsyncGenerator[tuple[str, object], None]:
    """Stream one LLM call with retry for transient errors.

    Retry policy:
    - Only retry on retryable errors (rate limits, server 5xx, connection).
      Non-retryable errors (auth, invalid request, content policy) fail fast.
    - Exponential backoff with jitter via ``calculate_delay`` from the
      ``retry`` module, which respects ``retry-after`` headers.
    - Context overflow is a special case: compact and retry once.
    - Message sanitization runs before every attempt.

    Yields ``(msg_type, data)`` tuples: ``chunk`` / ``heartbeat`` /
    ``progress`` / ``result`` / ``error``. Chunks flow through immediately
    so streaming UX is preserved across retries."""
    last_error: str | None = None
    overflow_retries = 0

    for attempt in range(MAX_LLM_ERROR_RETRIES + 1):
        _sanitize_tool_messages(messages)
        if attempt > 0:
            yield ("progress", f"LLM 错误，第{attempt}次重试...")
            state.metrics.llm_retries += 1
        state.metrics.llm_calls += 1

        error: str | None = None
        response = None
        streamed_text = ""
        async for msg_type, data in _stream_llm_response(
            messages,
            tools,
            agent_config,
            handle,
            state.temperature,
        ):
            if msg_type == "error":
                error = data
                last_error = data
            elif msg_type == "result":
                response, streamed_text = data
            else:
                yield (msg_type, data)

        if error is None and response is not None:
            yield ("result", (response, streamed_text))
            return

        # ── Error classification ──
        # Try to extract the original exception for precise classification.
        # The error string may contain the exception type and message.
        exc = _extract_exception(error) if error else None

        # Context overflow: compact and retry (once)
        if exc and is_context_overflow(exc) and overflow_retries < _MAX_OVERFLOW_RETRIES:
            overflow_retries += 1
            logger.warning("Context overflow detected, compacting and retrying")
            yield ("progress", "上下文超限，正在压缩后重试...")
            from .compaction import compact_messages_async

            compacted = await compact_messages_async(messages)
            messages[:] = compacted
            continue

        # Non-retryable error: fail fast
        if exc and not is_retryable(exc):
            logger.warning("Non-retryable LLM error: %s", str(exc)[:150])
            yield ("error", str(error))
            return

        # Retryable error with remaining attempts
        if attempt < MAX_LLM_ERROR_RETRIES:
            delay = calculate_delay(attempt, exc)
            logger.warning(
                "LLM retryable error (attempt %d/%d), sleeping %.1fs: %s",
                attempt + 1,
                MAX_LLM_ERROR_RETRIES,
                delay,
                str(error)[:120],
            )
            await asyncio.sleep(delay)

    # Exhausted retries
    if last_error is not None:
        yield ("error", f"{last_error}\n(提示：若反复出现此错误，可开启新对话来重置消息历史)")


def _extract_exception(error_str: str | None) -> Exception | None:
    """Try to reconstruct an Exception from an error string for classification.

    The ``retry`` module's ``is_retryable`` / ``is_context_overflow`` expect
    Exception objects (OpenAI SDK types). When the error arrives as a string
    from the streaming layer, we wrap it so the classifiers can still work
    via string matching fallbacks."""
    if not error_str:
        return None
    # If we already have an Exception object, return it directly
    if isinstance(error_str, Exception):
        return error_str
    return Exception(error_str)


async def _stream_llm_response(messages, tools, agent_config: AgentConfig, handle, temperature: float | None = None):
    response = LLMResponse()
    streamed_text = ""
    queue: asyncio.Queue = asyncio.Queue()
    use_temp = temperature if temperature is not None else agent_config.temperature
    loop = asyncio.get_running_loop()

    async def _consume_stream():
        nonlocal response, streamed_text
        last_heartbeat = loop.time()
        try:
            async for event in chat_with_tools_stream_async(messages, tools, use_temp, agent_config.task_label):
                # Fine-grained cancellation: check between events so a long
                # generation can be interrupted mid-stream.
                if handle.cancelled:
                    await queue.put(("error", "用户已取消"))
                    return
                if event.type == "text-delta":
                    await queue.put(("chunk", event.data.get("text", "")))
                    response.content += event.data.get("text", "")
                    streamed_text += event.data.get("text", "")
                elif event.type == "reasoning-delta":
                    # Capture reasoning without streaming it as visible text —
                    # it's preserved on the response for history/UI only.
                    response.reasoning += event.data.get("text", "")
                elif event.type == "tool-call-end":
                    tc_data = event.data
                    response.tool_calls.append(
                        ToolCall(
                            id=tc_data.get("id", ""),
                            name=tc_data.get("name", ""),
                            arguments=tc_data.get("arguments", ""),
                        )
                    )
                elif event.type == "finish":
                    response.finish_reason = event.data.get("reason", "")
                elif event.type in ("context-overflow", "retryable-error", "error"):
                    await queue.put(("error", event.data.get("error", "LLM error")))
                    return
                if loop.time() - last_heartbeat > 20:
                    await queue.put(("heartbeat", "模型仍在生成回复..."))
                    last_heartbeat = loop.time()
        except Exception as e:
            await queue.put(("error", str(e)))
            return
        finally:
            await queue.put(("done", None))

    task = asyncio.create_task(_consume_stream())

    try:
        while True:
            msg_type, data = await queue.get()
            if msg_type == "done":
                break
            elif msg_type == "chunk":
                yield ("chunk", data)
            elif msg_type == "error":
                yield ("error", data)
                await task
                return
            elif msg_type == "heartbeat":
                yield ("heartbeat", data)

        await task
    except asyncio.CancelledError:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        raise
    yield ("result", (response, streamed_text))


# ─────────────────────────────────────────────────────────────────────────────
# Stage: tool-call branch
# ─────────────────────────────────────────────────────────────────────────────


async def _handle_tool_calls(
    response: LLMResponse,
    messages: list[dict],
    agent_config: AgentConfig,
    user_message: str,
    kb,
    handle: RunHandle,
    doom_detector: DoomLoopDetector,
    state: LoopState,
    context: AgentContext,
) -> AsyncGenerator[LoopEvent, None]:
    streamed_text = response.content or ""

    # ── Drift detection (warning only, never aborts tool calls) ──
    # If the agent is calling tools, it's making progress — don't stop it.
    # Drift detection only injects a soft warning so the model is aware.
    # IMPORTANT: must run BEFORE appending the assistant(tool_calls) message.
    # The API requires tool messages to immediately follow assistant(tool_calls);
    # injecting a user message between them causes a 400 "must be followed by
    # tool messages" error.
    if streamed_text and len(streamed_text) > 5:
        is_completion, is_verify = state.classify_drift(streamed_text)
        if is_completion:
            state.record_completion_claim()
        if is_verify:
            state.record_verify_loop()
        if state.drift_limit_reached:
            yield LoopEvent(
                type="text-correction",
                data={
                    "reason": f"第{state.completion_claims + state.verify_loops}次{state.drift_signal_label}，建议停止重复操作",
                },
            )
            _append_user_hint(messages, _build_drift_correction(user_message, state))
            state.drift_corrected = True
            state.metrics.drift_corrections += 1

    # ── Append assistant message with tool_calls (after drift correction) ──
    assistant_msg = {
        "role": "assistant",
        "content": streamed_text,
        "tool_calls": [
            {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": tc.arguments}}
            for tc in response.tool_calls
        ],
    }
    messages.append(assistant_msg)

    # NOTE: Drift hard stop removed — if the agent is calling tools, it's
    # making progress. Don't abort real work. DoomLoopDetector catches
    # truly identical repeated calls; drift detection just warns.

    # ── Prepare tool calls: validate, permissions, doom loop ──
    prepared: list[dict] = []
    async for ev in _prepare_tool_calls(
        response,
        messages,
        agent_config,
        handle,
        doom_detector,
        state,
        prepared,
    ):
        yield ev

    if not prepared:
        # All tool calls were rejected (validation, permissions, etc.).
        # We MUST still append tool result messages for every tool_call so
        # the message list stays well-formed. Without this, the next LLM
        # call receives orphan assistant tool_calls → API error → abnormal_exit.
        for tc in response.tool_calls:
            if tc.id not in {m.get("tool_call_id", "") for m in messages if isinstance(m, dict)}:
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id,
                     "content": f"工具 {tc.name} 未执行（参数校验失败或权限不足）"}
                )
        return

    # ── KB mutation guard (warning only, never aborts) ──
    # Track consecutive KB mutations for metrics, but don't force-stop.
    # Batch operations (e.g. importing 10 characters) are legitimate.
    # DoomLoopDetector catches truly repetitive identical calls.
    from .tool_meta import READ_TOOLS

    tool_name_set = {tc.name for tc in response.tool_calls}
    _this_round_mutates_kb = any(getattr(registry.get(name), "mutates_kb", False) for name in tool_name_set)
    if _this_round_mutates_kb:
        state.record_kb_round()
        if state.kb_mutation_limit_reached:
            yield LoopEvent(
                type="text-correction",
                data={
                    "reason": f"已连续{state.kb_mutation_streak}轮知识库修改，请注意是否在重复操作",
                },
            )
            state.reset_kb_guard()
            state.metrics.kb_mutation_stops += 1
    else:
        state.record_non_kb_round()

    # ── Round categorization (for metrics) ──
    # Track rounds where only read-only tools were used (potential waste in write mode).
    if tool_name_set and tool_name_set.issubset(READ_TOOLS):
        state.metrics.read_only_rounds += 1
    # Track rounds where the model output substantial text AND called tools (confusion signal).
    if streamed_text and len(streamed_text) > 200 and tool_name_set:
        state.metrics.text_and_tool_rounds += 1

    yield LoopEvent(
        type="tool-start",
        data={
            "tool": ", ".join(p["tc"].name for p in prepared),
            "args": (
                f"{len(prepared)} 个工具并行执行" if len(prepared) > 1 else _safe_args_preview(prepared[0]["args"])
            ),
        },
    )

    # Record tool-call parts for history persistence (full args, not preview).
    for p in prepared:
        state.add_part(
            ToolCallPart(
                tool_call_id=p["tc"].id,
                name=p["tc"].name,
                arguments=p["tc"].arguments,
            )
        )

    # ── Split streaming vs parallel using tool metadata ──
    streaming_tasks = [p for p in prepared if getattr(registry.get(p["tc"].name), "streaming", False)]
    parallel_tasks = [p for p in prepared if p not in streaming_tasks]

    # ── Inject available tokens for context-aware writing tools ──
    current_tokens = count_message_tokens(messages)
    model_limit = get_context_limit(model_for("general"))
    available_for_context = int((model_limit * 0.85 - current_tokens) * 0.3)
    available_for_context = max(available_for_context, 8000)
    for p in streaming_tasks + parallel_tasks:
        if getattr(registry.get(p["tc"].name), "context_aware", False):
            p["args"]["_available_tokens"] = available_for_context

    # ── Execute streaming tools sequentially ──
    for p in streaming_tasks:
        tc, args = p["tc"], p["args"]
        result = {}
        try:
            async for prog in _execute_tool_streaming(tc.name, args, agent_config, user_message, kb, context):
                if isinstance(prog, dict):
                    if prog.get("_writing_meta"):
                        yield LoopEvent(type="writing", data=prog["_writing_meta"])
                    elif prog.get("_writing"):
                        yield LoopEvent(type="writing", data={"text": prog["_writing"]})
                    elif prog.get("_chunk"):
                        yield LoopEvent(type="chunk", data={"text": prog["_chunk"]})
                    elif prog.get("_progress"):
                        yield LoopEvent(type="progress", data={"stage": prog["_progress"]})
                    elif prog.get("_workflow"):
                        yield LoopEvent(type="workflow", data=prog["_workflow"])
                    else:
                        result = prog
                elif isinstance(prog, str):
                    result = {"text": prog}
        except Exception as e:
            # Streaming tool died mid-stream. Fall back to the error string
            # so we ALWAYS append a tool message for this tool_call (otherwise
            # the assistant_tool_calls message becomes orphaned and the next
            # LLM call 400s).
            logger.warning("Streaming tool %s raised: %s", tc.name, e)
            result = {"error": True, "tool": tc.name, "message": str(e)[:200]}
        try:
            async for ev in _process_tool_result(tc, result, agent_config, state, messages):
                yield ev
        except Exception as e:
            # Even the result-processor failed — manually append a placeholder
            # so the message list stays well-formed.
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": f"工具 {tc.name} 处理结果时出错: {str(e)[:200]}"}
            )
        # Collect ToolResultPart + any ChapterDiffPart derived from the result.
        _collect_result_parts(tc, result, state, messages)

        # ── Terminal stop: review_result signals the agent is done ──
        # Break out of the streaming loop immediately so the done event
        # at the end of _handle_tool_calls is reached. Without this, the
        # loop continues to the next streaming task, which may hang or
        # fail, causing abnormal_exit and a silent dead-end for the user.
        if state.metrics.finish_reason == "review_result":
            break

    # ── Execute non-streaming tools in parallel ──
    if parallel_tasks:

        async def _run_one(p):
            return await _execute_tool(p["tc"].name, p["args"], agent_config, user_message, kb, context)

        gather_tasks = [asyncio.create_task(_run_one(p)) for p in parallel_tasks]
        try:
            results = await asyncio.gather(*gather_tasks, return_exceptions=True)
        except asyncio.CancelledError:
            for t in gather_tasks:
                t.cancel()
            raise
        for p, result in zip(parallel_tasks, results, strict=False):
            tc = p["tc"]
            if isinstance(result, BaseException):
                if isinstance(result, asyncio.CancelledError):
                    raise
                result = f"工具 {tc.name} 出错: {str(result)[:100]}"
            elif isinstance(result, Exception):
                result = f"工具 {tc.name} 出错: {str(result)[:100]}"
            async for ev in _process_tool_result(tc, result, agent_config, state, messages):
                yield ev
            _collect_result_parts(tc, result, state, messages)

    yield LoopEvent(
        type="tool-end",
        data={
            "tool": ", ".join(p["tc"].name for p in prepared),
            "result_preview": messages[-1].get("content", "")[:150] if messages else "",
        },
    )

    # ── Notify frontend when chapters changed (metadata-driven) ──
    if any(getattr(registry.get(p["tc"].name), "touches_chapter", False) for p in prepared):
        yield LoopEvent(type="chapter_updated", data={})

    # ── Terminal tool result (review_result) — signal done and stop ──
    if state.metrics.finish_reason == "review_result":
        terminal_text = messages[-1].get("content", "") if messages else ""
        # If terminal text is trivial, include the last meaningful tool result
        if not terminal_text or _is_trivial_done(terminal_text):
            tool_summary = _extract_last_tool_summary(messages)
            if tool_summary:
                terminal_text = f"{terminal_text}\n\n{tool_summary}".strip()
            elif not terminal_text:
                terminal_text = (
                    f"本轮共执行 {state.metrics.tool_calls} 次工具调用、"
                    f"{state.round} 轮。"
                )
        yield LoopEvent(
            type="done",
            data={
                "message": terminal_text,
                "rounds": state.round,
                "parts": [p.to_dict() for p in state.parts],
                "metrics": _loop_metrics_dict(state.metrics),
            },
        )


async def _prepare_tool_calls(
    response: LLMResponse,
    messages: list[dict],
    agent_config: AgentConfig,
    handle: RunHandle,
    doom_detector: DoomLoopDetector,
    state: LoopState,
    prepared: list[dict],
) -> AsyncGenerator[LoopEvent, None]:
    """Validate args, enforce permissions and doom-loop guards. Appends valid
    tool calls to ``prepared`` and yields ``doom-loop`` / ``question`` events
    as needed (the latter must be emitted before awaiting the user's answer).

    Robustness: the body loops over ``response.tool_calls`` and appends a
    ``role: tool`` message for each one it touches. If a cancel or unexpected
    exception aborts the loop mid-iteration, the remaining tool_calls are
    backfilled with placeholder tool messages so the message list stays
    well-formed. ``_sanitize_tool_messages`` in the main loop is the belt;
    this is the suspenders."""
    processed_ids: set[str] = set()
    try:
        for tc in response.tool_calls:
            handle.check_cancelled()

            if doom_detector.record_call(tc.name, tc.arguments):
                # Doom loop detected — warning only, never skips tool calls.
                # Trust the LLM; if it's genuinely stuck it will exhaust its
                # own reasoning. We just log for observability.
                state.metrics.doom_loop_skips += 1
                logger.warning("Doom loop detected: %s called repeatedly, but not interrupting", tc.name)

            try:
                args = json.loads(tc.arguments) if tc.arguments else {}
            except json.JSONDecodeError:
                args = {}

            tool_def = registry.get(tc.name)
            if tool_def:
                validated_args, errors = validate_tool_input(tool_def, args)
                if errors:
                    messages.append(
                        {"role": "tool", "tool_call_id": tc.id, "content": f"参数校验失败: {'; '.join(errors)}"}
                    )
                    processed_ids.add(tc.id)
                    continue
                args = validated_args

            perm_action = permission_manager.check(tc.name)
            if perm_action == "deny":
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": f"工具 {tc.name} 被禁止。"})
                processed_ids.add(tc.id)
                continue
            if perm_action == "ask":
                confirm_msg = permission_manager.get_confirmation_message(tc.name)
                q_req = question_manager.create_question(
                    [
                        {
                            "question": confirm_msg,
                            "header": "权限确认",
                            "options": [
                                {"label": "确认执行", "description": "允许"},
                                {"label": "取消", "description": "中止"},
                            ],
                            "custom": False,
                        }
                    ],
                    agent_config.book_id,
                )
                yield LoopEvent(type="question", data={"id": q_req.id, "questions": q_req.questions})
                confirmed = await _await_answer(q_req.id)
                if not confirmed:
                    messages.append({"role": "tool", "tool_call_id": tc.id, "content": f"用户取消了 {tc.name}。"})
                    processed_ids.add(tc.id)
                    continue
                permission_manager.approve_once(tc.name)

            processed_ids.add(tc.id)
            prepared.append({"tc": tc, "args": args})
    except CancelledError:
        # User cancelled mid-loop — backfill any tool_calls not yet processed
        # so the message list doesn't end with orphan assistant tool_calls.
        logger.info(
            "_prepare_tool_calls cancelled mid-loop, backfilling %d remaining",
            len(response.tool_calls) - len(processed_ids),
        )
        for tc in response.tool_calls:
            if tc.id not in processed_ids:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": "[占位] 用户取消了本轮执行，不再调用此工具。",
                    }
                )
        raise
    except Exception as e:
        # Unexpected error in validation / permission layer. Backfill remaining
        # tool_calls with error messages so the message list stays well-formed,
        # then return normally instead of re-raising. Re-raising would propagate
        # the exception to the outer loop's finally block → abnormal_exit.
        logger.warning("_prepare_tool_calls exception mid-loop, backfilling remaining tool_calls: %s", e)
        for tc in response.tool_calls:
            if tc.id not in processed_ids:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": f"[错误] 准备工具调用时内部异常: {str(e)[:100]}",
                    }
                )


async def _await_answer(question_id: str) -> bool:
    try:
        # Check every 10s for cancellation instead of blocking 300s straight
        remaining = 300
        while remaining > 0:
            chunk = min(10, remaining)
            try:
                answers = await asyncio.wait_for(question_manager.wait_for_answer(question_id), timeout=chunk)
                return bool(answers and answers[0] and "确认" in answers[0][0])
            except TimeoutError:
                remaining -= chunk
                await asyncio.sleep(0)  # yield to allow cancellation
        return False
    except asyncio.CancelledError:
        raise  # Let cancellation propagate normally
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Unified tool-result processor (deduplicates streaming / parallel branches)
# ─────────────────────────────────────────────────────────────────────────────


async def _process_tool_result(
    tc: ToolCall,
    result,
    agent_config: AgentConfig,
    state: LoopState,
    messages: list[dict],
) -> AsyncGenerator[LoopEvent, None]:
    """Handle every special result type (plot_cards / writing_result /
    task_list / patch_result / review_result / question / default) for BOTH
    streaming and parallel tools, then append the tool message."""
    state.metrics.tool_calls += 1
    tool_name = tc.name if hasattr(tc, "name") else str(tc)
    state.metrics.tool_names[tool_name] = state.metrics.tool_names.get(tool_name, 0) + 1
    result_str: str
    terminal: str | None = None
    chapter_updated = False

    if isinstance(result, dict) and result.get("type") == "plot_cards":
        cards = result.get("cards", [])
        q_req = question_manager.create_question(
            [
                {
                    "question": "选择一个剧情方向",
                    "header": "剧情走向",
                    "options": [{"label": c.get("title", ""), "description": c.get("description", "")} for c in cards],
                    "card_type": "plot_cards",
                    "cards": cards,
                    "context_summary": result.get("context_summary", ""),
                    "custom": True,
                }
            ],
            agent_config.book_id,
        )
        yield LoopEvent(
            type="plot_cards",
            data={
                "id": q_req.id,
                "context_summary": result.get("context_summary", ""),
                "cards": cards,
                "instruction": result.get("instruction", ""),
            },
        )
        try:
            answers = await asyncio.wait_for(question_manager.wait_for_answer(q_req.id), timeout=300)
            selected_text = answers[0][0] if answers and answers[0] else "用户未选择"
        except TimeoutError:
            selected_text = "用户超时未选择"
        except (ValueError, IndexError, KeyError):
            selected_text = "用户拒绝了所有选项，请重新构思方向"
        result_str = f"用户的剧情方向选择: {selected_text}\n\n请根据用户选择继续。"

    elif isinstance(result, dict) and result.get("type") == "autopilot_plan":
        task_id = result.get("task_id", "")
        plan_summary = result.get("plan_summary", "")
        chapters = result.get("chapters", [])
        audit_mode = result.get("audit_mode", "soft")
        ch_list = "、".join(f"第{c['index']}章{c.get('title', '')}" for c in chapters[:5])
        confirm_msg = (
            f"是否启动 Autopilot 自主写作？\n\n"
            f"计划: {plan_summary}\n"
            f"章节: {ch_list}{'...' if len(chapters) > 5 else ''}\n"
            f"模式: {audit_mode}\n\n"
            f"启动后将在后台逐章执行，您可随时暂停/取消。"
        )
        q_req = question_manager.create_question(
            [
                {
                    "question": confirm_msg,
                    "header": "启动 Autopilot",
                    "options": [
                        {"label": "确认启动", "description": "开始执行写作计划"},
                        {"label": "取消", "description": "不启动 Autopilot"},
                    ],
                    "custom": False,
                }
            ],
            agent_config.book_id,
        )
        yield LoopEvent(type="question", data={"id": q_req.id, "questions": q_req.questions})
        confirmed = await _await_answer(q_req.id)
        if confirmed:
            from core.autopilot_runner import autopilot as ap

            ok = await ap.confirm_start(task_id)
            if ok:
                result_str = (
                    f"Autopilot 已启动！\n\n"
                    f"任务ID: {task_id}\n"
                    f"计划: {plan_summary}\n"
                    f"模式: {audit_mode}\n\n"
                    f"后台执行中，可在右侧面板监控进度。完成后会自动通知。"
                )
            else:
                result_str = "Autopilot 启动失败，请重试。"
        else:
            result_str = "用户取消了 Autopilot 启动。如需调整参数，请重新发起。"
            from core.task_queue import task_queue as tq

            tq.cancel_task(task_id)

    elif isinstance(result, dict) and result.get("type") == "writing_result":
        if result.get("saved"):
            yield LoopEvent(
                type="writing_end",
                data={
                    "chapter_id": result.get("chapter_id", ""),
                    "chapter_title": result.get("chapter_title", ""),
                    "word_count": result.get("word_count", 0),
                    "saved": True,
                },
            )
        result_str = result.get("text", "")

    elif isinstance(result, dict) and result.get("type") == "task_list":
        yield LoopEvent(type="task_list", data={"items": result.get("items", [])})
        # Track the active task list ID for terminal-branch completeness check
        tl_id = result.get("task_list_id", "")
        if tl_id:
            state.active_task_list_id = tl_id
        result_str = result.get("text", "")

    elif isinstance(result, dict) and result.get("type") == "patch_result":
        if not result.get("error"):
            yield LoopEvent(
                type="patch_result",
                data={
                    "chapter_id": result.get("chapter_id", ""),
                    "chapter_title": result.get("chapter_title", ""),
                    "operations": result.get("operations", []),
                    "patched_count": result.get("patched_count", 0),
                    "total_count": result.get("total_count", 0),
                    "word_count": result.get("word_count", 0),
                },
            )
        result_str = result.get("text", "") or result.get("error", "")

    elif isinstance(result, dict) and result.get("type") == "review_result":
        result_str = result.get("text", "")
        chapter_updated = True
        terminal = result_str

    elif isinstance(result, dict) and result.get("type") == "question":
        # ask_user tool — display a question popup on the frontend and block
        # until the user answers. Without this, the ask_user result is just a
        # JSON string the LLM sees but the user never gets a popup, causing the
        # agent to end prematurely ("didn't ask the user, just stopped").
        qs = result.get("questions", [])
        if qs:
            q_req = question_manager.create_question(qs, agent_config.book_id)
            yield LoopEvent(type="question", data={"id": q_req.id, "questions": q_req.questions})
            try:
                answers = await asyncio.wait_for(question_manager.wait_for_answer(q_req.id), timeout=300)
            except TimeoutError:
                answers = [["用户超时未回复"]]
            except Exception:
                answers = [["用户拒绝了提问"]]
            # Format answers as a readable string for the LLM
            answer_parts = []
            for i, q in enumerate(qs):
                q_text = q.get("question", f"问题{i + 1}")
                ans = answers[i] if i < len(answers) else ["未回复"]
                answer_parts.append(f"Q: {q_text}\nA: {', '.join(ans)}")
            result_str = "用户回答:\n" + "\n\n".join(answer_parts)
        else:
            result_str = "无问题"

    else:
        result_str = _finalize_tool_result(result)

    if result_str != "":
        messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_str})
    else:
        # MUST append a tool message even for empty results. Without this,
        # the assistant tool_calls entry becomes orphaned and the next LLM
        # call fails with 400: "An assistant message with 'tool_calls' must
        # be followed by tool messages responding to each 'tool_call_id'."
        messages.append({"role": "tool", "tool_call_id": tc.id, "content": "工具执行完成（无文本输出）"})

    # ── Post-extraction summary hint ──
    # extract_all_chapters / extract_chapter return structured data but the
    # LLM often just says "完成" after seeing it. Inject a hint that forces
    # a natural-language report so the user sees what was actually extracted.
    if tool_name in ("extract_all_chapters", "extract_chapter"):
        _append_user_hint(
            messages,
            (
                "[系统提示] 知识提取工具已返回结果。请用自然语言向用户汇报："
                "① 共处理了多少章 ② 新增了哪些角色/地点/设定（列出名字）"
                "③ 更新了多少已有实体 ④ 新增了多少关系和伏笔。"
                "必须输出完整报告，禁止只说'完成'或'提取完成'。"
            ),
        )

    if chapter_updated:
        yield LoopEvent(type="chapter_updated", data={})

    if terminal is not None:
        yield LoopEvent(type="chunk", data={"text": "\n\n" + terminal})
        state.metrics.finish_reason = "review_result"


def _finalize_tool_result(result) -> str:
    if isinstance(result, dict) and result.get("type") == "question":
        return json.dumps(result, ensure_ascii=False)
    elif isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False)
    result_str = str(result) if result else ""
    return truncate_tool_output(result_str)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _append_user_hint(messages: list[dict], content: str) -> None:
    """Unified mid-conversation injection: always ``role: user`` with a clear
    ``[系统提示]`` prefix. Some providers ignore non-leading ``role: system``
    messages, so using user turns keeps the instruction visible across backends."""
    messages.append({"role": "user", "content": content})


def _collect_result_parts(tc: ToolCall, result, state: LoopState, messages: list[dict]) -> None:
    """After a tool executes, record its ToolResultPart and any ChapterDiffPart.

    The tool message was already appended to ``messages`` by
    ``_process_tool_result``; we read it back so the recorded result matches
    exactly what the LLM saw. Chapter diffs are derived from the structured
    result dict (writing_result / patch_result) so the UI can render
    '📄 第3章 已修改' cards without re-querying.
    """
    result_str = ""
    for m in reversed(messages):
        if m.get("role") == "tool" and m.get("tool_call_id") == tc.id:
            result_str = m.get("content", "")
            break
    state.add_part(
        ToolResultPart(
            tool_call_id=tc.id,
            result=result_str,
            result_type=result.get("type", "") if isinstance(result, dict) else "",
            tool_name=tc.name,
        )
    )
    if isinstance(result, dict):
        rtype = result.get("type", "")
        if rtype == "writing_result" and result.get("saved"):
            state.add_part(
                ChapterDiffPart(
                    chapter_id=result.get("chapter_id", ""),
                    chapter_title=result.get("chapter_title", ""),
                    operation="created",
                    word_count=result.get("word_count", 0),
                )
            )
        elif rtype == "patch_result" and not result.get("error"):
            state.add_part(
                ChapterDiffPart(
                    chapter_id=result.get("chapter_id", ""),
                    chapter_title=result.get("chapter_title", ""),
                    operation="patched",
                    patch_count=result.get("patched_count", 0),
                    word_count=result.get("word_count", 0),
                )
            )


def _sanitize_tool_messages(messages: list[dict]) -> None:
    """In-place hygiene pass ensuring tool_call ↔ tool pairs are never orphaned.

    Removes tool messages whose ``tool_call_id`` has no matching assistant
    ``tool_calls`` entry (orphaned responses from compaction edge cases), and
    appends placeholder tool messages for any assistant ``tool_calls`` whose
    ``tool_call_id`` has no matching response (orphaned calls from partial
    processing — e.g. cancel/exception mid-loop in ``_prepare_tool_calls``).

    The LLM API strictly requires: *every* assistant message with ``tool_calls``
    must be followed by tool messages responding to each ``tool_call_id``. A
    violation produces an unrecoverable 400 that retries can't fix.
    """
    if not messages:
        return

    # Step 1: collect every tool_call_id referenced by any assistant message.
    all_call_ids: set[str] = set()
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                if tc_id:
                    all_call_ids.add(tc_id)

    if not all_call_ids:
        # No assistant-with-tool_calls in the conversation — nothing to do.
        # (Orphan tool messages with no assistant are exceedingly rare but
        # handled in step 2 as a defensive sweep.)
        pass

    # Step 2: sweep tool messages. Remove those whose call id isn't in
    # ``all_call_ids`` (truly orphan); track which ids got answered.
    answered: set[str] = set()
    indices_to_remove: list[int] = []
    for i, msg in enumerate(messages):
        if msg.get("role") == "tool":
            tc_id = msg.get("tool_call_id")
            if not tc_id:
                # Malformed tool message with no id — drop it.
                indices_to_remove.append(i)
                continue
            if tc_id not in all_call_ids:
                # Orphan tool message: assistant_tool_calls it responded to is
                # gone (e.g. summarised away by compaction). Drop it.
                indices_to_remove.append(i)
                continue
            answered.add(tc_id)

    for i in reversed(indices_to_remove):
        messages.pop(i)

    # Step 3: any call ids with no response yet get placeholders.
    # The API REQUIRES tool messages to immediately follow the assistant(tool_calls)
    # message they respond to — they cannot be arbitrarily placed. Find the
    # correct insertion point for each orphaned assistant msg and insert
    # placeholder tool messages immediately after it.
    orphaned = all_call_ids - answered
    if orphaned:
        # Build a map: tool_call_id → which assistant message it belongs to
        # (by index in the messages list). We need to insert tool placeholders
        # right after the LAST assistant message that carries tool_calls.
        # Strategy: for each assistant msg with tool_calls, collect its
        # orphaned ids, then insert placeholder tool messages after it.
        insertions: list[tuple[int, list[dict]]] = []  # (insert_after_idx, [tool_msgs])
        for i, msg in enumerate(messages):
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                orphaned_for_this: list[dict] = []
                for tc in msg["tool_calls"]:
                    tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                    if tc_id and tc_id in orphaned:
                        orphaned_for_this.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "content": "[占位] 上一步工具调用未获得响应（可能已取消或中断），请继续下一步。",
                        })
                if orphaned_for_this:
                    insertions.append((i, orphaned_for_this))
        # Insert in reverse order so indices stay valid
        for insert_after_idx, tool_msgs in reversed(insertions):
            for j, tm in enumerate(tool_msgs):
                messages.insert(insert_after_idx + 1 + j, tm)


def _build_drift_correction(user_message: str, state: LoopState) -> str:
    return (
        f"[系统提示] [⛔ 强制停止] 你已经{state.completion_claims}次声称任务完成或"
        f"{state.verify_loops}次陷入验证循环。你正在反复验证、清理、重建相同的数据——这是一个无限循环。"
        f"\n用户只要求：「{user_message[:150]}」"
        "\n\n立刻执行以下规则："
        "\n1. 停止所有验证、检查、确认操作——不要再调 search_knowledge 检查重复"
        "\n2. 停止所有清理、删除、重建操作——不要再 delete_entity / extract_knowledge"
        "\n3. 用你当前已知的信息直接输出简短汇报"
        "\n4. 如果发现有重复等问题，只在汇报末尾说一句'发现可能存在重复，需要我处理吗？'"
        "\n5. 绝对不要再调用任何工具"
    )


def _build_kb_overload_correction(user_message: str, state: LoopState) -> str:
    return (
        f"[系统提示] [⛔ 知识库操作过载] 你已经连续{state.kb_mutation_streak}轮进行知识库修改操作"
        "（delete_entity / extract_knowledge / update_entity）。"
        "知识库操作不可逆——你已经删删改改太多次了。"
        f"\n用户只要求：「{user_message[:150]}」"
        "\n\n立刻停止："
        "\n1. 不要再删除任何实体——即使发现有重复"
        "\n2. 不要再重新提取或重建任何数据"
        "\n3. 不要再调 search_knowledge 验证"
        "\n4. 用你当前已知的信息直接输出简短汇报"
        "\n5. 如有重复等问题，只在汇报末尾提一句'发现可能有重复，需要处理吗？'"
        "\n6. 绝对不要再调用任何工具"
    )


async def _build_sitrep_async(agent_config: "AgentConfig") -> str:
    try:
        from .thread_pools import io_pool

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(io_pool, _build_sitrep_sync, agent_config)
    except (OSError, RuntimeError) as e:
        logger.debug(f"Sitrep build failed: {e}")
        return ""


def _build_sitrep_sync(agent_config: "AgentConfig") -> str:
    """Build a brief project status refresh to anchor the LLM's knowledge."""
    from data.json_store import json_store

    from .graph_store import GraphStore
    from .knowledge import EntityType

    kb = GraphStore(agent_config.book_id)
    kb.init_schema()
    try:
        entities = kb.list_entities()
        book = json_store.get_book(agent_config.book_id)
        chapters = json_store.load_chapters(agent_config.book_id)
        chapter_count = len(chapters) if chapters else 0
        total_words = sum(len(json_store._chapter_view(c).get("content", "")) for c in chapters) if chapters else 0

        lines = [
            "[状态刷新 — 锚定当前真实项目状态]",
            f"书名: {book.get('title', '?')}",
            f"章节: {chapter_count} 章 | 总字数: {_fmt_words(total_words)}",
            f"实体: {len(entities)} 个",
        ]
        for etype in EntityType.BUILTIN:
            typed = [e for e in entities if e.type == etype]
            if typed:
                names = [e.name for e in typed[:8]]
                lines.append(f"  {etype}: {', '.join(names)}")
                if len(typed) > 8:
                    lines.append(f"  ... 共{len(typed)}个")

        vol_count = len(json_store.load_volumes(agent_config.book_id))
        if vol_count:
            lines.append(f"分卷: {vol_count} 卷")

        ref_ids = json_store.get_reference_books(agent_config.book_id)
        if ref_ids:
            ref_names = []
            for rid in ref_ids:
                try:
                    rb = json_store.get_book(rid)
                    ref_names.append(rb.get("title", rid))
                except (KeyError, TypeError):
                    pass
            if ref_names:
                lines.append(f"参考书: {', '.join(ref_names)}")

        return "\n".join(lines)
    finally:
        kb.close()


def _fmt_words(n: int) -> str:
    if n >= 10000:
        return f"{n / 10000:.1f}万"
    return str(n)


def _trim(s: str, max_len: int) -> str:
    s = str(s).replace("\n", " ").strip()
    if len(s) <= max_len:
        return s
    return s[:max_len] + "…"


def _safe_args_preview(args: dict) -> str:
    preview = {}
    for k, v in args.items():
        if isinstance(v, str) and len(v) > 100:
            preview[k] = v[:80] + f"...({len(v)}字)"
        else:
            preview[k] = v
    return json.dumps(preview, ensure_ascii=False)[:200]


# ─────────────────────────────────────────────────────────────────────────────
# Tool execution wrappers
# ─────────────────────────────────────────────────────────────────────────────


async def _execute_tool_streaming(
    name: str, args: dict, agent_config: AgentConfig, user_message: str, kb, context: AgentContext | None = None
):
    from tools.executor import execute_tool_streaming

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    async def _run():
        # Wrap in try/except so a tool exception ALWAYS terminates the queue.
        # Without this, an exception here leaves the queue without a None
        # sentinel → the consumer's `await queue.get()` deadlocks → the agent
        # loop hangs → abnormal_exit with no report to the user.
        try:
            result = await execute_tool_streaming(
                loop,
                name,
                args,
                kb,
                agent_config.book_id,
                user_message,
                agent_config.session_id,
                queue,
                context=context,
            )
        except BaseException as e:
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            logger.error("Streaming tool %s raised with args=%s: %s\n%s",
                         name, {k: str(v)[:200] for k, v in args.items()},
                         e, traceback.format_exc())
            result = {"error": True, "tool": name, "message": str(e)[:200]}
        await queue.put(result)
        await queue.put(None)

    task = asyncio.create_task(_run())

    while True:
        item = await queue.get()
        if item is None:
            break
        yield item

    await task


async def _execute_tool(
    name: str, args: dict, agent_config: AgentConfig, user_message: str, kb, context: AgentContext | None = None
) -> str | dict:
    from tools.executor import execute_tool

    loop = asyncio.get_running_loop()
    return await execute_tool(
        loop,
        name,
        args,
        kb,
        agent_config.book_id,
        user_message,
        agent_config.session_id,
        confirmed=True,
        context=context,
    )


def _persist_metrics(metrics, agent_config, user_message: str):
    """Persist loop metrics to JSONL file for analysis."""
    from datetime import datetime

    from .config import DATA_DIR

    metrics_file = DATA_DIR / "metrics.jsonl"
    record = {
        "timestamp": datetime.now().isoformat(),
        "agent_type": agent_config.agent_type,
        "book_id": agent_config.book_id,
        "user_message": user_message[:200],  # Truncate for storage
        "rounds": metrics.rounds,
        "llm_calls": metrics.llm_calls,
        "llm_retries": metrics.llm_retries,
        "tool_calls": metrics.tool_calls,
        "hallucination_hits": metrics.hallucination_hits,
        "hallucination_retry_rounds": metrics.hallucination_retry_rounds,
        "doom_loop_skips": metrics.doom_loop_skips,
        "read_only_rounds": metrics.read_only_rounds,
        "text_and_tool_rounds": metrics.text_and_tool_rounds,
        "plan_complete_early": metrics.plan_complete_early,
        "subagent_spawned": metrics.subagent_spawned,
        "subagent_types": metrics.subagent_types,
        "subagent_blocked": metrics.subagent_blocked,
        "compactions": metrics.compactions,
        "sitreps": metrics.sitreps,
        "drift_corrections": metrics.drift_corrections,
        "kb_mutation_stops": metrics.kb_mutation_stops,
        "cancellations": metrics.cancellations,
        "finish_reason": metrics.finish_reason,
        "total_tokens": metrics.total_tokens,
    }

    try:
        with open(metrics_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("Failed to persist metrics: %s", e)


def _loop_metrics_dict(metrics) -> dict:
    """Extract key metrics from LoopMetrics for done/agent_metrics events.
    Non-breaking addition — existing consumers ignore unknown keys."""
    result = {
        "llm_calls": metrics.llm_calls,
        "tool_calls": metrics.tool_calls,
        "rounds": metrics.rounds,
        "compactions": metrics.compactions,
        "finish_reason": metrics.finish_reason,
        "hallucination_hits": metrics.hallucination_hits,
        "drift_corrections": metrics.drift_corrections,
        "subagent_spawned": metrics.subagent_spawned,
    }
    if hasattr(metrics, "tool_names") and metrics.tool_names:
        result["tool_names"] = dict(metrics.tool_names)
    return result
