# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Foreshadow auto-matcher — detect foreshadow-payoff pairs via text similarity.

Uses a lightweight text similarity approach (TF-IDF cosine + keyword overlap)
instead of embeddings to avoid external dependencies. For each foreshadow,
scans subsequent chapters for text segments that could be the "payoff" (回收).

Dangling foreshadows (no match found within N chapters) are flagged.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from data.json_store import json_store

logger = logging.getLogger(__name__)

# Maximum chapters after a foreshadow to search for payoffs
_MAX_SEARCH_CHAPTERS = 30
# Similarity threshold for a match
_MATCH_THRESHOLD = 0.35
# Dangling threshold: if no match within this many chapters
_DANGLING_THRESHOLD = 15


@dataclass
class ForeshadowMatch:
    """A potential foreshadow-payoff match."""

    foreshadow_id: str = ""
    foreshadow_description: str = ""
    foreshadow_chapter: str = ""
    matched_chapter_id: str = ""
    matched_chapter_title: str = ""
    matched_text: str = ""
    similarity: float = 0.0
    status: str = "matched"  # matched / dangling / weak

    def to_dict(self) -> dict[str, Any]:
        return {
            "foreshadow_id": self.foreshadow_id,
            "foreshadow_description": self.foreshadow_description[:100],
            "foreshadow_chapter": self.foreshadow_chapter,
            "matched_chapter_id": self.matched_chapter_id,
            "matched_chapter_title": self.matched_chapter_title,
            "matched_text": self.matched_text[:200],
            "similarity": round(self.similarity, 3),
            "status": self.status,
        }


# ── TF-IDF similarity (lightweight, no external deps) ──


def _tokenize(text: str) -> list[str]:
    """Tokenize Chinese text into 2-char tokens."""
    clean = re.sub(r"\s+", "", text)
    return [clean[i : i + 2] for i in range(len(clean) - 1)]


