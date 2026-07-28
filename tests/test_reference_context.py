"""Tests for reference book context injection into writing prompts."""

from unittest.mock import MagicMock, patch


class TestBuildReferenceContext:
    """Tests for _build_reference_context function."""

    @patch("core.writer.json_store")
    def test_returns_empty_when_no_reference_books(self, mock_store):
        """Should return empty string when no reference books set."""
        from core.writer import _build_reference_context

        mock_store.get_reference_books.return_value = []

        result = _build_reference_context("book_123")

        assert result == ""
        mock_store.get_reference_books.assert_called_once_with("book_123")

    @patch("core.writer.json_store")
    def test_returns_empty_when_reference_books_none(self, mock_store):
        """Should return empty string when reference books is None."""
        from core.writer import _build_reference_context

        mock_store.get_reference_books.return_value = None

        result = _build_reference_context("book_123")

        assert result == ""

    @patch("core.graph_store.GraphStore")
    @patch("core.writer.json_store")
    def test_builds_context_with_entities(self, mock_store, mock_graph_store_class):
        """Should build context with entities from reference book."""
        from core.writer import _build_reference_context

        mock_store.get_reference_books.return_value = ["ref_123"]
        mock_store.get_book.return_value = {"title": "原著小说"}

        # Mock entity
        mock_entity = MagicMock()
        mock_entity.name = "张三"
        mock_entity.type = "character"
        mock_entity.data = {"personality": "勇敢", "role": "主角"}

        mock_kb = MagicMock()
        mock_kb.list_entities.return_value = [mock_entity]
        mock_graph_store_class.return_value = mock_kb

        result = _build_reference_context("book_123")

        assert "原著小说" in result
        assert "张三" in result
        assert "character" in result

    @patch("core.graph_store.GraphStore")
    @patch("core.writer.json_store")
    def test_builds_context_with_chapters(self, mock_store, mock_graph_store_class):
        """Should include full chapter content when ref_chapters specified."""
        from core.writer import _build_reference_context

        mock_store.get_reference_books.return_value = ["ref_123"]
        mock_store.get_book.return_value = {"title": "原著小说"}

        mock_kb = MagicMock()
        mock_kb.list_entities.return_value = []
        mock_graph_store_class.return_value = mock_kb

        # Mock chapter
        mock_chapter = {
            "id": "ch_abc123",
            "versions": [{"id": "v1", "content": "这是第一章的完整内容...", "title": "第一章"}],
        }
        mock_store.load_chapters.return_value = [mock_chapter]
        mock_store._chapter_view.return_value = {
            "id": "ch_abc123",
            "title": "第一章",
            "content": "这是第一章的完整内容，讲述了主角的故事。",
        }

        result = _build_reference_context("book_123", ref_chapters=["ch_abc"])

        assert "原著小说" in result
        assert "第一章" in result
        assert "这是第一章的完整内容" in result

    @patch("core.graph_store.GraphStore")
    @patch("core.writer.json_store")
    def test_truncates_long_chapters(self, mock_store, mock_graph_store_class):
        """Should truncate chapters longer than max_ref_chapter_chars (50000)."""
        from core.writer import _build_reference_context

        mock_store.get_reference_books.return_value = ["ref_123"]
        mock_store.get_book.return_value = {"title": "原著小说"}

        mock_kb = MagicMock()
        mock_kb.list_entities.return_value = []
        mock_graph_store_class.return_value = mock_kb

        # Mock long chapter (exceeds 50000 limit)
        long_content = "A" * 60000
        mock_chapter = {"id": "ch_long", "versions": [{"id": "v1", "content": long_content, "title": "长章节"}]}
        mock_store.load_chapters.return_value = [mock_chapter]
        mock_store._chapter_view.return_value = {"id": "ch_long", "title": "长章节", "content": long_content}

        result = _build_reference_context("book_123", ref_chapters=["ch_long"])

        assert "截断" in result
        assert len(result) < 52000  # Should be truncated to ~50000 chars + overhead

    @patch("core.graph_store.GraphStore")
    @patch("core.writer.json_store")
    def test_handles_multiple_reference_books(self, mock_store, mock_graph_store_class):
        """Should handle multiple reference books."""
        from core.writer import _build_reference_context

        mock_store.get_reference_books.return_value = ["ref_1", "ref_2"]
        mock_store.get_book.side_effect = [{"title": "原著一"}, {"title": "原著二"}]

        mock_kb = MagicMock()
        mock_kb.list_entities.return_value = []
        mock_graph_store_class.return_value = mock_kb

        result = _build_reference_context("book_123")

        assert "原著一" in result
        assert "原著二" in result

    @patch("core.writer.json_store")
    def test_handles_exception_gracefully(self, mock_store):
        """Should handle exceptions and still return partial results."""
        from core.writer import _build_reference_context

        mock_store.get_reference_books.return_value = ["bad_ref"]
        mock_store.get_book.side_effect = Exception("Book not found")

        result = _build_reference_context("book_123")

        assert "加载失败" in result


