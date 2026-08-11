"""anyspark.align.storytree — 叙事树（分叉路径模型，S59）。

主人洞察（叙事 = 不断分叉的路径树）：
- 小说 = 一棵不断分叉的路径树：节点 = 叙事状态，边 = 分叉
- 探索 = 树的生长器（每次探索在节点上长出 N 个候选分支）
- 锚点 = 用户标记"必经"的叙事节点（不管走哪条路都要到达）
- 主线 = 被选中走过的路径（chosen 链）；
- **探索可能性** = 未选的分叉（理论上可能走但没走的路——探索留痕，可回看）
- **支线** = 不如主线健壮、但确实在走/已完成的线路（感情线/复仇线——真实发生的次要故事线）
- 多线 = 并行主线；时间循环 = 节点回边标记（闭环）

极简设计（哲学：机制硬编码、内容自然语言；不做图算法——路径搜索/循环检测
是工程思维，写作是生长思维。叙事结构是内容，标记和选择足够，不计算）：
- 一张表，自然语言节点，chosen 标记主线轨迹，kind 标锚点/探索可能性/支线/循环
- 无图算法、无自动干预——判断权永远在人/AI

注入形态（树的导航，极小）：
  主线路径：... → 【当前】→ [锚点]...
  探索可能性（未选）：...
  支线（进行中）：...
"""

from __future__ import annotations

import contextlib
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

# 节点类型（机制硬编码；内容自然语言）
# root=根 / main=主线节点(chosen) / anchor=必经锚点 / candidate=探索可能性(未选分叉)
# subplot=支线(确实在走的次要线路) / loop=时间循环回边标记
NodeKind = Literal["root", "main", "anchor", "candidate", "subplot", "loop"]


@dataclass
class StoryNode:
    """叙事树的一个节点（叙事状态）。"""

    content: str  # 叙事状态（自然语言，如"陈渡在江心楼发现石墙刻字"）
    book_id: str = "main"
    parent_id: str | None = None  # 从哪个节点分叉来（根= None）
    kind: NodeKind = "candidate"  # 节点角色（默认=探索可能性，升级后为线）
    chosen: bool = False  # 被选中走过（主线轨迹 = chosen 链）
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=lambda: _now())
    # S76 画布布局（DESIGN §12.37）：手动调整坐标；None=未调整用自动布局
    pos_x: float | None = None
    pos_y: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "book_id": self.book_id,
            "content": self.content,
            "parent_id": self.parent_id,
            "kind": self.kind,
            "chosen": self.chosen,
            "created_at": self.created_at,
            "pos": (
                {"x": self.pos_x, "y": self.pos_y}
                if self.pos_x is not None and self.pos_y is not None
                else None
            ),
        }


def _now() -> str:
    return datetime.now(UTC).isoformat()


