"""anyspark.library.citation — 引用元数据格式化（S250，D2 引用管理）。

机制=纯函数格式化器，内容=书库书的 cite_meta JSON（元数据）——零新存储、
零新依赖。支持 GB/T 7714-2015（顺序编码制核心规则）与 BibTeX 两种目标格式。

cite_meta 约定（JSON dict，缺省字段安全跳过）：
    entry_type: article|book|thesis|inproceedings|report|online
    authors:    list[str]（按来源原样存储，格式化时做中文/英文区分）
    title/venue/year/volume/number/pages/doi/url: str
lang 不单列：按字符是否含 CJK 推断（同一份 meta 可出两种格式）。
"""

from __future__ import annotations

import re
from typing import Any

_CJK = re.compile(r"[\u4e00-\u9fff]")
_VALID_TYPES = {"article", "book", "thesis", "inproceedings", "report", "online"}

# GB/T 7714 文献类型标识（entry_type → 标识码）
_GBT_MARKER = {
    "article": "J",
    "book": "M",
    "thesis": "D",
    "inproceedings": "C",
    "report": "R",
    "online": "EB/OL",
}

# BibTeX 条目类型映射（thesis 不分硕博——meta 未含学位字段时落 mastersthesis，
# 补全字段 degree 后可区分，见 _bibtex_type）
_BIB_TYPES = {
    "article": "article",
    "book": "book",
    "thesis": "mastersthesis",
    "inproceedings": "inproceedings",
    "report": "techreport",
    "online": "misc",
}


def _is_zh(text: str) -> bool:
    """中文文献判定：任一作者或题名含 CJK。"""
    return bool(_CJK.search(text))


def _gbt_authors(meta: dict[str, Any]) -> str:
    """GB/T 7714 作者串：3 人内全列，>3 人取前 3 加「等/et al.」。"""
    authors = [a.strip() for a in meta.get("authors") or [] if a.strip()]
    if not authors:
        return ""
    zh = _is_zh(" ".join(authors) + str(meta.get("title") or ""))
    etc = "等" if zh else "et al"
    if len(authors) > 3:
        return ", ".join(authors[:3]) + f", {etc}"
    return ", ".join(authors)


def fmt_gbt7714(meta: dict[str, Any]) -> str:
    """GB/T 7714-2015 顺序编码制单条目（专著/期刊/学位论文/会议/报告/在线）。

    覆盖核心格式「作者. 题名[标识]. 出处, 年, 卷(期): 页码.」；online 走
    「题名[EB/OL]. (发布年)[引用日期省略]. URL.」的简化式（V1 不做引用日期）。
    """
    et = str(meta.get("entry_type") or "book")
    if et not in _VALID_TYPES:
        et = "book"
    marker = _GBT_MARKER[et]
    title = str(meta.get("title") or "").strip()
    year = str(meta.get("year") or "").strip()
    venue = str(meta.get("venue") or "").strip()
    volume = str(meta.get("volume") or "").strip()
    number = str(meta.get("number") or "").strip()
    pages = str(meta.get("pages") or "").strip().replace("--", "-")
    doi = str(meta.get("doi") or "").strip()
    url = str(meta.get("url") or "").strip()

    head = f"{_gbt_authors(meta)}. " if _gbt_authors(meta) else ""
    body = f"{title}[{marker}]. "
    tail = ""
    if et == "article":
        seg = venue
        if year:
            seg += f", {year}" if seg else year
        if volume:
            seg += f", {volume}"
        if number:
            seg += f"({number})"
        if pages:
            seg += f": {pages}"
        tail = seg + "."
    elif et in ("book", "thesis", "report", "inproceedings"):
        seg = venue  # 出版社/学位授予单位/会议名
        if year:
            seg += f", {year}" if seg else year
        if pages:
            seg += f": {pages}"
        tail = seg + "."
    elif et == "online":
        tail = f"({year}). {url}." if url else f"({year})."
    out = head + body + tail
    if doi and not url:
        out += f" DOI: {doi}."
    return re.sub(r"\s+", " ", out).strip()


