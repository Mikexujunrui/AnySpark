# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Tests for dedup module — SimHash and segment matching."""

from core.dedup import (
    DupPair,
    SegmentMatch,
    _hash64,
    _jaccard_similarity,
    _tokenize_ngrams,
    compute_simhash,
    find_repeated_segments,
    hamming_distance,
    simhash_similarity,
)


class TestSimHash:
    """Test SimHash computation and comparison."""

    def test_identical_text_same_hash(self):
        """Identical texts should produce identical SimHash values."""
        text = "这是一段测试文本，用于验证SimHash算法的正确性。"
        h1 = compute_simhash(text)
        h2 = compute_simhash(text)
        assert h1 == h2

    def test_similar_text_low_hamming(self):
        """Similar texts should have low Hamming distance."""
        text_a = "张三走进了酒馆，要了一壶酒。"
        text_b = "张三走进了酒馆，要了一壶酒。"
        h_a = compute_simhash(text_a)
        h_b = compute_simhash(text_b)
        assert hamming_distance(h_a, h_b) == 0

    def test_different_text_high_hamming(self):
        """Very different texts should have higher Hamming distance."""
        text_a = "天空蓝蓝的，鸟儿在歌唱。春天来了，万物复苏。"
        text_b = "黑暗笼罩大地，死亡降临。战争摧毁了一切。"
        h_a = compute_simhash(text_a)
        h_b = compute_simhash(text_b)
        assert hamming_distance(h_a, h_b) > 0

    def test_empty_text_zero_hash(self):
        """Empty text should produce zero hash."""
        assert compute_simhash("") == 0

    def test_similarity_range(self):
        """simhash_similarity should return value in [0, 1]."""
        h1 = compute_simhash("测试文本一")
        h2 = compute_simhash("完全不同的另一段文字")
        sim = simhash_similarity(h1, h2)
        assert 0 <= sim <= 1

    def test_hash64_stable(self):
        """Same token should always hash to same value."""
        assert _hash64("测试") == _hash64("测试")


class TestNgramTokenize:
    """Test n-gram tokenization."""

    def test_short_text(self):
        """Text shorter than n-gram size returns single token."""
        tokens = _tokenize_ngrams("ab")
        assert len(tokens) == 1

    def test_normal_text(self):
        """Normal text produces multiple n-grams."""
        tokens = _tokenize_ngrams("abcdef")
        assert len(tokens) == 4  # abc, bcd, cde, def

    def test_empty_text(self):
        """Empty text produces no tokens."""
        assert _tokenize_ngrams("") == []


class TestJaccardSimilarity:
    """Test Jaccard similarity."""

    def test_identical_sets(self):
        """Identical sets have Jaccard = 1."""
        s = {"a", "b", "c"}
        assert _jaccard_similarity(s, s) == 1.0

    def test_disjoint_sets(self):
        """Disjoint sets have Jaccard = 0."""
        assert _jaccard_similarity({"a", "b"}, {"c", "d"}) == 0.0

    def test_empty_sets(self):
        """Empty sets have Jaccard = 0."""
        assert _jaccard_similarity(set(), set()) == 0.0


class TestSegmentMatching:
    """Test segment-level repeated content detection."""

    def test_identical_segments(self):
        """Identical segments should be detected as repeats."""
        text_a = "这是一段重复的内容，请检测到它。"
        text_b = "这是一段重复的内容，请检测到它。"
        results = find_repeated_segments(text_a, text_b, window_size=10, threshold=0.5)
        assert len(results) > 0
        assert results[0][2] >= 0.5  # similarity score

    def test_different_segments(self):
        """Very different segments should not match."""
        text_a = "天空蓝蓝的，鸟儿在歌唱。春天来了，万物复苏。一切都很美好。"
        text_b = "黑暗笼罩大地，死亡降临。战争摧毁了一切。绝望蔓延。"
        results = find_repeated_segments(text_a, text_b, window_size=10, threshold=0.8)
        assert len(results) == 0

    def test_empty_texts(self):
        """Empty texts produce no matches."""
        assert find_repeated_segments("", "") == []
        assert find_repeated_segments("有内容", "") == []


class TestDataclasses:
    """Test dataclass serialization."""

    def test_dup_pair_to_dict(self):
        pair = DupPair(
            chapter_a_id="ch1",
            chapter_a_title="第一章",
            chapter_b_id="ch2",
            chapter_b_title="第二章",
            similarity=0.85,
            hamming_distance=5,
        )
        d = pair.to_dict()
        assert d["chapter_a_id"] == "ch1"
        assert d["similarity"] == 0.85

    def test_segment_match_to_dict(self):
        match = SegmentMatch(
            chapter_a_id="ch1",
            chapter_b_id="ch2",
            segment_a="重复段落内容",
            segment_b="重复段落内容",
            similarity=0.9,
            length=6,
        )
        d = match.to_dict()
        assert d["length"] == 6
        assert d["similarity"] == 0.9