def _tf_vector(tokens: list[str]) -> dict[str, float]:
    """Compute term frequency vector."""
    counter = Counter(tokens)
    total = len(tokens) or 1
    return {term: count / total for term, count in counter.items()}


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Compute cosine similarity between two sparse vectors."""
    if not vec_a or not vec_b:
        return 0.0
    dot = sum(vec_a.get(t, 0) * vec_b.get(t, 0) for t in vec_a if t in vec_b)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _keyword_overlap(text_a: str, text_b: str) -> float:
    """Simple keyword overlap ratio for short texts."""
    words_a = set(_tokenize(text_a))
    words_b = set(_tokenize(text_b))
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / min(len(words_a), len(words_b))


def _split_into_windows(text: str, window_size: int = 500) -> list[tuple[str, int]]:
    """Split text into sliding windows.

    Returns list of (window_text, start_position).
    """
    clean = re.sub(r"\s+", "", text)
    if len(clean) <= window_size:
        return [(clean, 0)] if clean else []
    windows: list[tuple[str, int]] = []
    step = window_size // 2  # 50% overlap
    for i in range(0, len(clean) - window_size + 1, step):
        windows.append((clean[i : i + window_size], i))
    return windows


# ── Foreshadow matching ──


def _get_foreshadows(book_id: str) -> list[dict]:
    """Get all foreshadows from the knowledge graph."""
    try:
        from core.graph_store import GraphStore

        store = GraphStore()
        return store.list_foreshadows()
    except Exception as e:
        logger.warning("Failed to load foreshadows: %s", e)
        return []


def _get_chapter_index(chapters: list[dict], chapter_id: str) -> int:
    """Get the 0-based index of a chapter in the regular chapter list."""
    regular = [ch for ch in chapters if not ch.get("is_extra")]
    for i, ch in enumerate(regular):
        if ch.get("id") == chapter_id:
            return i
    return -1


def match_foreshadows(book_id: str) -> list[ForeshadowMatch]:
    """Match all foreshadows to potential payoff passages in subsequent chapters.

    For each foreshadow:
    1. Get its description text
    2. Find which chapter it was set up in
    3. Scan subsequent chapters in sliding windows
    4. Score each window by TF-IDF cosine + keyword overlap
    5. Best match above threshold → "matched"
    6. No match within N chapters → "dangling"
    """
    foreshadows = _get_foreshadows(book_id)
    if not foreshadows:
        return []

    chapters = json_store.load_chapters(book_id)
    regular = [ch for ch in chapters if not ch.get("is_extra")]

    # Pre-compute chapter content and TF vectors
    chapter_data: list[dict] = []
    for ch in regular:
        cur = json_store._get_current_version(ch)
        content = cur.get("content", "")
        windows = _split_into_windows(content)
        window_vectors = [_tf_vector(_tokenize(w[0])) for w in windows]
        chapter_data.append(
            {
                "id": ch.get("id", ""),
                "title": cur.get("title", ch.get("title", "")),
                "windows": windows,
                "window_vectors": window_vectors,
            }
        )

    results: list[ForeshadowMatch] = []

    for fs in foreshadows:
        fs_id = fs.get("id", "")
        fs_desc = fs.get("name", "") or fs.get("description", "") or ""
        if not fs_desc:
            continue

        # Determine which chapter the foreshadow was set up in
        fs_chapter = fs.get("source_chapter", "") or fs.get("chapter_id", "")
        start_idx = _get_chapter_index(chapters, fs_chapter) if fs_chapter else 0
        if start_idx < 0:
            start_idx = 0

        # TF vector for the foreshadow description
        fs_tokens = _tokenize(fs_desc)
        fs_vector = _tf_vector(fs_tokens)

        best_match: ForeshadowMatch | None = None
        best_sim = 0.0

        # Search subsequent chapters
        end_idx = min(len(chapter_data), start_idx + _MAX_SEARCH_CHAPTERS + 1)
        for ci in range(start_idx, end_idx):
            ch = chapter_data[ci]
            for wi, (window_text, _) in enumerate(ch["windows"]):
                wv = ch["window_vectors"][wi]
                sim = _cosine_similarity(fs_vector, wv)
                # Boost with keyword overlap for short descriptions
                overlap = _keyword_overlap(fs_desc, window_text)
                combined = sim * 0.7 + overlap * 0.3

                if combined > best_sim:
                    best_sim = combined
                    best_match = ForeshadowMatch(
                        foreshadow_id=fs_id,
                        foreshadow_description=fs_desc,
                        foreshadow_chapter=fs_chapter,
                        matched_chapter_id=ch["id"],
                        matched_chapter_title=ch["title"],
                        matched_text=window_text,
                        similarity=combined,
                        status="matched" if combined >= _MATCH_THRESHOLD else "weak",
                    )

        if best_match and best_match.similarity >= _MATCH_THRESHOLD:
            results.append(best_match)
        elif best_match and best_match.similarity >= _MATCH_THRESHOLD * 0.5:
            best_match.status = "weak"
            results.append(best_match)
        else:
            # Dangling foreshadow
            search_range = end_idx - start_idx
            results.append(
                ForeshadowMatch(
                    foreshadow_id=fs_id,
                    foreshadow_description=fs_desc,
                    foreshadow_chapter=fs_chapter,
                    status="dangling" if search_range >= _DANGLING_THRESHOLD else "pending",
                    similarity=0.0,
                )
            )

    return results


def find_dangling_foreshadows(book_id: str) -> list[dict]:
    """Return only foreshadows that have no detected payoff (dangling)."""
    matches = match_foreshadows(book_id)
    return [m.to_dict() for m in matches if m.status == "dangling"]


def foreshadow_summary(book_id: str) -> dict[str, Any]:
    """Get summary of foreshadow matching status for a book."""
    matches = match_foreshadows(book_id)
    matched = [m for m in matches if m.status == "matched"]
    weak = [m for m in matches if m.status == "weak"]
    dangling = [m for m in matches if m.status == "dangling"]
    pending = [m for m in matches if m.status == "pending"]

    return {
        "book_id": book_id,
        "total_foreshadows": len(matches),
        "matched": len(matched),
        "weak": len(weak),
        "dangling": len(dangling),
        "pending": len(pending),
        "matches": [m.to_dict() for m in matches],
        "dangling_list": [m.to_dict() for m in dangling],
    }
