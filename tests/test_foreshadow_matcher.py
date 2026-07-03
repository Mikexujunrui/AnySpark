# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Tests for foreshadow matcher — TF-IDF similarity and matching logic."""

import pytest

from core.foreshadow_matcher import (
    ForeshadowMatch,
    _cosine_similarity,
    _keyword_overlap,
    _split_into_windows,
    _tf_vector,
    _tokenize,
)


class TestTokenize:
    """Test Chinese text tokenization."""

    def test_normal_text(self):
        tokens = _tokenize("abcdef")
        assert len(tokens) == 5  # ab, bc, cd, de, ef

    def test_empty_text(self):
        assert _tokenize("") == []

    def test_single_char(self):
        assert _tokenize("a") == []


class TestTFVector:
    """Test term frequency vector computation."""

    def test_empty_tokens(self):
        vec = _tf_vector([])
        assert vec == {}

    def test_single_token(self):
        vec = _tf_vector(["ab"])
        assert vec == {"ab": 1.0}

    def test_repeated_tokens(self):
        vec = _tf_vector(["ab", "ab", "cd"])
        assert vec["ab"] == 2 / 3
        assert vec["cd"] == 1 / 3


class TestCosineSimilarity:
    """Test cosine similarity computation."""

    def test_identical_vectors(self):
        vec = {"a": 0.5, "b": 0.5}
        assert _cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_disjoint_vectors(self):
        assert _cosine_similarity({"a": 1.0}, {"b": 1.0}) == 0.0

    def test_empty_vectors(self):
        assert _cosine_similarity({}, {}) == 0.0

    def test_partial_overlap(self):
        vec_a = {"a": 0.5, "b": 0.5}
        vec_b = {"a": 0.5, "c": 0.5}
        sim = _cosine_similarity(vec_a, vec_b)
        assert 0 < sim < 1


class TestKeywordOverlap:
    """Test keyword overlap ratio."""

    def test_identical_sets(self):
        assert _keyword_overlap("abcdef", "abcdef") > 0

    def test_disjoint_sets(self):
        assert _keyword_overlap("aaaa", "zzzz") == 0.0

    def test_empty_text(self):
        assert _keyword_overlap("", "test") == 0.0


class TestWindowSplitting:
    """Test sliding window generation."""

    def test_short_text(self):
        windows = _split_into_windows("短文本", window_size=500)
        assert len(windows) == 1
        assert windows[0][0] == "短文本"

    def test_long_text(self):
        text = "a" * 1000
        windows = _split_into_windows(text, window_size=500)
        assert len(windows) >= 2

    def test_empty_text(self):
        assert _split_into_windows("") == []


class TestForeshadowMatchDataclass:
    """Test ForeshadowMatch serialization."""

    def test_to_dict(self):
        match = ForeshadowMatch(
            foreshadow_id="fs1",
            foreshadow_description="神秘信件",
            foreshadow_chapter="ch1",
            matched_chapter_id="ch5",
            matched_chapter_title="第五章",
            matched_text="信件终于被打开了",
            similarity=0.85,
            status="matched",
        )
        d = match.to_dict()
        assert d["foreshadow_id"] == "fs1"
        assert d["similarity"] == 0.85
        assert d["status"] == "matched"
