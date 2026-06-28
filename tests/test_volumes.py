"""Tests for volume operations: CRUD, dedup, ID prefix matching, field conversion."""
import pytest

from core.errors import NotFoundError
from data.json_store import JsonStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    import core.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    s = JsonStore()
    s._books_file = tmp_path / "books.json"
    s._volumes_file = lambda bid: tmp_path / f"volumes_{bid}.json"
    s._chapters_file = lambda bid: tmp_path / f"chapters_{bid}.json"
    return s


@pytest.fixture
def book(store):
    return store.create_book("测试小说", "用于分卷测试")


# ── Basic CRUD ──


def test_add_volume(store, book):
    vol = store.add_volume(book["id"], "第一卷", "故事主线")
    assert vol["title"] == "第一卷"
    assert vol["storyLine"] == "故事主线"
    assert vol["chapters"] == []
    assert vol["order"] == 0


def test_add_multiple_volumes_order(store, book):
    v1 = store.add_volume(book["id"], "第一卷", "")
    v2 = store.add_volume(book["id"], "第二卷", "")
    v3 = store.add_volume(book["id"], "第三卷", "")
    assert v1["order"] == 0
    assert v2["order"] == 1
    assert v3["order"] == 2


def test_update_volume_title(store, book):
    vol = store.add_volume(book["id"], "旧标题", "")
    updated = store.update_volume(book["id"], vol["id"], {"title": "新标题"})
    assert updated["title"] == "新标题"


def test_update_volume_story_line(store, book):
    """Test snake_case → camelCase: storyLine field."""
    vol = store.add_volume(book["id"], "第一卷", "")
    updated = store.update_volume(book["id"], vol["id"], {"storyLine": "新主线"})
    assert updated["storyLine"] == "新主线"


def test_update_volume_not_found(store, book):
    with pytest.raises(NotFoundError):
        store.update_volume(book["id"], "nonexistent", {"title": "x"})


def test_delete_volume(store, book):
    vol = store.add_volume(book["id"], "要删的卷", "")
    store.delete_volume(book["id"], vol["id"])
    volumes = store.load_volumes(book["id"])
    assert len(volumes) == 0


def test_delete_volume_not_found_silent(store, book):
    """delete_volume should not raise if volume not found."""
    store.delete_volume(book["id"], "nonexistent")  # Should not raise


# ── Dedup: same-title volumes ──


def test_add_volume_dedup_same_title(store, book):
    """Creating volume with same title should return existing, not duplicate."""
    v1 = store.add_volume(book["id"], "第一卷", "主线A")
    v2 = store.add_volume(book["id"], "第一卷", "主线B")
    assert v1["id"] == v2["id"]  # Same ID returned
    volumes = store.load_volumes(book["id"])
    assert len(volumes) == 1  # Only one volume exists


def test_add_volume_different_titles_no_dedup(store, book):
    """Different titles should create separate volumes."""
    store.add_volume(book["id"], "第一卷", "")
    store.add_volume(book["id"], "第二卷", "")
    volumes = store.load_volumes(book["id"])
    assert len(volumes) == 2


# ── ID prefix matching (truncated IDs from list_volumes) ──


def test_resolve_volume_exact_match(store, book):
    vol = store.add_volume(book["id"], "第一卷", "")
    volumes = store.load_volumes(book["id"])
    resolved = store._resolve_volume(volumes, vol["id"])
    assert resolved is not None
    assert resolved["id"] == vol["id"]


def test_resolve_volume_prefix_match(store, book):
    """Truncated ID (first 8 chars) should resolve to full volume."""
    vol = store.add_volume(book["id"], "第一卷", "")
    volumes = store.load_volumes(book["id"])
    prefix = vol["id"][:8]
    resolved = store._resolve_volume(volumes, prefix)
    assert resolved is not None
    assert resolved["id"] == vol["id"]


