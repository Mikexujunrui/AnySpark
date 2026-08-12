# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Structured chapter hand-off cards and conservative transition audits.

The card deliberately separates facts visible at the beginning and end of a
chapter.  That makes cross-chapter checks deterministic: only two explicit,
high-confidence values are compared, and missing information is never treated
as a contradiction.
"""

from __future__ import annotations

from typing import Any

_STATE_FIELDS = ("location", "physical_state", "held_items", "unfinished_action")
_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


def _clean_text(value: Any, limit: int = 180) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text[:limit]


def _fact(value: Any) -> tuple[Any, str, str]:
    """Return (value, confidence, evidence) from old or structured fields."""

    if isinstance(value, dict):
        return value.get("value"), str(value.get("confidence", "low")).lower(), _clean_text(value.get("evidence"))
    if value in (None, "", [], {}):
        return None, "low", ""
    return value, "low", ""


def _comparable(value: Any) -> str:
    if isinstance(value, list):
        return "|".join(sorted(_clean_text(item, 80) for item in value if _clean_text(item, 80)))
    return _clean_text(value).replace(" ", "")


def _character_map(card: dict, boundary: str) -> dict[str, dict]:
    state = card.get(boundary, {})
    if not isinstance(state, dict):
        return {}
    characters = state.get("characters", {})
    if isinstance(characters, list):
        return {
            _clean_text(item.get("name"), 80): item
            for item in characters
            if isinstance(item, dict) and _clean_text(item.get("name"), 80)
        }
    return characters if isinstance(characters, dict) else {}


def audit_transition(previous: dict | None, current: dict) -> dict:
    """Compare previous end state with current start state conservatively.

    A conflict is reported only when both sides explicitly provide the same
    field with high confidence and cite evidence.  This avoids turning a
    model's omission or guess into a false continuity alarm.
    """

    if not previous:
        return {"confirmed_conflicts": [], "checked_fields": 0}

    prev_characters = _character_map(previous, "end_state")
    curr_characters = _character_map(current, "start_state")
    conflicts: list[dict[str, str]] = []
    checked = 0

    for name in sorted(set(prev_characters) & set(curr_characters)):
        prev_state = prev_characters.get(name, {})
        curr_state = curr_characters.get(name, {})
        if not isinstance(prev_state, dict) or not isinstance(curr_state, dict):
            continue
        for field in _STATE_FIELDS:
            prev_value, prev_conf, prev_evidence = _fact(prev_state.get(field))
            curr_value, curr_conf, curr_evidence = _fact(curr_state.get(field))
            if prev_value in (None, "", [], {}) or curr_value in (None, "", [], {}):
                continue
            if _CONFIDENCE_RANK.get(prev_conf, 0) < 2 or _CONFIDENCE_RANK.get(curr_conf, 0) < 2:
                continue
            if not prev_evidence or not curr_evidence:
                continue
            checked += 1
            if _comparable(prev_value) == _comparable(curr_value):
                continue
            conflicts.append(
                {
                    "subject": name,
                    "field": field,
                    "previous": _clean_text(prev_value),
                    "current": _clean_text(curr_value),
                    "previous_evidence": prev_evidence,
                    "current_evidence": curr_evidence,
                }
            )

    return {"confirmed_conflicts": conflicts, "checked_fields": checked}


def format_continuity_cards(cards: list[dict], max_chars: int = 1800) -> str:
    """Render hand-off cards into a compact, evidence-aware writing prompt."""

    lines: list[str] = []
    for card in cards:
        chapter = card.get("chapter_index", "?")
        title = _clean_text(card.get("chapter_title"), 80)
        lines.append(f"### 第{chapter}章{(' ' + title) if title else ''}")

        time_info = card.get("chapter_time", {})
        if isinstance(time_info, dict):
            start = _clean_text(time_info.get("start"), 80)
            end = _clean_text(time_info.get("end"), 80)
            elapsed = _clean_text(time_info.get("elapsed"), 80)
            if start or end or elapsed:
                lines.append(f"主时间范围：{start or '未知'} → {end or '未知'}；经过：{elapsed or '未知'}")

        end_characters = _character_map(card, "end_state")
        for name, state in list(end_characters.items())[:8]:
            if not isinstance(state, dict):
                continue
            facts: list[str] = []
            for field, label in (("location", "地点"), ("physical_state", "身体"), ("held_items", "持有"), ("unfinished_action", "未完动作")):
                value, confidence, _ = _fact(state.get(field))
                if value not in (None, "", [], {}) and confidence != "low":
                    rendered = "、".join(map(str, value)) if isinstance(value, list) else str(value)
                    facts.append(f"{label}={rendered}")
            if facts:
                lines.append(f"- {name}：" + "；".join(facts))

        open_threads = card.get("open_threads", [])
        if isinstance(open_threads, list) and open_threads:
            lines.append("未完成事项：" + "；".join(_clean_text(item, 120) for item in open_threads[:5]))

        if not end_characters and card.get("text"):
            lines.append(_clean_text(card.get("text"), 360))

        audit = card.get("transition_audit", {})
        conflicts = audit.get("confirmed_conflicts", []) if isinstance(audit, dict) else []
        for conflict in conflicts[:4]:
            if isinstance(conflict, dict):
                lines.append(
                    "⛔ 已确认交接冲突："
                    f"{_clean_text(conflict.get('subject'), 60)}的{_clean_text(conflict.get('field'), 60)}，"
                    f"上一章={_clean_text(conflict.get('previous'), 80)}，本章开头={_clean_text(conflict.get('current'), 80)}"
                )

        if sum(len(line) for line in lines) >= max_chars:
            break

    return "\n".join(lines)[:max_chars]

