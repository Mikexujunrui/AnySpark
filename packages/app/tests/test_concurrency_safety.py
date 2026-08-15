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


def test_cancel_one_task_keeps_others_running() -> None:
    """S152k：任务级取消——取消任务 A 不影响并行任务 B（此前 stop 引擎级全局，停 A 停 B）。"""
    import json
    import tempfile
    import time

    from anyspark.workflow import NodeResult, WorkflowDef, WorkflowEngine, WorkflowStore

    db = Path(tempfile.mkdtemp()) / "wf.db"
    store = WorkflowStore(db)
    wf = WorkflowDef.from_dict(
        {
            "name": "慢循环",
            "nodes": [
                {
                    "id": "loop",
                    "kind": "loop",
                    "params": {"body": ["work"], "max_iterations": 200, "collection_var": "items"},
                },
                {"id": "work", "kind": "script", "params": {"function": "noop"}},
            ],
            "edges": [],
        }
    )

    # runner：模拟耗时工作（每次迭代 sleep，让取消有机会触发）
    from typing import Any as _Any

    calls: dict[str, int] = {}

    def slow_runner(ctx: _Any, node: _Any) -> NodeResult:
        calls[node.id] = calls.get(node.id, 0) + 1
        time.sleep(0.02)
        return NodeResult(output="x")

    engine = WorkflowEngine(store, slow_runner)
    ta = store.create_task(wf, book_id="main", params={"items": json.dumps([1] * 100)})
    tb = store.create_task(wf, book_id="main", params={"items": json.dumps([1] * 100)})

    def run(tid: str) -> None:
        import contextlib

        with contextlib.suppress(Exception):
            engine.run_task(tid)

    import threading as _th

    a = _th.Thread(target=run, args=(ta,), daemon=True)
    b = _th.Thread(target=run, args=(tb,), daemon=True)
    a.start()
    b.start()
    time.sleep(0.15)  # 两任务都在跑
    engine.request_stop(ta)  # 只取消 A
    a.join(timeout=5)
    # A 应被取消
    status_a = store.get_task(ta)
    assert status_a is not None and status_a["status"] == "cancelled", status_a
    # B 不受影响，继续跑到 done
    b.join(timeout=15)
    status_b = store.get_task(tb)
    assert status_b is not None and status_b["status"] == "done", status_b
