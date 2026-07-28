"""Tests for list_books and set_reference_books validation."""

from unittest.mock import patch


class TestListBooks:
    """Tests for list_books handler."""

    @patch("tools.impl.handlers.json_store")
    def test_list_books_returns_available_projects(self, mock_store):
        """Should list all projects except the current one."""
        mock_store.load_books.return_value = [
            {"id": "book_123", "title": "当前书", "stats": {"entity_count": 5, "chapter_count": 10}},
            {"id": "book_456", "title": "参考书A", "stats": {"entity_count": 20, "chapter_count": 50}},
            {"id": "book_789", "title": "参考书B", "stats": {"entity_count": 10, "chapter_count": 30}},
        ]
        from tools.impl.handlers import _handle_materials

        result = _handle_materials("list_books", {}, "book_123")
        assert "参考书A" in result
        assert "参考书B" in result
        assert "当前书" not in result  # Should not include current book
        assert "book_456" in result
        assert "book_789" in result

    @patch("tools.impl.handlers.json_store")
    def test_list_books_empty_system(self, mock_store):
        """Should return empty message when no projects exist."""
        mock_store.load_books.return_value = []
        from tools.impl.handlers import _handle_materials

        result = _handle_materials("list_books", {}, "book_123")
        assert "没有项目" in result

    @patch("tools.impl.handlers.json_store")
    def test_list_books_only_current_book(self, mock_store):
        """Should return message when only current book exists."""
        mock_store.load_books.return_value = [
            {"id": "book_123", "title": "当前书", "stats": {}},
        ]
        from tools.impl.handlers import _handle_materials

        result = _handle_materials("list_books", {}, "book_123")
        assert "没有其他项目" in result


class TestSetReferenceBooksValidation:
    """Tests for set_reference_books ID validation."""

    @patch("tools.impl.handlers.json_store")
    def test_set_reference_books_valid_id(self, mock_store):
        """Should accept valid book IDs."""
        mock_store.load_books.return_value = [
            {"id": "book_123", "title": "当前书"},
            {"id": "book_456", "title": "参考书A"},
        ]
        from tools.impl.handlers import _handle_materials

        result = _handle_materials("set_reference_books", {"book_ids": ["book_456"]}, "book_123")
        assert "已设置参考书" in result
        assert "参考书A" in result
        mock_store.set_reference_books.assert_called_once_with("book_123", ["book_456"])

    @patch("tools.impl.handlers.json_store")
    def test_set_reference_books_invalid_id(self, mock_store):
        """Should reject invalid book IDs with helpful message."""
        mock_store.load_books.return_value = [
            {"id": "book_123", "title": "当前书"},
            {"id": "book_456", "title": "参考书A"},
        ]
        from tools.impl.handlers import _handle_materials

        result = _handle_materials("set_reference_books", {"book_ids": ["invalid_id"]}, "book_123")
        assert "不存在" in result
        assert "invalid_id" in result
        assert "list_books" in result  # Should suggest list_books
        mock_store.set_reference_books.assert_not_called()

    @patch("tools.impl.handlers.json_store")
    def test_set_reference_books_mixed_ids(self, mock_store):
        """Should reject all if any ID is invalid."""
        mock_store.load_books.return_value = [
            {"id": "book_123", "title": "当前书"},
            {"id": "book_456", "title": "参考书A"},
        ]
        from tools.impl.handlers import _handle_materials

        result = _handle_materials("set_reference_books", {"book_ids": ["book_456", "invalid_id"]}, "book_123")
        assert "不存在" in result
        assert "invalid_id" in result
        mock_store.set_reference_books.assert_not_called()

    @patch("tools.impl.handlers.json_store")
    def test_set_reference_books_clear_all(self, mock_store):
        """Should clear all reference books when empty array passed."""
        from tools.impl.handlers import _handle_materials

        result = _handle_materials("set_reference_books", {"book_ids": []}, "book_123")
        assert "清除" in result
        mock_store.set_reference_books.assert_called_once_with("book_123", [])
