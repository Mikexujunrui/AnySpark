"""
anyspark.library.search — 参考书检索（S86）。

只搜当前项目已选的参考书（书库的书 + 工作区其他项目），关键词命中返回
书名/章节/上下文片段。复用 search_chapters 的词表/包含匹配技术，作用域不同。
"""

from __future__ import annotations

import re
from typing import Any

from .store import LibraryStore

MAX_SNIPPET_CHARS = 300  # 每段上下文片段长度


def _hit_lines(text: str, keyword: str, max_hits: int = 5) -> list[dict[str, Any]]:
    """在文本中找关键词命中的段落片段（按行/段落切，返回上下文）。"""
    kw = keyword.lower()
    blocks = re.split(r"\n\s*\n", text)  # 按空行分段
    hits: list[dict[str, Any]] = []
    for b in blocks:
        if kw in b.lower():
            snippet = b.strip()
            if len(snippet) > MAX_SNIPPET_CHARS:
                idx = snippet.lower().find(kw)
                start = max(0, idx - 100)
                snippet = (
                    ("…" if start > 0 else "") + snippet[start : start + MAX_SNIPPET_CHARS] + "…"
                )
            hits.append({"count": b.lower().count(kw), "snippet": snippet})
            if len(hits) >= max_hits:
                break
    return hits


def search_reference_books(
    store: LibraryStore,
    project_book_id: str,
    keyword: str,
    project_files: Any | None = None,
    max_per_book: int = 3,
) -> dict[str, Any]:
    """检索项目已选参考书（book_id 关联）。

    project_files：可选回调（project 类型参考书按项目 book_id 读章节文件），
    缺省只检索书库的书。返回：{total_hits, results: [{ref_name, type, hits: [...]}]}
    """
    keyword = (keyword or "").strip()
    if not keyword:
        return {"total_hits": 0, "results": []}
    refs = store.get_references(project_book_id)
    results: list[dict[str, Any]] = []
    total = 0
    for ref in refs:
        if ref["type"] == "library":
            text = store.read_book(ref["id"], max_chars=300000)
            name = ref["name"]
        else:  # project：工作区其他项目
            if project_files is None:
                continue
            text = project_files(ref["id"])
            name = f"项目「{ref['id']}」"
        if not text.strip():
            continue
        hits = _hit_lines(text, keyword, max_hits=max_per_book)
        if hits:
            total += len(hits)
            results.append({"ref_name": name, "type": ref["type"], "hits": hits})
    return {"total_hits": total, "results": results}
