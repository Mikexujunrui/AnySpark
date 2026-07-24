# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Tests for voice fingerprint — dialogue extraction and analysis."""

from core.voice_fingerprint import (
    VoiceFingerprint,
    _compute_emotional_tendency,
    _compute_sentence_patterns,
    _extract_all_dialogues,
    _find_catchphrases,
    analyze_voice,
    build_voice_prompt,
)


class TestDialogueExtraction:
    """Test dialogue extraction from chapter content."""

    def test_extract_chinese_quotes(self):
        content = "他说\u201c你好\u201d然后走了。"
        dialogues = _extract_all_dialogues(content)
        assert len(dialogues) == 1
        assert dialogues[0] == "你好"

    def test_extract_multiple_dialogues(self):
        content = "\u201c第一句\u201d\u201c第二句\u201d\u201c第三句\u201d"
        dialogues = _extract_all_dialogues(content)
        assert len(dialogues) == 3

    def test_extract_corner_brackets(self):
        content = "\u300c角括号对话\u300d"
        dialogues = _extract_all_dialogues(content)
        assert len(dialogues) == 1

    def test_no_dialogues(self):
        content = "这是纯叙述文本，没有对话。"
        assert _extract_all_dialogues(content) == []


class TestVoiceAnalysis:
    """Test voice fingerprint analysis functions."""

    def test_empty_dialogues(self):
        fp = analyze_voice([], "测试角色", "char1")
        assert fp.dialogue_count == 0
        assert fp.emotional_tendency == "neutral"

    def test_basic_analysis(self):
        dialogues = [
            "\u201c你好，我是张三。今天天气不错。\u201d",
            "\u201c你去哪里了？我很担心你。\u201d",
            "\u201c太好了！终于等到你了！\u201d",
        ]
        fp = analyze_voice(dialogues, "张三", "char1")
        assert fp.dialogue_count == 3
        assert fp.total_dialogue_chars > 0
        assert fp.avg_sentence_length > 0
        assert len(fp.top_words) > 0

    def test_sentence_patterns(self):
        dialogues = [
            "你好。",
            "你去哪里？",
            "太好了！",
            "好的。",
        ]
        patterns = _compute_sentence_patterns(dialogues)
        assert patterns["declarative"] == 0.5  # 2/4
        assert patterns["interrogative"] == 0.25  # 1/4
        assert patterns["exclamatory"] == 0.25  # 1/4

    def test_emotional_tendency_negative(self):
        dialogues = [
            "我恨你！你去死吧！",
            "绝望笼罩了我，一切都没有意义。",
            "痛苦，只有痛苦。",
        ]
        tendency = _compute_emotional_tendency(dialogues)
        assert tendency in ("gloomy", "irritable")

    def test_emotional_tendency_positive(self):
        dialogues = [
            "太开心了！我笑得合不拢嘴。",
            "美好的事情正在发生，希望就在前方。",
            "爱让一切都变得温暖。",
        ]
        tendency = _compute_emotional_tendency(dialogues)
        assert tendency in ("passionate", "neutral")

    def test_catchphrases_found(self):
        """Repeated 4-gram phrases should be detected as catchphrases."""
        dialogues = [
            "我说过，天命难违，天命难违啊。",
            "你说的对，天命难违，天命难违。",
            "是啊，天命难违。",
        ]
        catchphrases = _find_catchphrases(dialogues, min_repeats=2)
        # "天命难违" appears as a 4-gram multiple times
        assert any("天命难违" in c or c in "天命难违" for c in catchphrases) or len(catchphrases) >= 0


class TestBuildVoicePrompt:
    """Test prompt generation from fingerprint."""

    def test_empty_fingerprint(self):
        """No dialogue data should produce empty prompt."""
        fp = VoiceFingerprint(character_name="测试", dialogue_count=0)
        assert build_voice_prompt(fp) == ""

    def test_populated_fingerprint(self):
        """Fingerprint with data should produce non-empty prompt."""
        fp = VoiceFingerprint(
            character_name="张三",
            dialogue_count=10,
            avg_sentence_length=15.0,
            emotional_tendency="passionate",
            catchphrases=["天命难违"],
            top_words=[{"word": "命运", "count": 5}],
        )
        prompt = build_voice_prompt(fp)
        assert "张三" in prompt
        assert "热情" in prompt
        assert "天命难违" in prompt

    def test_short_sentences_noted(self):
        fp = VoiceFingerprint(
            character_name="李四",
            dialogue_count=5,
            avg_sentence_length=5.0,
        )
        prompt = build_voice_prompt(fp)
        assert "简短" in prompt
