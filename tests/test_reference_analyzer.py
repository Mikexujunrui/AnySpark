# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Tests for reference_analyzer — structure analysis and style quantification."""

from unittest.mock import patch

import pytest

from core.reference_analyzer import (
    StructureReport,
    StyleFingerprint,
    _compute_dialogue_density,
    _compute_four_char_idiom_density,
    _compute_paragraph_length_stats,
    _compute_punctuation_pattern,
    _compute_sentence_length_distribution,
    _compute_ttr,
    _split_paragraphs,
    _split_sentences,
    _word_count,
    analyze_structure,
    load_analysis,
    quantify_style,
)

# ── Sample text for testing ──────────────────────────────────────────────

SAMPLE_CHAPTER_1 = """公子走进书房，只见凤尾森森，龙吟细细。

\u201c妹妹可大好了？\u201d公子问道。
小姐抿嘴一笑，\u201c哪里就好了，不过是强撑着罢了。\u201d
公子叹道：\u201c你总是这样，何苦来哉。\u201d

两人对坐无言，只听得窗外竹声飒飒。"""

SAMPLE_CHAPTER_2 = """话说老夫人在堂上坐定，众媳妇丫鬟簇拥而来。

\u201c今日是什么日子，怎么都来了？\u201d老夫人笑道。
大少奶奶忙上前说：\u201c老祖宗，今儿是端阳佳节，大家来给老太太请安。\u201d
老夫人点头道：\u201c难为你们想着。\u201d

于是摆下酒宴，众人依次入座。公子小姐同在一桌，少爷二姑娘紧挨着坐了。"""


# ── Text utility tests ───────────────────────────────────────────────────


class TestTextUtilities:
    def test_word_count(self):
        text = "你好 世界\n\n 这是测试"
        # 8 non-whitespace chars
        assert _word_count(text) == 8

    def test_split_sentences(self):
        text = "你好。世界！再见？"
        sentences = _split_sentences(text)
        assert len(sentences) == 3

    def test_split_paragraphs(self):
        text = "段落一。\n\n段落二。\n\n段落三。"
        paras = _split_paragraphs(text)
        assert len(paras) == 3

    def test_split_paragraphs_single(self):
        text = "只有一个段落。"
        paras = _split_paragraphs(text)
        assert len(paras) == 1


# ── Structure analysis tests ─────────────────────────────────────────────


class TestStructureAnalysis:
    """Test analyze_structure with mocked json_store."""

    def _mock_chapters(self):
        """Return mock chapter data that _chapter_view can process."""
        return [
            {
                "id": "ch1",
                "title": "第一回",
                "versions": [{"id": "v1", "content": SAMPLE_CHAPTER_1, "title": "第一回"}],
                "current_version": "v1",
            },
            {
                "id": "ch2",
                "title": "第二回",
                "versions": [{"id": "v2", "content": SAMPLE_CHAPTER_2, "title": "第二回"}],
                "current_version": "v2",
            },
        ]

    def test_analyze_structure_basic(self):
        """Given 2 chapters, verify structure report is correct."""
        with patch("core.reference_analyzer.json_store") as mock_store:
            mock_store.load_chapters.return_value = self._mock_chapters()
            mock_store._chapter_view.side_effect = lambda ch: {
                "title": ch["title"],
                "content": ch["versions"][0]["content"],
            }

            report = analyze_structure("test_book")

        assert report.book_id == "test_book"
        assert report.chapter_count == 2
        assert report.total_words > 0
        assert len(report.chapter_length_distribution) == 2
        assert len(report.dialogue_ratio_distribution) == 2
        assert 0.0 < report.avg_dialogue_ratio < 1.0
        assert len(report.pacing_curve) == 2
        assert report.pacing_curve[0]["chapter"] == 1
        assert report.pacing_curve[1]["chapter"] == 2

    def test_analyze_structure_empty_book(self):
        """Empty book should return empty report."""
        with patch("core.reference_analyzer.json_store") as mock_store:
            mock_store.load_chapters.return_value = []
            report = analyze_structure("empty_book")

        assert report.book_id == "empty_book"
        assert report.chapter_count == 0

    def test_structure_report_to_prompt_fragment(self):
        """to_prompt_fragment should produce readable constraint text."""
        report = StructureReport(
            book_id="test",
            chapter_count=80,
            total_words=680000,
            avg_chapter_length=8500.0,
            avg_dialogue_ratio=0.35,
            paragraph_stats={"avg_per_chapter": 12.0, "avg_length": 700.0},
            sentence_stats={"avg_per_chapter": 50.0, "avg_length": 17.0},
        )
        fragment = report.to_prompt_fragment()
        assert "80" in fragment
        assert "8500" in fragment or "8500" in fragment.replace(".0", "")
        assert "35.0%" in fragment or "35%" in fragment
        assert "续写" in fragment

    def test_empty_prompt_fragment(self):
        """Empty report should produce empty fragment."""
        report = StructureReport(book_id="empty")
        assert report.to_prompt_fragment() == ""


# ── Style quantification tests ───────────────────────────────────────────


