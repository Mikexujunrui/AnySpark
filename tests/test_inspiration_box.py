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
