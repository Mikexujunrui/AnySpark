"""anyspark.library — 参考书库扩展包（S86）。

参考书 = 只读检索源：全局书库（data/library/ 文件区）+ 项目可选若干参考书
（书库的书或工作区其他项目）。**不注入任何信息**，agent 按需检索
（reference_lookup 工具）——要借鉴时才翻书，不借鉴时书完全不干扰写作。
"""

from __future__ import annotations

from .search import search_reference_books
from .store import LibraryStore

__all__ = ["LibraryStore", "search_reference_books"]
