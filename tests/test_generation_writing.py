"""Tests for generation.py and writing.py pure functions."""

from tools._common import _parse_chapter_range
from tools.impl.generation import _coerce_to_dict


class TestCoerceToDict:
    """Test type coercion helper for generation module."""

    def test_none_returns_empty_dict(self):
        assert _coerce_to_dict(None) == {}

    def test_dict_passthrough(self):
        d = {"key": "value"}
        assert _coerce_to_dict(d) == d

    def test_valid_json_string(self):
        result = _coerce_to_dict('{"name": "test"}')
        assert result == {"name": "test"}

    def test_invalid_json_string(self):
        result = _coerce_to_dict("not valid json")
        assert result == {}

    def test_empty_string(self):
        assert _coerce_to_dict("") == {}
        assert _coerce_to_dict("   ") == {}

    def test_json_array_returns_empty(self):
        """JSON array should return empty dict (not a dict)."""
        result = _coerce_to_dict("[1, 2, 3]")
        assert result == {}

    def test_non_dict_non_str_non_none(self):
        """Non-dict/non-str values return empty dict."""
        assert _coerce_to_dict(123) == {}
        assert _coerce_to_dict(True) == {}
        assert _coerce_to_dict([]) == {}
        assert _coerce_to_dict(3.14) == {}

    def test_dict_with_nested_json_string(self):
        d = {"data": '{"inner": 1}'}
        # Only top-level coercion, nested strings stay as-is
        result = _coerce_to_dict(d)
        assert result == d
        assert isinstance(result["data"], str)


class TestParseChapterRangeGeneration:
    """Test chapter range parsing in generation module (0-based output)."""

    def test_single_number(self):
        assert _parse_chapter_range("3", 10) == [2]

    def test_range(self):
        assert _parse_chapter_range("2-5", 10) == [1, 2, 3, 4]

    def test_comma_separated(self):
        assert _parse_chapter_range("1,3,5", 10) == [0, 2, 4]

    def test_all_keyword(self):
        assert _parse_chapter_range("all", 5) == [0, 1, 2, 3, 4]

    def test_chinese_all(self):
        assert _parse_chapter_range("全部", 5) == [0, 1, 2, 3, 4]

    def test_out_of_range_filtered(self):
        result = _parse_chapter_range("1,15", 10)
        assert 14 not in result
        assert 0 in result

    def test_invalid_returns_empty(self):
        assert _parse_chapter_range("invalid", 10) == []

    def test_empty_returns_empty(self):
        assert _parse_chapter_range("", 10) == []

    def test_hash_stripped(self):
        result = _parse_chapter_range("#3", 10)
        assert result == [2]

    def test_fullwidth_parens(self):
        """Chinese parentheses are replaced but not stripped."""
        # "（3）" becomes "(3)" which is NOT a valid int
        result = _parse_chapter_range("\uff083\uff09", 10)
        assert result == []  # Unparseable after replacement

    def test_mixed_with_range_not_supported(self):
        """Mixed comma + range uses simple comma-first parsing."""
        result = _parse_chapter_range("1,3-5,8", 10)
        # "3-5" fails int conversion in comma-split mode
        assert isinstance(result, list)


class TestEndToEndCoverage:
    """Additional integration-style tests for coverage breadth."""

    def test_coerce_nested_json_fails_return_empty(self):
        """Malformed nested JSON still handled gracefully."""
        result = _coerce_to_dict('{"a": {"b":')
        assert result == {}

    def test_range_at_boundary(self):
        """Range exactly at the total boundary."""
        result = _parse_chapter_range("1-5", 5)
        assert result == [0, 1, 2, 3, 4]

    def test_range_exceeds_total(self):
        """Range exceeding total is clamped."""
        result = _parse_chapter_range("3-10", 5)
        assert all(0 <= i < 5 for i in result)
        assert len(result) > 0

    def test_zero_number(self):
        """Chapter 0 is out of range (1-based input)."""
        result = _parse_chapter_range("0", 10)
        assert result == []
