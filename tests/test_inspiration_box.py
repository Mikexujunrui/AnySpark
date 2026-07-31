# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Tests for inspiration box — card management with temp directory."""

from core.inspiration_box import (
    add_inspiration,
    archive_inspiration,
    delete_inspiration,
    get_inspiration,
    link_inspiration,
    list_inspirations,
    promote_inspiration,
    update_inspiration,
)


class TestInspirationCRUD:
    """Test CRUD operations on inspiration cards."""

    def test_add_and_get(self, tmp_path, monkeypatch):
        from core import inspiration_box

        monkeypatch.setattr(inspiration_box, "_INSPIRATIONS_DIR", tmp_path)

        insp = add_inspiration("book1", "一个关于命运的想法", tags=["命运", "主线"])
        assert insp["content"] == "一个关于命运的想法"
        assert insp["status"] == "inbox"
        assert "命运" in insp["tags"]

        fetched = get_inspiration("book1", insp["id"])
        assert fetched is not None
        assert fetched["content"] == "一个关于命运的想法"

    def test_list_all(self, tmp_path, monkeypatch):
        from core import inspiration_box

        monkeypatch.setattr(inspiration_box, "_INSPIRATIONS_DIR", tmp_path)

        add_inspiration("book1", "想法一")
        add_inspiration("book1", "想法二")
        add_inspiration("book1", "想法三")

        all_insp = list_inspirations("book1")
        assert len(all_insp) == 3

    def test_list_by_status(self, tmp_path, monkeypatch):
        from core import inspiration_box

        monkeypatch.setattr(inspiration_box, "_INSPIRATIONS_DIR", tmp_path)

        add_inspiration("book1", "想法一")
        insp2 = add_inspiration("book1", "想法二")
        promote_inspiration("book1", insp2["id"], "outline_node")

        inbox_only = list_inspirations("book1", status_filter="inbox")
        assert len(inbox_only) == 1
        assert inbox_only[0]["content"] == "想法一"

    def test_update(self, tmp_path, monkeypatch):
        from core import inspiration_box

        monkeypatch.setattr(inspiration_box, "_INSPIRATIONS_DIR", tmp_path)

        insp = add_inspiration("book1", "原始内容")
        updated = update_inspiration("book1", insp["id"], {"content": "修改后内容"})
        assert updated["content"] == "修改后内容"

    def test_delete(self, tmp_path, monkeypatch):
        from core import inspiration_box

        monkeypatch.setattr(inspiration_box, "_INSPIRATIONS_DIR", tmp_path)

        insp = add_inspiration("book1", "要删除的想法")
        assert delete_inspiration("book1", insp["id"]) is True
        assert get_inspiration("book1", insp["id"]) is None

    def test_delete_nonexistent(self, tmp_path, monkeypatch):
        from core import inspiration_box

        monkeypatch.setattr(inspiration_box, "_INSPIRATIONS_DIR", tmp_path)
        assert delete_inspiration("book1", "nonexistent_id") is False


class TestInspirationLinking:
    """Test linking inspirations to entities."""

    def test_link_character(self, tmp_path, monkeypatch):
        from core import inspiration_box

        monkeypatch.setattr(inspiration_box, "_INSPIRATIONS_DIR", tmp_path)

        insp = add_inspiration("book1", "张三的背景故事")
        result = link_inspiration("book1", insp["id"], "character", "char_zhangsan")
        assert "char_zhangsan" in result["linked_characters"]

    def test_link_chapter(self, tmp_path, monkeypatch):
        from core import inspiration_box

        monkeypatch.setattr(inspiration_box, "_INSPIRATIONS_DIR", tmp_path)

        insp = add_inspiration("book1", "第三章的伏笔")
        result = link_inspiration("book1", insp["id"], "chapter", "ch3")
        assert "ch3" in result["linked_chapters"]

    def test_invalid_target_type(self, tmp_path, monkeypatch):
        from core import inspiration_box

        monkeypatch.setattr(inspiration_box, "_INSPIRATIONS_DIR", tmp_path)

        insp = add_inspiration("book1", "测试")
        result = link_inspiration("book1", insp["id"], "invalid_type", "target1")
        assert result is None


