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


# ---------------------------------------------------------------------------
# S244：全局书库混合检索（关键词 + 语义向量）
# ---------------------------------------------------------------------------


def search_library_keyword(
    store: LibraryStore,
    keyword: str,
    max_per_book: int = 3,
) -> list[dict[str, Any]]:
    """全书库关键词检索（不限于项目已选参考书）。返回 [{book_id, book_name, snippet, count}]。"""
    keyword = (keyword or "").strip()
    if not keyword:
        return []
    out: list[dict[str, Any]] = []
    for b in store.list_books():
        text = store.read_book(b["id"], max_chars=300000)
        if not text.strip():
            continue
        for h in _hit_lines(text, keyword, max_hits=max_per_book):
            out.append(
                {
                    "book_id": b["id"],
                    "book_name": b["name"],
                    "snippet": h["snippet"],
                    "count": h["count"],
                }
            )
    return out


def search_library_hybrid(
    store: LibraryStore,
    vectors: Any | None,
    embedder: Any | None,
    query: str,
    top_k: int = 8,
    max_keyword_per_book: int = 3,
) -> dict[str, Any]:
    """全局书库混合检索：语义（向量余弦）+ 关键词（包含匹配）双通道。

    - embedder 不可用（未配 key）→ 语义通道降级跳过（degraded=True），
      只返回关键词通道——RAG 是增强层，绝不阻塞检索
    - 双通道各自排序返回（source 标记），前端分组展示；
      语义命中天然带相似度分，关键词命中带命中次数
    """
    query = (query or "").strip()
    if not query:
        return {"query": "", "semantic": [], "keyword": [], "degraded": False, "indexed_chunks": 0}

    # 语义通道
    semantic: list[dict[str, Any]] = []
    degraded = False
    indexed_chunks = 0
    if vectors is not None:
        st = vectors.stats()
        indexed_chunks = st.get("chunks", 0) or 0
    if vectors is not None and embedder is not None and embedder.available and indexed_chunks > 0:
        try:
            qvec = embedder.embed([query])[0]
            for h in vectors.search(qvec, top_k=top_k):
                book = store.get_book(h["book_id"])
                semantic.append(
                    {
                        "book_id": h["book_id"],
                        "book_name": book["name"] if book else h["book_id"],
                        "filename": h["filename"],
                        "snippet": h["text"][:400],
                        "score": h["score"],
                    }
                )
        except Exception as exc:  # embedding 服务故障时降级关键词，不阻塞检索
            degraded = True
            import logging

            logging.getLogger("anyspark.library").warning(
                "书库语义检索降级（embedding 失败）: %s", exc
            )
    else:
        degraded = embedder is None or not embedder.available

    # 关键词通道
    keyword_hits = search_library_keyword(store, query, max_per_book=max_keyword_per_book)

    return {
        "query": query,
        "semantic": semantic,
        "keyword": keyword_hits,
        "degraded": degraded,
        "indexed_chunks": indexed_chunks,
    }
