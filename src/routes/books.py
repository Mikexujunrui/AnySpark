from fastapi import APIRouter
from pydantic import BaseModel

from core.graph_store import GraphStore, get_store
from data.json_store import json_store

router = APIRouter(tags=["books"])


class BookCreate(BaseModel):
    title: str
    description: str = ""


class BookUpdate(BaseModel):
    title: str | None = None
    description: str | None = None


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


@router.put("/books/{book_id}")
def update_book(book_id: str, book: BookUpdate):
    """Update book title and/or description."""
    data = {k: v for k, v in book.model_dump().items() if v is not None}
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
