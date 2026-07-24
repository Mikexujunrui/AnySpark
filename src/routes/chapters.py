from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from core.errors import NotFoundError
from core.semantic_diff import compute_semantic_diff
from data.json_store import json_store

router = APIRouter(tags=["chapters"])


class ChapterCreate(BaseModel):
    title: str = "新章节"
    content: str = ""
    is_extra: bool = False
    status: str = "draft"  # "draft" | "final"


class ChapterUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    status: str | None = None  # "draft" | "final"


class ChapterStatusUpdate(BaseModel):
    status: str  # "draft" | "final"


class RevertRequest(BaseModel):
    version_id: str = ""


class PatchRequest(BaseModel):
    patches: list[dict]
    message: str = "局部编辑"


class TrackCreate(BaseModel):
    name: str = "新轨道"
    color: str = "#a78bfa"


class EventCreate(BaseModel):
    model_config = ConfigDict(extra="allow")


class EventUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")


class WorldbuildingUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")


class WBCategoryCreate(BaseModel):
    name: str = ""
    icon: str = ""
    parent_id: str | None = None


class WBEntryCreate(BaseModel):
    category_id: str = ""
    model_config = ConfigDict(extra="allow")


class WBEntryUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")


class LocationMapUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")


class OutlineSummaryUpdate(BaseModel):
    summary: str = ""


class OutlineChapterUpdate(BaseModel):
    model_config = ConfigDict(extra="allow")


class DetailedOutlineChapterUpdate(BaseModel):
    title: str = ""
    plot_chain: list[str] = []
    chapter_function: str = ""


class ImportChaptersRequest(BaseModel):
    chapter_ids: list[str]


@router.get("/books/{book_id}/chapters")
def list_chapters(book_id: str):
    chapters = json_store.load_chapters(book_id)
    return [json_store._chapter_view(ch) for ch in chapters]


@router.post("/books/{book_id}/chapters")
def create_chapter(book_id: str, chapter: ChapterCreate):
    return json_store.add_chapter(book_id, chapter.title, chapter.content, chapter.is_extra, status=chapter.status)


@router.get("/books/{book_id}/chapters/{chapter_id}")
def get_chapter(book_id: str, chapter_id: str):
    try:
        return json_store.get_chapter(book_id, chapter_id)
    except NotFoundError as e:
        raise HTTPException(404, e.message)


@router.put("/books/{book_id}/chapters/{chapter_id}")
def update_chapter(book_id: str, chapter_id: str, chapter: ChapterUpdate):
    try:
        return json_store.update_chapter(book_id, chapter_id, chapter.model_dump(exclude_unset=True))
    except NotFoundError as e:
        raise HTTPException(404, e.message)


@router.post("/books/{book_id}/chapters/{chapter_id}/promote")
def promote_chapter(book_id: str, chapter_id: str):
    """将草稿章节提升为定稿（status: draft → final）。"""
    try:
        return json_store.set_chapter_status(book_id, chapter_id, "final")
    except NotFoundError as e:
        raise HTTPException(404, e.message)


@router.post("/books/{book_id}/chapters/{chapter_id}/demote")
def demote_chapter(book_id: str, chapter_id: str):
    """将定稿章节降级为草稿（status: final → draft）。"""
    try:
        return json_store.set_chapter_status(book_id, chapter_id, "draft")
    except NotFoundError as e:
        raise HTTPException(404, e.message)


@router.delete("/books/{book_id}/chapters/{chapter_id}")
def delete_chapter(book_id: str, chapter_id: str):
    json_store.delete_chapter(book_id, chapter_id)
    return {"ok": True}


@router.get("/books/{book_id}/chapters/{chapter_id}/history")
def chapter_history(book_id: str, chapter_id: str):
    try:
        return json_store.chapter_history(book_id, chapter_id)
    except NotFoundError as e:
        raise HTTPException(404, e.message)


@router.get("/books/{book_id}/chapters/{chapter_id}/versions/{version_id}")
def get_version(book_id: str, chapter_id: str, version_id: str):
    try:
        return json_store.get_chapter_version(book_id, chapter_id, version_id)
    except NotFoundError as e:
        raise HTTPException(404, e.message)


