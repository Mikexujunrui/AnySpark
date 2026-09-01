"""anyspark.library.connectors — 文献获取连接器（S250，D3）。

V1：arXiv Atom API（export.arxiv.org，stdlib urllib + ElementTree，零新依赖）。
文献=书库条目+cite_meta（S250 合并方案）：导入即建库书 + 摘要章节 + 引用元数据，
自动获得 RAG 检索/reference_lookup/拆论文·文献综述工作流（library_book_id 通用）。

知网无公开 API（需账号/接口协议）——V1 不做，用户走既有上传导入通道（诚实边界）。
全文 PDF 解析：V1 只落摘要章节；全文可用既有 import 通道补进同一本书。
"""

from __future__ import annotations

import re
import uuid
import xml.etree.ElementTree as ET
from typing import Any
from urllib import request as _urlreq

from anyspark.library.store import LibraryStore

_ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}
_ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")
_TIMEOUT_S = 30


def _normalize_arxiv_id(raw: str) -> str:
    """接受裸 id / arXiv:ID / abs 链接，归一为「2101.00001」。"""
    m = _ARXIV_ID_RE.search(raw)
    if not m:
        raise ValueError(f"无法识别 arXiv id：{raw!r}（示例：2101.00001 或 abs 链接）")
    return m.group(1)


def fetch_arxiv(arxiv_id_or_url: str) -> dict[str, Any]:
    """抓取 arXiv 论文元数据（Atom API）→ 统一 cite_meta 形状 + 摘要。"""
    aid = _normalize_arxiv_id(arxiv_id_or_url)
    url = f"https://export.arxiv.org/api/query?id_list={aid}"
    with _urlreq.urlopen(url, timeout=_TIMEOUT_S) as resp:  # 固定 https 域名
        xml = resp.read()
    root = ET.fromstring(xml)
    entry = root.find("a:entry", _ATOM_NS)
    if entry is None:
        raise ValueError(f"arXiv 无返回条目：{aid}（id 是否正确？）")

    title = re.sub(r"\s+", " ", (entry.findtext("a:title", "", _ATOM_NS) or "")).strip()
    authors = [
        re.sub(r"\s+", " ", (e.findtext("a:name", "", _ATOM_NS) or "")).strip()
        for e in entry.findall("a:author", _ATOM_NS)
        if e.findtext("a:name", "", _ATOM_NS)
    ]
    summary = re.sub(r"\s+", " ", (entry.findtext("a:summary", "", _ATOM_NS) or "")).strip()
    published = entry.findtext("a:published", "", _ATOM_NS) or ""
    year = published[:4]
    doi = entry.findtext("{http://arxiv.org/schemas/atom}doi", "") or ""
    pdf = ""
    for link in entry.findall("a:link", _ATOM_NS):
        if link.get("title") == "pdf" or str(link.get("type") or "").endswith("pdf"):
            pdf = link.get("href") or ""
            break
    meta = {
        "entry_type": "article" if doi else "online",  # 有 DOI=已刊；否则预印本
        "authors": authors,
        "title": title,
        "venue": "arXiv:" + aid,
        "year": year,
        "doi": doi,
        "url": f"https://arxiv.org/abs/{aid}",
        "pdf_url": pdf,
    }
    return {"arxiv_id": aid, "meta": meta, "abstract": summary}


def import_arxiv_paper(store: LibraryStore, arxiv_id_or_url: str) -> dict[str, Any]:
    """arXiv 论文 → 库书（摘要章节 + cite_meta）。返回 book_id 供后续引用/检索。"""
    paper = fetch_arxiv(arxiv_id_or_url)
    meta = paper["meta"]
    # 书名取题名前 40 字（目录名安全化交给 store._safe_name）
    name = meta["title"][:40] or f"arXiv:{paper['arxiv_id']}"
    book = store.add_book(name or uuid.uuid4().hex[:8])
    bid = book["id"]
    # 摘要章节（md 文件，进入拆章/RAG 通道）
    chapter_md = (
        f"# 摘要\n\n{paper['abstract']}\n\n"
        f"## 元信息\n\n- arXiv: {paper['arxiv_id']}\n"
        f"- 作者：{', '.join(meta['authors'])}\n- 年份：{meta['year']}\n"
        f"- 链接：{meta['url']}\n\n"
        "> 全文 PDF 请经既有导入通道补入本书（V1 连接器只落摘要）。\n"
    )
    (store.root / bid / "00-摘要.md").write_text(chapter_md, encoding="utf-8")
    store.set_cite_meta(bid, meta)
    return {"book_id": bid, "name": name, "meta": meta, "abstract_len": len(paper["abstract"])}
