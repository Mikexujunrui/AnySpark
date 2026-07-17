"""Tests for _format_chapter_result helper function."""
from unittest.mock import patch


class TestFormatChapterResult:
    """Tests for the chapter result formatter."""

    @patch('tools.impl.writing.json_store')
    def test_returns_structured_format(self, mock_store):
        """Should return structured result with progress and preview."""
        from tools.impl.writing import _format_chapter_result

        mock_store.load_chapters.return_value = [{"id": "1"}, {"id": "2"}]
        mock_store.get_outline.return_value = {"chapters": [1, 2, 3, 4, 5]}

        result = _format_chapter_result(
            "book_123", "abc12345xyz", "第2章",
            "这是一段测试内容，讲述了主角的冒险故事。"
        )

        assert "✅ 章节: 第2章" in result
        assert "id: abc12345" in result
        assert "进度: 2/5" in result
        assert "内容预览:" in result
        assert "这是一段测试内容" in result

    @patch('tools.impl.writing.json_store')
    def test_no_hallucination_keywords(self, mock_store):
        """Result should NOT contain '已保存' which triggers hallucination detection."""
        from tools.impl.writing import _format_chapter_result

        mock_store.load_chapters.return_value = [{"id": "1"}]
        mock_store.get_outline.return_value = {"chapters": []}

        result = _format_chapter_result(
            "book_123", "abc12345", "第1章", "测试内容"
        )

        # These keywords could trigger Layer 1 hallucination detection
        assert "已保存" not in result
        assert "已完成" not in result
        assert "已经保存" not in result
        assert "写入" not in result

    @patch('tools.impl.writing.json_store')
    def test_progress_without_outline(self, mock_store):
        """Should show chapter count when no outline exists."""
        from tools.impl.writing import _format_chapter_result

        mock_store.load_chapters.return_value = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
        mock_store.get_outline.return_value = {"chapters": []}

        result = _format_chapter_result(
            "book_123", "abc12345", "第3章", "内容"
        )

        assert "共3章" in result

    @patch('tools.impl.writing.json_store')
    def test_content_preview_truncated(self, mock_store):
        """Long content should be truncated in preview."""
        from tools.impl.writing import _format_chapter_result

        mock_store.load_chapters.return_value = []
        mock_store.get_outline.return_value = {"chapters": []}

        long_content = "A" * 500
        result = _format_chapter_result(
            "book_123", "abc12345", "长章节", long_content
        )

        # Preview should be truncated at 150 chars
        assert "..." in result
        # Full length should be shown
        assert "500字" in result

    @patch('tools.impl.writing.json_store')
    def test_extra_info_appended(self, mock_store):
        """Extra info like scope should be appended."""
        from tools.impl.writing import _format_chapter_result

        mock_store.load_chapters.return_value = []
        mock_store.get_outline.return_value = {"chapters": []}

        result = _format_chapter_result(
            "book_123", "abc12345", "第1章", "内容",
            extra="知识范围: 人物: 叶凡, 林婉 | 禁止: 苏晴"
        )

        assert "知识范围:" in result
        assert "叶凡" in result
        assert "苏晴" in result

    @patch('tools.impl.writing.json_store')
    def test_word_count_accurate(self, mock_store):
        """Word count should match actual content length."""
        from tools.impl.writing import _format_chapter_result

        mock_store.load_chapters.return_value = []
        mock_store.get_outline.return_value = {"chapters": []}

        content = "这是一段测试内容" * 100  # 800 chars
        result = _format_chapter_result(
            "book_123", "abc12345", "测试章节", content
        )

        assert f"{len(content)}字" in result
