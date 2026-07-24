# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Narrative pacing analyzer — pure-function text statistics for chapter rhythm.

Computes 5 pacing dimensions per chapter and a composite score (0-100).
No LLM calls, no external dependencies beyond the Python standard library.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import Any

from data.json_store import json_store

# ── Simple Chinese sentiment lexicon (curated minimal set) ──

_POSITIVE_WORDS: frozenset[str] = frozenset(
    {
        "高兴",
        "快乐",
        "开心",
        "兴奋",
        "喜悦",
        "幸福",
        "欢喜",
        "欣慰",
        "激动",
        "感激",
        "感动",
        "温暖",
        "希望",
        "美好",
        "喜欢",
        "爱",
        "期待",
        "安心",
        "满意",
        "骄傲",
        "自信",
        "勇气",
        "光明",
        "胜利",
        "成功",
        "笑",
        "笑意",
    }
)

_NEGATIVE_WORDS: frozenset[str] = frozenset(
    {
        "悲伤",
        "痛苦",
        "愤怒",
        "恐惧",
        "绝望",
        "孤独",
        "寂寞",
        "寒冷",
        "黑暗",
        "死",
        "杀",
        "血",
        "泪",
        "哭",
        "恨",
        "怒",
        "惊",
        "恐",
        "慌",
        "乱",
        "失败",
        "失去",
        "离别",
        "背叛",
        "欺骗",
        "危险",
        "威胁",
        "压迫",
        "窒息",
    }
)

# Scene-transition cue words (time / location shifts)
_SCENE_CUES: tuple[str, ...] = (
    "第二天",
    "次日",
    "三天后",
    "一周后",
    "一个月后",
    "数日后",
    "几天后",
    "此时",
    "与此同时",
    "另一边",
    "另一处",
    "回到",
    "来到",
    "走进",
    "走出",
    "离开",
    "抵达",
    "出发",
    "入夜",
    "清晨",
    "黄昏",
    "夜晚",
    "午后",
)

# Sentence-ending punctuation for Chinese + English
_SENTENCE_ENDS = re.compile(r"[。！？!?…]+")


@dataclass
class PacingMetrics:
    """Five-dimension pacing metrics for a single chapter."""

    dialogue_ratio: float = 0.0  # 0-1, proportion of dialogue text
    sentence_length_variance: float = 0.0  # std-dev of sentence lengths
    scene_transition_count: int = 0  # raw count of scene shifts
    emotional_volatility: float = 0.0  # count of sentiment sign flips
    pacing_score: float = 0.0  # 0-100 composite

    def to_dict(self) -> dict[str, Any]:
        return {
            "dialogue_ratio": round(self.dialogue_ratio, 3),
            "sentence_length_variance": round(self.sentence_length_variance, 2),
            "scene_transition_count": self.scene_transition_count,
            "emotional_volatility": round(self.emotional_volatility, 2),
            "pacing_score": round(self.pacing_score, 1),
        }


@dataclass
class ChapterPacing:
    """Pacing data for a single chapter within a book context."""

    chapter_id: str = ""
    title: str = ""
    chapter_index: int = 0
    word_count: int = 0
    metrics: PacingMetrics = field(default_factory=PacingMetrics)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chapter_id": self.chapter_id,
            "title": self.title,
            "chapter_index": self.chapter_index,
            "word_count": self.word_count,
            **self.metrics.to_dict(),
        }


# ── Core analysis functions ──


def _extract_dialogues(content: str) -> list[str]:
    """Extract dialogue text within Chinese quotation marks.

    Supports both 「」 and "" styles.
    """
    # Chinese curly quotes \u201c \u201d
    dialogues: list[str] = []
    # Match text between Chinese double quotes
    for m in re.finditer(r"\u201c([^\u201d]+)\u201d", content):
        dialogues.append(m.group(1))
    # Also match corner brackets
    for m in re.finditer(r"\u300c([^\u300d]+)\u300d", content):
        dialogues.append(m.group(1))
    return dialogues


def _split_sentences(content: str) -> list[str]:
    """Split content into sentences by Chinese/English sentence-ending punctuation."""
    parts = _SENTENCE_ENDS.split(content)
    return [p.strip() for p in parts if p.strip()]


def _count_scene_transitions(content: str) -> int:
    """Count scene transitions by detecting cue words and paragraph breaks."""
    count = 0
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    # Cue-word detection
    for cue in _SCENE_CUES:
        count += content.count(cue)
    # Extra weight for paragraph-level breaks that start with a cue
    for para in paragraphs[1:]:  # skip first paragraph
        first_chars = para[:6]
        for cue in _SCENE_CUES:
            if cue in first_chars:
                count += 1
                break
    return count


