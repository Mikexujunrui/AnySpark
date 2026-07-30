import io
import json
import zipfile

import pytest
from fastapi import UploadFile

import routes.books as books_route


def _spark_file(manifest: dict, filename: str = "旧电脑作品.spark") -> UploadFile:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
    buffer.seek(0)
    return UploadFile(filename=filename, file=buffer)


@pytest.mark.asyncio
async def test_import_spark_creates_book_from_manifest(monkeypatch):
    created = []
    updated = []

    class FakeStore:
        def create_book(self, title, description):
            created.append((title, description))
            return {"id": "new-book", "title": title, "description": description}

        def update_book_stats(self, book_id, entity_count, chapter_count):
            updated.append((book_id, entity_count, chapter_count))

        def get_book(self, book_id):
            return {"id": book_id, "title": created[0][0], "description": created[0][1]}

        def delete_book(self, _book_id):
            raise AssertionError("successful import must not roll back")

    monkeypatch.setattr(books_route, "json_store", FakeStore())
    monkeypatch.setattr(books_route, "get_store", lambda _book_id: None)
    monkeypatch.setattr(
        books_route,
        "import_spark",
        lambda book_id, path: {"entities": 4, "chapters": 12, "errors": []},
    )

    result = await books_route.import_book_archive(
        _spark_file(
            {
                "format_version": 1,
                "book_id": "old-book",
                "book": {"title": "星火长篇", "description": "旧电脑上的项目"},
            }
        )
    )

    assert result["ok"] is True
    assert result["book"]["title"] == "星火长篇"
    assert created == [("星火长篇", "旧电脑上的项目")]
    assert updated == [("new-book", 4, 12)]


@pytest.mark.asyncio
async def test_import_old_spark_uses_filename(monkeypatch):
    class FakeStore:
        def create_book(self, title, description):
            return {"id": "new-book", "title": title, "description": description}

        def update_book_stats(self, *_args, **_kwargs):
            pass

        def get_book(self, book_id):
            return {"id": book_id, "title": "旧电脑作品", "description": ""}

        def delete_book(self, _book_id):
            pass

    monkeypatch.setattr(books_route, "json_store", FakeStore())
    monkeypatch.setattr(books_route, "get_store", lambda _book_id: None)
    monkeypatch.setattr(books_route, "import_spark", lambda _book_id, _path: {"entities": 0, "chapters": 1})

    result = await books_route.import_book_archive(
        _spark_file({"format_version": 1, "book_id": "old-book"})
    )
    assert result["book"]["title"] == "旧电脑作品"
