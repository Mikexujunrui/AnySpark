import io
from datetime import datetime


def export_txt(book_title: str, chapters: list[dict], include_metadata: bool = False) -> bytes:
    lines = []
    lines.append(f"《{book_title}》")
    lines.append(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append("=" * 40)
    lines.append("")

    for i, ch in enumerate(chapters, 1):
        title = ch.get("title", f"第{i}章")
        content = ch.get("content", "")
        lines.append(f"\n{'─' * 20}")
        lines.append(f"  {title}")
        lines.append(f"{'─' * 20}\n")
        if include_metadata:
            lines.append(f"  [创建: {ch.get('createdAt', '未知')}]")
            lines.append(f"  [字数: {len(content)}]")
            lines.append("")
        lines.append(content)
        lines.append("")

    lines.append("")
    lines.append("─── 全书完 ───")
    total = sum(len(ch.get("content", "")) for ch in chapters)
    lines.append(f"共 {len(chapters)} 章，{total} 字")

    return "\n".join(lines).encode("utf-8")


def export_docx(book_title: str, chapters: list[dict]) -> bytes:
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt
    except ImportError:
        raise ImportError("需要安装 python-docx: pip install python-docx")

    doc = Document()

    title_para = doc.add_heading(book_title, level=0)
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    doc.add_page_break()

    if len(chapters) > 1:
        doc.add_heading("目录", level=1)
        for i, ch in enumerate(chapters, 1):
            doc.add_paragraph(f"{i}. {ch.get('title', f'第{i}章')}", style='List Number')
        doc.add_page_break()

    for i, ch in enumerate(chapters, 1):
        title = ch.get("title", f"第{i}章")
        content = ch.get("content", "")
        doc.add_heading(title, level=1)

        for paragraph in content.split("\n"):
            p = paragraph.strip()
            if p:
                para = doc.add_paragraph()
                para.paragraph_format.first_line_indent = Pt(24)
                run = para.add_run(p)
                run.font.size = Pt(12)

        if i < len(chapters):
            doc.add_page_break()

    doc.add_paragraph("")
    final = doc.add_paragraph("── 全书完 ──")
    final.alignment = WD_ALIGN_PARAGRAPH.CENTER
    total = sum(len(ch.get("content", "")) for ch in chapters)
    stats = doc.add_paragraph(f"共 {len(chapters)} 章，{total} 字")
    stats.alignment = WD_ALIGN_PARAGRAPH.CENTER

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def export_single_chapter_txt(chapter: dict) -> bytes:
    title = chapter.get("title", "章节")
    content = chapter.get("content", "")
    text = f"{title}\n\n{content}"
    return text.encode("utf-8")
