# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Pacing analysis API routes."""

from fastapi import APIRouter

from core.pacing_analyzer import analyze_book, get_chapter_pacing

router = APIRouter(tags=["pacing"])


@router.get("/books/{book_id}/pacing")
def book_pacing(book_id: str):
    """Return pacing curve data for all chapters in a book."""
    results = analyze_book(book_id)
    return {
        "book_id": book_id,
        "chapters": [r.to_dict() for r in results],
        "total_chapters": len(results),
    }


@router.get("/books/{book_id}/pacing/{chapter_id}")
def chapter_pacing(book_id: str, chapter_id: str):
    """Return detailed pacing metrics for a single chapter."""
    result = get_chapter_pacing(book_id, chapter_id)
    if not result:
        return {"error": "Chapter not found", "chapter_id": chapter_id}, 404
    return result.to_dict()