class StoryTreeStore:
    """叙事树存储（SQLite）：分叉路径 + 锚点标记 + 主线轨迹。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db, check_same_thread=False, timeout=30)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS story_nodes (
                id TEXT PRIMARY KEY,
                book_id TEXT NOT NULL,
                content TEXT NOT NULL,
                parent_id TEXT,
                kind TEXT NOT NULL DEFAULT 'candidate',
                chosen INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                pos_x REAL,
                pos_y REAL
            );
            CREATE INDEX IF NOT EXISTS idx_story_nodes_book ON story_nodes(book_id);
            """
        )
        # S76 画布布局：补列（幂等，兼容旧库）
        for col in ("pos_x", "pos_y"):
            with contextlib.suppress(sqlite3.OperationalError):
                self._conn.execute(f"ALTER TABLE story_nodes ADD COLUMN {col} REAL")
        self._conn.commit()

    # ------------------------------------------------------------------
    # 节点操作
    # ------------------------------------------------------------------
    def add_node(
        self,
        content: str,
        book_id: str = "main",
        parent_id: str | None = None,
        kind: NodeKind = "candidate",
        chosen: bool = False,
    ) -> StoryNode:
        node = StoryNode(
            content=content.strip(),
            book_id=book_id,
            parent_id=parent_id,
            kind=kind,
            chosen=chosen,
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO story_nodes (id, book_id, content, parent_id, kind, chosen, "
                "created_at, pos_x, pos_y) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    node.id,
                    node.book_id,
                    node.content,
                    node.parent_id,
                    node.kind,
                    1 if node.chosen else 0,
                    node.created_at,
                    node.pos_x,
                    node.pos_y,
                ),
            )
            self._conn.commit()
        return node

    def get(self, node_id: str) -> StoryNode | None:
        row = self._conn.execute("SELECT * FROM story_nodes WHERE id=?", (node_id,)).fetchone()
        return _node_from_row(row) if row else None

    def list_nodes(self, book_id: str = "main") -> list[StoryNode]:
        rows = self._conn.execute(
            "SELECT * FROM story_nodes WHERE book_id=? ORDER BY created_at, rowid",
            (book_id,),
        ).fetchall()
        return [_node_from_row(r) for r in rows]

    def choose(self, node_id: str) -> StoryNode | None:
        """选择一条路径作为主线：标记 chosen（主线轨迹）。

        主线唯一（chosen 链）：选择时清除其他所有 chosen（主线切换时旧轨迹
        让位——当前主线 = 最新选择的路径）；支线(subplot)/锚点(anchor)不受影响。
        """
        node = self.get(node_id)
        if node is None:
            return None
        with self._lock:
            # 清除其他 chosen（主线唯一，切换即让位）
            self._conn.execute(
                "UPDATE story_nodes SET chosen=0 WHERE book_id=? AND id<>?",
                (node.book_id, node_id),
            )
            self._conn.execute(
                "UPDATE story_nodes SET chosen=1, kind='main' WHERE id=?", (node_id,)
            )
            self._conn.commit()
        return self.get(node_id)

    def mark_anchor(self, node_id: str) -> StoryNode | None:
        """把节点标记为必经锚点（不管走哪条路都要到达）。"""
        node = self.get(node_id)
        if node is None:
            return None
        with self._lock:
            self._conn.execute("UPDATE story_nodes SET kind='anchor' WHERE id=?", (node_id,))
            self._conn.commit()
        return self.get(node_id)

    def delete_node(self, node_id: str) -> bool:
        """删除节点及其所有后代节点（递归）。"""
        node = self.get(node_id)
        if node is None:
            return False
        with self._lock:
            # 递归删除所有后代节点
            self._delete_descendants(node_id)
            # 删除节点本身
            self._conn.execute("DELETE FROM story_nodes WHERE id=?", (node_id,))
            self._conn.commit()
        return True

    def _delete_descendants(self, parent_id: str) -> None:
        """递归删除指定节点的所有后代（内部方法，需在锁内调用）。"""
        children = self._conn.execute(
            "SELECT id FROM story_nodes WHERE parent_id=?", (parent_id,)
        ).fetchall()
        for child in children:
            self._delete_descendants(child["id"])
            self._conn.execute("DELETE FROM story_nodes WHERE id=?", (child["id"],))

    # ------------------------------------------------------------------
    # 树视图（注入用）
    # ------------------------------------------------------------------
    def current_path(self, book_id: str = "main") -> list[StoryNode]:
        """主线轨迹（chosen 链，按创建顺序）。"""
        return [n for n in self.list_nodes(book_id) if n.chosen]

    def render_tree(self, book_id: str = "main") -> str:
        """渲染叙事树导航块（注入用，极小）：主线 + 锚点 + 探索可能性 + 支线。

        概念（主人纠偏）：
        - 探索可能性 = 未选的分叉（理论上可能走但没走的路，探索留痕）
        - 支线 = 不如主线健壮、但确实在走的线路（真实发生的次要故事线）
        """
        nodes = self.list_nodes(book_id)
        if not nodes:
            return ""
        main = [n for n in nodes if n.chosen]  # 主线轨迹
        anchors = [n for n in nodes if n.kind == "anchor" and not n.chosen]  # 未达锚点
        candidates = [
            n for n in nodes if n.kind == "candidate" and not n.chosen
        ]  # 探索可能性（未选）
        subplots = [n for n in nodes if n.kind == "subplot"]  # 支线（确实在走）
        lines = ["# 叙事树"]
        if main:
            path = []
            for n in main:
                label = n.content[:30]
                path.append(f"[锚点]{label}" if n.kind == "anchor" else label)
            lines.append("主线：" + " → ".join(path[:6]))
        if anchors:
            # 锚点 = 目的地，需完整信息（不截断到30字，否则AI不知道要去哪）
            lines.append("必经锚点（未达，按顺序）：")
            for a in anchors[:3]:
                lines.append(f"  → {a.content}")
        if candidates:
            lines.append("探索可能性（未选）：" + "；".join(c.content[:30] for c in candidates[:5]))
        if subplots:
            lines.append("支线（进行中）：" + "；".join(s.content[:30] for s in subplots[:5]))
        return "\n".join(lines)

    def set_positions(self, book_id: str, positions: list[tuple[str, float, float]]) -> int:
        """S76：批量保存节点手动坐标（DESIGN §12.37：只存用户调整过的）。

        返回更新行数；不存在的节点/其他 book 自动跳过。
        """
        if not positions:
            return 0
        updated = 0
        with self._lock:
            for node_id, x, y in positions:
                cur = self._conn.execute(
                    "UPDATE story_nodes SET pos_x=?, pos_y=? WHERE id=? AND book_id=?",
                    (x, y, node_id, book_id),
                )
                updated += cur.rowcount
            self._conn.commit()
        return updated

    def close(self) -> None:
        self._conn.close()


