# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Tests for pacing analyzer — pure function unit tests."""

from core.pacing_analyzer import (
    ChapterPacing,
    PacingMetrics,
    _compute_emotional_volatility,
    _count_scene_transitions,
    _extract_dialogues,
    _split_sentences,
    analyze_chapter,
)


class TestAnalyzeChapter:
    """Test the main analyze_chapter function."""

    def test_empty_content(self):
        result = analyze_chapter("")
        assert isinstance(result, PacingMetrics)
        assert result.pacing_score == 0.0

    def test_whitespace_only(self):
        result = analyze_chapter("   \n\n  \t  ")
        assert result.pacing_score == 0.0

    def test_pure_narration(self):
        """Text with no dialogue should have dialogue_ratio = 0."""
        content = "天空灰蒙蒙的，风吹过荒原。远处传来阵阵雷声。"
        result = analyze_chapter(content)
        assert result.dialogue_ratio == 0.0
        assert result.pacing_score > 0  # non-zero because of scene/emotional metrics

    def test_dialogue_heavy(self):
        """Text with lots of dialogue should have high dialogue_ratio."""
        content = "\u201c你来了\u201d\u201c嗯，我来了\u201d\u201c为什么\u201d\u201c因为命运\u201d"
        result = analyze_chapter(content)
        assert result.dialogue_ratio > 0.3

    def test_pacing_score_range(self):
        """Pacing score should be between 0 and 100."""
        content = "这是一段测试文本。天空很蓝。鸟儿在歌唱。\u201c你好\u201d他说。"
        result = analyze_chapter(content)
        assert 0 <= result.pacing_score <= 100

    def test_scene_transitions(self):
        """Scene cue words should be detected."""
        content = "第一天，他们在酒馆喝酒。第二天，天空放晴。与此同时，远处传来号角声。"
        count = _count_scene_transitions(content)
        assert count >= 2  # at least "第二天" and "与此同时"

    def test_emotional_volatility(self):
        """Text with emotional shifts should have non-zero volatility.
        Content must exceed window_size (200 chars) to span multiple windows
        and trigger sentiment sign flips."""
        content = (
            "他很高兴，笑得合不拢嘴。" * 10
            + "突然，他感到悲伤，泪水涌出。" * 10
            + "愤怒在他心中燃烧，他想要报复。" * 10
            + "但希望依然存在，明天会更好。" * 10
        )
        vol = _compute_emotional_volatility(content)
        assert vol > 0

    def test_sentence_splitting(self):
        """Sentences should be split by Chinese sentence-end punctuation."""
        content = "第一句。第二句！第三句？第四句。"
        sentences = _split_sentences(content)
        assert len(sentences) == 4

    def test_dialogue_extraction(self):
        """Dialogues should be extracted from Chinese quotes."""
        content = "他说\u201c你好\u201d然后她回答\u201c谢谢\u201d"
        dialogues = _extract_dialogues(content)
        assert len(dialogues) == 2
        assert "你好" in dialogues
        assert "谢谢" in dialogues

    def test_metrics_to_dict(self):
        """to_dict should produce serializable output."""
        metrics = PacingMetrics(
            dialogue_ratio=0.3,
            sentence_length_variance=5.0,
            scene_transition_count=3,
            emotional_volatility=2.0,
            pacing_score=50.0,
        )
        d = metrics.to_dict()
        assert d["dialogue_ratio"] == 0.3
        assert d["pacing_score"] == 50.0
        assert d["scene_transition_count"] == 3

    def test_chapter_pacing_to_dict(self):
        """ChapterPacing.to_dict should include chapter metadata."""
        cp = ChapterPacing(
            chapter_id="ch1",
            title="第一章",
            chapter_index=1,
            word_count=3000,
        )
        d = cp.to_dict()
        assert d["chapter_id"] == "ch1"
        assert d["title"] == "第一章"
        assert d["chapter_index"] == 1
        assert d["word_count"] == 3000
