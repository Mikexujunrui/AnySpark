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
    # Deep style analysis (古典/半文半白小说续写)
    "sentence_rhythm": "sentence_rhythm_{book_id}.json",
    "rhetoric_density": "rhetoric_density_{book_id}.json",
    "prophecy_signature": "prophecy_signature_{book_id}.json",
    "narrative_pov": "narrative_pov_{book_id}.json",
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


# ── SentenceRhythm ───────────────────────────────────────────────────────


@dataclass
class SentenceRhythm:
    """句式韵律分析——捕捉半文半白的句式特征。

    纯 Python 确定性分析，不调用 LLM。
    """

    book_id: str = ""
    chapter_count: int = 0
    parallel_ratio: float = 0.0          # 对仗句占比
    four_six_prose_density: float = 0.0  # 四六骈文密度（四字+六字连用模式）
    classical_marker_density: float = 0.0  # 文言标记词密度（之/乎/者/也/矣/焉/哉）
    long_short_alternation: float = 0.0  # 长短句交替指数
    inversion_frequency: float = 0.0     # 倒装句频次

    def to_dict(self) -> dict[str, Any]:
        return {
            "book_id": self.book_id,
            "chapter_count": self.chapter_count,
            "parallel_ratio": round(self.parallel_ratio, 4),
            "four_six_prose_density": round(self.four_six_prose_density, 4),
            "classical_marker_density": round(self.classical_marker_density, 4),
            "long_short_alternation": round(self.long_short_alternation, 2),
            "inversion_frequency": round(self.inversion_frequency, 4),
        }

    def to_prompt_fragment(self) -> str:
        if not self.book_id:
            return ""
        lines = ["## 句式韵律约束"]
        if self.parallel_ratio:
            lines.append(f"对仗占比: {self.parallel_ratio:.1%}")
        if self.four_six_prose_density:
            lines.append(f"四六骈文密度: {self.four_six_prose_density:.4f}")
        if self.classical_marker_density:
            lines.append(f"文言标记密度: {self.classical_marker_density:.1f} 次/千字")
        if self.long_short_alternation:
            if self.long_short_alternation > 8:
                lines.append("长短句交替显著，节奏跳跃感强")
            elif self.long_short_alternation > 4:
                lines.append("长短句交替适中，节奏平稳")
            else:
                lines.append("句式长度均匀，节奏舒缓")
        if self.inversion_frequency:
            lines.append(f"倒装句频次: {self.inversion_frequency:.4f}")
        lines.append("续写时应保持相近的句式韵律特征。")
        return "\n".join(lines)


def analyze_sentence_rhythm(book_id: str) -> SentenceRhythm:
    """分析句式韵律特征——对仗、骈文、文言标记、长短交替、倒装。

    纯函数——无 LLM，无副作用，结果缓存。
    """
    chapter_contents = _load_chapter_contents(book_id)
    if not chapter_contents:
        return SentenceRhythm(book_id=book_id)

    classical_markers = re.compile(r"[之乎者也矣焉哉欤兮耶尔云]")
    inversion_markers = re.compile(r"(何|孰|焉|奚|胡|曷|岂|其|安|恶)")
    full_text = "\n\n".join(content for _, content in chapter_contents)

    total_sentences = 0
    parallel_count = 0
    four_six_count = 0
    classical_marker_total = 0
    length_diffs: list[float] = []
    inversion_count = 0

    sentences = _split_sentences(full_text)
    total_sentences = len(sentences)

    for chapter_title, content in chapter_contents:
        # Sentence-level analysis per chapter for pacing across book
        ch_sentences = _split_sentences(content)
        for i, s in enumerate(ch_sentences):
            s_len = _word_count(s)

            # 对仗检测：相邻句子长度比在 0.8-1.2 之间
            if i > 0:
                prev_len = _word_count(ch_sentences[i - 1])
                if prev_len > 0:
                    ratio = s_len / prev_len
                    if 0.8 <= ratio <= 1.2:
                        parallel_count += 1
                    length_diffs.append(abs(s_len - prev_len))

            # 倒装检测
            if inversion_markers.search(s[:10]):
                inversion_count += 1

        # 四六骈文检测
        clean_text = content.replace(" ", "").replace("\n", "")
        # 4-6-4-6 或 6-4-6-4 模式
        pattern = re.compile(r"(?:[\u4e00-\u9fff]{4}[\u4e00-\u9fff]{6}){2,}")
        four_six_count += len(pattern.findall(clean_text))

        # 文言标记词统计
        classical_marker_total += len(classical_markers.findall(content))

    # 计算结果
    ch_count = len(chapter_contents)
    total_chars = _word_count(full_text)
    total_chars_k = max(total_chars / 1000, 1)

    result = SentenceRhythm(
        book_id=book_id,
        chapter_count=ch_count,
        parallel_ratio=parallel_count / max(total_sentences, 1),
        four_six_prose_density=four_six_count / max(ch_count, 1),
        classical_marker_density=classical_marker_total / total_chars_k,
        long_short_alternation=statistics.mean(length_diffs) if length_diffs else 0.0,
        inversion_frequency=inversion_count / max(total_sentences, 1),
    )
    _save_analysis("sentence_rhythm", book_id, result.to_dict())
    return result


