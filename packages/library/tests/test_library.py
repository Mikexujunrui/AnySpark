"""anyspark.library — 书库/关联/检索测试。"""

import tempfile
from pathlib import Path

from anyspark.library import LibraryStore, search_reference_books


def _store() -> tuple[LibraryStore, Path]:
    d = Path(tempfile.mkdtemp())
    return LibraryStore(d / "lib.db", library_root=d / "library"), d


def test_book_crud_and_import() -> None:
    ls, _ = _store()
    try:
        b = ls.add_book("雾城风云")
        assert b["id"] == "雾城风云"
        ls.import_chapter("雾城风云", "第一章", "雨夜，陈渡推开钟表铺的门。老周擦拭怀表。")
        ls.import_chapter("雾城风云", "第二章", "雾城的钟声在午夜响起。")
        books = ls.list_books()
        assert len(books) == 1 and books[0]["chapters"] == 2
        assert "怀表" in ls.read_book("雾城风云")
    finally:
        ls.close()


def test_references_and_search() -> None:
    ls, _ = _store()
    try:
        ls.add_book("雾城风云")
        ls.import_chapter("雾城风云", "第一章", "雨夜，陈渡抵达雾城站。老周正在擦拭怀表。")
        ls.set_references("main", [{"type": "library", "id": "雾城风云"}])
        refs = ls.get_references("main")
        assert len(refs) == 1 and refs[0]["type"] == "library"
        # 检索命中
        res = search_reference_books(ls, "main", "怀表")
        assert res["total_hits"] >= 1
        assert res["results"][0]["ref_name"] == "雾城风云"
        # 未命中
        res2 = search_reference_books(ls, "main", "不存在的词")
        assert res2["total_hits"] == 0
        # 删除书 → 引用清理
        ls.delete_book("雾城风云")
        assert ls.get_references("main") == []
    finally:
        ls.close()


def test_project_reference_with_files() -> None:
    ls, _ = _store()
    try:
        ls.add_book("设定书")
        ls.import_chapter("设定书", "世界观", "这个世界的魔法有代价。")
        ls.set_references("main", [{"type": "library", "id": "设定书"}])

        def _proj(ref_book_id: str) -> str:
            return f"【第一章】\n{ref_book_id}的项目内容 含 代价"

        res = search_reference_books(ls, "main", "代价", project_files=_proj)
        assert res["total_hits"] >= 1
    finally:
        ls.close()
