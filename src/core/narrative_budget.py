# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Narrative-budget contracts for long-form chapter generation.

An output-token limit only controls length; it does not stop a model from
compressing an entire chapter arc into the first segment.  Segment contracts
separate *prose budget* from *plot budget*: each call receives one allowed
beat, an explicit stopping state, and future beats it must not consume.
"""

from __future__ import annotations

import json
import math
from contextvars import copy_context
from dataclasses import dataclass, field
from typing import Any

from .utils import safe_json_parse


@dataclass
class NarrativeSegmentContract:
    index: int
    total: int
    beat: str
    target_chars: int
    max_chars: int
    must_cover: list[str] = field(default_factory=list)
    forbidden_future: list[str] = field(default_factory=list)
    start_state: str = ""
    end_state: str = ""
    open_threads: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "total": self.total,
            "beat": self.beat,
            "target_chars": self.target_chars,
            "max_chars": self.max_chars,
            "must_cover": self.must_cover,
            "forbidden_future": self.forbidden_future,
            "start_state": self.start_state,
            "end_state": self.end_state,
            "open_threads": self.open_threads,
        }

    def render_prompt(self, previous_ending: str = "") -> str:
        previous = f"...​{previous_ending[-350:]}" if previous_ending else "（本章开头）"
        required = "；".join(self.must_cover) if self.must_cover else self.beat
        forbidden = "\n".join(f"- {item}" for item in self.forbidden_future[:6]) or "- 无明示后续事件"
        open_threads = "；".join(self.open_threads) if self.open_threads else "保留下一段的可推进空间"
        end_state = self.end_state or "只到达当前事件的直接结果，不得进入下一事件"
        start_state = self.start_state or "承接上一段的最后现场状态"
        return f"""# 分段创作合同（第 {self.index}/{self.total} 段）

前文结尾：{previous}
本段起始状态：{start_state}
本段唯一允许推进的事件：{self.beat}
本段必须覆盖：{required}
本段停止状态：{end_state}
本段结束时仍需保留：{open_threads}

下列是未来剧情边界，本段只能把它们当作“不得越过的警戒线”：
{forbidden}

【双重预算】
- 文字预算：目标 {self.target_chars} 个中文字符左右，硬上限 {self.max_chars} 字符。
- 剧情预算：只能消耗“本段唯一允许推进的事件”，不得总结或完成整章。
- 禁止用概述、蒙太奇或时间跳跃把后续事件塞进本段。
- 如本段不是最后一段，禁止使用全章总结、大结局或封闭式收尾。

直接输出连续的小说正文，不得输出标题、解释、步骤或合同内容。"""


@dataclass(frozen=True)
class BoundaryCheck:
    passed: bool
    reason: str = ""
    evidence: str = ""
    check_available: bool = True


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return str(value).strip()


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [text for item in value if (text := _as_text(item))]
    text = _as_text(value)
    return [text] if text else []


def _event_summary(event: Any) -> str:
    if isinstance(event, dict):
        for key in ("beat", "event", "summary", "text", "name"):
            if value := _as_text(event.get(key)):
                return value
        return json.dumps(event, ensure_ascii=False)
    return _as_text(event)


def _expand_beats(beats: list[Any], count: int) -> list[dict[str, Any]]:
    """Deterministic fallback when the planning model cannot return JSON."""

    if not beats:
        beats = ["按用户指令逐步推进当前场景"]
    expanded: list[dict[str, Any]] = []
    for index in range(count):
        source_index = min(len(beats) - 1, int(index * len(beats) / count))
        source = _event_summary(beats[source_index])
        same_source_slots = [i for i in range(count) if min(len(beats) - 1, int(i * len(beats) / count)) == source_index]
        phase = same_source_slots.index(index) + 1
        phase_total = len(same_source_slots)
        phase_note = f"（展开阶段 {phase}/{phase_total}）" if phase_total > 1 else ""
        expanded.append(
            {
                "beat": f"{source}{phase_note}",
                "must_cover": [f"只推进「{source}」的当前阶段"],
                "end_state": (
                    f"停在「{source}」的阶段 {phase}/{phase_total}，不得跳到后续事件"
                    if phase_total > 1
                    else "停在当前事件的直接结果"
                ),
                "open_threads": ["后续事件尚未发生"],
            }
        )
    return expanded


async def plan_segment_contracts(
    loop,
    *,
    source_beats: list[Any],
    instruction: str,
    target_chars: int,
    max_segment_chars: int = 2000,
) -> list[dict[str, Any]]:
    """Split a long writing task into semantic contracts before prose starts."""

    segment_count = max(2, min(12, math.ceil(max(target_chars, 1) / max(max_segment_chars, 1))))
    source = [_event_summary(item) for item in source_beats if _event_summary(item)]
    prompt = f"""请把下面的章节任务拆成恰好 {segment_count} 个连续写作段。