# ── RhetoricDensity ──────────────────────────────────────────────────────


@dataclass
class RhetoricDensity:
    """修辞手法密度分析——捕捉古典小说特有的修辞特征。

    纯 Python 确定性分析，不调用 LLM。
    """

    book_id: str = ""
    chapter_count: int = 0
    allusion_density: float = 0.0          # 用典密度（次/万字）
    allusion_sources: dict[str, int] = field(default_factory=dict)  # 典故来源分布
    homophone_pun_density: float = 0.0     # 谐音双关密度
    metaphor_marker_density: float = 0.0   # 比喻密度
    understatement_density: float = 0.0    # 春秋笔法/反讽标记密度

    def to_dict(self) -> dict[str, Any]:
        return {
            "book_id": self.book_id,
            "chapter_count": self.chapter_count,
            "allusion_density": round(self.allusion_density, 4),
            "allusion_sources": self.allusion_sources,
            "homophone_pun_density": round(self.homophone_pun_density, 4),
            "metaphor_marker_density": round(self.metaphor_marker_density, 4),
            "understatement_density": round(self.understatement_density, 4),
        }

    def to_prompt_fragment(self) -> str:
        if not self.book_id:
            return ""
        lines = ["## 修辞密度约束"]
        if self.allusion_density:
            lines.append(f"用典密度: {self.allusion_density:.2f} 次/万字")
            if self.allusion_sources:
                top = sorted(self.allusion_sources.items(), key=lambda x: -x[1])[:3]
                source_str = ", ".join(f"{k}({v}次)" for k, v in top)
                lines.append(f"主要典故来源: {source_str}")
        if self.homophone_pun_density:
            lines.append(f"谐音双关密度: {self.homophone_pun_density:.4f}")
        if self.metaphor_marker_density:
            lines.append(f"比喻手法密度: {self.metaphor_marker_density:.4f}")
        if self.understatement_density:
            lines.append(f"春秋笔法/反讽密度: {self.understatement_density:.4f}")
        lines.append("续写时应保持相近的修辞密度特征。")
        return "\n".join(lines)


# 常见典故关键词映射表
_ALLUSION_KEYWORDS: dict[str, list[str]] = {
    "庄子": ["庄子", "逍遥", "齐物", "养生主", "人间世", "德充符", "大宗师", "应帝王"],
    "离骚": ["离骚", "楚辞", "香草", "美人", "兮"],
    "诗经": ["诗经", "关雎", "蒹葭", "风雅颂", "三百篇"],
    "论语": ["论语", "孔子曰", "子曰", "不亦说乎"],
    "孟子": ["孟子", "孟子曰", "仁义"],
    "史记": ["史记", "太史公", "列传"],
    "世说新语": ["世说新语", "魏晋", "风流"],
    "西厢记": ["西厢", "崔莺莺", "张生", "红娘"],
    "牡丹亭": ["牡丹亭", "杜丽娘", "柳梦梅", "游园惊梦"],
    "庄子寓言": ["庖丁解牛", "庄周梦蝶", "濠梁之上", "望洋兴叹"],
}


