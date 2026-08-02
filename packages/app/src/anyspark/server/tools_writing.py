"""
anyspark.server.tools_writing — 写作场景真实工具。

让 Agent 能真正写作：读/写/列章节。工具是模块级函数（签名满足 core 的
ToolImplementer），通过 `book_id` + 共享 ChapterStore 真实落盘。
"""

from __future__ import annotations

from typing import Any

from anyspark.core.protocol import ParamSpec, ToolRegistry, ToolResult, ToolSpec
from anyspark.core.types import ToolCall
from anyspark.store import ChapterStore

# 默认当前写作书籍（阶段1 单本书；多书/切换在后续阶段引入）
DEFAULT_BOOK_ID = "main"


class WritingTools:
    """持有章节存储的写作工具实现组（注入共享 store，生命周期跟随 server）。"""

    def __init__(self, chapters: ChapterStore, book_id: str = DEFAULT_BOOK_ID) -> None:
        self._chapters = chapters
        self._book_id = book_id

    # -- 工具实现（签名匹配 ToolImplementer protocol）--
    def list_chapters(self, spec: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec.name, arguments=arguments)
        items = self._chapters.list_by_book(self._book_id)
        if not items:
            return ToolResult(call=call, ok=True, content="暂无已写章节。")
        lines = "\n".join(f"{c.order_index}: {c.title}" for c in items)
        return ToolResult(call=call, ok=True, content=lines)

    def read_chapter(self, spec: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec.name, arguments=arguments)
        title = str(arguments.get("title", "")).strip()
        if not title:
            return ToolResult(call=call, ok=False, content="缺少参数 title。")
        for c in self._chapters.list_by_book(self._book_id):
            if c.title == title:
                content = f"《{c.title}》全文如下：\n{c.content}"
                return ToolResult(call=call, ok=True, content=content)
        msg = f"未找到章节《{title}》。可用章节请用 list_chapters 查看。"
        return ToolResult(call=call, ok=False, content=msg)

    def write_chapter(self, spec: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec.name, arguments=arguments)
        title = str(arguments.get("title", "")).strip()
        content = str(arguments.get("content", ""))
        if not title or not content:
            return ToolResult(call=call, ok=False, content="缺少 title 或 content 参数。")
        all_chapters = self._chapters.list_by_book(self._book_id)
        existing = next((c for c in all_chapters if c.title == title), None)
        order = existing.order_index if existing else len(all_chapters)
        ch = self._chapters.upsert(self._book_id, title, content, order)
        note = "覆盖了旧版" if existing else "新建"
        return ToolResult(
            call=call,
            ok=True,
            content=f"已{note}章节《{title}》({ch.id})。",
            data={"chapter_id": ch.id, "title": title},
        )


# 工具规格（与 WritingTools 方法一一对应）
_WRITING_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="list_chapters",
        description="列出这本书当前已有的全部章节标题。",
    ),
    ToolSpec(
        name="read_chapter",
        description="读取某章全文，用于续写/修改时保持连贯。",
        params=[ParamSpec(name="title", type="string", required=True, description="章节标题")],
    ),
    ToolSpec(
        name="write_chapter",
        description="把写作正文保存为某章（新建或覆盖；覆盖前旧版进版本历史）。",
        params=[
            ParamSpec(name="title", type="string", required=True, description="章节标题"),
            ParamSpec(name="content", type="string", required=True, description="章节正文全文"),
        ],
    ),
]


def register_writing_tools(
    registry: ToolRegistry,
    chapters: ChapterStore,
    book_id: str = DEFAULT_BOOK_ID,
) -> None:
    """把写作工具集注册进注册表。"""
    tools = WritingTools(chapters, book_id)
    for spec in _WRITING_SPECS:
        registry.register(spec, getattr(tools, spec.name))