class TestStyleQuantification:
    """Test quantify_style and style analysis functions."""

    def _mock_chapters(self):
        return [
            {
                "id": "ch1",
                "title": "第一回",
                "versions": [{"id": "v1", "content": SAMPLE_CHAPTER_1, "title": "第一回"}],
                "current_version": "v1",
            },
            {
                "id": "ch2",
                "title": "第二回",
                "versions": [{"id": "v2", "content": SAMPLE_CHAPTER_2, "title": "第二回"}],
                "current_version": "v2",
            },
        ]

    def test_quantify_style_basic(self):
        with patch("core.reference_analyzer.json_store") as mock_store:
            mock_store.load_chapters.return_value = self._mock_chapters()
            mock_store._chapter_view.side_effect = lambda ch: {
                "title": ch["title"],
                "content": ch["versions"][0]["content"],
            }

            fp = quantify_style("test_book")

        assert fp.book_id == "test_book"
        assert fp.sentence_length_distribution  # non-empty
        assert 0.0 < fp.vocabulary_richness_ttr < 1.0
        assert fp.punctuation_pattern  # non-empty
        assert fp.dialogue_density > 0.0

    def test_quantify_style_empty_book(self):
        with patch("core.reference_analyzer.json_store") as mock_store:
            mock_store.load_chapters.return_value = []
            fp = quantify_style("empty_book")

        assert fp.book_id == "empty_book"
        assert not fp.sentence_length_distribution

    def test_sentence_length_distribution(self):
        text = (
            "短句。这也是短句。这是一个稍微长一点的句子呢。"
            "这是一个非常非常非常非常长的句子，包含了大量的文字内容，"
            "而且还有很多很多额外的描述用来确保超过四十字的阈值从而进入长句区间。"
        )
        dist = _compute_sentence_length_distribution(text)
        assert sum(dist.values()) == pytest.approx(1.0)
        assert dist["<10"] > 0  # has short sentences
        assert dist[">40"] > 0  # has long sentence

    def test_ttr(self):
        # Repeated text should have low TTR
        text = "你好你好你好你好你好"
        ttr = _compute_ttr(text)
        assert 0.0 < ttr < 0.5  # low diversity

        # Varied text should have higher TTR
        text2 = "苹果香蕉橘子葡萄西瓜荔枝"
        ttr2 = _compute_ttr(text2)
        assert ttr2 > ttr

    def test_punctuation_pattern(self):
        text = "你好。世界！再见？好了，好的。"
        pattern = _compute_punctuation_pattern(text)
        assert "。" in pattern
        assert pattern["。"] > 0
        assert "！" in pattern
        assert pattern["！"] > 0

    def test_paragraph_length_stats(self):
        text = "短段落。\n\n这是一个中等长度的段落，包含一些内容。\n\n这是一个非常非常长的段落，包含了大量的文字内容，用来测试段落长度统计功能是否正常工作。"
        stats = _compute_paragraph_length_stats(text)
        assert "mean" in stats
        assert "median" in stats
        assert stats["mean"] > 0

    def test_dialogue_density(self):
        text = "\u201c你好\u201d\u201c再见\u201d这是叙述部分。"
        density = _compute_dialogue_density(text)
        assert 0.0 < density < 1.0

    def test_four_char_idiom_density(self):
        # Text with repeated 4-char phrases
        text = "天命难违天命难违天命难违" * 3
        density = _compute_four_char_idiom_density(text)
        assert density > 0  # should detect repeated 4-grams

    def test_style_fingerprint_to_prompt_fragment(self):
        fp = StyleFingerprint(
            book_id="test",
            sentence_length_distribution={"<10": 0.2, "10-20": 0.4, "20-40": 0.3, ">40": 0.1},
            vocabulary_richness_ttr=0.72,
            four_char_idiom_density=0.05,
            punctuation_pattern={"。": 0.35, "，": 0.40},
            paragraph_length_stats={"mean": 85.0, "median": 80.0},
            dialogue_density=0.35,
        )
        fragment = fp.to_prompt_fragment()
        assert "文风" in fragment
        assert "句长" in fragment
        assert "0.720" in fragment or "0.72" in fragment

    def test_empty_style_prompt_fragment(self):
        fp = StyleFingerprint(book_id="")
        assert fp.to_prompt_fragment() == ""


# ── Caching tests ────────────────────────────────────────────────────────


class TestCaching:
    """Test analysis result caching and loading."""

    def test_load_analysis_missing(self, tmp_path):
        """load_analysis should return None for non-existent file."""
        with patch("core.reference_analyzer.ANALYSES_DIR", tmp_path):
            result = load_analysis("structure", "nonexistent_book")
        assert result is None

    def test_analysis_saved_and_loaded(self, tmp_path):
        """analyze_structure should save to disk, and load_analysis should read it."""
        mock_chapters = [
            {
                "id": "ch1",
                "title": "测试",
                "versions": [{"id": "v1", "content": "这是测试内容。", "title": "测试"}],
                "current_version": "v1",
            },
        ]

        with patch("core.reference_analyzer.ANALYSES_DIR", tmp_path):
            with patch("core.reference_analyzer.json_store") as mock_store:
                mock_store.load_chapters.return_value = mock_chapters
                mock_store._chapter_view.side_effect = lambda ch: {
                    "title": ch["title"],
                    "content": ch["versions"][0]["content"],
                }

                # First call: analyze and save
                report = analyze_structure("cache_test_book")
                assert report.chapter_count == 1

                # Verify file was saved
                saved = load_analysis("structure", "cache_test_book")
                assert saved is not None
                assert saved["chapter_count"] == 1
                assert saved["book_id"] == "cache_test_book"
