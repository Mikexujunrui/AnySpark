# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Reference work analyzer — structural analysis and style quantification.

Pure-Python deterministic analysis of imported reference books (原著).
No LLM calls — all metrics are computed from text statistics alone,
making results reproducible and cacheable.

Two main capabilities:
1. ``analyze_structure`` — per-chapter word count, dialogue ratio, paragraph
   stats, sentence stats, and a pacing curve across the whole book.
2. ``quantify_style`` — sentence length distribution, vocabulary richness
   (TTR), punctuation pattern, four-char idiom density, paragraph length
   stats, and dialogue density.

Results are cached as JSON files under ``data/analyses/`` and loaded by
``_build_reference_context`` in ``writer.py`` to inject constraints into
writing prompts.
"""

from __future__ import annotations

import json
import logging
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.config import DATA_DIR
from core.voice_fingerprint import _extract_all_dialogues
from data.json_store import json_store

logger = logging.getLogger(__name__)

# ── Storage ──────────────────────────────────────────────────────────────

ANALYSES_DIR = DATA_DIR / "analyses"
ANALYSES_DIR.mkdir(parents=True, exist_ok=True)

_FILE_MAP: dict[str, str] = {
    "structure": "structure_{book_id}.json",
    "style_fingerprint": "style_fingerprint_{book_id}.json",
}


def _analysis_path(analysis_type: str, book_id: str) -> Path:
    template = _FILE_MAP.get(analysis_type, "{analysis_type}_{book_id}.json")
    filename = template.format(book_id=book_id, analysis_type=analysis_type)
    return ANALYSES_DIR / filename


def load_analysis(analysis_type: str, ref_book_id: str) -> dict | None:
    """Load a cached analysis report. Returns ``None`` if not found."""
    path = _analysis_path(analysis_type, ref_book_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load analysis %s: %s", path, e)
        return None


def _save_analysis(analysis_type: str, book_id: str, data: dict) -> None:
    path = _analysis_path(analysis_type, book_id)
    try:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as e:
        logger.warning("Failed to save analysis %s: %s", path, e)


# ── Text utilities ───────────────────────────────────────────────────────

_SENTENCE_END_PATTERN = re.compile(r"[。！？!?…]+")


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences by Chinese/English sentence-ending punctuation."""
    parts = _SENTENCE_END_PATTERN.split(text)
    return [p.strip() for p in parts if p.strip()]