def _node_from_row(row: sqlite3.Row) -> StoryNode:
    return StoryNode(
        id=row["id"],
        book_id=row["book_id"],
        content=row["content"],
        parent_id=row["parent_id"],
        kind=row["kind"],
        chosen=bool(row["chosen"]),
        created_at=row["created_at"],
        pos_x=row["pos_x"],
        pos_y=row["pos_y"],
    )


# ---------------------------------------------------------------------------
# 线进度（StoryThread）：线的生命周期——探索可能性 → 被推进 → 升级为线
# ---------------------------------------------------------------------------


@dataclass
class StoryThread:
    """一条叙事线（主线/支线/多线之一）：线名 + 当前进度（映射锚）。

    概念（主人讨论）：线默认不预定义，而是在探索/写作中被发现可以成为线时
    升级（涌现）；用户也可随时手动声明（预定义是升级的快捷方式）。
    线进度 = 自然语言一句话，随写作更新（不怕章数漂移——"白泽查到旧档案"
    永远准确，不管在第几章）。
    """

    name: str  # 线名（如"白泽线""复仇线"）
    book_id: str = "main"
    content: str = ""  # 线的一句话描述（这条线是什么）
    progress: str = ""  # 当前进度（自然语言，映射锚）
    role: str = "main"  # main主线 / subplot支线 / parallel多线
    node_id: str | None = None  # 关联的叙事树节点（可空）
    status: str = "active"  # active / done
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=lambda: _now())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "book_id": self.book_id,
            "content": self.content,
            "progress": self.progress,
            "role": self.role,
            "node_id": self.node_id,
            "status": self.status,
            "created_at": self.created_at,
        }


class StoryThreadStore:
    """线进度存储（SQLite）：线的身份 + 当前进度（映射锚）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db, check_same_thread=False, timeout=30)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS story_threads (
                id TEXT PRIMARY KEY,
                book_id TEXT NOT NULL,
                name TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                progress TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'main',
                node_id TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def add(
        self,
        name: str,
        book_id: str = "main",
        content: str = "",
        progress: str = "",
        role: str = "main",
        node_id: str | None = None,
    ) -> StoryThread:
        t = StoryThread(
            name=name.strip(),
            book_id=book_id,
            content=content.strip(),
            progress=progress.strip(),
            role=role,
            node_id=node_id,
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO story_threads (id, book_id, name, content, progress, role, "
                "node_id, status, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    t.id,
                    t.book_id,
                    t.name,
                    t.content,
                    t.progress,
                    t.role,
                    t.node_id,
                    t.status,
                    t.created_at,
                ),
            )
            self._conn.commit()
        return t

    def list_threads(self, book_id: str = "main") -> list[StoryThread]:
        rows = self._conn.execute(
            "SELECT * FROM story_threads WHERE book_id=? ORDER BY created_at, rowid",
            (book_id,),
        ).fetchall()
        return [_thread_from_row(r) for r in rows]

    def get(self, thread_id: str) -> StoryThread | None:
        row = self._conn.execute("SELECT * FROM story_threads WHERE id=?", (thread_id,)).fetchone()
        return _thread_from_row(row) if row else None

    def update_progress(self, thread_id: str, progress: str) -> StoryThread | None:
        """更新线进度（映射锚，随写作推进）。"""
        with self._lock:
            self._conn.execute(
                "UPDATE story_threads SET progress=?, status='active' WHERE id=?",
                (progress.strip(), thread_id),
            )
            self._conn.commit()
        return self.get(thread_id)

    def mark_done(self, thread_id: str) -> StoryThread | None:
        with self._lock:
            self._conn.execute("UPDATE story_threads SET status='done' WHERE id=?", (thread_id,))
            self._conn.commit()
        return self.get(thread_id)

    def delete(self, thread_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM story_threads WHERE id=?", (thread_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def render_threads(self, book_id: str = "main") -> str:
        """渲染线进度块（注入用）：各线当前进度（映射锚）。"""
        threads = [t for t in self.list_threads(book_id) if t.status == "active"]
        if not threads:
            return ""
        lines = ["# 叙事线进度"]
        for t in threads:
            role = {"main": "主线", "subplot": "支线", "parallel": "多线"}.get(t.role, t.role)
            label = f"{role}「{t.name}」"
            if t.progress:
                lines.append(f"- {label}：{t.progress}")
            elif t.content:
                lines.append(f"- {label}：{t.content[:60]}")
        return "\n".join(lines)

    def close(self) -> None:
        self._conn.close()


def _thread_from_row(row: sqlite3.Row) -> StoryThread:
    return StoryThread(
        id=row["id"],
        name=row["name"],
        book_id=row["book_id"],
        content=row["content"],
        progress=row["progress"],
        role=row["role"],
        node_id=row["node_id"],
        status=row["status"],
        created_at=row["created_at"],
    )
