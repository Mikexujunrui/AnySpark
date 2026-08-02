"""
anyspark.server.tools_writing — 写作场景真实工具。

让 Agent 能真正写作：读/写/列章节；S11 扩展文件工具（沙箱读 txt/md/docx）。
工具是模块级函数（签名满足 core 的 ToolImplementer），通过 `book_id` + 共享
ChapterStore 真实落盘。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

from anyspark.core.protocol import ParamSpec, ToolRegistry, ToolResult, ToolSpec
from anyspark.core.types import ToolCall
from anyspark.store import ChapterStore

# 默认当前写作书籍（阶段1 单本书；多书/切换在后续阶段引入）
DEFAULT_BOOK_ID = "main"
# 文件工具沙箱：只允许读写此目录下文件（越界保护：阻止绝对路径与 ..）
SANDBOX_DIR = Path(__file__).resolve().parents[5] / "data" / "sandbox"
# 单次文件读写上限（越界保护：防注入超长/超大文件）
MAX_FILE_CHARS = 50_000


def _resolve_sandbox_path(raw: str) -> Path | None:
    """把相对路径解析到沙箱内；越界（绝对路径/..）返回 None。"""
    p = Path(raw)
    if p.is_absolute():
        return None
    resolved = (SANDBOX_DIR / p).resolve()
    if not str(resolved).startswith(str(SANDBOX_DIR.resolve())):
        return None
    return resolved


def _extract_docx_text(path: Path) -> str:
    """轻量 docx 文本提取（零依赖：zipfile 读 document.xml）。"""
    try:
        with zipfile.ZipFile(path) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
        # 段落 <w:p>...</w:p>，取 <w:t> 文本
        paras = re.findall(r"<w:p[^>]*>(.*?)</w:p>", xml, re.DOTALL)
        out = []
        for para in paras:
            texts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", para, re.DOTALL)
            out.append("".join(texts))
        return "\n".join(out)
    except Exception:
        return "（无法解析 docx 文件）"


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
        if len(content) > MAX_FILE_CHARS:
            return ToolResult(
                call=call, ok=False, content=f"正文超长（>{MAX_FILE_CHARS} 字），请分段写入。"
            )
        all_chapters = self._chapters.list_by_book(self._book_id)
        existing = next((c for c in all_chapters if c.title == title), None)
        order = existing.order_index if existing else len(all_chapters)
        ch = self._chapters.upsert(self._book_id, title, content, order)
        # 幻觉检测 fake_write 兜底：落盘后自校验（id 必须能回读）
        if self._chapters.get(ch.id) is None:
            return ToolResult(
                call=call, ok=False, content=f"落盘校验失败：章节《{title}》未能读回。"
            )
        note = "覆盖了旧版" if existing else "新建"
        return ToolResult(
            call=call,
            ok=True,
            content=f"已{note}章节《{title}》({ch.id})。",
            data={"chapter_id": ch.id, "title": title},
        )

    # -- S11 文件工具（沙箱读 txt/md/docx）--
    def read_file(self, spec: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec.name, arguments=arguments)
        raw = str(arguments.get("path", "")).strip()
        path = _resolve_sandbox_path(raw)
        if path is None:
            return ToolResult(
                call=call, ok=False, content="路径越界：只允许沙箱目录内相对路径（data/sandbox/）。"
            )
        if not path.exists():
            return ToolResult(call=call, ok=False, content=f"文件不存在：{raw}")
        try:
            if path.suffix.lower() == ".docx":
                text = _extract_docx_text(path)
            else:
                text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"读取失败：{exc}")
        if len(text) > MAX_FILE_CHARS:
            text = text[:MAX_FILE_CHARS] + "\n…（已截断）"
        return ToolResult(call=call, ok=True, content=f"文件 {raw} 内容：\n{text}")

    def write_file(self, spec: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec.name, arguments=arguments)
        raw = str(arguments.get("path", "")).strip()
        content = str(arguments.get("content", ""))
        if len(content) > MAX_FILE_CHARS:
            return ToolResult(call=call, ok=False, content=f"内容超长（>{MAX_FILE_CHARS} 字）。")
        path = _resolve_sandbox_path(raw)
        if path is None:
            return ToolResult(
                call=call, ok=False, content="路径越界：只允许沙箱目录内相对路径（data/sandbox/）。"
            )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"写入失败：{exc}")
        return ToolResult(call=call, ok=True, content=f"已写入 {raw}（{len(content)} 字）。")


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
    ToolSpec(
        name="read_file",
        description=(
            "读取沙箱内文件（txt/md/docx），用于参考资料。只允许 data/sandbox/ 内相对路径。"
        ),
        params=[
            ParamSpec(
                name="path", type="string", required=True, description="相对路径，如 notes/设定.md"
            )
        ],
    ),
    ToolSpec(
        name="write_file",
        description=(
            "写入沙箱内文件（txt/md），用于保存参考资料/笔记。只允许 data/sandbox/ 内相对路径。"
        ),
        params=[
            ParamSpec(
                name="path", type="string", required=True, description="相对路径，如 notes/设定.md"
            ),
            ParamSpec(name="content", type="string", required=True, description="文件内容"),
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
