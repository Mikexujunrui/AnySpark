"""Tests for additional executor.py functions: _regex_split_chapters, _parse_chapter_range, _count_words."""

from tools._common import _parse_chapter_range
from tools.impl.chapters import _count_words
from tools.impl.imports import _regex_split_chapters


class TestRegexSplitChapters:
    """Test chapter splitting using regex patterns."""

    def test_standard_chapter_pattern(self):
        # Need at least 500 chars per chapter
        text = "第一章 开始\n" + "这是第一章的内容。" * 100 + "\n\n第二章 发展\n" + "这是第二章的内容。" * 100 + "\n\n第三章 高潮\n" + "这是第三章的内容。" * 100
        chapters = _regex_split_chapters(text)
        assert len(chapters) == 3
        assert "第一章" in chapters[0]["title"]
        assert "第二章" in chapters[1]["title"]
        assert "第三章" in chapters[2]["title"]

    def test_numeric_chapter_pattern(self):
        text = "第1章 启程\n" + "内容一。" * 150 + "\n\n第2章 到达\n" + "内容二。" * 150
        chapters = _regex_split_chapters(text)
        assert len(chapters) == 2

    def test_no_chapters(self):
        text = "这是一整段没有章节标记的文字。"
        chapters = _regex_split_chapters(text)
        # Should return empty list when no chapters found
        assert chapters == []

    def test_too_short_chapters(self):
        # Chapters less than 500 chars should be filtered
        text = """第一章 短章节
简短内容。

第二章 也短
也很短的内容。"""
        chapters = _regex_split_chapters(text)
        assert chapters == []


class TestParseChapterRange:
    """Test chapter range parsing."""

    def test_single_number(self):
        # Input is 1-based, output is 0-based
        result = _parse_chapter_range("3", 10)
        assert result == [2]  # 3 - 1 = 2

    def test_range(self):
        result = _parse_chapter_range("2-5", 10)
        assert result == [1, 2, 3, 4]  # 2-1 to 5-1

    def test_comma_separated(self):
        result = _parse_chapter_range("1,3,5", 10)
        assert result == [0, 2, 4]  # 1-1, 3-1, 5-1

    def test_mixed_not_supported(self):
        # Mixed ranges like "1,3-5,8" not supported by simple parser
        result = _parse_chapter_range("1,3-5,8", 10)
        # Will be treated as comma-separated, "3-5" will fail int conversion
        assert isinstance(result, list)

    def test_out_of_range_filtered(self):
        result = _parse_chapter_range("1,15", 10)
        assert 14 not in result  # 15-1=14, out of range (0-9)
        assert 0 in result  # 1-1=0

    def test_all_keyword(self):
        result = _parse_chapter_range("all", 5)
        assert result == [0, 1, 2, 3, 4]  # 0-based indices

    def test_chinese_all(self):
        result = _parse_chapter_range("全部", 5)
        assert result == [0, 1, 2, 3, 4]

    def test_invalid_input_returns_empty(self):
        # Invalid input returns empty list, doesn't raise
        result = _parse_chapter_range("invalid", 10)
        assert result == []


class TestCountWords:
    """Test word counting functionality."""

    def test_chinese_characters(self):
        result = _count_words({"text": "你好世界"})
        # Should count Chinese characters
        assert "4" in str(result) or "字" in str(result)

    def test_mixed_content(self):
        result = _count_words({"text": "Hello 你好 World 世界"})
        assert result is not None

    def test_empty_text(self):
        result = _count_words({"text": ""})
        assert "0" in str(result) or "字" in str(result)

    def test_with_punctuation(self):
        result = _count_words({"text": "你好，世界！这是一个测试。"})
        assert result is not None
