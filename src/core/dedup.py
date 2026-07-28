# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Cross-chapter deduplication — SimHash + sliding window for repeated content.

Pure-function module with no external dependencies. Uses Python's built-in
hashlib and itertools for similarity detection.

Two-level approach:
1. SimHash (64-bit) per chapter → fast pairwise Hamming distance for chapter-level similarity
2. N-gram Jaccard similarity for precise segment-level matching
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from data.json_store import json_store

# SimHash parameters
_SIMHASH_BITS = 64
_NGRAM_SIZE = 3  # character-level 3-grams for Chinese text


@dataclass
class DupPair:
    """A pair of chapters with high similarity."""

    chapter_a_id: str = ""
    chapter_a_title: str = ""
    chapter_b_id: str = ""
    chapter_b_title: str = ""
    similarity: float = 0.0  # 0-1
    hamming_distance: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "chapter_a_id": self.chapter_a_id,
            "chapter_a_title": self.chapter_a_title,
            "chapter_b_id": self.chapter_b_id,
            "chapter_b_title": self.chapter_b_title,
            "similarity": round(self.similarity, 3),
            "hamming_distance": self.hamming_distance,
        }


@dataclass
class SegmentMatch:
    """A specific repeated segment between two chapters."""

    chapter_a_id: str = ""
    chapter_b_id: str = ""
    segment_a: str = ""  # the repeated text in chapter A
    segment_b: str = ""  # the matching text in chapter B
    similarity: float = 0.0
    length: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "chapter_a_id": self.chapter_a_id,
            "chapter_b_id": self.chapter_b_id,
            "segment_a": self.segment_a[:200],
            "segment_b": self.segment_b[:200],
            "similarity": round(self.similarity, 3),
            "length": self.length,
        }


# ── SimHash implementation ──


def _tokenize_ngrams(text: str, n: int = _NGRAM_SIZE) -> list[str]:
    """Generate character-level n-grams from text."""
    clean = re.sub(r"\s+", "", text)
    if len(clean) < n:
        return [clean] if clean else []
    return [clean[i : i + n] for i in range(len(clean) - n + 1)]


def _hash64(token: str) -> int:
    """Stable 64-bit hash for a token."""
    h = hashlib.md5(token.encode("utf-8")).hexdigest()
    return int(h[:16], 16)


def compute_simhash(text: str) -> int:
    """Compute a 64-bit SimHash fingerprint for the given text.

    Algorithm:
    1. Tokenize text into n-grams
    2. Hash each n-gram to 64 bits
    3. For each bit position, sum +1 if the bit is set, -1 if not
    4. Final bit = 1 if sum > 0, else 0
    """
    tokens = _tokenize_ngrams(text)
    if not tokens:
        return 0

    vector = [0] * _SIMHASH_BITS
    for token in tokens:
        h = _hash64(token)
        for i in range(_SIMHASH_BITS):
            if h & (1 << i):
                vector[i] += 1
            else:
                vector[i] -= 1

    fingerprint = 0
    for i in range(_SIMHASH_BITS):
        if vector[i] > 0:
            fingerprint |= 1 << i
    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    """Count differing bits between two 64-bit SimHash values."""
    return bin(a ^ b).count("1")


def simhash_similarity(a: int, b: int) -> float:
    """Convert Hamming distance to similarity score (0-1)."""
    dist = hamming_distance(a, b)
    return 1.0 - (dist / _SIMHASH_BITS)


# ── Segment-level matching ──


