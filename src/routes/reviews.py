from fastapi import APIRouter
from pydantic import BaseModel

from core.review_panel import panel
from data.json_store import json_store

router = APIRouter(tags=["reviews"])


class ReviewerToggle(BaseModel):
    active: bool


class CustomReviewer(BaseModel):
    name: str
    persona: str
    category: str = "reader"
    avatar: str = "user"
    scoring_dimensions: list[dict] | None = None
    needs_knowledge: bool = False


class RunReviewRequest(BaseModel):
    chapter_id: str
    reviewer_ids: list[str] | None = None
    mode: str = "concurrent"


@router.get("/books/{book_id}/reviewers")
async def list_reviewers(book_id: str):
    return panel.list_reviewers(include_inactive=True)


@router.get("/books/{book_id}/reviewers/{reviewer_id}")
async def get_reviewer(book_id: str, reviewer_id: str):
    r = panel.get_reviewer(reviewer_id)
    if not r:
        return {"error": f"Not found: {reviewer_id}"}
    return r.to_detail()


@router.patch("/books/{book_id}/reviewers/{reviewer_id}")
async def toggle_reviewer(book_id: str, reviewer_id: str, body: ReviewerToggle):
    ok = panel.set_active(reviewer_id, body.active)
    if not ok:
        return {"error": f"Not found: {reviewer_id}"}
    return {"id": reviewer_id, "active": body.active}


@router.post("/books/{book_id}/reviewers/custom")
async def add_custom_reviewer(book_id: str, body: CustomReviewer):
    r = panel.add_custom_reviewer(
        rid=body.name.lower().replace(" ", "_"),
        name=body.name,
        persona=body.persona,
        category=body.category,
        avatar=body.avatar,
        scoring_dimensions=body.scoring_dimensions,
        needs_knowledge=body.needs_knowledge,
    )
    return r.to_dict()


@router.delete("/books/{book_id}/reviewers/custom/{reviewer_id}")
async def remove_custom_reviewer(book_id: str, reviewer_id: str):
    ok = panel.remove_custom_reviewer(reviewer_id)
    return {"ok": ok}


@router.get("/books/{book_id}/reviews")
async def list_reviews(book_id: str):
    reviews = json_store.load_reviews(book_id)
    for r in reviews:
        r.pop("individual_reviews", None)
    return reviews


@router.get("/books/{book_id}/reviews/{review_id}")
async def get_review(book_id: str, review_id: str):
    return json_store.get_review(book_id, review_id)


@router.delete("/books/{book_id}/reviews/{review_id}")
async def delete_review(book_id: str, review_id: str):
    json_store.delete_review(book_id, review_id)
    return {"ok": True}
