from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from core.archive import export_spark
from core.exporter import export_docx, export_epub, export_single_chapter_txt, export_txt
from data.json_store import json_store

router = APIRouter(tags=["export"])

def _make_download_response(data: bytes, filename: str, media_type: str) -> Response:
    encoded = quote(filename)
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
        },
    )


@router.get("/books/{book_id}/export")
def export_book(book_id: str, format: str = "txt", metadata: bool = False):
    try:
        book = json_store.get_book(book_id)
    except Exception:
        raise HTTPException(404, "书籍不存在")

    raw_chapters = json_store.load_chapters(book_id)
    if not raw_chapters:
        raise HTTPException(400, "暂无章节可导出")

    chapters = [json_store._chapter_view(ch) for ch in raw_chapters]
    title = book.get("title", "未命名")

    if format == "docx":
        try:
            data = export_docx(title, chapters)
        except ImportError as e:
            raise HTTPException(500, str(e))
        return _make_download_response(data, f"{title}.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    elif format == "spark":
        try:
            path = export_spark(book_id)
            return FileResponse(
                path,
                media_type="application/zip",
                filename=f"{title}.spark",
                headers={
                    "Content-Disposition":
                        f"attachment; filename*=UTF-8''{quote(f'{title}.spark')}",
                },
            )
        except Exception as e:
            raise HTTPException(500, f"导出失败: {e}")
    elif format == "epub":
        try:
            data = export_epub(title, chapters)
        except ImportError as e:
            raise HTTPException(500, str(e))
        return _make_download_response(data, f"{title}.epub",
            "application/epub+zip")
    else:
        data = export_txt(title, chapters, include_metadata=metadata)
        return _make_download_response(data, f"{title}.txt", "text/plain; charset=utf-8")


@router.get("/books/{book_id}/chapters/{chapter_id}/export")
def export_chapter(book_id: str, chapter_id: str):
    try:
        chapter = json_store.get_chapter(book_id, chapter_id)
    except Exception:
        raise HTTPException(404, "章节不存在")

    data = export_single_chapter_txt(chapter)
    title = chapter.get("title", "章节")
    return _make_download_response(data, f"{title}.txt", "text/plain; charset=utf-8")
