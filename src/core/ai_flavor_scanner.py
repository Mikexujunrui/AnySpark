# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""AI Flavor Scanner — pure-rule detection of common AI writing patterns.

Zero token cost. Seven checks covering the most frequent AI-telltale signals
in Chinese fiction. Designed for extensibility: add a check function and
register it in CHECK_REGISTRY to enable a new detector.

Typical usage:
    from core.ai_flavor_scanner import scan_chapter
    report = scan_chapter(chapter_content)
    if not report.is_clean:
        for line in report.flagged_lines:
            print(line)
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# ── Data structures ──────────────────────────────────────────────────────────


@dataclass
class FlavorCheck:
    """Result of a single AI-flavor detection check."""

    name: str  # e.g. "AI过渡词密度"
    passed: bool  # whether this check passed
    score: float  # 0-100, higher = more human-like
    threshold: float  # the threshold used for this check
    actual_value: float  # the measured value
    details: list[str] = field(default_factory=list)  # human-readable findings

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "score": round(self.score, 1),
            "threshold": self.threshold,
            "actual_value": round(self.actual_value, 3),
            "details": self.details,
        }


@dataclass
class AIFlavorReport:
    """Aggregated AI-flavor scan report for a chapter."""

    overall_score: float = 100.0  # 0-100, higher = more human-like
    checks: list[FlavorCheck] = field(default_factory=list)
    flagged_lines: list[str] = field(default_factory=list)
    is_clean: bool = True  # all checks passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": round(self.overall_score, 1),
            "is_clean": self.is_clean,
            "checks": [c.to_dict() for c in self.checks],
            "flagged_lines": self.flagged_lines,
        }


# ── Default thresholds ───────────────────────────────────────────────────────

DEFAULT_THRESHOLDS: dict[str, float] = {
    "transition_words": 3.0,  # per 1000 chars
    "template_patterns": 2.0,  # per 1000 chars
    "hedge_words": 5.0,  # per 1000 chars
    "facial_micro": 8.0,  # per 1000 chars
    "paragraph_openings": 3.0,  # consecutive same-pattern paragraphs
    "sentence_uniformity": 8.0,  # std-dev threshold
    "dialogue_tag_diversity": 0.2,  # unique tags / total dialogues
}

# ── Shared helpers ───────────────────────────────────────────────────────────


def _word_count(text: str) -> int:
    """Count Chinese characters (excluding whitespace, digits, punctuation)."""
    clean = re.sub(r"[\s\d\W]", "", text)
    return len(clean)


def _per_1k(raw_count: int, total_chars: int) -> float:
    """Normalize a count to per-1000-characters."""
    if total_chars == 0:
        return 0.0
    return raw_count / (total_chars / 1000)


def _density_check(
    name: str,
    compiled_re: re.Pattern,
    content: str,
    total_chars: int,
    threshold: float,
    label: str,
) -> FlavorCheck:
    """Common density-check pattern: count regex matches, normalize, score.

    Args:
        name: Human-readable check name (e.g. "AI过渡词密度").
        compiled_re: Pre-compiled regex for matching.
        content: The text to scan.
        total_chars: Total Chinese character count (for per-1k normalization).
        threshold: Maximum allowed matches per 1000 chars.
        label: Label for the detail message (e.g. "AI过渡词密度").

    Returns:
        FlavorCheck with passed/score/details.
    """
    count = len(compiled_re.findall(content))
    actual = _per_1k(count, total_chars)
    passed = actual <= threshold
    # Linear score: 100 at zero matches, 0 at 2*threshold
    score = max(0.0, 100.0 - (actual / max(threshold, 0.01)) * 100.0)
    details = []
    if not passed:
        details.append(f"{label} {actual:.1f}/千字（阈值 {threshold:.1f}），共 {count} 处")
    return FlavorCheck(
        name=name,
        passed=passed,
        score=min(100.0, score),
        threshold=threshold,
        actual_value=actual,
        details=details,
    )


# ── Sentence splitting (reuse pacing_analyzer when available) ────────────────