def test_resolve_volume_ambiguous_prefix(store, book):
    """If prefix matches multiple volumes, should return None."""
    # Create volumes that share a common prefix by manipulating IDs
    volumes = [
        {"id": "1781691449747", "title": "第一卷", "chapters": [], "order": 0},
        {"id": "1781691449748", "title": "第二卷", "chapters": [], "order": 1},
    ]
    store.save_volumes(book["id"], volumes)
    loaded = store.load_volumes(book["id"])
    # Prefix "17816914" matches both
    resolved = store._resolve_volume(loaded, "17816914")
    assert resolved is None


def test_resolve_volume_no_match(store, book):
    store.add_volume(book["id"], "第一卷", "")
    volumes = store.load_volumes(book["id"])
    resolved = store._resolve_volume(volumes, "99999999")
    assert resolved is None


def test_update_volume_with_prefix_id(store, book):
    """update_volume should work with truncated ID via prefix match."""
    vol = store.add_volume(book["id"], "第一卷", "")
    prefix = vol["id"][:8]
    updated = store.update_volume(book["id"], prefix, {"title": "改名了"})
    assert updated["title"] == "改名了"


def test_delete_volume_with_prefix_id(store, book):
    """delete_volume should work with truncated ID via prefix match."""
    vol = store.add_volume(book["id"], "第一卷", "")
    prefix = vol["id"][:8]
    store.delete_volume(book["id"], prefix)
    volumes = store.load_volumes(book["id"])
    assert len(volumes) == 0


def test_move_chapter_to_volume_with_prefix_id(store, book):
    """move_chapter_to_volume should work with truncated volume ID."""
    vol = store.add_volume(book["id"], "第一卷", "")
    ch = store.add_chapter(book["id"], "测试章节", "内容" * 100)
    prefix = vol["id"][:8]
    store.add_chapter_to_volume(book["id"], prefix, ch["id"])
    volumes = store.load_volumes(book["id"])
    assert ch["id"] in volumes[0]["chapters"]


# ── Chapter-volume association ──


def test_add_chapter_to_volume(store, book):
    vol = store.add_volume(book["id"], "第一卷", "")
    ch = store.add_chapter(book["id"], "测试章节", "内容" * 100)
    store.add_chapter_to_volume(book["id"], vol["id"], ch["id"])
    volumes = store.load_volumes(book["id"])
    assert ch["id"] in volumes[0]["chapters"]


def test_chapter_only_in_one_volume(store, book):
    """Adding chapter to vol2 should remove it from vol1."""
    v1 = store.add_volume(book["id"], "第一卷", "")
    v2 = store.add_volume(book["id"], "第二卷", "")
    ch = store.add_chapter(book["id"], "测试章节", "内容" * 100)
    store.add_chapter_to_volume(book["id"], v1["id"], ch["id"])
    store.add_chapter_to_volume(book["id"], v2["id"], ch["id"])
    volumes = store.load_volumes(book["id"])
    vol1 = next(v for v in volumes if v["id"] == v1["id"])
    vol2 = next(v for v in volumes if v["id"] == v2["id"])
    assert ch["id"] not in vol1["chapters"]
    assert ch["id"] in vol2["chapters"]


def test_remove_chapter_from_volume(store, book):
    vol = store.add_volume(book["id"], "第一卷", "")
    ch = store.add_chapter(book["id"], "测试章节", "内容" * 100)
    store.add_chapter_to_volume(book["id"], vol["id"], ch["id"])
    store.remove_chapter_from_volume(book["id"], ch["id"])
    volumes = store.load_volumes(book["id"])
    assert ch["id"] not in volumes[0]["chapters"]


def test_move_chapter_to_nonexistent_volume(store, book):
    ch = store.add_chapter(book["id"], "测试章节", "内容" * 100)
    with pytest.raises(NotFoundError):
        store.add_chapter_to_volume(book["id"], "nonexistent", ch["id"])