@router.post("/books/{book_id}/chapters/{chapter_id}/revert")
def revert_chapter(book_id: str, chapter_id: str, data: RevertRequest):
    if not data.version_id:
        raise HTTPException(400, "需要 version_id")
    try:
        return json_store.revert_chapter(book_id, chapter_id, data.version_id)
    except NotFoundError as e:
        raise HTTPException(404, e.message)


@router.delete("/books/{book_id}/chapters/{chapter_id}/versions/{version_id}")
def delete_version(book_id: str, chapter_id: str, version_id: str):
    try:
        return json_store.delete_version(book_id, chapter_id, version_id)
    except NotFoundError as e:
        raise HTTPException(404, e.message)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/books/{book_id}/chapters/{chapter_id}/purge")
def purge_history(book_id: str, chapter_id: str):
    try:
        return json_store.purge_chapter_history(book_id, chapter_id)
    except NotFoundError as e:
        raise HTTPException(404, e.message)


@router.post("/books/{book_id}/chapters/{chapter_id}/patch")
def patch_chapter(book_id: str, chapter_id: str, data: PatchRequest):
    """局部编辑章节：支持 replace/insert_after/insert_before/delete/append/prepend 操作。"""
    if not data.patches:
        raise HTTPException(400, "patches 列表不能为空")
    try:
        return json_store.patch_chapter(book_id, chapter_id, data.patches, message=data.message)
    except NotFoundError as e:
        raise HTTPException(404, e.message)
    except ValueError as e:
        raise HTTPException(400, str(e))


class ReorderRequest(BaseModel):
    order: list[str]


@router.post("/books/{book_id}/chapters/reorder")
def reorder_chapters(book_id: str, data: ReorderRequest):
    """重新排列章节顺序。order 是章节 ID 列表，按新顺序排列。"""
    if not data.order:
        raise HTTPException(400, "order 不能为空")
    try:
        return json_store.reorder_chapters(book_id, data.order)
    except NotFoundError as e:
        raise HTTPException(404, e.message)
    except Exception as e:
        raise HTTPException(500, str(e)[:200])


@router.post("/books/{book_id}/reference-books/{ref_book_id}/chapters/import")
def import_reference_chapters(book_id: str, ref_book_id: str, data: ImportChaptersRequest):
    """从参考书籍导入指定章节到当前书籍。"""
    import asyncio

    from tools.executor import _import_reference_chapters

    try:
        # 创建一个临时的 asyncio event loop 来运行异步函数
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _import_reference_chapters(
                    loop=loop,
                    args={"ref_book_id": ref_book_id, "chapter_ids": data.chapter_ids},
                    kb=None,  # 不需要知识库，只需要读取章节内容
                    book_id=book_id,
                )
            )
            return {"status": "success", "message": result}
        finally:
            loop.close()
    except Exception as e:
        raise HTTPException(500, f"导入章节失败：{str(e)}")


@router.get("/books/{book_id}/timeline-data")
def get_timeline_data(book_id: str):
    return json_store.load_timeline(book_id)


@router.post("/books/{book_id}/timeline-data/tracks")
def add_track(book_id: str, data: TrackCreate):
    return json_store.add_timeline_track(book_id, data.name, data.color)


@router.post("/books/{book_id}/timeline-data/events")
def add_event(book_id: str, data: EventCreate):
    return json_store.add_timeline_event(book_id, data.model_dump())


@router.put("/books/{book_id}/timeline-data/events/{event_id}")
def update_event(book_id: str, event_id: str, data: EventUpdate):
    try:
        return json_store.update_timeline_event(book_id, event_id, data.model_dump())
    except Exception as e:
        raise HTTPException(404, str(e))


@router.delete("/books/{book_id}/timeline-data/events/{event_id}")
def delete_event(book_id: str, event_id: str):
    json_store.delete_timeline_event(book_id, event_id)
    return {"ok": True}


@router.delete("/books/{book_id}/timeline-data/tracks/{track_id}")
def delete_track(book_id: str, track_id: str):
    json_store.delete_timeline_track(book_id, track_id)
    return {"ok": True}


