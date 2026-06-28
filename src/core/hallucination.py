# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Hallucination detection — structural verification, not keyword scanning.

Previous versions had 8 layers of keyword/regex matching on the model's text
output. This caused persistent false positives because Chinese words like
"完成"/"成功"/"已删除"/"我来" are ubiquitous in normal writing and conversation.

The industry consensus (OpenAI SDK, LangChain, Anthropic, Cursor) is: don't
scan text for action claims. The ``tool_calls`` field is already a separate
structured channel — if it's empty, nothing executes. Period.

This module retains only the two detection layers that catch patterns the
structural protocol CAN'T cover:

  Layer 1 (fake_tool):  Model narrates calling a tool in natural language —
                        "我调用了 write_chapter" — without emitting tool_calls.
                        This is a specific, dangerous fabrication.

  Layer 2 (fake_write): Model claims to have written/edited a specific chapter
                        with word counts/save confirmation — "第3章已完成，共6000字"
                        — without emitting tool_calls. This is the most damaging
                        hallucination because it convinces the user work was done.

All other layers (past-tense claims, future promises, investigation plans,
sequential narration, data fabrication, acknowledgment traps) have been
removed. They caused more false positives than true positives.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ── Layer 1: Fake tool narration ────────────────────────────────────────────
TOOL_NAME_PATTERNS = [
    "write_chapter", "delegate_writing", "edit_chapter", "store_chapter",
    "extract_knowledge", "extract_all_chapters", "import_chapters",
    "list_chapters", "read_chapter", "delete_chapter", "batch_edit_chapters",
    "generate_outline", "generate_timeline", "generate_detailed_outline",
    "generate_worldbuilding", "generate_location_map",
    "search_knowledge", "add_knowledge", "update_knowledge",
    "create_volume", "delete_volume", "list_volumes",
    "run_review", "manage_reviewers",
    "web_search", "web_fetch",
    "store_inspiration", "list_inspirations",
]
TOOL_NARRATION_PREFIXES = [
    "调用了", "调用", "使用了", "使用", "执行了", "执行",
    "运行了", "运行", "启动了", "启动",
]

# ── Layer 2: Fake write/edit completion ──────────────────────────────────────
CHAPTER_REF_PATTERNS = [
    r"第\s*\d+\s*章",
    r"第\s*[一二三四五六七八九十百零\d]+\s*章",
    r"番外\s*\d+",
    r"#E?\d+",
    r"第\s*\d+\s*节",
]
WRITE_ACTION_KEYWORDS = [
    "写了", "写入", "写完", "创作了", "撰写了",
    "修改了", "编辑了", "改写了", "调整了", "重写了",
    "增加了", "添加了", "删除了", "补充了", "优化了",
    "润色了", "扩写了", "缩写了", "修订了", "更新了",
]
WORD_COUNT_PATTERNS = [
    r"写了\s*\d+\s*字",
    r"约\s*\d+\s*字",
    r"大约\s*\d+\s*字",
    r"近\s*\d+\s*字",
    r"超过\s*\d+\s*字",
    r"不到\s*\d+\s*字",
    r"字数\s*[约为达到]*\s*\d+",
    r"\d+\s*余字",
    r"\d+\s*字左右",
    r"\d+\s*多字",
    r"\d+\s*字的",
    r"篇幅\s*\d+",
    r"共\s*\d+\s*字",
    r"共计\s*\d+\s*字",
]
SAVE_CONFIRM_KEYWORDS = [
    "保存成功", "已保存到", "成功保存", "成功写入",
    "写入成功", "已存入", "存储成功", "保存完毕",
]


@dataclass
class HallucinationResult:
    """Result of hallucination detection."""
    detected: bool
    layer: str  # "fake_tool", "fake_write", or ""
    matched_keywords: list[str]

    @property
    def should_retry(self) -> bool:
        return self.detected