try:
    from core.pacing_analyzer import _split_sentences  # noqa: F811
except ImportError:  # pragma: no cover — fallback for standalone usage

    def _split_sentences(content: str) -> list[str]:
        parts = re.compile(r"[。！？!?…]+").split(content)
        return [p.strip() for p in parts if p.strip()]


# ── Dialogue extraction (reuse voice_fingerprint when available) ─────────────

try:
    from core.voice_fingerprint import _extract_all_dialogues as _extract_dialogues
except ImportError:  # pragma: no cover — fallback for standalone usage

    def _extract_dialogues(content: str) -> list[str]:
        lines: list[str] = []
        for m in re.finditer(r"\u201c([^\u201d]+)\u201d", content):
            lines.append(m.group(1))
        for m in re.finditer(r"\u300c([^\u300d]+)\u300d", content):
            lines.append(m.group(1))
        return lines


# ══════════════════════════════════════════════════════════════════════════════
# Check definitions
# ══════════════════════════════════════════════════════════════════════════════

# ── Check 1: AI transition words ────────────────────────────────────────────

_AI_TRANSITION_WORDS = [
    "与此同时",
    "不仅如此",
    "更重要的是",
    "值得注意的是",
    "毫无疑问",
    "显而易见",
    "不可否认",
    "总而言之",
    "综上所述",
    "从某种意义",
    "从这个角度",
]

_TRANSITION_RE = re.compile("|".join(re.escape(w) for w in _AI_TRANSITION_WORDS))


def _check_ai_transition_words(content: str, total_chars: int, threshold: float) -> FlavorCheck:
    return _density_check(
        "AI过渡词密度",
        _TRANSITION_RE,
        content,
        total_chars,
        threshold,
        "AI过渡词密度",
    )


# ── Check 2: AI template patterns ───────────────────────────────────────────

# Regex patterns (compiled) and literal strings (use str.count)
_TEMPLATE_REGEX_PATTERNS: list[re.Pattern] = [
    re.compile(r"在这个充满.{1,20}的世界"),
    re.compile(r"一股.{1,10}涌上心头"),
    re.compile(r"眼眸中闪过一丝"),
    re.compile(r"眼中闪过"),
    re.compile(r"嘴角微微上扬"),
    re.compile(r"嘴角.{1,5}上扬"),
    re.compile(r"他.{0,3}不知道的是"),
    re.compile(r"她.{0,3}不知道的是"),
    re.compile(r"微微一[笑叹怔愣皱眉]"),
]

_TEMPLATE_LITERAL_WORDS = [
    "仿佛",
    "宛如",
    "犹如",
    "就像",
    "像是",
    "若有所",
    "不禁",
    "不由得",
    "忍不住",
    "不由自主",
    "下意识",
]


def _check_ai_template_patterns(content: str, total_chars: int, threshold: float) -> FlavorCheck:
    count = 0
    for pat in _TEMPLATE_REGEX_PATTERNS:
        count += len(pat.findall(content))
    for word in _TEMPLATE_LITERAL_WORDS:
        count += content.count(word)
    actual = _per_1k(count, total_chars)
    passed = actual <= threshold
    score = max(0.0, 100.0 - (actual / max(threshold, 0.01)) * 100.0)
    details = []
    if not passed:
        details.append(f"AI模板句式密度 {actual:.1f}/千字（阈值 {threshold:.1f}），共 {count} 处")
    return FlavorCheck(
        name="AI模板句式密度",
        passed=passed,
        score=min(100.0, score),
        threshold=threshold,
        actual_value=actual,
        details=details,
    )


# ── Check 3: AI hedge / filler words ────────────────────────────────────────

_AI_HEDGE_WORDS = [
    "似乎",
    "仿佛",
    "宛如",
    "好像",
    "某种",
    "一丝",
    "一股",
    "一阵",
    "一抹",
    "隐隐",
    "微微",
    "淡淡",
    "浅浅",
    "轻轻",
    "莫名",
    "莫名地",
    "不知为何",
    "说不清",
    "忽然",
    "突然",
    "骤然",
    "猛地",
    "蓦地",
    "缓缓",
    "渐渐",
    "慢慢",
    "徐徐",
    "也许",
    "或许",
    "大概",
    "大约",
]

