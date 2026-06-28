from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from core.errors import NotFoundError
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
    model_config = ConfigDict(extra='allow')


class EventUpdate(BaseModel):
    model_config = ConfigDict(extra='allow')


class WorldbuildingUpdate(BaseModel):
    model_config = ConfigDict(extra='allow')


class WBCategoryCreate(BaseModel):
    name: str = ""
    icon: str = ""
    parent_id: str | None = None


class WBEntryCreate(BaseModel):
    category_id: str = ""
    model_config = ConfigDict(extra='allow')


class WBEntryUpdate(BaseModel):
    model_config = ConfigDict(extra='allow')


class LocationMapUpdate(BaseModel):
    model_config = ConfigDict(extra='allow')


class OutlineSummaryUpdate(BaseModel):
    summary: str = ""


class OutlineChapterUpdate(BaseModel):
    model_config = ConfigDict(extra='allow')


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
                    args={
                        "ref_book_id": ref_book_id,
                        "chapter_ids": data.chapter_ids
                    },
                    kb=None,  # 不需要知识库，只需要读取章节内容
                    book_id=book_id
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
    return json_store.add_worldbuilding_category(
        book_id, data.name, data.icon, data.parent_id)


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
