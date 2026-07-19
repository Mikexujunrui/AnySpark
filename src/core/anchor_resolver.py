# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Evidence anchor resolver — locate fuzzy LLM references in source text.

Ported from Wiki-Graph's ``EvidenceResolver`` (TypeScript → Python).
Pure algorithmic module — no LLM calls, no external dependencies.

Key use cases:
- Hallucination detection: verify that LLM claims like "第3章提到张三喜欢李四"
  actually appear in chapter 3.
- Knowledge panel "view source": jump to the exact sentence that supports a
  knowledge claim.

Algorithm:
    1. Parse anchor spec (``full`` or ``head_tail`` mode)
    2. Rank candidate sentences using composite scoring:
       - 0.35 x char n-gram (Dice coefficient, 2-gram + 3-gram)
       - 0.35 x sequence similarity (longest common subsequence)
       - 0.20 x Levenshtein similarity
       - 0.10 x length penalty
    3. Auto-resolve when confidence is high, return candidates otherwise.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Scoring constants ────────────────────────────────────────────────────────
MIN_AUTO_RESOLVE_GAP = 0.07
MIN_AUTO_RESOLVE_SCORE = 0.9
MIN_CANDIDATE_SCORE = 0.55
VERY_HIGH_CONFIDENCE_SCORE = 0.97
MAX_CANDIDATE_DISPLAY = 3


@dataclass
class RankedCandidate:
    """A candidate sentence with its match score against an anchor."""

    index: int
    sentence_id: int  # 1-based sentence index
    text: str
    score: float
    exact_raw: bool = False
    exact_normalized: bool = False
    exact_substring: bool = False
    prev_text: str = ""
    next_text: str = ""


@dataclass
class ResolutionResult:
    """Successful resolution of an anchor to a range of sentences."""

    sentence_ids: list[int]
    confidence: float
    strategy: str  # e.g. "exact_raw", "exact_substring_scored", "auto_top1"


@dataclass
class ResolutionFailure:
    """Anchor could not be resolved confidently."""

    field_name: str
    code: str  # "invalid_anchor", "none", "low_confidence", "ambiguous_ranked"
    message: str
    candidates: list[RankedCandidate] = field(default_factory=list)


def _normalize_text(text: str) -> str:
    """Normalize text for comparison: strip whitespace, lowercase."""
    return re.sub(r"\s+", " ", text.strip()).lower()


def _char_ngrams(text: str, size: int) -> set[str]:
    """Extract character n-grams from text."""
    if len(text) <= size:
        return {text} if text else set()
    return {text[i : i + size] for i in range(len(text) - size + 1)}


def _dice_coefficient(left: set[str], right: set[str]) -> float:
    """Dice coefficient for two sets of n-grams."""
    if not left or not right:
        return 0.0
    overlap = len(left & right)
    return (2 * overlap) / (len(left) + len(right))


def _char_ngram_score(left: str, right: str) -> float:
    """Composite char n-gram score: average of Dice(2-gram) + Dice(3-gram)."""
    left_bigrams = _char_ngrams(left, 2)
    right_bigrams = _char_ngrams(right, 2)
    left_trigrams = _char_ngrams(left, 3)
    right_trigrams = _char_ngrams(right, 3)
    return (_dice_coefficient(left_bigrams, right_bigrams) +
            _dice_coefficient(left_trigrams, right_trigrams)) / 2


