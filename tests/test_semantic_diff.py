# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Tests for semantic diff — data model and response parsing."""

from core.semantic_diff import (
    SemanticChange,
    SemanticDiff,
    _parse_diff_response,
    _truncate_content,
)


class TestSemanticDiffParsing:
    """Test LLM response parsing into SemanticDiff."""

    def test_parse_valid_response(self):
        """A valid JSON response should parse correctly."""
        response = """{
            "changes": [
                {
                    "category": "character_emotion",
                    "description": "角色张三的情绪从愤怒变为悲伤",
                    "old_text": "张三怒不可遏",
                    "new_text": "张三默默低头",
                    "severity": "moderate"
                }
            ],
            "summary": "主要调整了角色情绪",
            "impact_level": "moderate"
        }"""
        diff = _parse_diff_response(response)
        assert isinstance(diff, SemanticDiff)
        assert len(diff.changes) == 1
        assert diff.changes[0].category == "character_emotion"
        assert diff.changes[0].severity == "moderate"
        assert diff.summary == "主要调整了角色情绪"
        assert diff.impact_level == "moderate"

    def test_parse_empty_changes(self):
        """Response with empty changes list should parse."""
        response = '{"changes": [], "summary": "无变更", "impact_level": "cosmetic"}'
        diff = _parse_diff_response(response)
        assert len(diff.changes) == 0
        assert diff.summary == "无变更"

    def test_parse_invalid_json(self):
        """Invalid JSON should return a diff with error summary."""
        diff = _parse_diff_response("not json at all")
        assert isinstance(diff, SemanticDiff)
        assert "解析" in diff.summary or "失败" in diff.summary

    def test_parse_missing_fields(self):
        """Missing fields should use defaults."""
        response = '{"changes": [{"category": "test"}]}'
        diff = _parse_diff_response(response)
        assert len(diff.changes) == 1
        assert diff.changes[0].category == "test"
        assert diff.changes[0].severity == "minor"  # default
        assert diff.impact_level == "cosmetic"  # default


class TestTruncateContent:
    """Test content truncation."""

    def test_short_content_unchanged(self):
        content = "短文本"
        assert _truncate_content(content, 8000) == content

    def test_long_content_truncated(self):
        content = "a" * 10000
        truncated = _truncate_content(content, 1000)
        assert len(truncated) < len(content)
        assert "中间部分省略" in truncated

    def test_preserves_beginning_and_end(self):
        content = "开头内容" + "中" * 1000 + "结尾内容"
        truncated = _truncate_content(content, 100)
        assert "开头内容" in truncated
        assert "结尾内容" in truncated


class TestDataclasses:
    """Test dataclass serialization."""

    def test_semantic_change_to_dict(self):
        change = SemanticChange(
            category="scene_location",
            description="场景从酒馆变为街道",
            old_text="酒馆",
            new_text="街道",
            severity="minor",
        )
        d = change.to_dict()
        assert d["category"] == "scene_location"
        assert d["severity"] == "minor"

    def test_semantic_diff_to_dict(self):
        diff = SemanticDiff(
            changes=[
                SemanticChange(category="test", description="test"),
            ],
            summary="测试摘要",
            impact_level="moderate",
        )
        d = diff.to_dict()
        assert d["change_count"] == 1
        assert d["summary"] == "测试摘要"
        assert d["impact_level"] == "moderate"