目标总字数：{target_chars}；每段硬上限：{max_segment_chars}。

用户指令：
{instruction[:3000]}

已有事件链：
{json.dumps(source, ensure_ascii=False)}

只输出 JSON：
{{"segments":[{{"beat":"本段唯一推进的事件","must_cover":["必须出现的局部节拍"],"start_state":"起始状态","end_state":"必须停下的状态","open_threads":["未解决问题"]}}]}}

要求：剧情只能向前推进，不得重复；前 {segment_count - 1} 段不得完成整章任务；
每段 end_state 必须可验证；每段只承担总剧情的一部分。"""

    def _run_plan() -> str:
        from .llm_client import chat

        return chat(
            prompt,
            system="你是长篇叙事分段规划器，只分配剧情预算，不写正文。",
            temperature=0.1,
            task="extraction",
        )

    try:
        raw = await loop.run_in_executor(None, copy_context().run, _run_plan)
        parsed = safe_json_parse(raw, default={})
        segments = parsed.get("segments", []) if isinstance(parsed, dict) else []
        if isinstance(segments, list) and len(segments) == segment_count:
            return [segment if isinstance(segment, dict) else {"beat": _as_text(segment)} for segment in segments]
    except Exception:
        pass
    return _expand_beats(source_beats, segment_count)


def build_segment_contracts(
    events: list[Any],
    *,
    target_chars: int,
    max_segment_chars: int,
) -> list[NarrativeSegmentContract]:
    clean_events = [event for event in events if _event_summary(event)]
    if not clean_events:
        return []
    total = len(clean_events)
    default_target = max(200, min(max_segment_chars, math.ceil(target_chars / total)))
    summaries = [_event_summary(event) for event in clean_events]
    contracts: list[NarrativeSegmentContract] = []
    for index, event in enumerate(clean_events):
        data = event if isinstance(event, dict) else {}
        explicit_forbidden = _as_list(data.get("must_not_cover") or data.get("forbidden_future"))
        future = explicit_forbidden + summaries[index + 1 :]
        contracts.append(
            NarrativeSegmentContract(
                index=index + 1,
                total=total,
                beat=summaries[index],
                target_chars=int(data.get("target_chars") or default_target),
                max_chars=int(data.get("max_chars") or max_segment_chars),
                must_cover=_as_list(data.get("must_cover")) or [summaries[index]],
                forbidden_future=list(dict.fromkeys(future)),
                start_state=_as_text(data.get("start_state")),
                end_state=_as_text(data.get("end_state")),
                open_threads=_as_list(data.get("open_threads")),
            )
        )
    return contracts


async def check_segment_boundary(loop, text: str, contract: NarrativeSegmentContract) -> BoundaryCheck:
    """Use a small judging call to detect narrative scope collapse."""

    clean = (text or "").strip()
    if len(clean) > contract.max_chars:
        return BoundaryCheck(
            False,
            f"文字预算超限：{len(clean)} > {contract.max_chars}",
            clean[contract.max_chars : contract.max_chars + 120],
        )
    if not contract.forbidden_future or contract.index >= contract.total:
        return BoundaryCheck(True)

    prompt = f"""判断当前小说片段是否偷跑到后续剧情。你只做边界分类，不评价文风，不改写。

当前允许事件：{contract.beat}
规定停止状态：{contract.end_state or '停在当前事件直接结果'}
必须保留：{json.dumps(contract.open_threads, ensure_ascii=False)}
未来事件（只用于检查是否越界）：{json.dumps(contract.forbidden_future[:8], ensure_ascii=False)}

待检查正文：
{clean[: max(contract.max_chars + 500, 2500)]}

如正文已经完成、确认、总结或用蒙太奇带过任一未来事件，则 passed=false。
仅有自然的伏笔或情绪预示，且事件尚未发生，可以 passed=true。
只输出 JSON：{{"passed":true,"reason":"","evidence":""}}"""

    def _run_check() -> str:
        from .llm_client import chat

        return chat(
            prompt,
            system="你是保守的叙事边界检查器，只根据提供的当前和未来事件判断。",
            temperature=0.0,
            task="extraction",
        )

    try:
        raw = await loop.run_in_executor(None, copy_context().run, _run_check)
        parsed = safe_json_parse(raw, default=None)
        if isinstance(parsed, dict) and isinstance(parsed.get("passed"), bool):
            return BoundaryCheck(
                passed=parsed["passed"],
                reason=_as_text(parsed.get("reason")),
                evidence=_as_text(parsed.get("evidence")),
            )
    except Exception as exc:
        return BoundaryCheck(True, f"边界检查不可用: {str(exc)[:100]}", check_available=False)
    return BoundaryCheck(True, "边界检查返回格式无法解析", check_available=False)