@router.post("/books/{book_id}/purge-all-history")
def purge_all_history(book_id: str):
    count = json_store.purge_all_chapters_history(book_id)
    return {"ok": True, "purged": count}


@router.get("/books/{book_id}/worldbuilding")
def get_worldbuilding(book_id: str):
    return json_store.get_worldbuilding(book_id)


@router.put("/books/{book_id}/worldbuilding")
def save_worldbuilding(book_id: str, data: WorldbuildingUpdate):
    json_store.save_worldbuilding(book_id, data.model_dump())
    return {"ok": True}


@router.post("/books/{book_id}/worldbuilding/categories")
def add_wb_category(book_id: str, data: WBCategoryCreate):
    return json_store.add_worldbuilding_category(book_id, data.name, data.icon, data.parent_id)


@router.post("/books/{book_id}/worldbuilding/entries")
def add_wb_entry(book_id: str, data: WBEntryCreate):
    cat_id = data.category_id
    entry = {k: v for k, v in data.model_dump().items() if k != "category_id"}
    return json_store.add_worldbuilding_entry(book_id, cat_id, entry)


@router.put("/books/{book_id}/worldbuilding/entries/{entry_id}")
def update_wb_entry(book_id: str, entry_id: str, data: WBEntryUpdate):
    return json_store.update_worldbuilding_entry(book_id, entry_id, data.model_dump())


@router.delete("/books/{book_id}/worldbuilding/entries/{entry_id}")
def delete_wb_entry(book_id: str, entry_id: str):
    json_store.delete_worldbuilding_entry(book_id, entry_id)
    return {"ok": True}


@router.get("/books/{book_id}/location-map")
def get_location_map(book_id: str):
    return json_store.get_location_map(book_id)


@router.put("/books/{book_id}/location-map")
def save_location_map(book_id: str, data: LocationMapUpdate):
    json_store.save_location_map(book_id, data.model_dump())
    return {"ok": True}


@router.get("/books/{book_id}/detailed-outline")
def get_detailed_outline(book_id: str):
    return json_store.get_detailed_outline(book_id)


@router.get("/books/{book_id}/outline")
def get_outline(book_id: str):
    return json_store.get_outline(book_id)


@router.get("/books/{book_id}/continuity-cards")
def get_continuity_cards(book_id: str):
    """Return continuity cards for all chapters."""
    return json_store.load_continuity_cards(book_id)


@router.get("/books/{book_id}/flavor-reports")
def get_flavor_reports(book_id: str):
    """Return AI flavor scan reports for all chapters."""
    return json_store.load_flavor_reports(book_id)


@router.get("/books/{book_id}/notes")
def get_notes(book_id: str):
    """Return all notes for the book."""
    return json_store.load_notes(book_id)


@router.post("/books/{book_id}/notes")
def add_note(book_id: str, data: dict):
    """Add a note."""
    content = data.get("content", "")
    if not content:
        raise HTTPException(400, "content is required")
    tags = data.get("tags", [])
    return json_store.add_note(book_id, content, tags)


@router.delete("/books/{book_id}/notes/{note_id}")
def delete_note(book_id: str, note_id: str):
    """Delete a note by ID."""
    ok = json_store.delete_note(book_id, note_id)
    if not ok:
        raise HTTPException(404, "笔记不存在")
    return {"ok": True}


@router.post("/books/{book_id}/flavor-reports/scan-all")
def scan_all_flavor_reports(book_id: str):
    """Scan all chapters without existing flavor reports. Pure rule-based, zero token cost."""
    from core.ai_flavor_scanner import scan_chapter

    chapters = json_store.load_chapters(book_id)
    existing = json_store.load_flavor_reports(book_id)
    existing_chapters = existing.get("chapters", {})

    scanned = 0
    skipped = 0
    for ch in chapters:
        ch_idx = str(chapters.index(ch))
        if ch_idx in existing_chapters:
            skipped += 1
            continue
        cur = json_store._get_current_version(ch)
        content = cur.get("content", "")
        if content and len(content) >= 100:
            try:
                flavor = scan_chapter(content)
                json_store.save_flavor_report(book_id, int(ch_idx), flavor.to_dict())
                scanned += 1
            except Exception:
                pass

    return {"ok": True, "scanned": scanned, "skipped": skipped, "total": len(chapters)}