def _detect_allusions(text: str) -> dict[str, int]:
    """用关键词匹配检测典故引用。"""
    result: dict[str, int] = {}
    for source, keywords in _ALLUSION_KEYWORDS.items():
        count = 0
        for kw in keywords:
            count += text.count(kw)
        if count > 0:
            result[source] = count
    return result


# 春秋笔法/反讽标记
_UNDERSTATEMENT_MARKERS: list[str] = [
    "笑道", "不言", "罢了", "可见", "所谓", "不过", "倒也", "也就不",
    "罢了罢了", "何必", "何苦", "白白", "倒也罢了",
]

# 比喻标记词
_METAPHOR_MARKERS: list[str] = [
    "如", "似", "若", "好比", "仿佛", "如同", "宛如", "恰似",
    "一般", "一样", "似的", "般", "犹如",
]


def analyze_rhetoric_density(book_id: str) -> RhetoricDensity:
    """分析修辞手法密度——用典、谐音双关、比喻、反讽。

    纯函数——无 LLM，无副作用，结果缓存。
    """
    chapter_contents = _load_chapter_contents(book_id)
    if not chapter_contents:
        return RhetoricDensity(book_id=book_id)

    full_text = "\n\n".join(content for _, content in chapter_contents)
    total_chars = _word_count(full_text)
    total_chars_wan = max(total_chars / 10000, 1)
    ch_count = len(chapter_contents)

    # 用典检测
    allusion_sources = _detect_allusions(full_text)
    total_allusions = sum(allusion_sources.values())

    # 谐音双关检测（检测人名/地名中的谐音模式）
    homophone_pattern = re.compile(r"(?:谐音|双关|谐|音意)[：:]\s*[^\n]{5,}")
    homophone_count = len(homophone_pattern.findall(full_text))

    # 比喻检测
    metaphor_count = 0
    for marker in _METAPHOR_MARKERS:
        metaphor_count += full_text.count(marker)

    # 春秋笔法检测
    understatement_count = 0
    for marker in _UNDERSTATEMENT_MARKERS:
        understatement_count += full_text.count(marker)

    result = RhetoricDensity(
        book_id=book_id,
        chapter_count=ch_count,
        allusion_density=total_allusions / total_chars_wan,
        allusion_sources=allusion_sources,
        homophone_pun_density=homophone_count / max(ch_count, 1),
        metaphor_marker_density=metaphor_count / max(ch_count, 1),
        understatement_density=understatement_count / max(ch_count, 1),
    )
    _save_analysis("rhetoric_density", book_id, result.to_dict())
    return result


# ── ProphecySignature ────────────────────────────────────────────────────


@dataclass
class ProphecySignature:
    """预叙/谶语特征分析——古典小说独特的叙事手法。

    纯 Python 确定性分析，不调用 LLM。
    """

    book_id: str = ""
    chapter_count: int = 0
    poem_prophecy_count: int = 0         # 诗词型谶语数量
    dialogue_prophecy_count: int = 0     # 对话型谶语数量
    symbolic_action_count: int = 0       # 象征性行为
    dream_omen_count: int = 0            # 托梦/预感类
    avg_prophecy_per_chapter: float = 0.0  # 平均每章预叙密度

    def to_dict(self) -> dict[str, Any]:
        return {
            "book_id": self.book_id,
            "chapter_count": self.chapter_count,
            "poem_prophecy_count": self.poem_prophecy_count,
            "dialogue_prophecy_count": self.dialogue_prophecy_count,
            "symbolic_action_count": self.symbolic_action_count,
            "dream_omen_count": self.dream_omen_count,
            "avg_prophecy_per_chapter": round(self.avg_prophecy_per_chapter, 2),
        }

    def to_prompt_fragment(self) -> str:
        if not self.book_id:
            return ""
        lines = ["## 谶语/预叙特征"]
        lines.append(f"诗词型谶语: {self.poem_prophecy_count}处")
        lines.append(f"对话暗示: {self.dialogue_prophecy_count}处")
        if self.symbolic_action_count:
            lines.append(f"象征性行为: {self.symbolic_action_count}处")
        if self.dream_omen_count:
            lines.append(f"托梦/预感: {self.dream_omen_count}处")
        lines.append(f"平均每章预叙密度: {self.avg_prophecy_per_chapter:.2f}处/章")
        lines.append("续写时应注意保持适当的谶语密度，每章埋设 1-2 处暗示。")
        return "\n".join(lines)


