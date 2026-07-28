"""Search API Routes — full-text search across chapters, entities, and worldbuilding."""

from fastapi import APIRouter, Query

from core.search import fts as fts_engine

router = APIRouter(prefix="/books/{book_id}/search", tags=["search"])


@router.get("")
def search(
    book_id: str,
    q: str = Query("", description="搜索关键词"),
    limit: int = Query(20, ge=1, le=100),
):
    if not q:
        return {"results": {"chapters": [], "entities": [], "worldbuilding": []}}
    results = fts_engine.search(book_id, q, limit)
    total = len(results["chapters"]) + len(results["entities"]) + len(results["worldbuilding"])
    return {"query": q, "total": total, "results": results}


@router.get("/chapters")
def search_chapters(
    book_id: str,
    q: str = Query("", description="搜索关键词"),
    limit: int = Query(10, ge=1, le=50),
):
    results = fts_engine.search_chapters(book_id, q, limit)
    return {"query": q, "results": results}


@router.get("/entities")
def search_entities(
    book_id: str,
    q: str = Query("", description="搜索关键词"),
    limit: int = Query(10, ge=1, le=50),
):
    results = fts_engine.search_entities(book_id, q, limit)
    return {"query": q, "results": results}
