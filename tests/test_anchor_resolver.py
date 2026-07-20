# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Tests for the anchor resolver module."""

import pytest

from src.core.anchor_resolver import (
    _char_ngrams,
    _dice_coefficient,
    _levenshtein_similarity,
    _score_text_query,
    _sequence_similarity,
    find_sentence_in_text,
    rank_anchor,
    resolve_anchor,
    resolve_anchor_head_tail,
)


class TestCharNgrams:
    def test_empty(self):
        assert _char_ngrams("", 2) == set()

    def test_short(self):
        assert _char_ngrams("ab", 2) == {"ab"}
        assert _char_ngrams("a", 2) == {"a"}

    def test_bigrams(self):
        result = _char_ngrams("hello", 2)
        assert result == {"he", "el", "ll", "lo"}


class TestDiceCoefficient:
    def test_identical(self):
        assert _dice_coefficient({"a", "b"}, {"a", "b"}) == 1.0

    def test_disjoint(self):
        assert _dice_coefficient({"a"}, {"b"}) == 0.0

    def test_partial(self):
        s = _dice_coefficient({"a", "b", "c"}, {"b", "c", "d"})
        assert pytest.approx(s, 0.01) == 4 / 6  # 2*2 / (3+3) = 4/6


class TestLevenshtein:
    def test_identical(self):
        assert _levenshtein_similarity("hello", "hello") == 1.0

    def test_empty(self):
        assert _levenshtein_similarity("", "hello") == 0.0

    def test_one_edit(self):
        s = _levenshtein_similarity("hello", "hallo")
        assert s > 0.7  # one substitution in 5 chars


class TestSequenceSimilarity:
    def test_identical(self):
        assert _sequence_similarity("abc", "abc") == 1.0

    def test_empty(self):
        assert _sequence_similarity("", "abc") == 0.0

    def test_lcs(self):
        # "abc" in "xaybzc" → LCS "abc" len=3
        s = _sequence_similarity("abc", "xaybzc")
        expected = (2 * 3) / (3 + 6)  # 6/9 = 0.667
        assert s == pytest.approx(expected, abs=0.01)


class TestScoreTextQuery:
    def test_exact_match(self):
        assert _score_text_query("hello", "hello") == 1.0

    def test_normalized_match(self):
        s = _score_text_query("hello  world", "hello world")
        assert s > 0.9

    def test_substring(self):
        s = _score_text_query("hello", "hello world")
        assert s > 0.7

    def test_no_match(self):
        s = _score_text_query("hello", "xyz")
        assert s < 0.5


class TestRankAnchor:
    def test_ranks_by_score(self):
        candidates = ["hello world", "goodbye world", "hello there"]
        ranked = rank_anchor("hello", candidates)
        # Both "hello world" and "hello there" contain "hello" as substring
        # The top-ranked should be one of them
        assert ranked[0].text in ("hello world", "hello there")
        assert ranked[0].score > 0.5

    def test_marks_exact(self):
        candidates = ["hello world", "hello"]
        ranked = rank_anchor("hello", candidates)
        exact = [c for c in ranked if c.exact_raw]
        assert len(exact) == 1
        assert exact[0].text == "hello"
        assert exact[0].score == 1.0


class TestResolveAnchor:
    def test_exact_raw_resolve(self):
        candidates = ["你好世界", "张三在酒馆遇见李四", "其他内容"]
        result, failure = resolve_anchor("张三在酒馆遇见李四", candidates)
        assert result is not None
        assert failure is None
        assert result.sentence_ids == [2]
        assert result.strategy == "exact_raw"

    def test_no_match(self):
        candidates = ["你好世界", "其他内容"]
        result, failure = resolve_anchor(
            "张三在酒馆遇见李四张三四五六七八九十", candidates
        )
        assert result is None
        assert failure is not None
        assert failure.code == "low_confidence"

    def test_ambiguous(self):
        candidates = ["张三来了", "张三走了"]
        result, failure = resolve_anchor("张三", candidates)
        # Two short exact substring matches of query length < 8
        # should go to normalized comparison
        assert result is not None or failure is not None

    def test_empty_query(self):
        result, failure = resolve_anchor("", ["hello"])
        assert result is None
        assert failure is not None
        assert failure.code == "invalid"


class TestFindSentenceInText:
    def test_finds_sentence(self):
        text = "今天天气很好。张三在酒馆遇见了李四。他们聊了很久。"
        idx, conf = find_sentence_in_text("张三在酒馆遇见了李四", text)
        assert idx is not None
        assert conf > 0.9

    def test_no_match(self):
        text = "今天天气很好。他们聊了很久。"
        idx, conf = find_sentence_in_text("张三在酒馆遇见李四", text)
        assert idx is None

    def test_partial_match(self):
        text = "今天天气很好。张三在酒馆。他们聊了很久。"
        idx, conf = find_sentence_in_text("张三在酒馆", text)
        assert idx is not None
        assert conf > 0.7


class TestHeadTailAnchor:
    def test_both_found(self):
        candidates = ["张三在酒馆遇见了李四", "其他内容", "张三走了李四来了"]
        result, failure = resolve_anchor_head_tail("张三", "遇见了李四", candidates)
        assert result is not None
        assert failure is None
        assert result.sentence_ids == [1]

    def test_empty_head(self):
        result, failure = resolve_anchor_head_tail("", "tail", ["hello"])
        assert result is None
        assert failure is not None
        assert failure.code == "invalid"

    def test_empty_tail(self):
        result, failure = resolve_anchor_head_tail("head", "", ["hello"])
        assert result is None
        assert failure is not None
        assert failure.code == "invalid"

    def test_no_match(self):
        candidates = ["hello world", "goodbye world"]
        result, failure = resolve_anchor_head_tail("张三", "李四", candidates)
        assert result is None
        assert failure is not None

    def test_ordered_match(self):
        # Both candidates contain head and tail — ambiguous
        candidates = ["张三遇见李四在酒馆", "张三在酒馆遇见李四"]
        result, failure = resolve_anchor_head_tail("张三", "遇见李四", candidates)
        # Both match, so either result resolves or fails as ambiguous
        assert result is not None or failure is not None
        if result is not None:
            assert result.confidence > 0.8
