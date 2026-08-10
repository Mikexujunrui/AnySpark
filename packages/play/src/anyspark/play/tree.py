"""
anyspark.play.tree — 互动推演树存储（SQLite）。

设计（DESIGN §12.27）：
- play_sessions：一次推演会话（扮演角色/切入场景/状态/当前节点）。
- play_nodes：推演节点（scene 场景描述 + chosen_label 该节点由哪条选择产生）。
- play_options：节点下的候选行动（label + is_custom 自定义位 + chosen +
  child_node_id 选择后生成的子节点）。

树形：node.parent_id 构成树；选择 option 后生成 child node，option.child_node_id
指向它。回溯分叉 = 把 current_node_id 指回历史节点并挂新一批 options（原选项保留）。

哲学：机制（表结构/树操作/回溯）硬编码；内容（scene/选项文本）自然语言。
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS play_sessions (
    id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL DEFAULT 'main',
    title TEXT DEFAULT '',
    role TEXT NOT NULL,
    seed TEXT NOT NULL,
    status TEXT NOT NULL,            -- running | ended
    max_depth INTEGER NOT NULL DEFAULT 20,
    current_node_id TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS play_nodes (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    parent_id TEXT DEFAULT '',        -- 根节点为空
    depth INTEGER NOT NULL DEFAULT 0,
    scene TEXT NOT NULL,
    chosen_label TEXT DEFAULT '',     -- 本节点由哪条选择产生（根为空）
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS play_options (
    id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    label TEXT NOT NULL,
    is_custom INTEGER NOT NULL DEFAULT 0,
    chosen INTEGER NOT NULL DEFAULT 0,
    child_node_id TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_nodes_session ON play_nodes (session_id);
CREATE INDEX IF NOT EXISTS idx_options_node ON play_options (node_id);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _gen(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class PlayStore:
    """互动推演树存储（单连接 + 锁，与项目其他 store 同模式）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # ------------------------------------------------------------------
    # 会话
    # ------------------------------------------------------------------
    def create_session(
        self,
        *,
        role: str,
        seed: str,
        book_id: str = "main",
        title: str = "",
        max_depth: int = 20,
    ) -> dict[str, Any]:
        sid = _gen("play")
        now = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO play_sessions"
                " (id, book_id, title, role, seed, status, max_depth, current_node_id,"
                "  created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, 'running', ?, '', ?, ?)",
                (sid, book_id, title, role, seed, max_depth, now, now),
            )
            self._conn.commit()
        return self.get_session(sid)  # type: ignore[return-value]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM play_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, book_id, title, role, status, max_depth, current_node_id,"
                " created_at, updated_at FROM play_sessions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def end_session(self, session_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE play_sessions SET status = 'ended', updated_at = ? WHERE id = ?",
                (_now(), session_id),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def set_current(self, session_id: str, node_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE play_sessions SET current_node_id = ?, updated_at = ? WHERE id = ?",
                (node_id, _now(), session_id),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # 节点 + 选项
    # ------------------------------------------------------------------
    def add_node(
        self,
        *,
        session_id: str,
        parent_id: str,
        depth: int,
        scene: str,
        chosen_label: str = "",
    ) -> str:
        nid = _gen("node")
        with self._lock:
            self._conn.execute(
                "INSERT INTO play_nodes"
                " (id, session_id, parent_id, depth, scene, chosen_label, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (nid, session_id, parent_id, depth, scene, chosen_label, _now()),
            )
            self._conn.commit()
        return nid

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM play_nodes WHERE id = ?", (node_id,)).fetchone()
        return dict(row) if row is not None else None

    def add_options(self, node_id: str, labels: list[str]) -> list[dict[str, Any]]:
        """为节点挂一批候选行动（全部未选择）。"""
        opts: list[dict[str, Any]] = []
        now = _now()
        with self._lock:
            for label in labels:
                oid = _gen("opt")
                self._conn.execute(
                    "INSERT INTO play_options"
                    " (id, node_id, label, is_custom, chosen, child_node_id, created_at)"
                    " VALUES (?, ?, ?, 0, 0, '', ?)",
                    (oid, node_id, label, now),
                )
                opts.append(self._option_dict(oid))
            self._conn.commit()
        return opts

    def options_of(self, node_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM play_options WHERE node_id = ? ORDER BY created_at, rowid",
                (node_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_option(self, option_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM play_options WHERE id = ?", (option_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def choose_option(self, option_id: str, child_node_id: str) -> None:
        """标记选项被选中并连到生成的子节点（自定义位也走这里落库）。"""
        with self._lock:
            self._conn.execute(
                "UPDATE play_options SET chosen = 1, child_node_id = ?, created_at = ?"
                " WHERE id = ?",
                (child_node_id, _now(), option_id),
            )
            self._conn.commit()

    def add_custom_option(self, node_id: str, label: str, child_node_id: str) -> dict[str, Any]:
        """用户自定义行动：落库为一条 is_custom=1 且已选中的选项。"""
        oid = _gen("opt")
        with self._lock:
            self._conn.execute(
                "INSERT INTO play_options"
                " (id, node_id, label, is_custom, chosen, child_node_id, created_at)"
                " VALUES (?, ?, ?, 1, 1, ?, ?)",
                (oid, node_id, label, child_node_id, _now()),
            )
            self._conn.commit()
        return self._option_dict(oid)

    # ------------------------------------------------------------------
    # 树查询（路径）
    # ------------------------------------------------------------------
    def path_to(self, node_id: str) -> list[dict[str, Any]]:
        """从根到指定节点的路径（node + 该节点产生它的选择 label）。"""
        path: list[dict[str, Any]] = []
        seen: set[str] = set()
        cur = self.get_node(node_id)
        while cur is not None and cur["id"] not in seen:
            seen.add(cur["id"])
            entry: dict[str, Any] = {
                "node": cur,
                "chosen_label": cur["chosen_label"] or "",
            }
            path.append(entry)
            pid = cur["parent_id"]
            cur = self.get_node(pid) if pid else None
        path.reverse()
        return path

    def session_tree(self, session_id: str) -> dict[str, Any]:
        """会话完整树：nodes + options（供前端渲染/回溯浏览）。"""
        with self._lock:
            nodes = self._conn.execute(
                "SELECT * FROM play_nodes WHERE session_id = ? ORDER BY created_at, rowid",
                (session_id,),
            ).fetchall()
            node_ids = [n["id"] for n in nodes]
            opts: list[dict[str, Any]] = []
            if node_ids:
                marks = ",".join("?" * len(node_ids))
                opts_rows = self._conn.execute(
                    f"SELECT * FROM play_options WHERE node_id IN ({marks})"
                    " ORDER BY created_at, rowid",
                    node_ids,
                ).fetchall()
                opts = [dict(r) for r in opts_rows]
        return {"nodes": [dict(n) for n in nodes], "options": opts}

    def _option_dict(self, option_id: str) -> dict[str, Any]:
        row = self._conn.execute("SELECT * FROM play_options WHERE id = ?", (option_id,)).fetchone()
        return dict(row) if row is not None else {"id": option_id}