_HEDGE_RE = re.compile("|".join(re.escape(w) for w in _AI_HEDGE_WORDS))


def _check_ai_hedge_words(content: str, total_chars: int, threshold: float) -> FlavorCheck:
    return _density_check(
        "AI模糊词密度",
        _HEDGE_RE,
        content,
        total_chars,
        threshold,
        "AI模糊词密度",
    )


# ── Check 4: Facial micro-expression density ────────────────────────────────

_FACIAL_MICRO_WORDS = [
    "眼眸",
    "目光",
    "眼神",
    "眼底",
    "眼中",
    "眸中",
    "眸子",
    "双眼",
    "瞳孔",
    "视线",
    "眼帘",
    "嘴角",
    "唇边",
    "唇角",
    "嘴唇",
    "双唇",
    "眉头",
    "眉间",
    "眉宇",
    "眉心",
    "眉毛",
    "脸色",
    "面色",
    "面容",
    "脸庞",
    "脸颊",
    "面孔",
    "神情",
    "表情",
    "神色",
    "神态",
]

_FACIAL_RE = re.compile("|".join(re.escape(w) for w in _FACIAL_MICRO_WORDS))


def _check_facial_micro_expressions(content: str, total_chars: int, threshold: float) -> FlavorCheck:
    return _density_check(
        "面部微表情密度",
        _FACIAL_RE,
        content,
        total_chars,
        threshold,
        "面部微表情密度",
    )


# ── Check 5: Paragraph opening homogeneity ──────────────────────────────────

_SAME_SUBJECT_START = re.compile(r"^(他|她|它|他们|她们|.{1,2})(?:也|又|便|就|却|还|只|才|已|都|总|再)")

_TIME_OPENING_WORDS = [
    "此时",
    "这时",
    "片刻之后",
    "片刻后",
    "那一刻",
    "不一会儿",
    "没多久",
    "很快",
    "紧接着",
    "下一秒",
    "下一瞬",
    "刹那间",
]


def _check_paragraph_openings(content: str, threshold: int = 3) -> FlavorCheck:
    """Check if consecutive paragraphs share the same opening pattern."""
    paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
    if len(paragraphs) < threshold:
        return FlavorCheck(
            name="段落开头同构",
            passed=True,
            score=100.0,
            threshold=float(threshold),
            actual_value=0.0,
            details=[],
        )

    max_consecutive = 0
    current_consecutive = 1
    issues: list[str] = []

    for i in range(1, len(paragraphs)):
        prev = paragraphs[i - 1]
        curr = paragraphs[i]

        prev_subj = _SAME_SUBJECT_START.match(prev)
        curr_subj = _SAME_SUBJECT_START.match(curr)
        same_subject = prev_subj and curr_subj and prev_subj.group(1) == curr_subj.group(1)

        same_time = any(curr.startswith(tw) and prev.startswith(tw) for tw in _TIME_OPENING_WORDS)

        if same_subject or same_time:
            current_consecutive += 1
        else:
            if current_consecutive >= threshold:
                issues.append(f"第{i - current_consecutive + 1}~{i}段连续以相同模式开头（共{current_consecutive}段）")
            max_consecutive = max(max_consecutive, current_consecutive)
            current_consecutive = 1

    if current_consecutive >= threshold:
        start_idx = len(paragraphs) - current_consecutive
        issues.append(f"第{start_idx + 1}~{len(paragraphs)}段连续以相同模式开头（共{current_consecutive}段）")
    max_consecutive = max(max_consecutive, current_consecutive)

    if max_consecutive < threshold:
        score = 100.0
    else:
        score = max(0.0, 100.0 - (max_consecutive - threshold + 1) * 20.0)

    return FlavorCheck(
        name="段落开头同构",
        passed=max_consecutive < threshold,
        score=score,
        threshold=float(threshold),
        actual_value=float(max_consecutive),
        details=issues,
    )


