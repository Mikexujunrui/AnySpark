"""
anyspark.server.pipeline — 输入消化管线（S48-P3：原始区 → 格式化区）。

设计决策（原始区存档，格式化区操作）：
```
上传区/任何格式（txt/md/docx/pdf，图片仅存档+引用）
  → extract_text：零依赖文本提取（txt/md 直读 / docx zipfile / pdf zlib 尽力而为）
  → 判别：
     长文（多章结构）→ chapterize 规则拆章 → 章节/ {order:03d}-{title}.md
     资料/设定类    → LLM 摘要卡 → 卡片/摘要卡-{name}.md（+ SQLite materials 兼容）
  → 格式化产物进工作区，原始文件原地不动（存档）
```
多模态（图片理解/OCR）明确不做——图片只支持上传存档 + md 相对引用 + 导出携带（EPUB），
放未来计划（决策记录）。机制（提取/拆章规则/存储位置）硬编码；内容（章节/卡片）自然语言。
"""

from __future__ import annotations

import re
import zipfile
import zlib
from pathlib import Path

# 章节标题模式（机制硬编码：中文出版/网文 + 英文常用）
_CHAPTER_RE = re.compile(
    r"^\s*(第[0-9一二三四五六七八九十百千万]+[章节回卷部篇][^\n]{0,40}|"
    r"Chapter\s+\d+[^\n]{0,40}|CHAPTER\s+\d+[^\n]{0,40})\s*$"
)
# md 图片引用：![alt](path)
_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def extract_text(path: Path) -> str:
    """零依赖文本提取（txt/md 直读；docx zipfile；pdf zlib 尽力而为）。

    pdf 为轻量提取：解 FlateDecode 流 + 抽文本操作符（Tj/TJ），
    仅覆盖非扫描、无加密的简单 PDF——复杂/扫描件返回提示（多模态 OCR 放未来）。
    """
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md", ".markdown"):
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix == ".pdf":
        return _extract_pdf(path)
    return ""


def _extract_docx(path: Path) -> str:
    """docx 文本提取（zipfile 读 word/document.xml，段落 <w:p> 内 <w:t> 拼接）。"""
    try:
        with zipfile.ZipFile(path) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
        paras = re.findall(r"<w:p[^>]*>(.*?)</w:p>", xml, re.DOTALL)
        out = []
        for para in paras:
            texts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", para, re.DOTALL)
            out.append("".join(texts))
        return "\n".join(out)
    except Exception:
        return ""


def _extract_pdf(path: Path) -> str:
    """轻量 PDF 文本提取：解 FlateDecode 流 → 抽 BT...ET 内的 Tj/TJ 文本。

    尽力而为：无加密、文本型 PDF 可提取；扫描件/复杂版式返回空（提示走未来多模态）。
    """
    try:
        data = path.read_bytes()
        texts: list[str] = []
        # 流对象：<< /Filter /FlateDecode ... >> stream ... endstream
        for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.DOTALL):
            raw = m.group(1)
            try:
                dec = zlib.decompress(raw)
            except Exception:
                continue
            # 文本操作符：Tj（单个）与 TJ（数组）；括号内转义处理
            for tm in re.finditer(rb"\((?:[^()\\]|\\.)*\)\s*Tj", dec):
                texts.append(_pdf_unquote(tm.group(0)))
            for tm in re.finditer(rb"\[((?:[^\[\]\\]|\\.)*)\]\s*TJ", dec):
                inner = tm.group(1)
                parts = re.findall(rb"\((?:[^()\\]|\\.)*\)", inner)
                texts.append("".join(_pdf_unquote(p) for p in parts))
        return (
            "\n".join(t for t in texts if t.strip())
            or "（PDF 未能提取文本：可能是扫描件，OCR 多模态放未来计划）"
        )
    except Exception:
        return "（PDF 解析失败）"


def _pdf_unquote(token: bytes) -> str:
    """PDF 括号字符串：去括号 + 解转义（\\( \\) \\\\ 等）。"""
    inner = token[1:]
    # 从右往左找配对的右括号
    depth = 0
    end = len(inner)
    for i, ch in enumerate(inner):
        if ch == 0x5C:  # backslash
            continue
        if ch == 0x28:
            depth += 1
        elif ch == 0x29:
            depth -= 1
            if depth == 0:
                end = i
                break
    inner = inner[:end]
    # 解转义
    out = re.sub(rb"\\([()\\])", rb"\1", inner)
    try:
        return out.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def chapterize(text: str, fallback_title: str = "全文") -> list[dict[str, str]]:
    """规则拆章：按章节标题模式切分。

    标题行（第X章/Chapter N）开新章；其余行归当前章。
    无任何标题 → 整篇作为一章（title=fallback）。
    """
    lines = text.split("\n")
    chapters: list[dict[str, str]] = []
    cur_title: str | None = None
    cur_lines: list[str] = []
    for line in lines:
        if _CHAPTER_RE.match(line):
            if cur_title is not None:
                chapters.append({"title": cur_title, "content": "\n".join(cur_lines).strip()})
            cur_title = line.strip()
            cur_lines = []
        else:
            cur_lines.append(line)
    if cur_title is not None:
        chapters.append({"title": cur_title, "content": "\n".join(cur_lines).strip()})
    if not chapters:
        body = "\n".join(lines).strip()
        if body:
            chapters = [{"title": fallback_title, "content": body}]
    return chapters
