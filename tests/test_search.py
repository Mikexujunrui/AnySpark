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