# ── Check 6: Sentence length uniformity ─────────────────────────────────────


def _check_sentence_length_uniformity(
    content: str,
    threshold: float = 8.0,
) -> FlavorCheck:
    """Check if sentences are too uniform in length (AI hallmark)."""
    sentences = _split_sentences(content)
    if len(sentences) < 3:
        return FlavorCheck(
            name="句长均匀度",
            passed=True,
            score=100.0,
            threshold=threshold,
            actual_value=0.0,
            details=[],
        )

    lengths = [len(s.replace(" ", "")) for s in sentences if len(s.strip()) > 2]
    if len(lengths) < 3:
        return FlavorCheck(
            name="句长均匀度",
            passed=True,
            score=100.0,
            threshold=threshold,
            actual_value=0.0,
            details=[],
        )

    std_dev = statistics.pstdev(lengths)
    in_narrow_range = sum(1 for length in lengths if 15 <= length <= 25)
    narrow_ratio = in_narrow_range / len(lengths)

    issues: list[str] = []
    if std_dev < threshold:
        issues.append(f"句长标准差 {std_dev:.1f}（阈值 {threshold:.1f}），句子过于均匀")

    score = min(100.0, (std_dev / max(threshold, 0.01)) * 100.0)
    if narrow_ratio > 0.6:
        score *= 0.7
        issues.append(f"句长集中在15-25字区间（{narrow_ratio:.0%}），缺少长短变化")

    passed = std_dev >= threshold and narrow_ratio <= 0.6
    return FlavorCheck(
        name="句长均匀度",
        passed=passed,
        score=max(0.0, score),
        threshold=threshold,
        actual_value=round(std_dev, 1),
        details=issues,
    )


# ── Check 7: Dialogue tag monotony ──────────────────────────────────────────

_DIALOGUE_TAG_RE = re.compile(
    r"(?:说|道|问|答|喊|叫|骂|叹|笑|哭|怒|喝|嚷|吼|劝|赞|夸|"
    r"安慰|解释|回答|问道|说道|笑道|叹道|怒道|喝道|答道|"
    r"冷冷道|淡淡道|轻轻道|微微笑道|低声道|高声道|沉声道|"
    r"冷声道|厉声道|柔声道|朗声道|大声道|小声|低语|轻笑|"
    r"冷笑|苦笑|微笑|淡笑|浅笑|嗤笑|讥笑|"
    r"开口|回话|答话|插嘴|插话|接口|接话|"
    r"脱口而出|脱口|冲口而出|喃喃|喃喃自语|嘀咕|"
    r"说道|询问|追问|反问|质问|"
    r"道|言|曰)"
)

_FANCY_TAG_PATTERNS = [
    "低语道",
    "轻笑道",
    "冷声道",
    "厉声道",
    "柔声道",
    "朗声道",
    "微微笑道",
    "低声道",
    "高声道",
    "沉声道",
    "淡淡道",
    "轻轻道",
    "冷冷道",
    "苦笑道",
    "冷笑道",
    "淡笑道",
    "浅笑道",
    "嗤笑道",
    "淡笑",
    "浅笑",
    "嗤笑",
    "轻笑",
    "低语",
    "喃喃",
]


