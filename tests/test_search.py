"""Tests for FullTextSearch (sqlite FTS5)."""

import os
import tempfile

import pytest

from core.search import FullTextSearch


@pytest.fixture
def search():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    name = tmp.name
    tmp.close()
    s = FullTextSearch(name)
    yield s
    try:
        if hasattr(s, "_local") and hasattr(s._local, "conn") and s._local.conn:
            s._local.conn.close()
    except Exception:
        pass
    try:
        os.unlink(name)
    except Exception:
        pass


def test_index_and_search_chapter(search):
    search.index_chapter("testbook", {"id": "ch1", "title": "第一章 穿越", "content": "主角穿越到异世界大陆"})
    results = search.search("testbook", "穿越")
    assert len(results["chapters"]) > 0


def test_search_entities(search):
    search.index_entity("testbook", "e1", "unique_entity_name", "character", ["nickname"], {"attr": "value"})
    results = search.search("testbook", "unique_entity_name")
    assert len(results["entities"]) > 0
    assert results["entities"][0]["name"] == "unique_entity_name"


def test_search_worldbuilding(search):
    data = {
        "categories": [
            {
                "name": "test",
                "entries": [{"title": "uniquewbtitle", "content": "testing worldbuilding content here morewords"}],
            }
        ]
    }
    search.index_worldbuilding("testbook", data)
    results = search.search("testbook", "uniquewbtitle")
    assert len(results["worldbuilding"]) > 0


def test_empty_search(search):
    results = search.search("testbook", "")
    assert results == {"chapters": [], "entities": [], "worldbuilding": []}


def test_remove_chapter(search):
    search.index_chapter("testbook", {"id": "ch_rm", "title": "删除测试", "content": "toBeDeletedContent123"})
    search.remove_chapter("ch_rm")
    results = search.search("testbook", "toBeDeleted")
    assert len(results["chapters"]) == 0


def test_clear_book(search):
    search.index_chapter("testbook", {"id": "ch_cl", "title": "清理测试", "content": "clearTestContent321"})
    search.index_entity("testbook", "e_cl", "name_cl", "character", [], {})
    search.clear_book("testbook")
    results = search.search("testbook", "name_cl")
    assert len(results["entities"]) == 0
    assert len(results["chapters"]) == 0


def test_index_and_search_material(search):
    search.index_material({"id": "m1", "title": "素材一", "tags": ["tag1", "tag2"], "content": "unique material body text"})
    results = search.search_materials("unique material", limit=5)
    assert any(r["id"] == "m1" for r in results)


def test_remove_material(search):
    search.index_material({"id": "m_rm", "title": "待删素材", "tags": [], "content": "materialToBeRemovedXYZ"})
    search.remove_material("m_rm")
    results = search.search_materials("materialToBeRemoved", limit=5)
    assert all(r["id"] != "m_rm" for r in results)


def test_index_chapters_batch(search):
    chapters = [
        {"id": f"chb{i}", "title": f"批量章{i}", "content": f"batch content {i} unique seed"}
        for i in range(3)
    ]
    search.index_chapters_batch("batchbook", chapters)
    for i in range(3):
        results = search.search("batchbook", f"{i} unique")
        assert any(r["id"] == f"chb{i}" for r in results["chapters"])


def test_rebuild_is_idempotent(search):
    """Indexing the same content twice must not duplicate results (INSERT OR REPLACE)."""
    search.index_chapter("book", {"id": "dup1", "title": "去重", "content": "dedup unique content abc"})
    search.index_chapter("book", {"id": "dup1", "title": "去重", "content": "dedup unique content abc"})
    results = search.search("book", "dedup")
    assert len(results["chapters"]) == 1
