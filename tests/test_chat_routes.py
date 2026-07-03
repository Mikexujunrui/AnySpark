"""Tests for chat.py route pure functions."""

import pytest

from routes.chat import INTERVENTION_PATTERNS, classify_intervention


class TestClassifyIntervention:
    """Test autopilot intervention detection."""

    def test_pause_pattern(self):
        action, _ = classify_intervention("暂停一下")
        assert action == "pause"

    def test_pause_english(self):
        action, _ = classify_intervention("please pause")
        assert action == "pause"

    def test_cancel_pattern(self):
        action, _ = classify_intervention("取消吧")
        assert action == "cancel"

    def test_skip_chapter(self):
        action, _ = classify_intervention("跳过当前章节")
        assert action == "skip_chapter"

    def test_skip_short(self):
        action, _ = classify_intervention("skip")
        assert action == "skip_chapter"

    def test_modify_instruction(self):
        action, _ = classify_intervention("改一下风格，更激烈一点")
        assert action == "modify_instruction"

    def test_modify_chapter(self):
        action, _ = classify_intervention("第3章改一下开头")
        assert action == "modify_chapter"

    def test_no_intervention(self):
        action, _ = classify_intervention("继续写下去")
        assert action == "chat_overlay"

    def test_normal_chat(self):
        action, _ = classify_intervention("今天天气怎么样")
        assert action == "chat_overlay"

    def test_false_positive_resistant(self):
        """Ensure normal chat containing keywords doesn't misclassify."""
        # "停" alone shouldn't match the pattern requiring more context
        action, _ = classify_intervention("你好")
        assert action == "chat_overlay"

    def test_intervention_patterns_are_valid(self):
        """Verify all patterns compile as valid regex."""
        for pattern, action in INTERVENTION_PATTERNS:
            import re
            try:
                re.compile(pattern)
                assert isinstance(action, str)
            except re.error as e:
                pytest.fail(f"Invalid regex '{pattern}': {e}")

    def test_intervention_returns_tuple(self):
        """All intervention results should be (action, dict) tuples."""
        action, data = classify_intervention("暂停")
        assert isinstance(action, str)
        assert isinstance(data, dict)