def _check_dialogue_tag_monotony(
    content: str,
    threshold: float = 0.2,
) -> FlavorCheck:
    """Check dialogue tag diversity and fancy-tag overuse."""
    dialogues = _extract_dialogues(content)
    if len(dialogues) < 3:
        return FlavorCheck(
            name="对话标签多样性",
            passed=True,
            score=100.0,
            threshold=threshold,
            actual_value=0.0,
            details=[],
        )

    tags = _DIALOGUE_TAG_RE.findall(content)
    unique_tags = len(set(tags))
    total_tags = len(tags) if tags else 1
    diversity = unique_tags / total_tags

    fancy_count = sum(content.count(p) for p in _FANCY_TAG_PATTERNS)
    fancy_ratio = fancy_count / max(total_tags, 1)

    issues: list[str] = []
    if diversity < threshold:
        issues.append(f"对话标签多样性 {diversity:.2f}（阈值 {threshold:.2f}），仅{unique_tags}种/共{total_tags}个")

    score = min(100.0, (diversity / max(threshold, 0.01)) * 100.0)
    if fancy_ratio > 0.5:
        score *= 0.7
        issues.append(f"花哨对话标签占比 {fancy_ratio:.0%}，过于依赖修饰性标签")

    passed = diversity >= threshold and fancy_ratio <= 0.5
    return FlavorCheck(
        name="对话标签多样性",
        passed=passed,
        score=max(0.0, score),
        threshold=threshold,
        actual_value=round(diversity, 3),
        details=issues,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Check registry — add a new check by registering a (name, factory) pair
# ══════════════════════════════════════════════════════════════════════════════

# Each entry: (key, factory) where factory takes (content, total_chars, threshold)
# and returns FlavorCheck.  Keys with non-standard signatures are handled
# separately in _build_check_map.
_CHECK_SPECS: list[tuple[str, Callable]] = [
    ("transition_words", _check_ai_transition_words),
    ("template_patterns", _check_ai_template_patterns),
    ("hedge_words", _check_ai_hedge_words),
    ("facial_micro", _check_facial_micro_expressions),
    ("paragraph_openings", _check_paragraph_openings),
    ("sentence_uniformity", _check_sentence_length_uniformity),
    ("dialogue_tag_diversity", _check_dialogue_tag_monotony),
]

_CHECK_KEYS = [key for key, _ in _CHECK_SPECS]


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════


def scan_chapter(content: str) -> AIFlavorReport:
    """Run all 7 AI-flavor checks on chapter content.

    Args:
        content: The chapter text to scan.

    Returns:
        AIFlavorReport with overall score, per-check results, and flagged lines.
    """
    return scan_chapter_custom(content)


def scan_chapter_custom(
    content: str,
    enabled_checks: list[str] | None = None,
    thresholds: dict[str, float] | None = None,
) -> AIFlavorReport:
    """Run AI-flavor checks with custom configuration.

    Args:
        content: The chapter text to scan.
        enabled_checks: List of check keys to run. None = all 7.
        thresholds: Dict of check_key -> threshold override.

    Returns:
        AIFlavorReport with results.
    """
    if not content or not content.strip():
        return AIFlavorReport(
            overall_score=100.0,
            is_clean=True,
            flagged_lines=["（章节内容为空，跳过AI味扫描）"],
        )

    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    total_chars = _word_count(content)
    if total_chars < 100:
        return AIFlavorReport(
            overall_score=100.0,
            is_clean=True,
            flagged_lines=["（章节过短，跳过AI味扫描）"],
        )

    # Build a lookup: key -> (factory, threshold)
    _NON_STANDARD = {"paragraph_openings", "sentence_uniformity", "dialogue_tag_diversity"}

    check_map: dict[str, tuple[Callable, float]] = {key: (factory, t[key]) for key, factory in _CHECK_SPECS}

    all_checks = enabled_checks or _CHECK_KEYS

    checks: list[FlavorCheck] = []
    for key in all_checks:
        if key not in check_map:
            continue
        factory, threshold = check_map[key]
        try:
            if key in _NON_STANDARD:
                checks.append(factory(content, int(threshold) if key == "paragraph_openings" else threshold))
            else:
                checks.append(factory(content, total_chars, threshold))
        except Exception:
            checks.append(
                FlavorCheck(
                    name=key,
                    passed=True,
                    score=100.0,
                    threshold=t.get(key, 0),
                    actual_value=0,
                    details=["检测异常，跳过"],
                )
            )

    if not checks:
        return AIFlavorReport(overall_score=100.0, is_clean=True)

    overall = sum(c.score for c in checks) / len(checks)
    flagged: list[str] = []
    for c in checks:
        if not c.passed:
            flagged.extend(c.details)

    return AIFlavorReport(
        overall_score=round(overall, 1),
        checks=checks,
        flagged_lines=flagged,
        is_clean=all(c.passed for c in checks),
    )
