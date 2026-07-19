# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Prophecy Parser — extract prophetic/omen text from novel chapters.

Extracts judgment poems, flower tags, drinking games, lantern riddles,
couplets, and dream omens from chapter text, parsing them into structured
ForeshadowNode instances for the foreshadow network.

Pure Python deterministic analysis with regex-based pattern matching.
No LLM calls — results are reproducible.

To add novel-specific prophecy patterns (e.g. specific judgment poems or
prophecy verses), extend ``extract_prophecies_from_text`` with additional
pattern logic rather than modifying the general patterns here.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from data.json_store import json_store

from .foreshadow_network import ForeshadowNode, ForeshadowType

logger = logging.getLogger(__name__)


# ── General prophecy patterns (novel-agnostic) ──────────────────────────

# 判词
_GENERAL_POEM_PATTERN = re.compile(
    r"(?:判词|判语)[：:]\s*([^\n]{5,200})"
)

# 花签/酒令
_FLOWER_TAG_PATTERN = re.compile(
    r"(?:花签|签上|签诗|签语|令)[：:：]?\s*([^\n]{5,200})"
)

# 灯谜
_LANTERN_RIDDLE_PATTERN = re.compile(
    r"(?:灯谜|谜语|谜面|谜)[：:：]?\s*([^\n]{5,200})"
)

# 对联/匾额
_COUPLET_PATTERN = re.compile(
    r"(?:对联|对子|匾额|联云|联语)[：:：]?\s*([^\n]{5,100})"
)

# 梦境/预兆（通用）
_DREAM_PATTERN = re.compile(
    r"(?:梦见|梦到|梦游|梦中|恍惚|魂游|神游)[^\n]{10,}"
)


def extract_prophecies_from_text(text: str) -> list[dict[str, Any]]:
    """从文本中提取所有预叙性内容。

    Returns:
        list of dict with keys: type (ForeshadowType), raw_text, context
    """
    results: list[dict[str, Any]] = []

    # 判词
    for m in _GENERAL_POEM_PATTERN.finditer(text):
        results.append({
            "type": ForeshadowType.PROPHECY_POEM,
            "raw_text": m.group(1).strip()[:100],
            "context": m.group(0)[:80],
        })

    # 花签/酒令
    for m in _FLOWER_TAG_PATTERN.finditer(text):
        results.append({
            "type": ForeshadowType.PROPHECY_POEM,
            "raw_text": m.group(1).strip()[:80],
            "context": m.group(0)[:60],
        })

    # 灯谜
    for m in _LANTERN_RIDDLE_PATTERN.finditer(text):
        results.append({
            "type": ForeshadowType.PROPHECY_POEM,
            "raw_text": m.group(1).strip()[:80],
            "context": m.group(0)[:60],
        })

    # 对联/匾额
    for m in _COUPLET_PATTERN.finditer(text):
        results.append({
            "type": ForeshadowType.PROPHECY_POEM,
            "raw_text": m.group(1).strip()[:80],
            "context": m.group(0)[:60],
        })

    # 梦境/预兆
    for m in _DREAM_PATTERN.finditer(text):
        results.append({
            "type": ForeshadowType.DREAM_OMEN,
            "raw_text": m.group(0)[:80],
            "context": m.group(0)[:60],
        })

    return results


