"""Loop state, metrics, and drift/hallucination accounting for the agent loop.

Extracts the ~10 mutable local counters and the drift/KB/hallucination logic
out of the 900-line ``_loop_inner`` so they can be unit-tested and reasoned
about independently of the async-generator control flow.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from .config import config

logger = logging.getLogger(__name__)


# ── Thresholds (centralised, no longer magic numbers in the loop) ──
COMPLETION_CLAIM_LIMIT = 2  # N completion claims → force stop
VERIFY_LOOP_LIMIT = 2  # N verify/check loops → force stop
KB_MUTATION_LIMIT = 6  # N consecutive KB-mutating rounds → force stop
NON_KB_RESET_ROUNDS = 3  # read-only rounds before KB streak resets
WRITING_COOLDOWN_ROUNDS = 5  # rounds since last writing before cooling down

# Drift keyword sets — module-level so they are not rebuilt every iteration.
#
# IMPORTANT: These must only match phrases that signal REPETITION/RE-DOING —
# i.e. the model is undoing and redoing the same work in a loop. Generic
# completion words like "完成"/"已保存"/"已创建"/"已写入" appear in every
# legitimate progress report and MUST NOT be here, otherwise normal multi-step
# execution (update entity → "已更新" → create phase → "已创建") gets falsely
# flagged as drift and force-stopped.
DRIFT_COMPLETION_KEYWORDS = (
    # Re-doing signals — model is undoing/redoing the same operation
    "重新提取",
    "重新创建",
    "重新写入",
    "重新写",
    "删干净了",
    "删干净",
    "清理一下",
    "重新清理",
    "再删一遍",
    "再清理",
    "再来一遍",
    "重新来",
)
DRIFT_VERIFY_KEYWORDS = (
    # Re-checking signals — model keeps verifying the same thing in a loop
    "再检查",
    "再确认",
    "再看看",
    "再查一下",
    "重复实体",
    "重复的",
    "有重复",
    "看到有重复",
    "残留",
    "旧数据",
    "多条重复",
    "又出现重复",
)

# Read-only tools permitted as a single tail call after drift correction.
# Anything mutating state still force-stops, avoiding the old "one strike
# and you're out" behaviour that killed legitimate clean-up reads.
TAILSAFE_TOOLS = frozenset(
    {
        "search_knowledge",
        "list_chapters",
        "read_chapter",
        "get_outline",
        "get_timeline",
        "get_detailed_outline",
        "get_worldbuilding",
        "chapter_history",
        "diff_chapters",
        "count_words",
        "list_volumes",
        "list_references",
        "list_reference_chapters",
        "search_reference",
        "get_style",
        "list_styles",
        "list_skills",
        "list_workflows",
        "browse_workflows",
        "browse_materials",
        "search_materials",
    }
)


class WritingMode(Enum):
    IDLE = "idle"
    CREATIVE = "creative"
    COOLDOWN = "cooldown"


@dataclass
class LoopMetrics:
    """Observability counters. Logged at loop end so thresholds can be tuned
    from data instead of guesswork."""

    rounds: int = 0
    llm_calls: int = 0
    llm_retries: int = 0
    tool_calls: int = 0
    hallucination_hits: dict = field(default_factory=dict)
    compactions: int = 0
    sitreps: int = 0
    drift_corrections: int = 0
    kb_mutation_stops: int = 0
    tool_names: dict = field(default_factory=dict)  # tool_name -> call count
    cancellations: int = 0
    finish_reason: str = ""
    total_tokens: int = 0  # cumulative input+output tokens this run
    # ── Round categorisation (for efficiency analysis) ──
    hallucination_retry_rounds: int = 0  # rounds spent correcting hallucinations
    doom_loop_skips: int = 0  # rounds where doom loop prevented execution
    read_only_rounds: int = 0  # rounds with only read-only tool calls
    text_and_tool_rounds: int = 0  # rounds with both output text + tool calls
    plan_complete_early: bool = False  # whether plan complete short-circuited
    # ── Subagent tracking ──
    subagent_spawned: int = 0  # total subagents spawned this run
    subagent_types: dict = field(default_factory=dict)  # type -> count breakdown
    subagent_blocked: int = 0  # subagents blocked by plan-mode guard

    def record_hallucination(self, layer: str) -> None:
        self.hallucination_hits[layer] = self.hallucination_hits.get(layer, 0) + 1

    def summary(self) -> str:
        hits = self.hallucination_hits or "none"
        plan_flag = " plan_early" if self.plan_complete_early else ""
        subagent_info = ""
        if self.subagent_spawned > 0:
            type_breakdown = ",".join(f"{k}={v}" for k, v in sorted(self.subagent_types.items()))
            subagent_info = f" subagents={self.subagent_spawned} ({type_breakdown})"
        if self.subagent_blocked > 0:
            subagent_info += f" subagent_blocked={self.subagent_blocked}"
        return (
            f"rounds={self.rounds} llm_calls={self.llm_calls} "
            f"tool_calls={self.tool_calls} hallucination={hits} "
            f"hall_retries={self.hallucination_retry_rounds} doom_skips={self.doom_loop_skips} "
            f"readonly={self.read_only_rounds} mixed={self.text_and_tool_rounds} "
            f"compactions={self.compactions} sitreps={self.sitreps} "
            f"drift_corr={self.drift_corrections} kb_stops={self.kb_mutation_stops}"
            f"{subagent_info} "
            f"tokens={self.total_tokens} "
            f"finish={self.finish_reason}{plan_flag}"
        )


@dataclass
class LoopState:
    """All mutable per-run state for one agent loop, replacing the loose
    collection of local variables that previously lived inside ``_loop_inner``.
    """

    max_rounds: int = 0  # Hard safety cap
    soft_round_limit: int = 0  # Soft nudge threshold, defaults to max_rounds
    base_temperature: float = 0.3
    token_budget_limit: int = 0  # cumulative token cap; 0 = disabled

    # round accounting
    round: int = 0

    # Plan-detection: count nudges when the model writes intentions
    # ("我先...", "我来...") without tool_calls. Capped at 2 to prevent
    # infinite loops.
    plan_nudges: int = 0

    # Task-list state tracking — the task list is treated as a multi-step
    # state machine. Incomplete items are noted in the final done message
    # but never interrupt the loop.
    active_task_list_id: str = ""  # ID of the most recently created/updated task list

    # drift detection (two independent signals, no longer conflated)
    completion_claims: int = 0
    verify_loops: int = 0
    drift_corrected: bool = False
    tail_consumed: bool = False  # one read-only tail call allowed after correction

    # KB mutation guard (sliding window)
    kb_mutation_streak: int = 0
    non_kb_rounds: int = 0

    # writing-mode / temperature
    has_writing_output: bool = False
    rounds_since_writing: int = 0
    temperature: float = 0.0

    # Structured parts collected during this turn for history persistence.
    parts: list = field(default_factory=list)

    # Diagnostic context for abnormal_exit logging — last round's signal so
    # the finally block can log WHY the loop died (which tool, last LLM text).
    # Without this, abnormal_exit leaves no trace in server.log for diagnosis.
    last_tool_calls: str = ""       # last round's tool names (e.g. "extract_all_chapters")
    last_text_preview: str = ""     # last streamed_text preview (first 200 chars)

    def add_part(self, part) -> None:
        self.parts.append(part)

    metrics: LoopMetrics = field(default_factory=LoopMetrics)

    def __post_init__(self) -> None:
        self.temperature = self.base_temperature
        # soft_round_limit=0 means unlimited (no progressive warnings).

    # ── round accounting ──
    def advance_round(self) -> None:
        self.round += 1
        self.metrics.rounds = self.round

    def rewind_round(self) -> None:
        """Rewind one round so a hallucination retry doesn't consume the
        round budget. Clamped to 0 so it can never go negative."""
        self.round = max(0, self.round - 1)
        self.metrics.rounds = self.round

    # ── token budget accounting (industry-standard dual control: rounds + tokens) ──
    def record_token_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Accumulate input+output tokens for this round into the run total."""
        self.metrics.total_tokens += max(0, input_tokens) + max(0, output_tokens)

    @property
    def token_budget_exceeded(self) -> bool:
        """True when cumulative tokens hit the budget cap (0 = disabled)."""
        if self.token_budget_limit <= 0:
            return False
        return self.metrics.total_tokens >= self.token_budget_limit

    @property
    def exhausted(self) -> bool:
        """Hard safety cap. 0 = unlimited — behaviour-based guards (doom-loop,
        drift detection, KB mutation guard) still terminate pathological loops."""
        if self.max_rounds <= 0:
            return False
        return self.round >= self.max_rounds

    @property
    def rounds_remaining(self) -> int:
        if self.soft_round_limit <= 0:
            return 999_999  # effectively unlimited
        return max(0, self.soft_round_limit - self.round)

    @property
    def is_near_limit(self) -> bool:
        if self.soft_round_limit <= 0:
            return False
        return self.rounds_remaining <= 3 and self.rounds_remaining > 0

    @property
    def soft_limit_exceeded(self) -> bool:
        if self.soft_round_limit <= 0:
            return False
        return self.round >= self.soft_round_limit and self.round < self.max_rounds

    # ── writing mode / adaptive temperature ──
    def update_writing_mode(self, streamed_text: str) -> None:
        if streamed_text and len(streamed_text) > 200:
            self.has_writing_output = True
            self.rounds_since_writing = 0
            self.temperature = self.base_temperature
        elif not self.has_writing_output and self.round > 1:
            # Pure tool-operation chain: lower temperature to curb
            # "describing instead of doing". Toggleable for A/B testing.
            if getattr(config.agent, "adaptive_temperature", True):
                self.temperature = max(0.2, self.base_temperature * 0.5)
        else:
            self.temperature = self.base_temperature

        self.rounds_since_writing += 1
        if self.has_writing_output and self.rounds_since_writing >= WRITING_COOLDOWN_ROUNDS:
            self.has_writing_output = False

    # ── drift detection (signals kept separate) ──
    def classify_drift(self, streamed_text: str) -> tuple[bool, bool]:
        """Return ``(is_completion_claim, is_verify_loop)``. The two are no
        longer merged into one counter so their correction messages can differ."""
        if not streamed_text or len(streamed_text) <= 5:
            return False, False
        is_completion = any(kw in streamed_text for kw in DRIFT_COMPLETION_KEYWORDS)
        is_verify = any(kw in streamed_text for kw in DRIFT_VERIFY_KEYWORDS)
        return is_completion, is_verify

    def record_completion_claim(self) -> None:
        self.completion_claims += 1

    def record_verify_loop(self) -> None:
        self.verify_loops += 1

    @property
    def drift_limit_reached(self) -> bool:
        return self.completion_claims >= COMPLETION_CLAIM_LIMIT or self.verify_loops >= VERIFY_LOOP_LIMIT

    @property
    def drift_signal_label(self) -> str:
        if self.completion_claims >= COMPLETION_CLAIM_LIMIT:
            return "完成声明"
        return "验证循环"

    # ── KB mutation guard ──
    def record_kb_round(self) -> None:
        self.kb_mutation_streak += 1
        self.non_kb_rounds = 0

    def record_non_kb_round(self) -> None:
        self.non_kb_rounds += 1
        if self.non_kb_rounds >= NON_KB_RESET_ROUNDS:
            self.kb_mutation_streak = 0

    @property
    def kb_mutation_limit_reached(self) -> bool:
        return self.kb_mutation_streak >= KB_MUTATION_LIMIT

    def reset_kb_guard(self) -> None:
        self.kb_mutation_streak = 0

    # ── post-correction tail tool ──
    def allow_tail_tools(self, tool_names: set[str]) -> bool:
        """After a drift correction, allow a single round of read-only tools
        so the model can verify state before reporting. Anything mutating
        still force-stops."""
        if self.tail_consumed:
            return False
        return bool(tool_names) and tool_names.issubset(TAILSAFE_TOOLS)

    def consume_tail(self) -> None:
        self.tail_consumed = True
