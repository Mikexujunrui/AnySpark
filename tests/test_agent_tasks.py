"""Tests for agent task list storage in json_store."""
import pytest

from data.json_store import JsonStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Create a JsonStore with temp data directory."""
    import core.config as cfg
    import data.stores._base as base_mod
    monkeypatch.setattr(base_mod, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(cfg, 'DATA_DIR', tmp_path)
    return JsonStore()


class TestAgentTaskListStorage:
    """Tests for task list CRUD operations."""

    def test_load_task_lists_empty(self, store):
        """Should return empty list when no task lists exist."""
        result = store.load_task_lists("book_123")
        assert result == []

    def test_create_task_list(self, store):
        """Should create a task list with items."""
        items = [
            {"label": "读取章节", "tool": "read_chapter"},
            {"label": "拆解剧情链", "tool": "decompose_chapter"},
            {"label": "按链复写", "tool": "rewrite_by_chain"},
        ]
        tl = store.create_task_list("book_123", "复写流程", items)
        assert "id" in tl
        assert tl["id"].startswith("tasks_")
        assert tl["title"] == "复写流程"
        assert tl["status"] == "pending"
        assert len(tl["items"]) == 3
        assert tl["items"][0]["label"] == "读取章节"
        assert tl["items"][0]["status"] == "pending"
        assert tl["items"][0]["tool"] == "read_chapter"

    def test_get_task_list_by_id(self, store):
        """Should retrieve task list by ID."""
        tl = store.create_task_list("book_123", "测试", [{"label": "任务1"}])
        retrieved = store.get_task_list("book_123", tl["id"])
        assert retrieved["title"] == "测试"

    def test_get_task_list_by_prefix(self, store):
        """Should retrieve task list by ID prefix."""
        tl = store.create_task_list("book_123", "测试", [{"label": "任务1"}])
        prefix = tl["id"][:8]
        retrieved = store.get_task_list("book_123", prefix)
        assert retrieved["title"] == "测试"

    def test_get_task_list_latest(self, store):
        """Should return latest task list when no ID provided."""
        store.create_task_list("book_123", "第一个", [{"label": "A"}])
        tl2 = store.create_task_list("book_123", "第二个", [{"label": "B"}])

        retrieved = store.get_task_list("book_123")
        assert retrieved["title"] == "第二个"
        assert retrieved["id"] == tl2["id"]

    def test_get_task_list_not_found(self, store):
        """Should raise NotFoundError when task list doesn't exist."""
        from core.errors import NotFoundError
        with pytest.raises(NotFoundError):
            store.get_task_list("book_123", "nonexistent")

    def test_get_task_list_empty(self, store):
        """Should raise NotFoundError when no task lists exist."""
        from core.errors import NotFoundError
        with pytest.raises(NotFoundError):
            store.get_task_list("book_123")

    def test_update_task_item(self, store):
        """Should update a task item's status."""
        store.create_task_list("book_123", "测试", [
            {"label": "任务1"},
            {"label": "任务2"},
        ])

        updated = store.update_task_item("book_123", None, 0, "done", "已完成")
        assert updated["items"][0]["status"] == "done"
        assert updated["items"][0]["result_summary"] == "已完成"
        assert updated["items"][0]["updated_at"] is not None
        assert updated["items"][1]["status"] == "pending"  # Unchanged

    def test_update_task_item_auto_status_done(self, store):
        """Should auto-set list status to done when all items done."""
        store.create_task_list("book_123", "测试", [
            {"label": "任务1"},
            {"label": "任务2"},
        ])

        store.update_task_item("book_123", None, 0, "done")
        updated = store.update_task_item("book_123", None, 1, "done")
        assert updated["status"] == "done"

    def test_update_task_item_auto_status_in_progress(self, store):
        """Should auto-set list status to in_progress when any item in progress."""
        store.create_task_list("book_123", "测试", [
            {"label": "任务1"},
            {"label": "任务2"},
        ])

        updated = store.update_task_item("book_123", None, 0, "in_progress")
        assert updated["status"] == "in_progress"

    def test_update_task_item_auto_status_failed(self, store):
        """Should auto-set list status to failed when any item failed."""
        store.create_task_list("book_123", "测试", [
            {"label": "任务1"},
            {"label": "任务2"},
        ])

        updated = store.update_task_item("book_123", None, 0, "failed")
        assert updated["status"] == "failed"

    def test_update_task_item_auto_status_done_with_skipped(self, store):
        """Should consider skipped items as complete for list status."""
        store.create_task_list("book_123", "测试", [
            {"label": "任务1"},
            {"label": "任务2"},
        ])

        store.update_task_item("book_123", None, 0, "done")
        updated = store.update_task_item("book_123", None, 1, "skipped")
        assert updated["status"] == "done"

    def test_update_task_item_not_found(self, store):
        """Should raise NotFoundError for invalid item index."""
        from core.errors import NotFoundError
        store.create_task_list("book_123", "测试", [{"label": "任务1"}])

        with pytest.raises(NotFoundError):
            store.update_task_item("book_123", None, 99, "done")

    def test_add_task_items(self, store):
        """Should append items to existing task list."""
        store.create_task_list("book_123", "测试", [{"label": "原有任务"}])

        new_items = [{"label": "新任务1"}, {"label": "新任务2"}]
        updated = store.add_task_items("book_123", None, new_items)

        assert len(updated["items"]) == 3
        assert updated["items"][0]["label"] == "原有任务"
        assert updated["items"][1]["label"] == "新任务1"
        assert updated["items"][1]["index"] == 1  # Continues from previous
        assert updated["items"][2]["index"] == 2

    def test_task_lists_isolated_by_book(self, store):
        """Task lists should be isolated per book_id."""
        store.create_task_list("book_a", "A的任务", [{"label": "A任务"}])
        store.create_task_list("book_b", "B的任务", [{"label": "B任务"}])

        lists_a = store.load_task_lists("book_a")
        lists_b = store.load_task_lists("book_b")

        assert len(lists_a) == 1
        assert len(lists_b) == 1
        assert lists_a[0]["title"] == "A的任务"
        assert lists_b[0]["title"] == "B的任务"
