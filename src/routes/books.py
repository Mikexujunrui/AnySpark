import io
import json
import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from core.archive import ARCHIVE_VERSION, MANIFEST_FILENAME, import_spark
from core.creative_constitution import MAX_CONSTITUTION_CHARS
from core.graph_store import GraphStore, get_store
from data.json_store import json_store

router = APIRouter(tags=["books"])


class BookCreate(BaseModel):
    title: str
    description: str = ""


class BookUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    creativeConstitution: str | None = None
    constitutionEnabled: bool | None = None


MAX_SPARK_UPLOAD_BYTES = 200 * 1024 * 1024


def _compute_total_words(book_id: str) -> int:
    try:
        chapters = json_store.load_chapters(book_id)
        total = 0
        for c in chapters:
            view = json_store._chapter_view(c)
            total += len(view.get("content", ""))
        return total
    except Exception:
        return 0


@router.get("/books")
async def list_books():
    books = json_store.load_books()
    for b in books:
        b["totalWords"] = _compute_total_words(b["id"])
    return books


@router.get("/books/{book_id}")
def get_book(book_id: str):
    book = json_store.get_book(book_id)
    book["totalWords"] = _compute_total_words(book_id)
    return book


@router.post("/books")
def create_book(book: BookCreate):
    new_book = json_store.create_book(book.title, book.description)
    get_store(new_book["id"])
    return new_book


@router.post("/books/import-spark")
async def import_book_archive(file: UploadFile):
    """Create a book project from a portable .spark archive."""
    filename = file.filename or ""
    if not filename.lower().endswith(".spark"):
        raise HTTPException(400, "请选择 .spark 项目归档")

    content = await file.read(MAX_SPARK_UPLOAD_BYTES + 1)
    if len(content) > MAX_SPARK_UPLOAD_BYTES:
        raise HTTPException(413, ".spark 归档不能超过 200MB")

    try:
        with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
            if MANIFEST_FILENAME not in archive.namelist():
                raise ValueError("缺少 manifest.json")
            manifest = json.loads(archive.read(MANIFEST_FILENAME))
            if manifest.get("format_version") != ARCHIVE_VERSION:
                raise ValueError(f"不支持的归档版本: {manifest.get('format_version')}")
    except (zipfile.BadZipFile, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(400, f"无效的 .spark 归档：{exc}")

    metadata = manifest.get("book") if isinstance(manifest.get("book"), dict) else {}
    title = str(metadata.get("title") or Path(filename).stem).strip() or "导入的项目"
    description = str(metadata.get("description") or "从 .spark 归档导入")
    book = json_store.create_book(title, description)
    constitution = str(metadata.get("creativeConstitution") or "")[:MAX_CONSTITUTION_CHARS]
    if constitution or metadata.get("constitutionEnabled") is False:
        book = json_store.update_book(
            book["id"],
            {
                "creativeConstitution": constitution,
                "constitutionEnabled": metadata.get("constitutionEnabled", True) is not False,
            },
        )
    get_store(book["id"])

    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".spark", delete=False) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name
        stats = import_spark(book["id"], temp_path)
        json_store.update_book_stats(
            book["id"],
            entity_count=stats.get("entities", 0),
            chapter_count=stats.get("chapters", 0),
        )
        book = json_store.get_book(book["id"])
        return {"ok": True, "book": book, "stats": stats}
    except Exception as exc:
        try:
            json_store.delete_book(book["id"])
            GraphStore(book["id"])._run(
                "MATCH (n {project_id: $pid}) DETACH DELETE n",
                {"pid": book["id"]},
            )
        except Exception:
            pass
        raise HTTPException(400, f"导入失败：{exc}")
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


@router.put("/books/{book_id}")
def update_book(book_id: str, book: BookUpdate):
    """Update book title and/or description."""
    data = {k: v for k, v in book.model_dump().items() if v is not None}
    if len(data.get("creativeConstitution", "")) > MAX_CONSTITUTION_CHARS:
        raise HTTPException(400, f"创作宪法不能超过 {MAX_CONSTITUTION_CHARS} 字")
    if not data:
        return json_store.get_book(book_id)
    return json_store.update_book(book_id, data)


@router.delete("/books/{book_id}")
def delete_book(book_id: str):
    json_store.delete_book(book_id)
    try:
        store = GraphStore(book_id)
        store._run("MATCH (e {project_id: $pid}) DETACH DELETE e", {"pid": book_id})
    except Exception:
        pass
    return {"ok": True}
