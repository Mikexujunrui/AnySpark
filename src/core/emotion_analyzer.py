# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Emotional curve analyzer — chapter-level emotional tone detection.

Pure-Python deterministic analysis of emotional arcs across a book.
Detects per-chapter primary tones, tone transitions, and turning
points where mood shifts abruptly.

No LLM calls — results are reproducible and cacheable.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from data.json_store import json_store

logger = logging.getLogger(__name__)


# ── Storage ──────────────────────────────────────────────────────────────

ANALYSES_DIR = Path(__file__).resolve().parents[2] / "data" / "analyses"
ANALYSES_DIR.mkdir(parents=True, exist_ok=True)


def _analysis_path(book_id: str) -> Path:
    return ANALYSES_DIR / f"emotional_curve_{book_id}.json"


def load_emotional_curve(book_id: str) -> dict | None:
    """Load cached emotional curve analysis."""
    path = _analysis_path(book_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load emotional curve %s: %s", path, e)
        return None


def _save_emotional_curve(book_id: str, data: dict) -> None:
    path = _analysis_path(book_id)
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        logger.warning("Failed to save emotional curve %s: %s", path, e)


# ── Emotional tone lexicon ──────────────────────────────────────────────

# Each emotion category with associated keywords
# 七类情感基调：喜(joy)、怒(anger)、哀(sorrow)、乐(pleasure)、惊(surprise)、思(contemplation)、淡(calm)
_EMOTION_LEXICON: dict[str, list[str]] = {
    "joy": [
        "高兴", "快乐", "开心", "欢喜", "欢天喜地", "笑", "喜", "乐", "欢",
        "欣喜", "愉悦", "畅快", "得意", "满足", "称心", "美满",
    ],
    "anger": [
        "怒", "气愤", "恼", "恨", "气", "忿", "愤", "怒道", "生气",
        "大怒", "大怒道", "咬牙切齿", "怒气冲冲", "愤然",
    ],
    "sorrow": [
        "悲", "哀", "伤", "哭", "泣", "泪", "愁", "痛", "苦", "凄凉",
        "伤心", "悲伤", "悲痛", "哀伤", "泪下", "痛哭", "哽咽",
        "叹息", "叹", "伤感", "悲凉", "落泪", "垂泪",
    ],
    "pleasure": [
        "乐", "趣", "雅", "赏", "宴", "游", "嬉", "戏", "玩",
        "赏花", "赋诗", "听曲", "看戏", "结社", "宴会",
    ],
    "surprise": [
        "惊", "讶", "怪", "奇", "异", "骇", "愕", "怔", "愣",
        "大惊", "吃惊", "惊讶", "诧异", "奇怪", "不知", "骇然",
    ],
    "contemplation": [
        "思", "想", "念", "忆", "悟", "参", "禅", "静思", "默想",
        "沉思", "思量", "思忖", "念及", "回想", "追忆",
    ],
    "calm": [
        "静", "淡", "闲", "幽", "宁", "安", "恬", "怡", "宜",
        "清静", "宁静", "安闲", "淡然", "从容", "平和",
    ],
}

# Pre-compile patterns for each emotion
_EMOTION_PATTERNS: dict[str, re.Pattern] = {
    emotion: re.compile("|".join(re.escape(kw) for kw in keywords))
    for emotion, keywords in _EMOTION_LEXICON.items()
}

# Joy-to-sorrow transition markers (乐极生悲)
_JOY_TO_SORROW_MARKERS: list[str] = [
    "不料", "谁知", "忽然", "突然", "正在", "正说", "正然",
    "不想", "岂知", "谁知", "猛然", "顿然",
]


# ── Data models ─────────────────────────────────────────────────────────


@dataclass
class EmotionalCurve:
    """每章情感基调的时间序列——乐极生悲模式的量化。"""

    book_id: str = ""
    chapter_count: int = 0
    chapter_tone_sequence: list[dict] = field(default_factory=list)
    tone_transition_matrix: dict[str, dict[str, float]] = field(default_factory=dict)
    joy_to_sorrow_ratio: float = 0.0
    dominant_tone: str = "calm"
    emotional_volatility: float = 0.0  # 情绪波动度

    def to_dict(self) -> dict[str, Any]:
        return {
            "book_id": self.book_id,
            "chapter_count": self.chapter_count,
            "chapter_tone_sequence": self.chapter_tone_sequence,
            "tone_transition_matrix": self.tone_transition_matrix,
            "joy_to_sorrow_ratio": round(self.joy_to_sorrow_ratio, 3),
            "dominant_tone": self.dominant_tone,
            "emotional_volatility": round(self.emotional_volatility, 3),
        }

    def to_prompt_fragment(self) -> str:
        if not self.book_id or not self.chapter_tone_sequence:
            return ""
        lines = ["## 情感弧线约束"]

        # 主导情感基调
        tone_names = {
            "joy": "喜悦", "anger": "愤怒", "sorrow": "哀伤",
            "pleasure": "欢愉", "surprise": "惊讶", "contemplation": "沉思", "calm": "平淡",
        }
        dominant_cn = tone_names.get(self.dominant_tone, self.dominant_tone)
        lines.append(f"全篇主导情感基调: {dominant_cn}")

        if self.joy_to_sorrow_ratio > 0.1:
            lines.append(f"乐极生悲转折密度: {self.joy_to_sorrow_ratio:.2f} 次/章")

        if self.emotional_volatility > 0.5:
            lines.append("情绪波动度: 高，情感起伏剧烈")
        elif self.emotional_volatility > 0.2:
            lines.append("情绪波动度: 中等，有适度起伏")
        else:
            lines.append("情绪波动度: 低，情感平稳")

        # 最后几章的情感趋势
        recent = self.chapter_tone_sequence[-5:] if len(self.chapter_tone_sequence) >= 5 else self.chapter_tone_sequence
        if recent:
            recent_tones = [t["primary_tone"] for t in recent]
            lines.append(f"近几章情感走向: {' → '.join(tone_names.get(t, t) for t in recent_tones)}")

        lines.append("续写时应保持相近的情感弧线模式和转折节奏。")
        return "\n".join(lines)


# ── Analysis functions ──────────────────────────────────────────────────


def _detect_chapter_tone(content: str) -> tuple[str, float]:
    """检测一章的主导情感基调和强度（0-1）。"""
    scores: dict[str, int] = {}
    for emotion, pattern in _EMOTION_PATTERNS.items():
        scores[emotion] = len(pattern.findall(content))

    if not any(scores.values()):
        return "calm", 0.0

    dominant = max(scores, key=scores.get)
    total = sum(scores.values())
    intensity = scores[dominant] / max(total, 1)
    return dominant, intensity


def _detect_joy_to_sorrow_transitions(content: str) -> int:
    """检测乐极生悲转折点数。"""
    count = 0
    for marker in _JOY_TO_SORROW_MARKERS:
        count += content.count(marker)
    return count


def _compute_transition_matrix(
    sequence: list[dict],
) -> dict[str, dict[str, float]]:
    """计算情感转换概率矩阵。"""
    if len(sequence) < 2:
        return {}

    transitions: dict[str, Counter] = {}
    for i in range(len(sequence) - 1):
        from_tone = sequence[i]["primary_tone"]
        to_tone = sequence[i + 1]["primary_tone"]
        if from_tone not in transitions:
            transitions[from_tone] = Counter()
        transitions[from_tone][to_tone] += 1

    matrix: dict[str, dict[str, float]] = {}
    for from_tone, counter in transitions.items():
        total = sum(counter.values())
        matrix[from_tone] = {tone: count / total for tone, count in counter.items()}

    return matrix


def _compute_volatility(sequence: list[dict]) -> float:
    """计算情绪波动度——相邻章情感基调变化的频率。"""
    if len(sequence) < 2:
        return 0.0

    changes = 0
    for i in range(len(sequence) - 1):
        if sequence[i]["primary_tone"] != sequence[i + 1]["primary_tone"]:
            changes += 1
    return changes / (len(sequence) - 1)


def _load_chapter_contents(book_id: str) -> list[tuple[str, str]]:
    """Load all chapter (title, content) pairs from a book."""
    chapters = json_store.load_chapters(book_id)
    results: list[tuple[str, str]] = []
    for ch in chapters:
        view = json_store._chapter_view(ch)
        title = view.get("title", "")
        content = view.get("content", "")
        if content:
            results.append((title, content))
    return results


def analyze_emotional_curve(book_id: str) -> EmotionalCurve:
    """分析全书情感弧线——逐章基调 + 转换矩阵 + 乐极生悲模式。

    纯函数——无 LLM，结果缓存。
    """
    chapter_contents = _load_chapter_contents(book_id)
    if not chapter_contents:
        return EmotionalCurve(book_id=book_id)

    tone_sequence: list[dict] = []
    total_jts = 0

    for idx, (title, content) in enumerate(chapter_contents):
        dominant_tone, intensity = _detect_chapter_tone(content)
        jts_count = _detect_joy_to_sorrow_transitions(content)
        total_jts += jts_count

        tone_sequence.append({
            "chapter": idx + 1,
            "title": title[:20],
            "primary_tone": dominant_tone,
            "intensity": round(intensity, 3),
            "joy_to_sorrow_markers": jts_count,
        })

    ch_count = len(chapter_contents)
    transition_matrix = _compute_transition_matrix(tone_sequence)
    volatility = _compute_volatility(tone_sequence)

    # 主导情感基调
    tone_counter = Counter(t["primary_tone"] for t in tone_sequence)
    dominant_tone = tone_counter.most_common(1)[0][0] if tone_counter else "calm"

    # 统计全文各情感类型的总频次
    full_text = "\n\n".join(content for _, content in chapter_contents)
    total_scores: dict[str, int] = {}
    for emotion, pattern in _EMOTION_PATTERNS.items():
        total_scores[emotion] = len(pattern.findall(full_text))
    if total_scores:
        dominant_tone = max(total_scores, key=total_scores.get)

    curve = EmotionalCurve(
        book_id=book_id,
        chapter_count=ch_count,
        chapter_tone_sequence=tone_sequence,
        tone_transition_matrix=transition_matrix,
        joy_to_sorrow_ratio=total_jts / max(ch_count, 1),
        dominant_tone=dominant_tone,
        emotional_volatility=volatility,
    )

    _save_emotional_curve(book_id, curve.to_dict())
    return curve
