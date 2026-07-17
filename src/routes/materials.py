from fastapi import APIRouter
from pydantic import BaseModel

from core.search import fts
from data.json_store import json_store

router = APIRouter(tags=["materials"])


class MaterialCreate(BaseModel):
    title: str
    content: str
    tags: list[str] | None = None
    source: str = "manual"
    source_url: str = ""


class RefBooksSet(BaseModel):
    book_ids: list[str]


class SubscribeRequest(BaseModel):
    material_id: str


@router.get("/materials")
async def list_materials(book_id: str = ""):
    """列出当前项目订阅的资料（需传 book_id），或全局资料（不传 book_id）"""
    if book_id:
        subs = json_store.load_material_subs(book_id)
        mats = json_store.load_materials()
        result = [m for m in mats if m["id"] in subs]
        return {"materials": result, "subscribed_ids": subs}
    return {"materials": json_store.load_materials()}


@router.post("/materials")
async def add_material(body: MaterialCreate):
    mat = json_store.add_material(
        title=body.title,
        content=body.content,
        tags=body.tags or [],
        source=body.source,
        source_url=body.source_url,
    )
    fts.index_material(mat)
    return mat


@router.delete("/materials/{material_id}")
async def delete_material(material_id: str):
    json_store.delete_material(material_id)
    fts.remove_material(material_id)
    return {"ok": True}


@router.get("/materials/search")
async def search_materials(q: str = "", book_id: str = ""):
    """全文搜索资料库，可选按项目订阅过滤"""
    subs = None
    if book_id:
        subs = json_store.load_material_subs(book_id)
    if q:
        results = fts.search_materials(q, subs)
    else:
        mats = json_store.load_materials()
        if subs is not None:
            mats = [m for m in mats if m["id"] in subs]
        results = [{"id": m["id"], "title": m["title"],
                     "tags": m.get("tags", []),
                     "snippet": m.get("content", "")[:80]} for m in mats]
    return {"results": results}


@router.post("/books/{book_id}/material-subs")
async def subscribe_material(book_id: str, body: SubscribeRequest):
    json_store.subscribe_material(book_id, body.material_id)
    return {"ok": True}


@router.delete("/books/{book_id}/material-subs/{material_id}")
async def unsubscribe_material(book_id: str, material_id: str):
    json_store.unsubscribe_material(book_id, material_id)
    return {"ok": True}


@router.get("/books/{book_id}/references")
async def get_references(book_id: str):
    ref_ids = json_store.get_reference_books(book_id)
    books = [b for b in json_store.load_books() if b["id"] in ref_ids]
    return {"reference_book_ids": ref_ids, "references": books}


@router.put("/books/{book_id}/references")
async def set_references(book_id: str, body: RefBooksSet):
    json_store.set_reference_books(book_id, body.book_ids)
    return {"ok": True}