def _sequence_similarity(left: str, right: str) -> float:
    """Longest common subsequence (LCS) normalized by total length."""
    if left == right:
        return 1.0
    if not left or not right:
        return 0.0

    m, n = len(left), len(right)
    # Full DP matrix for LCS length
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if left[i - 1] == right[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    lcs_len = dp[m][n]
    return (2 * lcs_len) / (m + n)


def _levenshtein_similarity(left: str, right: str) -> float:
    """Levenshtein distance normalized as similarity."""
    if left == right:
        return 1.0
    if not left or not right:
        return 0.0

    m, n = len(left), len(right)
    prev = list(range(n + 1))
    curr = [0] * (n + 1)

    for i in range(1, m + 1):
        curr[0] = i
        for j in range(1, n + 1):
            insert = curr[j - 1] + 1
            delete = prev[j] + 1
            replace = prev[j - 1] + (0 if left[i - 1] == right[j - 1] else 1)
            curr[j] = min(insert, delete, replace)
        prev, curr = curr, prev

    distance = prev[n]
    return 1.0 - distance / max(m, n)


def _length_penalty(left: str, right: str) -> float:
    """Penalize large length differences."""
    return 1.0 - abs(len(left) - len(right)) / max(len(left), len(right), 1)


def _score_text_query(query: str, candidate: str) -> float:
    """Composite score: query against a candidate sentence.

    Returns a float in [0, 1].
    """
    query_norm = _normalize_text(query)
    candidate_norm = _normalize_text(candidate)

    if not query_norm or not candidate_norm:
        return 0.0

    # Exact matches
    if query_norm == candidate_norm:
        return 1.0
    if candidate_norm in query_norm:
        return min(0.92, 0.78 + 0.14 * len(candidate_norm) / max(len(query_norm), 1))
    if query_norm in candidate_norm:
        return 0.75 + 0.25 * len(query_norm) / max(len(candidate_norm), 1)

    return (
        0.35 * _char_ngram_score(query_norm, candidate_norm)
        + 0.35 * _sequence_similarity(query_norm, candidate_norm)
        + 0.20 * _levenshtein_similarity(query_norm, candidate_norm)
        + 0.10 * _length_penalty(query_norm, candidate_norm)
    )


def rank_anchor(
    query: str,
    candidate_texts: list[str],
    candidate_indices: list[int] | None = None,
) -> list[RankedCandidate]:
    """Rank candidate sentences against a query anchor string.

    Args:
        query: The anchor text to search for (e.g. "张三在酒馆遇见李四").
        candidate_texts: List of sentence texts to search in.
        candidate_indices: Optional 1-based indices for each sentence. If None,
            uses 1-based enumeration.

    Returns:
        List of RankedCandidate sorted by descending score.
    """
    if candidate_indices is None:
        candidate_indices = list(range(1, len(candidate_texts) + 1))

    query_norm = _normalize_text(query)
    ranked: list[RankedCandidate] = []

    for i, (text, sid) in enumerate(zip(candidate_texts, candidate_indices, strict=False)):
        text_norm = _normalize_text(text)

        # Check exact match types
        exact_raw = query.strip() == text.strip()
        exact_normalized = query_norm == text_norm
        exact_substring = query_norm in text_norm

        if exact_raw:
            score = 1.0
        elif exact_normalized:
            score = 0.995
        elif exact_substring:
            coverage = len(query_norm) / max(len(text_norm), 1)
            score = min(1.0, 0.75 + 0.25 * coverage)
        else:
            score = _score_text_query(query, text)

        prev_text = candidate_texts[i - 1] if i > 0 else ""
        next_text = candidate_texts[i + 1] if i + 1 < len(candidate_texts) else ""

        ranked.append(RankedCandidate(
            index=i,
            sentence_id=sid,
            text=text,
            score=score,
            exact_raw=exact_raw,
            exact_normalized=exact_normalized,
            exact_substring=exact_substring,
            prev_text=prev_text,
            next_text=next_text,
        ))

    # Sort by score descending, then by exact match flags, then by index
    ranked.sort(key=lambda c: (-c.score, not c.exact_raw, not c.exact_substring,
                                not c.exact_normalized, c.index))
    return ranked


def resolve_anchor(
    query: str,
    candidate_texts: list[str],
    candidate_indices: list[int] | None = None,
    min_index: int | None = None,
) -> tuple[ResolutionResult | None, ResolutionFailure | None]:
    """Try to resolve an anchor query to a specific sentence or range.

    Supports two modes:
    - ``full``: The query is a complete text fragment (default).
    - ``head_tail``: Use ``resolve_anchor_head_tail(head, tail, ...)`` instead.

    Args:
        query: The anchor text to match.
        candidate_texts: List of sentence texts.
        candidate_indices: 1-based sentence indices.
        min_index: If provided, only consider candidates at or after this index.

    Returns:
        A tuple of (result, failure). Exactly one will be non-None.
    """
    if not query or not query.strip():
        return None, ResolutionFailure(
            field_name="query",
            code="invalid",
            message="Query is empty",
        )

    candidates = rank_anchor(query, candidate_texts, candidate_indices)

    if min_index is not None:
        candidates = [c for c in candidates if c.index >= min_index]

    if not candidates:
        return None, ResolutionFailure(
            field_name="query",
            code="none",
            message="No candidates available",
        )

    return _resolve_from_candidates(candidates, query)


def resolve_anchor_head_tail(
    head: str,
    tail: str,
    candidate_texts: list[str],
    candidate_indices: list[int] | None = None,
) -> tuple[ResolutionResult | None, ResolutionFailure | None]:
    """Resolve a head_tail anchor: match a sentence starting with ``head``
    and ending with ``tail``.

    Examples:
        head="张三", tail="遇见李四" matches "张三在酒馆遇见李四"

    The head and tail are scored independently against each candidate,
    then combined with an ordering bonus.
    """
    if not head or not head.strip():
        return None, ResolutionFailure(
            field_name="head",
            code="invalid",
            message="Head anchor is empty",
        )
    if not tail or not tail.strip():
        return None, ResolutionFailure(
            field_name="tail",
            code="invalid",
            message="Tail anchor is empty",
        )

    if candidate_indices is None:
        candidate_indices = list(range(1, len(candidate_texts) + 1))

    head_norm = _normalize_text(head)
    tail_norm = _normalize_text(tail)

    ranked: list[RankedCandidate] = []
    for i, (text, sid) in enumerate(zip(candidate_texts, candidate_indices, strict=False)):
        text_norm = _normalize_text(text)

        head_pos = text_norm.find(head_norm)
        tail_pos = text_norm.rfind(tail_norm)

        if head_pos != -1 and tail_pos != -1 and head_pos <= tail_pos:
            covered = head_norm + tail_norm
            coverage = min(1.0, len(covered) / max(1, len(text_norm)))
            score = 0.82 + 0.18 * coverage
            exact_sub = True
        else:
            head_score = _score_text_query(head, text)
            tail_score = _score_text_query(tail, text)
            ordered = 1.0 if head_pos <= tail_pos else 0.85
            score = ((head_score + tail_score) / 2) * ordered
            exact_sub = False

        prev_text = candidate_texts[i - 1] if i > 0 else ""
        next_text = candidate_texts[i + 1] if i + 1 < len(candidate_texts) else ""

        ranked.append(RankedCandidate(
            index=i,
            sentence_id=sid,
            text=text,
            score=score,
            exact_substring=exact_sub,
            prev_text=prev_text,
            next_text=next_text,
        ))

    ranked.sort(key=lambda c: (-c.score, not c.exact_substring, c.index))

    if not ranked:
        return None, ResolutionFailure(
            field_name="head_tail",
            code="none",
            message="No candidates available",
        )

    return _resolve_from_candidates(ranked, f"{head[:20]}...{tail[:20]}")


def _resolve_from_candidates(
    candidates: list[RankedCandidate],
    query_label: str,
) -> tuple[ResolutionResult | None, ResolutionFailure | None]:
    """Shared resolution logic for both full and head_tail anchors."""

    # Strategy 1: single exact raw match
    exact_raw = [c for c in candidates if c.exact_raw]
    if len(exact_raw) == 1:
        c = exact_raw[0]
        return ResolutionResult(
            sentence_ids=[c.sentence_id],
            confidence=c.score,
            strategy="exact_raw",
        ), None
    if len(exact_raw) > 1:
        return None, ResolutionFailure(
            field_name=query_label[:40],
            code="ambiguous_exact_raw",
            message=f"Multiple exact matches for '{query_label[:40]}'",
            candidates=exact_raw[:MAX_CANDIDATE_DISPLAY],
        )

    # Strategy 2: single exact substring match (query length >= 8 chars)
    exact_sub = [c for c in candidates if c.exact_substring]
    if len(exact_sub) == 1 and len(query_label.strip()) >= 8:
        c = exact_sub[0]
        return ResolutionResult(
            sentence_ids=[c.sentence_id],
            confidence=c.score,
            strategy="exact_substring",
        ), None

    # Strategy 3: single exact normalized match
    exact_norm = [c for c in candidates if c.exact_normalized]
    if len(exact_norm) == 1:
        c = exact_norm[0]
        return ResolutionResult(
            sentence_ids=[c.sentence_id],
            confidence=c.score,
            strategy="exact_normalized",
        ), None

    # Strategy 4: auto-resolve by score thresholds
    top = candidates[0]
    second_score = candidates[1].score if len(candidates) > 1 else 0.0
    gap = top.score - second_score

    if top.score < MIN_CANDIDATE_SCORE:
        return None, ResolutionFailure(
            field_name=query_label[:40],
            code="low_confidence",
            message=f"Best candidate score={top.score:.3f} below threshold",
            candidates=candidates[:MAX_CANDIDATE_DISPLAY],
        )

    if len(candidates) == 1:
        return ResolutionResult(
            sentence_ids=[top.sentence_id],
            confidence=top.score,
            strategy="auto_top1_single",
        ), None

    if top.score >= VERY_HIGH_CONFIDENCE_SCORE:
        return ResolutionResult(
            sentence_ids=[top.sentence_id],
            confidence=top.score,
            strategy="auto_top1_very_high",
        ), None

    if top.score >= MIN_AUTO_RESOLVE_SCORE and gap >= MIN_AUTO_RESOLVE_GAP:
        return ResolutionResult(
            sentence_ids=[top.sentence_id],
            confidence=top.score,
            strategy="auto_top1",
        ), None

    return None, ResolutionFailure(
        field_name=query_label[:40],
        code="ambiguous_ranked",
        message=f"Ambiguous match for '{query_label[:40]}': top={top.score:.3f}, gap={gap:.3f}",
        candidates=candidates[:MAX_CANDIDATE_DISPLAY],
    )


def find_sentence_in_text(
    anchor_text: str,
    full_text: str,
    min_confidence: float = 0.55,
) -> tuple[int | None, float]:
    """Convenience: find a sentence containing the anchor in a full text.

    Splits `full_text` into sentences (by Chinese/English punctuation),
    then runs `resolve_anchor` to find the best match.

    Args:
        anchor_text: The text to search for.
        full_text: The full source text to search in.
        min_confidence: Minimum confidence threshold.

    Returns:
        Tuple of (sentence_index, confidence). sentence_index is 1-based,
        or None if no match found.
    """
    # Split into sentences
    sentences = re.split(r"(?<=[。！？.!?\n])\s*", full_text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return None, 0.0

    result, failure = resolve_anchor(anchor_text, sentences)
    if result is not None and result.confidence >= min_confidence:
        return result.sentence_ids[0], result.confidence

    # Fallback: return best candidate even if not auto-resolved
    if failure is not None and failure.candidates:
        best = failure.candidates[0]
        if best.score >= min_confidence:
            return best.sentence_id, best.score

    return None, 0.0
