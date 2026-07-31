"""Work-product flows: writing_result / patch_result / review_result.

These produce chapter-change events for the frontend and (for review)
a terminal chunk.
"""

from core.loop_event import LoopEvent


async def flow_writing_result(result: dict, book_id: str):
    """Always tell the frontend whether generated prose was actually saved."""
    saved = bool(result.get("saved"))
    error_text = result.get("error", "") or ("" if saved else result.get("text", ""))
    events = [
        LoopEvent(
            type="writing_end",
            data={
                "chapter_id": result.get("chapter_id", ""),
                "chapter_title": result.get("chapter_title", ""),
                "word_count": result.get("word_count", 0),
                "saved": saved,
                "partial": bool(result.get("partial")),
                "error": str(error_text)[:300],
            },
        )
    ]
    result_str = result.get("text", "") or result.get("error", "")
    return events, result_str, False, None


async def flow_patch_result(result: dict, book_id: str):
    """局部修改结果：非错误时向前端发 patch_result 事件。"""
    events: list[LoopEvent] = []
    if not result.get("error"):
        events.append(
            LoopEvent(
                type="patch_result",
                data={
                    "chapter_id": result.get("chapter_id", ""),
                    "chapter_title": result.get("chapter_title", ""),
                    "operations": result.get("operations", []),
                    "patched_count": result.get("patched_count", 0),
                    "total_count": result.get("total_count", 0),
                    "word_count": result.get("word_count", 0),
                },
            )
        )
    result_str = result.get("text", "") or result.get("error", "")
    return events, result_str, False, None


async def flow_review_result(result: dict, book_id: str):
    """评审结果：终结本轮（terminal），标记章节已更新。"""
    result_str = result.get("text", "")
    return [], result_str, True, result_str