def detect_hallucination(text: str) -> HallucinationResult:
    """Check if text contains fabricated tool calls or write completions.

    Only two patterns are checked:
    - **fake_tool**: "我调用了 write_chapter" (narrating a tool call in text)
    - **fake_write**: "第3章已完成，共6000字" (claiming chapter written with specifics)

    All other patterns (past-tense claims, future promises, investigation plans,
    sequential narration, data fabrication, acknowledgment traps) have been
    removed — they caused too many false positives on normal Chinese text.

    Args:
        text: The LLM's response text (stripped).

    Returns:
        HallucinationResult indicating which layer was triggered, if any.
    """
    if not text:
        return HallucinationResult(detected=False, layer="", matched_keywords=[])

    # Layer 1: Fake tool narration
    fake_tool = _detect_fake_tool_narration(text)
    if fake_tool:
        return HallucinationResult(
            detected=True,
            layer="fake_tool",
            matched_keywords=fake_tool,
        )

    # Layer 2: Fake write/edit completion
    fake_write = _detect_fake_write_completion(text)
    if fake_write:
        return HallucinationResult(
            detected=True,
            layer="fake_write",
            matched_keywords=fake_write,
        )

    return HallucinationResult(detected=False, layer="", matched_keywords=[])


def _detect_fake_tool_narration(text: str) -> list[str]:
    """Detect when agent describes calling tools in natural language.

    Examples:
    - "我调用了 write_chapter 工具"
    - "使用 delegate_writing 写入了第1章"
    - "执行了 edit_chapter 来修改"
    """
    found = []
    for tool_name in TOOL_NAME_PATTERNS:
        if tool_name in text:
            # Check if it's in a narration context (preceded by action verbs)
            for prefix in TOOL_NARRATION_PREFIXES:
                # Pattern: "prefix + ... + tool_name" within ~30 chars
                pattern = rf"{re.escape(prefix)}.{{0,20}}{re.escape(tool_name)}"
                if re.search(pattern, text):
                    found.append(f"{prefix}{tool_name}")
                    break
            # Also check if tool_name is followed by action verbs ("write_chapter 写入了")
            action_suffixes = ["写入", "修改", "编辑", "删除", "提取", "保存", "创建", "生成"]
            for suffix in action_suffixes:
                if f"{tool_name} {suffix}" in text or f"{tool_name}{suffix}" in text:
                    if f"{tool_name}{suffix}" not in found:
                        found.append(f"{tool_name}{suffix}")
                    break
    return found


def _detect_fake_write_completion(text: str) -> list[str]:
    """Detect when agent claims to have written/edited chapters with specific details
    but no tool calls were made.

    This catches the most common hallucination pattern:
    "第3章已完成，共6000字，增加了叶凡与林婉的对手戏..."
    — chapter reference + write/edit verb + word count or save confirmation.

    Detection logic (requires combination, not single keyword):
      1. Chapter reference exists (第N章, 番外N, etc.)
      2. AND write/edit action verb exists (写了, 修改了, etc.)
      3. AND (word count claim OR save confirmation) exists
    All three conditions must be met to avoid false positives on legitimate summaries.
    """
    found = []

    # Check 1: chapter reference
    has_chapter_ref = False
    for pat in CHAPTER_REF_PATTERNS:
        if re.search(pat, text):
            has_chapter_ref = True
            found.append(f"chapter_ref:{pat}")
            break

    if not has_chapter_ref:
        return []

    # Check 2: write/edit action verb
    matched_actions = [kw for kw in WRITE_ACTION_KEYWORDS if kw in text]
    if not matched_actions:
        return []
    found.append(f"write_action:{','.join(matched_actions[:3])}")

    # Check 3a: word count claim
    has_word_count = False
    for pat in WORD_COUNT_PATTERNS:
        if re.search(pat, text):
            has_word_count = True
            found.append(f"word_count:{pat}")
            break

    # Check 3b: save confirmation
    matched_saves = [kw for kw in SAVE_CONFIRM_KEYWORDS if kw in text]
    if matched_saves:
        has_word_count = True
        found.append(f"save_confirm:{','.join(matched_saves[:3])}")

    if not has_word_count:
        return []

    return found