def _jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Compute Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 0.0
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def find_repeated_segments(
    text_a: str,
    text_b: str,
    window_size: int = 80,
    threshold: float = 0.7,
) -> list[tuple[str, str, float]]:
    """Find repeated segments between two texts using sliding window + Jaccard.

    Returns list of (segment_a, segment_b, similarity) tuples.
    """
    if not text_a or not text_b:
        return []

    results: list[tuple[str, str, float]] = []
    seen: set[tuple[int, int]] = set()

    clean_a = re.sub(r"\s+", "", text_a)
    clean_b = re.sub(r"\s+", "", text_b)

    if len(clean_a) < window_size or len(clean_b) < window_size:
        return results

    for i in range(0, len(clean_a) - window_size + 1, window_size // 2):
        seg_a = clean_a[i : i + window_size]
        ngrams_a = set(_tokenize_ngrams(seg_a))

        for j in range(0, len(clean_b) - window_size + 1, window_size // 2):
            if (i, j) in seen:
                continue
            seg_b = clean_b[j : j + window_size]
            ngrams_b = set(_tokenize_ngrams(seg_b))
            sim = _jaccard_similarity(ngrams_a, ngrams_b)
            if sim >= threshold:
                results.append((seg_a, seg_b, sim))
                seen.add((i, j))

    return results


# ── Book-level analysis ──


def find_similar_pairs(book_id: str, threshold: float = 0.8) -> list[DupPair]:
    """Find chapter pairs with high SimHash similarity.

    Args:
        book_id: The book to analyze.
        threshold: Minimum similarity (0-1) to report. Default 0.8.
    """
    chapters = json_store.load_chapters(book_id)
    regular = [ch for ch in chapters if not ch.get("is_extra")]

    # Compute SimHash for each chapter
    hashes: list[tuple[str, str, int]] = []
    for ch in regular:
        cur = json_store._get_current_version(ch)
        content = cur.get("content", "")
        sh = compute_simhash(content)
        title = cur.get("title", ch.get("title", ""))
        hashes.append((ch.get("id", ""), title, sh))

    # Pairwise comparison
    pairs: list[DupPair] = []
    for i in range(len(hashes)):
        for j in range(i + 1, len(hashes)):
            sim = simhash_similarity(hashes[i][2], hashes[j][2])
            dist = hamming_distance(hashes[i][2], hashes[j][2])
            if sim >= threshold:
                pairs.append(
                    DupPair(
                        chapter_a_id=hashes[i][0],
                        chapter_a_title=hashes[i][1],
                        chapter_b_id=hashes[j][0],
                        chapter_b_title=hashes[j][1],
                        similarity=sim,
                        hamming_distance=dist,
                    )
                )

    pairs.sort(key=lambda p: p.similarity, reverse=True)
    return pairs


def find_repeated_segments_book(
    book_id: str,
    min_length: int = 80,
    threshold: float = 0.7,
) -> list[SegmentMatch]:
    """Find specific repeated text segments across all chapter pairs.

    Args:
        book_id: The book to analyze.
        min_length: Minimum segment length in characters.
        threshold: Minimum Jaccard similarity to report.
    """
    chapters = json_store.load_chapters(book_id)
    regular = [ch for ch in chapters if not ch.get("is_extra")]

    # Pre-compute content
    contents: list[tuple[str, str, str]] = []
    for ch in regular:
        cur = json_store._get_current_version(ch)
        content = cur.get("content", "")
        contents.append((ch.get("id", ""), cur.get("title", ch.get("title", "")), content))

    matches: list[SegmentMatch] = []
    for i in range(len(contents)):
        for j in range(i + 1, len(contents)):
            segs = find_repeated_segments(
                contents[i][2],
                contents[j][2],
                window_size=min_length,
                threshold=threshold,
            )
            for seg_a, seg_b, sim in segs:
                matches.append(
                    SegmentMatch(
                        chapter_a_id=contents[i][0],
                        chapter_b_id=contents[j][0],
                        segment_a=seg_a,
                        segment_b=seg_b,
                        similarity=sim,
                        length=len(seg_a),
                    )
                )

    matches.sort(key=lambda m: m.length, reverse=True)
    return matches


def dedup_book(book_id: str) -> dict[str, Any]:
    """Run full dedup analysis and return combined results."""
    pairs = find_similar_pairs(book_id)
    segments = find_repeated_segments_book(book_id)
    return {
        "book_id": book_id,
        "similar_pairs": [p.to_dict() for p in pairs],
        "repeated_segments": [s.to_dict() for s in segments],
        "total_pairs": len(pairs),
        "total_segments": len(segments),
    }
