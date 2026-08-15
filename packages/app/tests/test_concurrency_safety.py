"""S152j：并发安全测试——章节序号原子分配 + 文件写锁。

覆盖：
- next_order：并发/顺序调用分配不重复序号（此前 max+1 非原子，并发撞序）
- 章节文件写：文件锁存在且 write/delete 正常（不破坏既有行为）
"""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path

from anyspark.store.sqlite import ChapterStore


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "t.db"


def test_next_order_atomic_sequential() -> None:
    """顺序分配：0,1,2 递增（跨 upsert 不重复）。"""
    store = ChapterStore(str(_db()))
    assert store.next_order("book-a") == 0
    store.upsert("book-a", "第一章", "内容", store.next_order("book-a"))
    store.upsert("book-a", "第二章", "内容", store.next_order("book-a"))
    store.upsert("book-a", "第三章", "内容", store.next_order("book-a"))
    orders = [c.order_index for c in store.list_by_book("book-a")]
    assert orders == [0, 1, 2], f"序号应递增不重复: {orders}"
    # 不同项目独立计数
    assert store.next_order("book-b") == 0


def test_next_order_concurrent_threads() -> None:
    """并发分配：N 线程取号后立即落库，最终序号全部唯一（锁内 MAX+1 原子性）。"""
    store = ChapterStore(str(_db()))

    def worker(i: int) -> None:
        o = store.next_order("book-a")
        store.upsert("book-a", f"章{i}", "内容", o)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    orders = [c.order_index for c in store.list_by_book("book-a")]
    assert len(orders) == 12
    assert len(set(orders)) == 12, f"并发分配应唯一: {sorted(orders)}"
    assert sorted(orders) == list(range(12))


def test_workspace_file_lock_present() -> None:
    """S152j：Workspace 文件锁存在且写/删章节正常。"""
    from anyspark.server.workspace import Workspace

    ws = Workspace(root=Path(tempfile.mkdtemp()) / "ws")
    assert hasattr(ws, "_file_lock"), "Workspace 应持有文件写锁"
    # 写 → 读 → 删（锁不破坏既有行为）
    f = ws.write_chapter("main", 0, "第一章", "正文")
    assert f.read_text(encoding="utf-8") == "正文"
    assert ws.delete_chapter_file("main", 0, "第一章") is True
    assert not f.exists()