def _split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs by double-newline."""
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def _word_count(text: str) -> int:
    """Character count excluding whitespace (CJK-friendly)."""
    return len(text.replace("\n", "").replace(" ", "").replace("\t", ""))


def _load_chapter_contents(book_id: str) -> list[tuple[str, str]]:
    """Load all chapter (title, content) pairs from a book.

    Returns list of (title, content) tuples, using current version content.
    """
    chapters = json_store.load_chapters(book_id)
    results: list[tuple[str, str]] = []
    for ch in chapters:
        view = json_store._chapter_view(ch)
        title = view.get("title", "")
        content = view.get("content", "")
        if content:
            results.append((title, content))
    return results


# ── StructureReport ─────────────────────────────────────────────────────


@dataclass
class StructureReport:
    """Structural analysis of a reference book."""

    book_id: str = ""
    chapter_count: int = 0
    total_words: int = 0
    avg_chapter_length: float = 0.0
    chapter_length_distribution: list[int] = field(default_factory=list)
    dialogue_ratio_distribution: list[float] = field(default_factory=list)
    avg_dialogue_ratio: float = 0.0
    paragraph_stats: dict[str, Any] = field(default_factory=dict)
    sentence_stats: dict[str, Any] = field(default_factory=dict)
    pacing_curve: list[dict] = field(default_factory=list)
    pov_distribution: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "book_id": self.book_id,
            "chapter_count": self.chapter_count,
            "total_words": self.total_words,
            "avg_chapter_length": round(self.avg_chapter_length, 1),
            "chapter_length_distribution": self.chapter_length_distribution,
            "dialogue_ratio_distribution": [
                round(r, 3) for r in self.dialogue_ratio_distribution
            ],
            "avg_dialogue_ratio": round(self.avg_dialogue_ratio, 3),
            "paragraph_stats": self.paragraph_stats,
            "sentence_stats": self.sentence_stats,
            "pacing_curve": self.pacing_curve,
            "pov_distribution": self.pov_distribution,
        }

    def to_prompt_fragment(self) -> str:
        """Generate a writing-constraint prompt fragment from the structure report."""
        if not self.chapter_count:
            return ""
        lines = [
            f"原著共 {self.chapter_count} 章，{self.total_words} 字，"
            f"平均每章 {self.avg_chapter_length:.0f} 字。",
            f"平均对话占比 {self.avg_dialogue_ratio:.1%}。",
        ]
        para_avg = self.paragraph_stats.get("avg_per_chapter", 0)
        para_len = self.paragraph_stats.get("avg_length", 0)
        if para_avg:
            lines.append(f"平均每章 {para_avg:.0f} 段，每段约 {para_len:.0f} 字。")
        sent_avg = self.sentence_stats.get("avg_per_chapter", 0)
        sent_len = self.sentence_stats.get("avg_length", 0)
        if sent_avg:
            lines.append(f"平均每章 {sent_avg:.0f} 句，每句约 {sent_len:.0f} 字。")
        lines.append("续写时应保持相近的章节篇幅和对话密度。")
        return "\n".join(lines)


def analyze_structure(book_id: str) -> StructureReport:
    """Analyze the structural patterns of a reference book.

    Pure function — no LLM, no side effects except caching the result.
    """
    chapter_contents = _load_chapter_contents(book_id)
    if not chapter_contents:
        return StructureReport(book_id=book_id)

    chapter_lengths: list[int] = []
    dialogue_ratios: list[float] = []
    all_para_counts: list[int] = []
    all_para_lengths: list[int] = []
    all_sent_counts: list[int] = []
    all_sent_lengths: list[int] = []
    pacing_curve: list[dict] = []

    for idx, (title, content) in enumerate(chapter_contents):
        wc = _word_count(content)
        chapter_lengths.append(wc)

        # Dialogue ratio
        dialogues = _extract_all_dialogues(content)
        dialogue_chars = sum(len(d) for d in dialogues)
        ratio = dialogue_chars / wc if wc > 0 else 0.0
        dialogue_ratios.append(ratio)

        # Paragraph stats
        paragraphs = _split_paragraphs(content)
        all_para_counts.append(len(paragraphs))
        para_lens = [_word_count(p) for p in paragraphs if p]
        all_para_lengths.extend(para_lens)

        # Sentence stats
        sentences = _split_sentences(content)
        all_sent_counts.append(len(sentences))
        sent_lens = [_word_count(s) for s in sentences if s]
        all_sent_lengths.extend(sent_lens)

        # Pacing score: normalize word count and dialogue ratio to 0-1
        pace_score = (wc / 10000.0) * 0.6 + ratio * 0.4
        pacing_curve.append({
            "chapter": idx + 1,
            "title": title[:20],
            "word_count": wc,
            "dialogue_ratio": round(ratio, 3),
            "pace_score": round(pace_score, 3),
        })

    total_words = sum(chapter_lengths)
    chapter_count = len(chapter_lengths)
    avg_chapter = total_words / chapter_count if chapter_count else 0.0
    avg_dialogue = (
        sum(dialogue_ratios) / chapter_count if chapter_count else 0.0
    )

    para_avg_per_ch = (
        statistics.mean(all_para_counts) if all_para_counts else 0.0
    )
    para_avg_len = (
        statistics.mean(all_para_lengths) if all_para_lengths else 0.0
    )
    sent_avg_per_ch = (
        statistics.mean(all_sent_counts) if all_sent_counts else 0.0
    )
    sent_avg_len = (
        statistics.mean(all_sent_lengths) if all_sent_lengths else 0.0
    )

    report = StructureReport(
        book_id=book_id,
        chapter_count=chapter_count,
        total_words=total_words,
        avg_chapter_length=avg_chapter,
        chapter_length_distribution=chapter_lengths,
        dialogue_ratio_distribution=dialogue_ratios,
        avg_dialogue_ratio=avg_dialogue,
        paragraph_stats={
            "avg_per_chapter": round(para_avg_per_ch, 1),
            "avg_length": round(para_avg_len, 1),
        },
        sentence_stats={
            "avg_per_chapter": round(sent_avg_per_ch, 1),
            "avg_length": round(sent_avg_len, 1),
        },
        pacing_curve=pacing_curve,
    )

    # Cache the result
    _save_analysis("structure", book_id, report.to_dict())
    return report


# ── StyleFingerprint ────────────────────────────────────────────────────


@dataclass
class StyleFingerprint:
    """Quantitative style fingerprint of a reference book."""

    book_id: str = ""
    sentence_length_distribution: dict[str, float] = field(default_factory=dict)
    vocabulary_richness_ttr: float = 0.0
    punctuation_pattern: dict[str, float] = field(default_factory=dict)
    four_char_idiom_density: float = 0.0
    paragraph_length_stats: dict[str, Any] = field(default_factory=dict)
    dialogue_density: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "book_id": self.book_id,
            "sentence_length_distribution": {
                k: round(v, 3) for k, v in self.sentence_length_distribution.items()
            },
            "vocabulary_richness_ttr": round(self.vocabulary_richness_ttr, 3),
            "punctuation_pattern": {
                k: round(v, 4) for k, v in self.punctuation_pattern.items()
            },
            "four_char_idiom_density": round(self.four_char_idiom_density, 4),
            "paragraph_length_stats": self.paragraph_length_stats,
            "dialogue_density": round(self.dialogue_density, 3),
        }

    def to_prompt_fragment(self) -> str:
        """Generate a style-constraint prompt fragment."""
        if not self.book_id:
            return ""
        lines = ["## 文风量化约束"]

        dist = self.sentence_length_distribution
        if dist:
            lines.append("句长分布（占比）:")
            for bucket in ["<10", "10-20", "20-40", ">40"]:
                val = dist.get(bucket, 0.0)
                if val > 0:
                    lines.append(f"  {bucket}字: {val:.1%}")

        if self.vocabulary_richness_ttr:
            lines.append(f"词汇丰富度(TTR): {self.vocabulary_richness_ttr:.3f}")

        if self.four_char_idiom_density:
            lines.append(f"四字成语密度: {self.four_char_idiom_density:.4f}")

        punct = self.punctuation_pattern
        if punct:
            top_punct = sorted(punct.items(), key=lambda x: -x[1])[:5]
            punct_str = ", ".join(f"{k}:{v:.2%}" for k, v in top_punct)
            lines.append(f"标点模式: {punct_str}")

        para = self.paragraph_length_stats
        if para:
            lines.append(
                f"段落长度: 均值{para.get('mean', 0):.0f}字, "
                f"中位数{para.get('median', 0):.0f}字"
            )

        if self.dialogue_density:
            lines.append(f"对话密度: {self.dialogue_density:.1%}")

        lines.append("续写时应尽量匹配以上文风量化指标。")
        return "\n".join(lines)


# ── Style analysis functions ────────────────────────────────────────────

_STOP_WORDS: frozenset[str] = frozenset({
    "的", "了", "是", "在", "我", "你", "他", "她", "它", "们", "这", "那",
    "一个", "什么", "怎么", "为什么", "不", "没", "有", "就", "都", "也",
    "还", "又", "只", "才", "却", "但", "而", "及", "与", "或", "把", "被",
    "对", "给", "向", "从", "到", "于", "为", "以", "其", "之", "者", "所",
    "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
})

_PUNCT_TO_TRACK: list[str] = ["。", "，", "！", "？", "——", "……", "；", "："]
_FOUR_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff]{4,}")


def _compute_sentence_length_distribution(text: str) -> dict[str, float]:
    """Compute the distribution of sentence lengths into four buckets."""
    sentences = _split_sentences(text)
    if not sentences:
        return {}

    buckets = {"<10": 0, "10-20": 0, "20-40": 0, ">40": 0}
    for s in sentences:
        wc = _word_count(s)
        if wc < 10:
            buckets["<10"] += 1
        elif wc < 20:
            buckets["10-20"] += 1
        elif wc < 40:
            buckets["20-40"] += 1
        else:
            buckets[">40"] += 1

    total = len(sentences)
    return {k: v / total for k, v in buckets.items()}


def _compute_ttr(text: str) -> float:
    """Compute Type-Token Ratio using 2-char sliding window tokenization."""
    clean = text.replace(" ", "").replace("\n", "").replace("\t", "")
    if len(clean) < 2:
        return 0.0
    tokens: list[str] = []
    for i in range(len(clean) - 1):
        token = clean[i : i + 2]
        if token not in _STOP_WORDS:
            tokens.append(token)
    if not tokens:
        return 0.0
    unique = len(set(tokens))
    total = len(tokens)
    return unique / total if total > 0 else 0.0


def _compute_punctuation_pattern(text: str) -> dict[str, float]:
    """Compute the frequency of key punctuation marks."""
    total_chars = len(text)
    if total_chars == 0:
        return {}
    result: dict[str, float] = {}
    for punct in _PUNCT_TO_TRACK:
        count = text.count(punct)
        result[punct] = count / total_chars
    return result


def _compute_four_char_idiom_density(text: str) -> float:
    """Estimate four-character idiom density.

    Extracts all 4-char CJK substrings, then counts those that appear
    at least twice (a heuristic for being established phrases rather
    than random 4-char sequences).
    """
    clean = text.replace(" ", "").replace("\n", "").replace("\t", "")
    candidates: list[str] = []
    for m in _FOUR_CHAR_PATTERN.finditer(clean):
        segment = m.group()
        # Extract all 4-char sliding windows within the segment
        for i in range(len(segment) - 3):
            candidates.append(segment[i : i + 4])

    if not candidates:
        return 0.0

    counter = Counter(candidates)
    # Count 4-grams that appear 3+ times (likely idioms/phrases)
    idiom_count = sum(1 for _, cnt in counter.items() if cnt >= 3)
    total_chars = len(clean)
    return idiom_count / (total_chars / 10000) if total_chars > 0 else 0.0


def _compute_paragraph_length_stats(text: str) -> dict[str, Any]:
    """Compute paragraph length statistics."""
    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return {}
    lengths = [_word_count(p) for p in paragraphs if p]
    if not lengths:
        return {}
    return {
        "mean": round(statistics.mean(lengths), 1),
        "median": round(statistics.median(lengths), 1),
        "std": round(statistics.pstdev(lengths), 1) if len(lengths) > 1 else 0.0,
    }


def _compute_dialogue_density(text: str) -> float:
    """Compute the overall dialogue density (dialogue chars / total chars)."""
    dialogues = _extract_all_dialogues(text)
    dialogue_chars = sum(len(d) for d in dialogues)
    total = _word_count(text)
    return dialogue_chars / total if total > 0 else 0.0


def quantify_style(book_id: str) -> StyleFingerprint:
    """Quantify the writing style of a reference book.

    Pure function — no LLM, no side effects except caching the result.
    """
    chapter_contents = _load_chapter_contents(book_id)
    if not chapter_contents:
        return StyleFingerprint(book_id=book_id)

    # Concatenate all chapter text for whole-book analysis
    full_text = "\n\n".join(content for _, content in chapter_contents)

    fingerprint = StyleFingerprint(
        book_id=book_id,
        sentence_length_distribution=_compute_sentence_length_distribution(full_text),
        vocabulary_richness_ttr=_compute_ttr(full_text),
        punctuation_pattern=_compute_punctuation_pattern(full_text),
        four_char_idiom_density=_compute_four_char_idiom_density(full_text),
        paragraph_length_stats=_compute_paragraph_length_stats(full_text),
        dialogue_density=_compute_dialogue_density(full_text),
    )

    _save_analysis("style_fingerprint", book_id, fingerprint.to_dict())
    return fingerprint
