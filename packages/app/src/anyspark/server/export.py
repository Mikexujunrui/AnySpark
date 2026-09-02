"""
anyspark.server.export — 全书导出（S48-P3：多格式 + 图片携带）。

- txt/md：章节拼接（md 保留图片引用路径）
- epub：EPUB 3 零依赖导出（zipfile + xhtml）——收集章节 md 内的图片引用，
  复制进 epub images/ 并改写 src；原始区图片（如 上传/xxx.png）随导出携带。
  图片支持（决策记录）：md 相对引用 → 导出带入，无需多模态理解。
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_HEAD_RE = re.compile(r"^(#{1,3})\s+(.+)$")
_NUM_ITEM_RE = re.compile(r"^\d+[.、)]\s+")


def export_txt(chapters: list[dict[str, str]]) -> str:
    return "\n\n".join(f"{c['title']}\n{c['content']}" for c in chapters)


def export_md(chapters: list[dict[str, str]]) -> str:
    return "\n\n".join(f"# {c['title']}\n\n{c['content']}" for c in chapters)


_TEX_SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def _tex_escape(text: str) -> str:
    return "".join(_TEX_SPECIALS.get(ch, ch) for ch in text)


def export_latex(chapters: list[dict[str, str]]) -> str:
    """LaTeX 导出（S250，D2 学术硬缺口）：md 章节 → 可编译 tex 骨架。"""
    body: list[str] = []

    def _flush_para(p: list[str]) -> None:
        if p:
            body.append("\n".join(p))
            p.clear()

    for c in chapters:
        body.append(f"\\section{{{_tex_escape(c['title'])}}}")
        lines = str(c["content"]).splitlines()
        in_code = False
        para: list[str] = []
        in_list = ""  # 当前列表环境：""（不在列表）/ "itemize" / "enumerate"
        for line in lines:
            if line.strip().startswith("```"):
                _flush_para(para)
                if in_list:
                    body.append(f"\\end{{{in_list}}}")
                    in_list = ""
                body.append("\\begin{verbatim}" if not in_code else "\\end{verbatim}")
                in_code = not in_code
                continue
            if in_code:
                body.append(line)
                continue
            m = _HEAD_RE.match(line)
            if m:
                _flush_para(para)
                if in_list:
                    body.append(f"\\end{{{in_list}}}")
                    in_list = ""
                # ##/### → subsection/subsubsection（# 已被章标题占用）
                hashes = len(m.group(1))
                cmd = "subsection" if hashes <= 2 else "subsubsection"
                body.append(f"\\{cmd}{{{_tex_escape(m.group(2).strip())}}}")
                continue
            stripped = line.strip()
            if not stripped:
                _flush_para(para)
                if in_list:
                    body.append(f"\\end{{{in_list}}}")
                    in_list = ""
                continue
            if stripped.startswith(("- ", "* ", "+ ")) or _NUM_ITEM_RE.match(stripped):
                _flush_para(para)
                env = "enumerate" if _NUM_ITEM_RE.match(stripped) else "itemize"
                if not in_list:
                    body.append(f"\\begin{{{env}}}")
                    in_list = env
                elif in_list != env:  # 类型切换：闭旧开新
                    body.append(f"\\end{{{in_list}}}")
                    body.append(f"\\begin{{{env}}}")
                    in_list = env
                inner = stripped.lstrip("-*+ ").lstrip("0123456789. ")
                body.append(f"\\item {_tex_escape(inner)}")
                continue
            para.append(_tex_escape(line))
        _flush_para(para)
        if in_list:
            body.append(f"\\end{{{in_list}}}")
    preamble = (
        "% AnySpark LaTeX 导出（V1：ctex 文档类，中文直出）\n"
        "\\documentclass[UTF8]{ctexart}\n"
        "\\usepackage{geometry}\n"
        "\\geometry{a4paper, margin=2.5cm}\n"
        "\n\\begin{document}\n"
    )
    return preamble + "\n\n".join(body) + "\n\\end{document}\n"


def _md_to_xhtml(title: str, content: str) -> str:
    """md 正文 → xhtml 段落（按空行分段；图片引用原样保留待导出时改写）。"""
    import html

    paras = [p.strip() for p in content.split("\n\n") if p.strip()]
    body = "\n".join(f"<p>{html.escape(p)}</p>" for p in paras)
    if not body:
        body = "<p></p>"
    return f"<h2>{html.escape(title)}</h2>\n{body}"


def export_epub(
    title: str,
    author: str,
    chapters: list[dict[str, str]],
    image_dir: Path | None = None,
) -> bytes:
    """EPUB 3 导出（零依赖 zipfile）。image_dir：章节 md 引用图片的相对基目录。"""
    images: dict[str, bytes] = {}
    xhtml_parts: list[str] = []
    manifest: list[str] = []
    spine: list[str] = []
    uuid_val = _uuid()
    for i, ch in enumerate(chapters, 1):
        cid = f"ch{i}"

        # 收集并改写图片引用
        def _repl(m: re.Match[str]) -> str:
            raw = m.group(2).strip()
            if raw.startswith(("http://", "https://", "data:")):
                return m.group(0)
            src = raw
            if image_dir is not None and not Path(raw).is_absolute():
                p = (image_dir / raw).resolve()
                if p.exists() and p.is_file():
                    ext = p.suffix.lower().lstrip(".") or "png"
                    fname = f"images/{uuid_val[:8]}-{p.stem[:40]}.{ext}"
                    images[fname] = p.read_bytes()
                    src = fname
            return f'<img src="{src}" alt="{m.group(1)}"/>'

        body = _IMG_RE.sub(_repl, ch["content"])
        xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head>
<title>{_esc(ch["title"])}</title></head><body>
{_md_to_xhtml(ch["title"], body)}
</body></html>"""
        xhtml_parts.append(xhtml)
        manifest.append(f'<item id="{cid}" href="{cid}.xhtml" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="{cid}"/>')

    for img_path in images:
        ext = img_path.rsplit(".", 1)[-1].lower()
        mime = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "webp": "image/webp",
        }.get(ext, "image/png")
        img_id = f"img{len(manifest)}"
        manifest.append(f'<item id="{img_id}" href="{img_path}" media-type="{mime}"/>')

    nav_lines = (
        f'<li><a href="{i + 1}.xhtml">{_esc(c["title"])}</a></li>' for i, c in enumerate(chapters)
    )
    nav = f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>目录</title></head><body>
<nav epub:type="toc"><h1>目录</h1><ol>
{"".join(nav_lines)}
</ol></nav></body></html>"""
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="bookid">{uuid_val}</dc:identifier>
<dc:title>{_esc(title)}</dc:title>
<dc:creator>{_esc(author)}</dc:creator>
<dc:language>zh-CN</dc:language>
<meta property="dcterms:modified">{_now_iso()}</meta>
</metadata>
<manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
{"".join(manifest)}
</manifest>
<spine>{"".join(spine)}</spine>
</package>"""
    container = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
</rootfiles>
</container>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", container)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/nav.xhtml", nav)
        for idx, xhtml in enumerate(xhtml_parts, 1):
            zf.writestr(f"OEBPS/{idx}.xhtml", xhtml)
        for img_path in images:
            zf.writestr(f"OEBPS/{img_path}", images[img_path])
    return buf.getvalue()


def _esc(s: str) -> str:
    import html

    return html.escape(s)


def _uuid() -> str:
    import uuid

    return str(uuid.uuid4())


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
