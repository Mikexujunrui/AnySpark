# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Inspiration inbox API routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.inspiration_box import (
    add_inspiration,
    archive_inspiration,
    delete_inspiration,
    get_inspiration,
    link_inspiration,
    list_inspirations,
    promote_inspiration,
    search_inspirations,
    update_inspiration,
)

router = APIRouter(tags=["inspiration"])


class InspirationCreate(BaseModel):
    content: str
    tags: list[str] = []
    linked_characters: list[str] = []
    linked_chapters: list[str] = []
    linked_foreshadows: list[str] = []


class InspirationUpdate(BaseModel):
    content: str | None = None
    tags: list[str] | None = None
    status: str | None = None


class LinkRequest(BaseModel):
    target_type: str  # character / chapter / foreshadow
    target_id: str


class PromoteRequest(BaseModel):
    target_type: str  # outline_node / foreshadow / character_note


@router.get("/books/{book_id}/inspirations")
def list_insp(book_id: str, status: str | None = None):
    """List all inspirations, optionally filtered by status."""
    return {
        "book_id": book_id,
        "inspirations": list_inspirations(book_id, status),
    }


@router.post("/books/{book_id}/inspirations")
def create_insp(book_id: str, req: InspirationCreate):
    """Create a new inspiration card."""
    return add_inspiration(
        book_id=book_id,
        content=req.content,
        tags=req.tags,
        linked_characters=req.linked_characters,
        linked_chapters=req.linked_chapters,
        linked_foreshadows=req.linked_foreshadows,
    )


@router.get("/books/{book_id}/inspirations/{insp_id}")
def get_insp(book_id: str, insp_id: str):
    """Get a single inspiration by ID."""
    insp = get_inspiration(book_id, insp_id)
    if not insp:
        raise HTTPException(404, "Inspiration not found")
    return insp


@router.patch("/books/{book_id}/inspirations/{insp_id}")
def patch_insp(book_id: str, insp_id: str, req: InspirationUpdate):
    """Update an inspiration card."""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")
    result = update_inspiration(book_id, insp_id, updates)
    if not result:
        raise HTTPException(404, "Inspiration not found")
    return result


@router.post("/books/{book_id}/inspirations/{insp_id}/link")
def link_insp(book_id: str, insp_id: str, req: LinkRequest):
    """Link an inspiration to a character/chapter/foreshadow."""
    result = link_inspiration(book_id, insp_id, req.target_type, req.target_id)
    if not result:
        raise HTTPException(404, "Inspiration not found")
    return result


@router.post("/books/{book_id}/inspirations/{insp_id}/promote")
def promote_insp(book_id: str, insp_id: str, req: PromoteRequest):
    """Promote an inspiration to a formal structure."""
    result = promote_inspiration(book_id, insp_id, req.target_type)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@router.post("/books/{book_id}/inspirations/{insp_id}/archive")
def archive_insp(book_id: str, insp_id: str):
    """Archive an inspiration."""
    result = archive_inspiration(book_id, insp_id)
    if not result:
        raise HTTPException(404, "Inspiration not found")
    return result


@router.delete("/books/{book_id}/inspirations/{insp_id}")
def remove_insp(book_id: str, insp_id: str):
    """Permanently delete an inspiration."""
    if delete_inspiration(book_id, insp_id):
        return {"ok": True}
    raise HTTPException(404, "Inspiration not found")


@router.get("/books/{book_id}/inspirations/search")
def search_insp(book_id: str, q: str = ""):
    """Search inspirations by content/tags."""
    if not q:
        return {"results": [], "query": q}
    results = search_inspirations(book_id, q)
    return {"results": results, "query": q, "total": len(results)}