def _compute_emotional_volatility(content: str) -> float:
    """Compute sentiment sign-flip count over sliding windows.

    Scans the text in ~200-char windows, counts positive/negative word
    presence, and tallies how many times the sentiment polarity flips.
    """
    window_size = 200
    polarities: list[int] = []  # +1, -1, 0
    for i in range(0, len(content), window_size):
        chunk = content[i : i + window_size]
        pos = sum(1 for w in _POSITIVE_WORDS if w in chunk)
        neg = sum(1 for w in _NEGATIVE_WORDS if w in chunk)
        if pos > neg:
            polarities.append(1)
        elif neg > pos:
            polarities.append(-1)
        else:
            polarities.append(0)

    # Count sign flips (ignoring zeros)
    flips = 0
    last_sign = 0
    for p in polarities:
        if p == 0:
            continue
        if last_sign != 0 and p != last_sign:
            flips += 1
        last_sign = p
    return float(flips)


def analyze_chapter(content: str) -> PacingMetrics:
    """Analyze a single chapter's text and return pacing metrics.

    Pure function — no side effects, no I/O.
    """
    if not content or not content.strip():
        return PacingMetrics()

    # Strip whitespace for word counting
    clean = content.replace("\n", "").replace(" ", "").replace("\r", "")
    total_chars = len(clean)
    if total_chars == 0:
        return PacingMetrics()

    # 1. Dialogue ratio
    dialogues = _extract_dialogues(content)
    dialogue_chars = sum(len(d) for d in dialogues)
    dialogue_ratio = dialogue_chars / total_chars if total_chars > 0 else 0.0

    # 2. Sentence length variance
    sentences = _split_sentences(content)
    sentence_lengths = [len(s.replace(" ", "")) for s in sentences if len(s.strip()) > 2]
    if len(sentence_lengths) >= 2:
        sentence_length_variance = statistics.pstdev(sentence_lengths)
    else:
        sentence_length_variance = 0.0

    # 3. Scene transitions
    scene_transitions = _count_scene_transitions(content)

    # 4. Emotional volatility
    emotional_volatility = _compute_emotional_volatility(content)

    # 5. Composite pacing score (0-100)
    # Higher dialogue ratio → faster pace
    # Higher sentence length variance → more dynamic (faster perceived pace)
    # More scene transitions → faster pace
    # More emotional volatility → faster pace
    # All normalized to 0-100 range with clamp
    score = (
        min(dialogue_ratio * 100, 100) * 0.30
        + min(sentence_length_variance * 2, 100) * 0.20
        + min(scene_transitions * 5, 100) * 0.25
        + min(emotional_volatility * 10, 100) * 0.25
    )
    pacing_score = max(0.0, min(100.0, score))

    return PacingMetrics(
        dialogue_ratio=dialogue_ratio,
        sentence_length_variance=sentence_length_variance,
        scene_transition_count=scene_transitions,
        emotional_volatility=emotional_volatility,
        pacing_score=pacing_score,
    )


def analyze_book(book_id: str) -> list[ChapterPacing]:
    """Analyze all chapters in a book and return per-chapter pacing data.

    Reads chapter content from json_store. Regular chapters are numbered
    sequentially; extras get their own index after the regular set.
    """
    chapters = json_store.load_chapters(book_id)
    results: list[ChapterPacing] = []

    regular = [ch for ch in chapters if not ch.get("is_extra")]
    extras = [ch for ch in chapters if ch.get("is_extra")]

    idx = 0
    for ch in regular:
        idx += 1
        cur = json_store._get_current_version(ch)
        content = cur.get("content", "")
        metrics = analyze_chapter(content)
        word_count = cur.get("word_count") or len(content.replace("\n", "").replace(" ", ""))
        results.append(
            ChapterPacing(
                chapter_id=ch.get("id", ""),
                title=cur.get("title", ch.get("title", "")),
                chapter_index=idx,
                word_count=word_count,
                metrics=metrics,
            )
        )

    extra_idx = len(regular) + 1
    for ch in extras:
        cur = json_store._get_current_version(ch)
        content = cur.get("content", "")
        metrics = analyze_chapter(content)
        word_count = cur.get("word_count") or len(content.replace("\n", "").replace(" ", ""))
        results.append(
            ChapterPacing(
                chapter_id=ch.get("id", ""),
                title=cur.get("title", ch.get("title", "")),
                chapter_index=extra_idx,
                word_count=word_count,
                metrics=metrics,
            )
        )
        extra_idx += 1

    return results


def get_chapter_pacing(book_id: str, chapter_id: str) -> ChapterPacing | None:
    """Get pacing metrics for a single chapter by ID."""
    chapters = json_store.load_chapters(book_id)
    ch = json_store._resolve_by_id(chapters, chapter_id)
    if not ch:
        return None
    cur = json_store._get_current_version(ch)
    content = cur.get("content", "")
    metrics = analyze_chapter(content)
    word_count = cur.get("word_count") or len(content.replace("\n", "").replace(" ", ""))

    # Determine index
    all_chs = json_store.load_chapters(book_id)
    regular = [c for c in all_chs if not c.get("is_extra")]
    try:
        ch_index = next(i + 1 for i, c in enumerate(regular) if c.get("id") == ch.get("id"))
    except StopIteration:
        ch_index = 0

    return ChapterPacing(
        chapter_id=ch.get("id", ""),
        title=cur.get("title", ch.get("title", "")),
        chapter_index=ch_index,
        word_count=word_count,
        metrics=metrics,
    )