class TestInspirationPromotion:
    """Test promotion and archiving."""

    def test_promote(self, tmp_path, monkeypatch):
        from core import inspiration_box

        monkeypatch.setattr(inspiration_box, "_INSPIRATIONS_DIR", tmp_path)

        insp = add_inspiration("book1", "可提升的想法")
        result = promote_inspiration("book1", insp["id"], "foreshadow")
        assert result["status"] == "promoted"
        assert result["promoted_to"] == "foreshadow"
        assert result["promoted_at"] != ""

    def test_archive(self, tmp_path, monkeypatch):
        from core import inspiration_box

        monkeypatch.setattr(inspiration_box, "_INSPIRATIONS_DIR", tmp_path)

        insp = add_inspiration("book1", "要归档的想法")
        result = archive_inspiration("book1", insp["id"])
        assert result["status"] == "archived"

    def test_promote_nonexistent(self, tmp_path, monkeypatch):
        from core import inspiration_box

        monkeypatch.setattr(inspiration_box, "_INSPIRATIONS_DIR", tmp_path)
        result = promote_inspiration("book1", "nonexistent", "outline_node")
        assert "error" in result


class TestInspirationTool:
    """Test the Agent-facing manage_inspirations tool implementation."""

    def _run_tool(self, args: dict, tmp_path, monkeypatch) -> str:
        from core import inspiration_box
        from tools.impl.inspirations import _manage_inspirations

        monkeypatch.setattr(inspiration_box, "_INSPIRATIONS_DIR", tmp_path)
        return _manage_inspirations(args, "book1", "")

    def test_add_and_list(self, tmp_path, monkeypatch):
        out = self._run_tool({"action": "add", "content": "灵感A", "tags": ["主线"]}, tmp_path, monkeypatch)
        assert "灵感已添加" in out

        out = self._run_tool({"action": "list"}, tmp_path, monkeypatch)
        assert "灵感A" in out
        assert "[inbox]" in out

    def test_get_and_update(self, tmp_path, monkeypatch):
        out = self._run_tool({"action": "add", "content": "灵感B"}, tmp_path, monkeypatch)
        insp_id = out.split("(id: ")[1].split(")")[0]

        out = self._run_tool({"action": "get", "inspiration_id": insp_id}, tmp_path, monkeypatch)
        assert "灵感B" in out

        out = self._run_tool({"action": "update", "inspiration_id": insp_id, "status": "archived"}, tmp_path, monkeypatch)
        assert "已更新" in out

        out = self._run_tool({"action": "list", "status": "archived"}, tmp_path, monkeypatch)
        assert "灵感B" in out

    def test_search_delete_unknown_action(self, tmp_path, monkeypatch):
        self._run_tool({"action": "add", "content": "命运轮回"}, tmp_path, monkeypatch)
        out = self._run_tool({"action": "search", "query": "命运"}, tmp_path, monkeypatch)
        assert "命运轮回" in out

        out = self._run_tool({"action": "list"}, tmp_path, monkeypatch)
        insp_id = out.split("[")[1].split("]")[0]
        out = self._run_tool({"action": "delete", "inspiration_id": insp_id}, tmp_path, monkeypatch)
        assert "已删除" in out

        out = self._run_tool({"action": "bogus"}, tmp_path, monkeypatch)
        assert "未知操作" in out

    def test_missing_required_params(self, tmp_path, monkeypatch):
        out = self._run_tool({"action": "add"}, tmp_path, monkeypatch)
        assert "content" in out
        out = self._run_tool({"action": "delete"}, tmp_path, monkeypatch)
        assert "inspiration_id" in out