# 诗词谶语模式
_POEM_PROPHECY_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?:判词|判语|判辞)[：:]\s*[^\n]{10,}"),
    re.compile(r"〔.+〕"),   # 曲牌/曲辞
    re.compile(r"[签词|签语|签文][：:]\s*[^\n]{5,}"),
    re.compile(r"灯谜[：:]\s*[^\n]{5,}"),
    re.compile(r"酒令[：:]\s*[^\n]{5,}"),
    re.compile(r"诗[：:]\s*[^\n]{10,}"),
    re.compile(r"词[：:]\s*[^\n]{10,}"),
]

# 对话谶语模式——特定动词后的留白/暗示性语句
_DIALOGUE_PROPHECY_PATTERNS: list[re.Pattern] = [
    re.compile(r'[笑道|叹道|暗道|冷笑道|哭道|悲道]\u201c[^\u201d]{15,}\u201d'),
    re.compile(r"你放心[！。！？，]"),
    re.compile(r"再[也又]不能[^\n]{5,}"),
    re.compile(r"后[来日][^\n]{10,}(?:便|就|也)"),
]

# 象征性行为关键词（通用）
_SYMBOLIC_ACTIONS: list[str] = [
    "放生", "出家", "修行", "断簪", "裂帛", "断情",
]

# 梦境/预感关键词
_DREAM_OMEN_KEYWORDS: list[str] = [
    "梦见", "梦到", "梦游", "梦境", "梦中", "恍惚",
    "预感", "预兆", "兆头", "不祥", "心惊肉跳",
    "魂魄", "阴司", "阎王", "鬼神",
]


def analyze_prophecy_signature(book_id: str) -> ProphecySignature:
    """分析谶语/预叙特征——诗词谶语、对话暗示、象征行为、托梦预感。

    纯函数——无 LLM，无副作用，结果缓存。
    """
    chapter_contents = _load_chapter_contents(book_id)
    if not chapter_contents:
        return ProphecySignature(book_id=book_id)

    ch_count = len(chapter_contents)
    total_poem = 0
    total_dialogue = 0
    total_symbolic = 0
    total_dream = 0

    for title, content in chapter_contents:
        # 诗词型谶语
        for pattern in _POEM_PROPHECY_PATTERNS:
            total_poem += len(pattern.findall(content))

        # 对话型暗示
        for pattern in _DIALOGUE_PROPHECY_PATTERNS:
            total_dialogue += len(pattern.findall(content))

        # 象征性行为
        for keyword in _SYMBOLIC_ACTIONS:
            total_symbolic += content.count(keyword)

        # 托梦/预感
        for keyword in _DREAM_OMEN_KEYWORDS:
            total_dream += content.count(keyword)

    total = total_poem + total_dialogue + total_symbolic + total_dream

    result = ProphecySignature(
        book_id=book_id,
        chapter_count=ch_count,
        poem_prophecy_count=total_poem,
        dialogue_prophecy_count=total_dialogue,
        symbolic_action_count=total_symbolic,
        dream_omen_count=total_dream,
        avg_prophecy_per_chapter=total / max(ch_count, 1),
    )
    _save_analysis("prophecy_signature", book_id, result.to_dict())
    return result


# ── NarrativePOVSignature ────────────────────────────────────────────────


