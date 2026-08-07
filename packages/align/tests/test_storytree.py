"""S59 叙事树测试：分叉路径 + 锚点 + 线升级（探索可能性→线）。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from anyspark.align import StoryThreadStore, StoryTreeStore


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "tree.db"


def test_node_add_and_choose() -> None:
    """叙事树：加节点 + 选择主线（chosen 链）。"""
    s = StoryTreeStore(_db())
    try:
        root = s.add_node("怀表初见", kind="root")
        n2 = s.add_node("雾中楼", parent_id=root.id)
        n3 = s.add_node("石墙刻字", parent_id=n2.id)
        # 选为主线
        s.choose(n3.id)
        s.choose(n2.id)
        path = s.current_path("main")
        assert len(path) == 1  # 同级候选 chosen 互斥，最后选的生效
        assert path[0].id == n2.id
        assert path[0].kind == "main"
    finally:
        s.close()


def test_anchor_mark() -> None:
    """锚点标记：必经节点。"""
    s = StoryTreeStore(_db())
    try:
        root = s.add_node("起点", kind="root")
        anc = s.add_node("白泽登场", parent_id=root.id)
        s.mark_anchor(anc.id)
        assert s.get(anc.id) is not None
        assert s.get(anc.id).kind == "anchor"  # type: ignore[union-attr]
        tree = s.render_tree("main")
        assert "必经锚点" in tree and "白泽登场" in tree
    finally:
        s.close()


def test_thread_lifecycle() -> None:
    """线升级：加线 → 更新进度 → 完成。"""
    t = StoryThreadStore(_db())
    try:
        th = t.add("白泽线", content="白泽调查守夜人", role="subplot")
        assert th.status == "active"
        t.update_progress(th.id, "白泽查到旧档案")
        got = t.get(th.id)
        assert got is not None and got.progress == "白泽查到旧档案"
        t.mark_done(th.id)
        assert t.get(th.id).status == "done"  # type: ignore[union-attr]
        # render 只含 active
        t2 = t.add("主线", role="main", progress="陈渡在石墙")
        block = t.render_threads("main")
        assert "白泽" not in block and "陈渡在石墙" in block
    finally:
        t.close()


def test_render_tree_shows_candidates_and_threads() -> None:
    """注入渲染：主线 + 锚点 + 探索可能性 + 支线。"""
    s = StoryTreeStore(_db())
    t = StoryThreadStore(_db())
    try:
        root = s.add_node("怀表初见", kind="root")
        main = s.add_node("雾中楼", parent_id=root.id, kind="candidate")
        s.choose(main.id)
        cand = s.add_node("石墙背后是密道", parent_id=main.id, kind="candidate")
        anc = s.add_node("白泽登场", parent_id=main.id, kind="candidate")
        s.mark_anchor(anc.id)
        t.add("白泽线", role="subplot", progress="查到旧档案")
        block = s.render_tree("main")
        assert "主线" in block and "雾中楼" in block
        assert "探索可能性" in block and "密道" in block
        assert "必经锚点" in block and "白泽登场" in block
        # 支线在 thread 块
        thread_block = t.render_threads("main")
        assert "支线" in thread_block and "白泽线" in thread_block
    finally:
        s.close()
        t.close()
