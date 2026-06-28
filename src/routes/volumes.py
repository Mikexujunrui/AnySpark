from fastapi import APIRouter
from pydantic import BaseModel

from data.json_store import json_store

router = APIRouter(tags=["volumes"])


class VolumeCreate(BaseModel):
    title: str
    story_line: str = ""


class VolumeUpdate(BaseModel):
    title: str | None = None
    story_line: str | None = None
    order: int | None = None


class ChapterMove(BaseModel):
    chapter_id: str


@router.get("/books/{book_id}/volumes")
async def list_volumes(book_id: str):
    volumes = json_store.load_volumes(book_id)
    chapters = json_store.load_chapters(book_id)
    chapter_titles = {c["id"]: c.get("title", "") for c in chapters}

    result = []
    for v in volumes:
        entries = []
        for cid in v.get("chapters", []):
            entries.append({
                "id": cid,
                "title": chapter_titles.get(cid, ""),
            })
        result.append({
            "id": v["id"],
            "title": v["title"],
            "storyLine": v.get("storyLine", ""),
            "order": v.get("order", 0),
            "chapters": entries,
            "createdAt": v.get("createdAt", ""),
            "updatedAt": v.get("updatedAt", ""),
        })
    # Ensure ungrouped chapters are listed
    grouped_ids = set()
    for v in volumes:
        grouped_ids.update(v.get("chapters", []))
    ungrouped = []
    for c in chapters:
        view = json_store._chapter_view(c)
        if view["id"] not in grouped_ids:
            ungrouped.append({"id": view["id"], "title": view.get("title", "")})

    return {"volumes": result, "ungrouped_chapters": ungrouped}


@router.post("/books/{book_id}/volumes")
async def create_volume(book_id: str, body: VolumeCreate):
    vol = json_store.add_volume(book_id, body.title, body.story_line)
    return vol


@router.put("/books/{book_id}/volumes/{volume_id}")
async def update_volume(book_id: str, volume_id: str, body: VolumeUpdate):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    vol = json_store.update_volume(book_id, volume_id, data)
    return vol


@router.delete("/books/{book_id}/volumes/{volume_id}")
async def delete_volume(book_id: str, volume_id: str):
    json_store.delete_volume(book_id, volume_id)
    return {"ok": True}


@router.post("/books/{book_id}/volumes/{volume_id}/chapters")
async def move_chapter_to_volume(book_id: str, volume_id: str, body: ChapterMove):
    json_store.add_chapter_to_volume(book_id, volume_id, body.chapter_id)
    return {"ok": True}


@router.delete("/books/{book_id}/volumes/{volume_id}/chapters/{chapter_id}")
async def remove_chapter_from_volume(book_id: str, volume_id: str, chapter_id: str):
    json_store.remove_chapter_from_volume(book_id, chapter_id)
    return {"ok": True}