@router.post("/books/{book_id}/continuity-cards/generate")
async def generate_continuity_cards(book_id: str):
    """Generate continuity cards for all existing chapters. Uses flash model
    for speed — each card is ~400 tokens max_tokens."""
    import asyncio

    from tools.impl.knowledge import _generate_continuity_card

    chapters = json_store.load_chapters(book_id)
    if not chapters:
        return {"ok": False, "message": "没有章节"}

    generated = 0
    for idx, ch in enumerate(chapters):
        view = json_store._chapter_view(ch)
        content = view.get("content", "")
        title = view.get("title", "")
        if not content or len(content) < 200:
            continue
        ch_num = idx + 1
        # Skip if already generated
        existing = json_store.load_continuity_cards(book_id)
        if str(ch_num) in existing.get("chapters", {}):
            continue
        loop = asyncio.get_running_loop()
        card = await _generate_continuity_card(loop, content, ch_num, title)
        if card:
            json_store.save_continuity_card(book_id, ch_num, card)
            generated += 1

    return {"ok": True, "generated": generated, "total": len(chapters)}


@router.put("/books/{book_id}/outline/summary")
def update_outline_summary(book_id: str, data: OutlineSummaryUpdate):
    return json_store.update_outline_summary(book_id, data.summary)


@router.put("/books/{book_id}/outline/chapters/{chapter_index}")
def update_outline_chapter(book_id: str, chapter_index: int, data: OutlineChapterUpdate):
    return json_store.update_outline_chapter(book_id, chapter_index - 1, data.model_dump())


@router.put("/books/{book_id}/detailed-outline/chapters/{chapter_index}")
def update_detailed_outline_chapter(book_id: str, chapter_index: int, data: DetailedOutlineChapterUpdate):
    update = {}
    if data.title:
        update["title"] = data.title
    if data.plot_chain:
        update["plot_chain"] = data.plot_chain
    if data.chapter_function:
        update["chapter_function"] = data.chapter_function
    return json_store.update_detailed_outline_chapter(book_id, chapter_index - 1, update)


@router.put("/books/{book_id}/outline/extras/{extra_index}")
def update_outline_extra(book_id: str, extra_index: int, data: OutlineChapterUpdate):
    return json_store.update_outline_extra(book_id, extra_index - 1, data.model_dump())


@router.put("/books/{book_id}/detailed-outline/extras/{extra_index}")
def update_detailed_outline_extra(book_id: str, extra_index: int, data: DetailedOutlineChapterUpdate):
    update = {}
    if data.title:
        update["title"] = data.title
    if data.plot_chain:
        update["plot_chain"] = data.plot_chain
    if data.chapter_function:
        update["chapter_function"] = data.chapter_function
    return json_store.update_detailed_outline_extra(book_id, extra_index - 1, update)


class SemanticDiffRequest(BaseModel):
    old_version_id: str
    new_version_id: str


@router.post("/books/{book_id}/chapters/{chapter_id}/semantic-diff")
async def chapter_semantic_diff(book_id: str, chapter_id: str, req: SemanticDiffRequest):
    """Compute semantic diff between two chapter versions using LLM."""
    chapters = json_store.load_chapters(book_id)
    ch = json_store._resolve_by_id(chapters, chapter_id)
    if not ch:
        raise HTTPException(status_code=404, detail="Chapter not found")

    versions = ch.get("versions", [])
    old_v = next((v for v in versions if v.get("id") == req.old_version_id), None)
    new_v = next((v for v in versions if v.get("id") == req.new_version_id), None)
    if not old_v or not new_v:
        raise HTTPException(status_code=404, detail="Version not found")

    result = await compute_semantic_diff(
        old_content=old_v.get("content", ""),
        new_content=new_v.get("content", ""),
        chapter_title=new_v.get("title", ch.get("title", "")),
    )
    return result.to_dict()
