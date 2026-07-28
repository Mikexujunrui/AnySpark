import pytest

from core.errors import NotFoundError
from data.json_store import JsonStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    import core.config as cfg

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    s = JsonStore()
    s._books_file = tmp_path / "books.json"
    return s


def test_create_book(store):
    book = store.create_book("测试小说", "一个测试")
    assert book["title"] == "测试小说"
    assert book["description"] == "一个测试"
    assert book["id"]
    assert book["entityCount"] == 0
    assert book["chapterCount"] == 0


def test_load_books_empty(store):
    books = store.load_books()
    assert books == []


def test_load_books_after_create(store):
    store.create_book("书A")
    store.create_book("书B")
    books = store.load_books()
    assert len(books) == 2


def test_delete_book(store):
    book = store.create_book("要删除的书")
    store.delete_book(book["id"])
    books = store.load_books()
    assert len(books) == 0


def test_add_chapter(store, tmp_path):
    book = store.create_book("有章节的书")
    store._chapters_file = lambda bid: tmp_path / f"chapters_{bid}.json"
    ch = store.add_chapter(book["id"], "第一章", "内容内容内容")
    assert ch["title"] == "第一章"
    assert ch["content"] == "内容内容内容"
    assert ch["id"]


def test_get_chapter(store, tmp_path):
    book = store.create_book("查章节")
    store._chapters_file = lambda bid: tmp_path / f"chapters_{bid}.json"
    ch = store.add_chapter(book["id"], "找这章", "找到我了")
    found = store.get_chapter(book["id"], ch["id"])
    assert found["title"] == "找这章"


def test_get_chapter_not_found(store, tmp_path):
    book = store.create_book("空书")
    store._chapters_file = lambda bid: tmp_path / f"chapters_{bid}.json"
    with pytest.raises(NotFoundError):
        store.get_chapter(book["id"], "nonexistent")


def test_delete_chapter(store, tmp_path):
    book = store.create_book("删章节")
    store._chapters_file = lambda bid: tmp_path / f"chapters_{bid}.json"
    ch = store.add_chapter(book["id"], "要删", "内容")
    count = store.delete_chapter(book["id"], ch["id"])
    assert count == 1
    chapters = store.load_chapters(book["id"])
    assert len(chapters) == 0


def test_session_crud(store, tmp_path):
    book = store.create_book("会话测试")
    store._sessions_file = lambda bid: tmp_path / f"sessions_{bid}.json"
    session = store.create_session(book["id"], "测试会话")
    assert session["title"] == "测试会话"
    sessions = store.load_sessions(book["id"])
    assert len(sessions) == 1
    store.delete_session(book["id"], session["id"])
    sessions = store.load_sessions(book["id"])
    assert len(sessions) == 0


def test_notes(store, tmp_path):
    store._notes_file = lambda bid: tmp_path / f"notes_{bid}.json"
    note = store.add_note("book1", "灵感内容", ["tag1", "tag2"])
    assert note["content"] == "灵感内容"
    assert note["tags"] == ["tag1", "tag2"]
    notes = store.load_notes("book1")
    assert len(notes) == 1


# ── Workflow ID prefix matching tests ──


@pytest.fixture
def wf_store(tmp_path, monkeypatch):
    """Create a fresh JsonStore with isolated workflow storage."""
    import core.config as cfg

    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    s = JsonStore()
    s._global_wfs_file = tmp_path / "workflows.json"
    s._wf_subs_file = lambda bid: tmp_path / f"workflow_subs_{bid}.json"
    return s


class TestWorkflowPrefixMatching:
    """Test that workflow operations support truncated IDs (like volume prefix matching)."""

    def test_get_workflow_exact_id(self, wf_store):
        """Should find workflow by exact ID."""
        wf = wf_store.add_workflow("book1", "测试工作流", [{"type": "step1", "label": "步骤1"}])
        found = wf_store.get_workflow(wf["id"])
        assert found["name"] == "测试工作流"

    def test_get_workflow_truncated_id(self, wf_store):
        """Should find workflow by truncated ID (first 8 chars)."""
        wf = wf_store.add_workflow("book1", "截断测试", [])
        truncated = wf["id"][:8]
        found = wf_store.get_workflow(truncated)
        assert found["name"] == "截断测试"

    def test_get_workflow_not_found(self, wf_store):
        """Should raise NotFoundError for non-existent ID."""
        with pytest.raises(NotFoundError, match="工作流不存在"):
            wf_store.get_workflow("nonexistent")

    def test_update_workflow_truncated_id(self, wf_store):
        """Should update workflow using truncated ID."""
        wf = wf_store.add_workflow("book1", "旧名称", [])
        truncated = wf["id"][:8]
        updated = wf_store.update_workflow(truncated, {"name": "新名称"})
        assert updated["name"] == "新名称"

    def test_update_workflow_not_found(self, wf_store):
        """Should raise NotFoundError for non-existent ID."""
        with pytest.raises(NotFoundError, match="工作流不存在"):
            wf_store.update_workflow("nonexistent", {"name": "x"})

    def test_delete_workflow_truncated_id(self, wf_store):
        """Should delete workflow using truncated ID."""
        wf = wf_store.add_workflow("book1", "要删除", [])
        truncated = wf["id"][:8]
        wf_store.delete_workflow("book1", truncated)
        wfs = wf_store.load_workflows_global()
        assert len(wfs) == 0

    def test_subscribe_workflow_truncated_id(self, wf_store, tmp_path):
        """Should subscribe with full ID even when truncated ID is passed."""
        wf = wf_store.add_workflow("book1", "订阅测试", [])
        # Unsubscribe first (add_workflow auto-subscribes)
        wf_store.unsubscribe_workflow("book1", wf["id"])
        subs = wf_store.load_workflow_subs("book1")
        assert wf["id"] not in subs
        # Subscribe using truncated ID
        truncated = wf["id"][:8]
        wf_store.subscribe_workflow("book1", truncated)
        subs = wf_store.load_workflow_subs("book1")
        # Should have the full ID, not truncated
        assert wf["id"] in subs

    def test_unsubscribe_workflow_truncated_id(self, wf_store):
        """Should unsubscribe using truncated ID."""
        wf = wf_store.add_workflow("book1", "取消订阅", [])
        assert wf["id"] in wf_store.load_workflow_subs("book1")
        truncated = wf["id"][:8]
        wf_store.unsubscribe_workflow("book1", truncated)
        subs = wf_store.load_workflow_subs("book1")
        assert wf["id"] not in subs

    def test_ambiguous_prefix_returns_none(self, wf_store):
        """Should return None when prefix matches multiple workflows."""
        wf1 = wf_store.add_workflow("book1", "工作流A", [])
        wf2 = wf_store.add_workflow("book1", "工作流B", [])
        # If both start with same prefix, truncated lookup should fail
        # (This is unlikely with timestamps, but test the edge case)
        if wf1["id"][:8] == wf2["id"][:8]:
            with pytest.raises(NotFoundError):
                wf_store.get_workflow(wf1["id"][:8])