def build_foreshadow_from_prophecy(
    prophecy: dict[str, Any],
    source_chapter: int,
    book_id: str = "default",
    linked_entity_hints: dict[str, list[str]] | None = None,
) -> ForeshadowNode:
    """将提取的预叙文本转为 ForeshadowNode。

    Args:
        prophecy: extract_prophecies_from_text 返回的单个条目
        source_chapter: 预叙所在的章节号
        book_id: 书籍ID
        linked_entity_hints: 可选，{实体名: [关键词列表]} 映射，
            用于将预叙文本与特定实体关联（如判词对应角色命运）。
    """
    import uuid
    raw = prophecy.get("raw_text", "")
    fs_type = prophecy.get("type", ForeshadowType.EVENT_FORESHADOW)

    linked_entities: list[str] = []
    hints_at: list[str] = []

    if linked_entity_hints:
        for entity_name, keywords in linked_entity_hints.items():
            for kw in keywords:
                if kw in raw:
                    if entity_name not in linked_entities:
                        linked_entities.append(entity_name)
                    hints_at.append(f"{entity_name}: {kw}")
                    break

    if not hints_at:
        hints_at.append(f"预叙: {raw[:60]}")

    return ForeshadowNode(
        id=f"fs_{uuid.uuid4().hex[:8]}",
        type=fs_type,
        description=raw[:200],
        source_chapter=source_chapter,
        linked_entities=linked_entities,
        hints_at_outcomes=hints_at,
        confidence=0.7 if linked_entities else 0.4,
        project_id=book_id,
    )


def extract_all_prophecies_from_book(
    book_id: str,
    linked_entity_hints: dict[str, list[str]] | None = None,
) -> list[ForeshadowNode]:
    """从全书所有章节提取预叙节点。

    Args:
        book_id: 书籍ID
        linked_entity_hints: 可选，传给 build_foreshadow_from_prophecy
            用于将预叙文本与实体关联。

    Returns:
        预叙 ForeshadowNode 列表
    """
    chapters = json_store.load_chapters(book_id)
    results: list[ForeshadowNode] = []

    for ch in chapters:
        view = json_store._chapter_view(ch)
        content = view.get("content", "")
        ch_title = view.get("title", "")
        ch_number = _extract_chapter_number(ch_title, ch.get("index", 0))

        prophecies = extract_prophecies_from_text(content)
        for prop in prophecies:
            node = build_foreshadow_from_prophecy(
                prop, source_chapter=ch_number, book_id=book_id,
                linked_entity_hints=linked_entity_hints,
            )
            results.append(node)

    logger.info(
        "Extracted %d prophecies from book %s (%d chapters)",
        len(results), book_id, len(chapters),
    )
    return results


def _extract_chapter_number(title: str, fallback: int) -> int:
    """从回目提取回数。如 '第一回' → 1。"""
    m = re.match(r"第[一二三四五六七八九十百千]+回", title)
    if not m:
        return fallback
    cn_num = m.group(0)[1:-1]  # 去掉"第"和"回"
    cn_map = {
        "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
        "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
        "百": 100, "千": 1000,
    }
    total = 0
    temp = 0
    for ch in cn_num:
        if ch in cn_map:
            val = cn_map[ch]
            if val >= 10:
                temp = max(temp, 1) * val
            else:
                temp += val
        else:
            total += temp
            temp = 0
    total += temp
    return total if total > 0 else fallback


def print_prophecy_summary(book_id: str) -> None:
    """Print a summary of prophecies found in a book."""
    nodes = extract_all_prophecies_from_book(book_id)
    if not nodes:
        print(f"书中未找到预叙内容（{book_id}）")
        return

    type_counter: dict[str, int] = {}
    for n in nodes:
        type_counter[n.type.value] = type_counter.get(n.type.value, 0) + 1

    print(f"\n=== 预叙提取报告: {book_id} ===")
    print(f"总计: {len(nodes)} 处预叙")
    for t, count in sorted(type_counter.items(), key=lambda x: -x[1]):
        print(f"  {t}: {count} 处")
    print()

    chapters: dict[int, list[ForeshadowNode]] = {}
    for n in nodes:
        chapters.setdefault(n.source_chapter, []).append(n)

    for ch in sorted(chapters.keys()):
        print(f"  第{ch}回 ({len(chapters[ch])}处):")
        for n in chapters[ch][:3]:
            print(f"    [{n.type.value}] {n.description[:60]}")
        if len(chapters[ch]) > 3:
            print(f"    ... 还有{len(chapters[ch]) - 3}处")


if __name__ == "__main__":
    import sys
    book_id = sys.argv[1] if len(sys.argv) > 1 else "default"
    print_prophecy_summary(book_id)