class TestBuildWritePromptWithReference:
    """Tests for _build_write_prompt with ref_chapters parameter."""

    @patch("core.writer.json_store")
    def test_prompt_without_reference(self, mock_store):
        """Should build prompt without reference section when no ref books."""
        from core.writer import _build_write_prompt

        mock_store.get_reference_books.return_value = []

        prompt, system = _build_write_prompt("写第一章", "strict", "book_123")

        assert "写第一章" in prompt
        assert "参考书" not in prompt

    @patch("core.graph_store.GraphStore")
    @patch("core.writer.ContextManager")
    @patch("core.writer.json_store")
    def test_prompt_with_reference_entities(self, mock_store, mock_cm, mock_graph_store_class):
        """Should include reference entities in prompt."""
        from core.writer import _build_write_prompt

        mock_store.get_reference_books.return_value = ["ref_123"]
        mock_store.get_book.return_value = {"title": "原著"}

        mock_entity = MagicMock()
        mock_entity.name = "主角"
        mock_entity.type = "character"
        mock_entity.data = {"role": "英雄"}

        mock_kb = MagicMock()
        mock_kb.list_entities.return_value = [mock_entity]
        mock_graph_store_class.return_value = mock_kb

        mock_cm_instance = MagicMock()
        mock_cm_instance.build_writing_context.return_value = "知识库内容"
        mock_cm.return_value = mock_cm_instance

        prompt, system = _build_write_prompt("写第一章", "strict", "book_123")

        assert "参考书" in prompt
        assert "原著" in prompt


class TestToolDefinitions:
    """Tests for tool definitions with ref_chapters parameter."""

    def test_write_chapter_has_ref_chapters_param(self):
        """write_chapter tool should have ref_chapters parameter."""
        from core.tools import registry

        tool = registry.get("write_chapter")
        assert tool is not None
        assert "ref_chapters" in tool.parameters
        assert tool.parameters["ref_chapters"]["type"] == "array"

    def test_delegate_writing_has_ref_chapters_param(self):
        """delegate_writing tool should have ref_chapters parameter."""
        from core.tools import registry

        tool = registry.get("delegate_writing")
        assert tool is not None
        assert "ref_chapters" in tool.parameters
        assert tool.parameters["ref_chapters"]["type"] == "array"

    def test_list_reference_chapters_tool_exists(self):
        """list_reference_chapters tool should exist."""
        from core.tools import registry

        tool = registry.get("list_reference_chapters")
        assert tool is not None
        assert "ref_book_id" in tool.parameters

    def test_list_reference_chapters_in_read_tools(self):
        """list_reference_chapters should be in READ_TOOLS."""
        from core.tool_meta import READ_TOOLS

        assert "list_reference_chapters" in READ_TOOLS
