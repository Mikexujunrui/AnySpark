"""
anyspark.workflow.store — 工作流存储（SQLite，模板与执行任务分离）。

设计（DESIGN §12.22）：
- workflow_templates：定义模板（与书解耦，可迁移）。definition JSON 整存。
- workflow_drafts：AI 生成的候选草稿（未生效，人工确认 promote 转正）。
- workflow_tasks：运行任务（冻结定义快照 + 绑定 book_id + 状态）。
- workflow_node_states：任务内每节点执行状态（断点恢复的依据）。

哲学：机制（表结构/状态机/事务）硬编码；内容（指令/条件）自然语言 JSON。
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anyspark.core.db import connect as sqlite_connect

from .definition import (
    NodeStatus,
    TaskStatus,
    WorkflowDef,
    WorkflowNode,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS workflow_templates (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    definition TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflow_drafts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    definition TEXT NOT NULL,
    hint TEXT DEFAULT '',
    status TEXT DEFAULT 'draft',   -- draft | promoted | rejected
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflow_tasks (
    id TEXT PRIMARY KEY,
    template_id TEXT,
    name TEXT NOT NULL,
    book_id TEXT NOT NULL,
    definition TEXT NOT NULL,      -- 冻结快照
    status TEXT NOT NULL,          -- queued|running|waiting_approval|done|failed|cancelled
    current_node_id TEXT DEFAULT '',
    results TEXT DEFAULT '{}',     -- 输出变量表 {var: value}
    error TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS workflow_node_states (
    task_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    status TEXT NOT NULL,          -- pending|running|done|failed|skipped
    attempts INTEGER DEFAULT 0,
    output TEXT DEFAULT '',
    error TEXT DEFAULT '',
    token_usage INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (task_id, node_id)
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _gen(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


class WorkflowStore:
    """工作流存储（单连接 + 锁，与项目其他 store 同模式）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        # S79：连接配置收敛到 anyspark.core.db.connect
        self._conn = sqlite_connect(self._db)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # ------------------------------------------------------------------
    # 模板 CRUD
    # ------------------------------------------------------------------
    def add_template(self, definition: WorkflowDef) -> WorkflowDef:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO workflow_templates"
                " (id, name, description, definition, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    definition.id,
                    definition.name,
                    definition.description,
                    json.dumps(definition.to_dict(), ensure_ascii=False),
                    definition.created_at,
                ),
            )
            self._conn.commit()
        return definition

    def list_templates(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, name, description, created_at FROM workflow_templates"
                " ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_template(self, template_id: str) -> WorkflowDef | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT definition FROM workflow_templates WHERE id = ?", (template_id,)
            ).fetchone()
        if row is None:
            return None
        return WorkflowDef.from_dict(json.loads(row["definition"]))

    def delete_template(self, template_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM workflow_templates WHERE id = ?", (template_id,))
            self._conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # 草稿（AI 生成候选，人工确认闸门）
    # ------------------------------------------------------------------
    def add_draft(self, definition: WorkflowDef, hint: str = "") -> WorkflowDef:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO workflow_drafts"
                " (id, name, description, definition, hint, status, created_at)"
                " VALUES (?, ?, ?, ?, ?, 'draft', ?)",
                (
                    definition.id,
                    definition.name,
                    definition.description,
                    json.dumps(definition.to_dict(), ensure_ascii=False),
                    hint,
                    definition.created_at,
                ),
            )
            self._conn.commit()
        return definition

    def list_drafts(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, name, description, hint, status, created_at"
                " FROM workflow_drafts ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_draft(self, draft_id: str) -> WorkflowDef | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT definition FROM workflow_drafts WHERE id = ?", (draft_id,)
            ).fetchone()
        if row is None:
            return None
        return WorkflowDef.from_dict(json.loads(row["definition"]))

    def promote_draft(self, draft_id: str) -> WorkflowDef | None:
        """草稿转正为模板（skill_drafts 同款闸门：人工确认才生效）。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT definition FROM workflow_drafts WHERE id = ?", (draft_id,)
            ).fetchone()
            if row is None:
                return None
            definition = WorkflowDef.from_dict(json.loads(row["definition"]))
            self._conn.execute(
                "INSERT OR REPLACE INTO workflow_templates"
                " (id, name, description, definition, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    definition.id,
                    definition.name,
                    definition.description,
                    json.dumps(definition.to_dict(), ensure_ascii=False),
                    definition.created_at,
                ),
            )
            self._conn.execute(
                "UPDATE workflow_drafts SET status = 'promoted' WHERE id = ?",
                (draft_id,),
            )
            self._conn.commit()
        return definition

    def reject_draft(self, draft_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE workflow_drafts SET status = 'rejected' WHERE id = ?",
                (draft_id,),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def delete_draft(self, draft_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM workflow_drafts WHERE id = ?", (draft_id,))
            self._conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # 任务（定义快照冻结 + 节点状态 = 断点恢复基础）
    # ------------------------------------------------------------------
    def create_task(
        self,
        definition: WorkflowDef,
        *,
        book_id: str,
        template_id: str | None = None,
    ) -> str:
        task_id = _gen("task")
        now = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO workflow_tasks"
                " (id, template_id, name, book_id, definition, status, current_node_id,"
                "  results, error, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, 'queued', '', '{}', '', ?, ?)",
                (
                    task_id,
                    template_id,
                    definition.name,
                    book_id,
                    json.dumps(definition.to_dict(), ensure_ascii=False),
                    now,
                    now,
                ),
            )
            for n in definition.nodes:
                self._conn.execute(
                    "INSERT INTO workflow_node_states"
                    " (task_id, node_id, status, attempts, output, error, token_usage, updated_at)"
                    " VALUES (?, ?, 'pending', 0, '', '', 0, ?)",
                    (task_id, n.id, now),
                )
            self._conn.commit()
        return task_id

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM workflow_tasks WHERE id = ?", (task_id,)
            ).fetchone()
            if row is None:
                return None
            task = dict(row)
            states = self._conn.execute(
                "SELECT * FROM workflow_node_states WHERE task_id = ? ORDER BY node_id",
                (task_id,),
            ).fetchall()
        task["definition"] = WorkflowDef.from_dict(json.loads(task["definition"]))
        task["results"] = json.loads(task["results"])
        task["node_states"] = [dict(s) for s in states]
        return task

    def list_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, template_id, name, book_id, status, current_node_id,"
                " created_at, updated_at, error"
                " FROM workflow_tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        current_node_id: str = "",
        error: str = "",
    ) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE workflow_tasks SET status = ?, current_node_id = ?, error = ?,"
                " updated_at = ? WHERE id = ?",
                (status, current_node_id, error, _now(), task_id),
            )
            self._conn.commit()

    def update_node_state(
        self,
        task_id: str,
        node: WorkflowNode,
        status: NodeStatus,
        *,
        output: str = "",
        error: str = "",
        token_usage: int = 0,
        attempts: int | None = None,
    ) -> None:
        with self._lock:
            if attempts is None:
                attempts = self._node_attempts(task_id, node.id)
            self._conn.execute(
                "UPDATE workflow_node_states SET status = ?, output = ?, error = ?,"
                " token_usage = ?, attempts = ?, updated_at = ?"
                " WHERE task_id = ? AND node_id = ?",
                (status, output, error, token_usage, attempts, _now(), task_id, node.id),
            )
            self._conn.commit()

    def increment_attempts(self, task_id: str, node_id: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE workflow_node_states SET attempts = attempts + 1, updated_at = ?"
                " WHERE task_id = ? AND node_id = ?",
                (_now(), task_id, node_id),
            )
            self._conn.commit()
        return cur.rowcount

    def _node_attempts(self, task_id: str, node_id: str) -> int:
        row = self._conn.execute(
            "SELECT attempts FROM workflow_node_states WHERE task_id = ? AND node_id = ?",
            (task_id, node_id),
        ).fetchone()
        return int(row["attempts"]) if row else 0

    def append_result(self, task_id: str, key: str, value: Any) -> None:
        with self._lock:
            row = self._conn.execute(
                "SELECT results FROM workflow_tasks WHERE id = ?", (task_id,)
            ).fetchone()
            results: dict[str, Any] = {}
            if row is not None:
                results = json.loads(row["results"])
            results[key] = value
            self._conn.execute(
                "UPDATE workflow_tasks SET results = ?, updated_at = ? WHERE id = ?",
                (json.dumps(results, ensure_ascii=False), _now(), task_id),
            )
            self._conn.commit()

    def node_status(self, task_id: str, node_id: str) -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT status FROM workflow_node_states WHERE task_id = ? AND node_id = ?",
                (task_id, node_id),
            ).fetchone()
        return str(row["status"]) if row else "pending"

    def node_output(self, task_id: str, node_id: str) -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT output FROM workflow_node_states WHERE task_id = ? AND node_id = ?",
                (task_id, node_id),
            ).fetchone()
        return str(row["output"]) if row else ""