@dataclass
class NarrativePOVSignature:
    """叙事视角分析——古典小说'看官听说'式叙事的频率和分布。

    纯 Python 确定性分析，不调用 LLM。
    """

    book_id: str = ""
    chapter_count: int = 0
    omniscient_markers: list[dict] = field(default_factory=list)  # 全知标记分布
    limited_pov_sections: int = 0           # 限知视角段落数
    pov_shift_frequency: float = 0.0        # 视角切换频率（次/章）
    narrator_intervention_count: int = 0    # 叙事者干预次数

    def to_dict(self) -> dict[str, Any]:
        return {
            "book_id": self.book_id,
            "chapter_count": self.chapter_count,
            "omniscient_markers": self.omniscient_markers[:10],
            "limited_pov_sections": self.limited_pov_sections,
            "pov_shift_frequency": round(self.pov_shift_frequency, 2),
            "narrator_intervention_count": self.narrator_intervention_count,
        }

    def to_prompt_fragment(self) -> str:
        if not self.book_id:
            return ""
        lines = ["## 叙事视角约束"]
        if self.omniscient_markers:
            lines.append(f"全知视角标记出现 {len(self.omniscient_markers)} 次")
        if self.limited_pov_sections:
            lines.append(f"限知视角段落: {self.limited_pov_sections} 段")
        if self.pov_shift_frequency:
            lines.append(f"视角切换频率: {self.pov_shift_frequency:.1f} 次/章")
        if self.narrator_intervention_count:
            lines.append(f"叙事者干预: {self.narrator_intervention_count} 次")
        lines.append("续写时应保持相近的叙事视角模式和干预频率。")
        return "\n".join(lines)


# 全知视角标记
_OMNISCIENT_MARKERS: list[str] = [
    "看官听说", "你道", "原来", "不在话下", "且说", "却说",
    "话说", "话分两头", "单说", "正是", "不知", "且听下回分解",
]

# 限知视角标记——以人物感知词开头的段落
# 注：此处为通用人称代词/视角标记；特定小说的人物名需调用时传入
_POV_GENERIC_STARTERS: list[str] = [
    "他", "她", "我", "他们", "她们", "我们",
]


def analyze_narrative_pov(
    book_id: str,
    character_names: list[str] | None = None,
) -> NarrativePOVSignature:
    """分析叙事视角模式——全知标记、限知段落、视角切换、叙事者干预。

    Args:
        book_id: 书籍ID
        character_names: 可选，小说主要角色名列表，用于检测限知视角段落。
            如不传则使用通用人称代词检测。

    纯函数——无 LLM，无副作用，结果缓存。
    """
    chapter_contents = _load_chapter_contents(book_id)
    if not chapter_contents:
        return NarrativePOVSignature(book_id=book_id)

    omniscient_hits = []
    limited_count = 0
    intervention_count = 0
    ch_count = len(chapter_contents)

    # 使用传入的角色名或通用标记
    pov_starters = character_names if character_names else _POV_GENERIC_STARTERS

    for title, content in chapter_contents:
        # 全知视角标记
        for marker in _OMNISCIENT_MARKERS:
            positions = []
            idx = 0
            while True:
                idx = content.find(marker, idx)
                if idx < 0:
                    break
                positions.append({"marker": marker, "position": idx})
                idx += len(marker)
            omniscient_hits.extend(positions)

        # 限知视角段落（以人物感知词开头的段落）
        paragraphs = _split_paragraphs(content)
        for para in paragraphs:
            para_stripped = para.strip()
            for starter in pov_starters:
                if para_stripped.startswith(starter):
                    limited_count += 1
                    break

        # 叙事者干预（"可见"、"所谓"、"此乃"等引导的议论句）
        intervention_pattern = re.compile(
            r"(可见|所谓|此乃|这便是|正所谓|此正是|所以说|这便|这就是|这便是)",
        )
        intervention_count += len(intervention_pattern.findall(content))

    result = NarrativePOVSignature(
        book_id=book_id,
        chapter_count=ch_count,
        omniscient_markers=omniscient_hits,
        limited_pov_sections=limited_count,
        pov_shift_frequency=len(omniscient_hits) / max(ch_count, 1),
        narrator_intervention_count=intervention_count,
    )
    _save_analysis("narrative_pov", book_id, result.to_dict())
    return result


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