def _bibtex_escape(s: str) -> str:
    """BibTeX 特殊字符转义（& % _ #）。"""
    for ch, rep in (("&", r"\&"), ("%", r"\%"), ("_", r"\_"), ("#", r"\#")):
        s = s.replace(ch, rep)
    return s


def _bibtex_type(meta: dict[str, Any]) -> str:
    et = str(meta.get("entry_type") or "book")
    t = _BIB_TYPES.get(et, "book")
    if et == "thesis" and str(meta.get("degree") or "").lower().startswith(("phd", "doc")):
        t = "phdthesis"
    return t


def bibtex_key(meta: dict[str, Any]) -> str:
    """BibTeX 引用键：首作者姓氏 + 年 + 题名首词（如 zhang2024sleep）。"""
    authors = meta.get("authors") or []
    surname = "anon"
    if authors:
        first = str(authors[0]).strip()
        # 「张三」取姓；「Zhang, San」/「San Zhang」取 Zhang
        surname = (
            first.split(",")[0].strip()
            if "," in first
            else first.split()[-1]
            if " " in first
            else first[:1]
        )
        surname = re.sub(r"[^A-Za-z\u4e00-\u9fff]", "", surname) or "anon"
        if surname.isascii():
            surname = surname.lower()  # BibTeX 键习惯：英文部分全小写
    year = str(meta.get("year") or "0000")[:4]
    words = re.findall(r"[A-Za-z\u4e00-\u9fff]+", str(meta.get("title") or ""))
    if not words:
        return f"{surname}{year}item"
    word = words[0]
    if _CJK.search(word) and len(word) > 2:
        word = word[:2]  # 中文题名无空格分词：键取前两字（如「睡眠」）
    return f"{surname}{year}{word.lower() if word.isascii() else word}"


def fmt_bibtex(meta: dict[str, Any]) -> str:
    """BibTeX 单条目（article/book/phdthesis|mastersthesis/inproceedings/techreport/misc）。"""
    et = str(meta.get("entry_type") or "book")
    if et not in _VALID_TYPES:
        et = "book"
    authors = [a.strip() for a in meta.get("authors") or [] if a.strip()]
    fields: list[tuple[str, str]] = [("author", " and ".join(authors))] if authors else []
    fields.append(("title", str(meta.get("title") or "")))
    venue = str(meta.get("venue") or "").strip()
    if et == "article":
        fields.append(("journal", venue))
    elif et == "inproceedings":
        fields.append(("booktitle", venue))
    elif et in ("book",):
        fields.append(("publisher", venue))
    elif et in ("thesis",):
        fields.append(("school", venue))
    elif et == "report":
        fields.append(("institution", venue))
    for k in ("year", "volume", "number"):
        v = str(meta.get(k) or "").strip()
        if v:
            fields.append((k, v))
    pages = str(meta.get("pages") or "").strip().replace("-", "--")
    if pages:
        fields.append(("pages", pages))
    for k in ("doi", "url"):
        v = str(meta.get(k) or "").strip()
        if v:
            fields.append((k, v))
    body = ",\n".join(f"  {k} = {{{_bibtex_escape(v)}}}" for k, v in fields if v)
    return f"@{_bibtex_type(meta)}{{{bibtex_key(meta)},\n{body}\n}}"


def minimal_meta(book_name: str) -> dict[str, Any]:
    """无元数据书的兜底条目（题名=书名，标注待补全——诚实降级而非编造）。"""
    return {
        "entry_type": "book",
        "authors": [],
        "title": book_name,
        "venue": "",
        "year": "",
        "note": "引用元数据待补全",
    }


def format_note(meta: dict[str, Any]) -> str:
    """缺失关键字段的提示（供工具输出末尾附「待补全」说明）。"""
    missing = [
        k
        for k in ("authors", "title", "year")
        if not (meta.get(k) or ([meta.get(k)] if isinstance(meta.get(k), str) else []))
    ]
    parts = []
    note = str(meta.get("note") or "").strip()
    if note:
        parts.append(note)  # minimal_meta 的「引用元数据待补全」诚实标注
    if missing:
        parts.append(f"⚠ 元数据缺字段：{'、'.join(missing)}")
    if not parts:
        return ""
    return "；".join(parts) + "（POST /api/library/{id}/cite-meta 补全）"
