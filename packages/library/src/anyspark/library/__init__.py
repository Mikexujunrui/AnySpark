"""anyspark.library — 参考书库扩展包（S86）。

参考书 = 只读检索源：全局书库（data/library/ 文件区）+ 项目可选若干参考书
（书库的书或工作区其他项目）。**不注入任何信息**，agent 按需检索
（reference_lookup 工具）——要借鉴时才翻书，不借鉴时书完全不干扰写作。

S244：书库 RAG——语义向量检索（embedding.py + vectors.py），
与关键词检索融合为混合检索（search_library_hybrid）。
"""

from __future__ import annotations

from .embedding import EmbeddingClient
from .search import search_library_hybrid, search_reference_books
from .store import LibraryStore
from .vectors import LibraryVectors, chunk_text, cosine

__all__ = [
    "EmbeddingClient",
    "LibraryStore",
    "LibraryVectors",
    "chunk_text",
    "cosine",
    "search_library_hybrid",
    "search_reference_books",
]
