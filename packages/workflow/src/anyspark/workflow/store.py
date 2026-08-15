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
    created_at TEXT NOT NULL,
    builtin INTEGER NOT NULL DEFAULT 0
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
            # S152：旧库迁移 builtin 列（预置模板保护——系统模板不可删）
            cols = {r[1] for r in self._conn.execute("PRAGMA table_info(workflow_templates)")}
            if "builtin" not in cols:
                self._conn.execute(
                    "ALTER TABLE workflow_templates ADD COLUMN builtin INTEGER NOT NULL DEFAULT 0"
                )
            self._conn.commit()
        self._seed_templates()

    # ------------------------------------------------------------------
    # S121 种子模板（空表时播入：调研工作流——提案 B 首个真实模板）
    # ------------------------------------------------------------------
    def _seed_templates(self) -> None:
        """空表时播种内置模板（与书解耦、可迁移；用户可删/改）。"""
        with self._lock:
            n = self._conn.execute("SELECT COUNT(*) FROM workflow_templates").fetchone()[0]
            if n > 0:
                return
            research = WorkflowDef.from_dict(
                {
                    "name": "资料调研",
                    "description": (
                        "子 Agent 调研：网络搜索 + 参考书摘录 → 整理报告 → 落项目资料池"
                        "（fresh 上下文，不占主循环）"
                    ),
                    "nodes": [
                        {
                            "id": "n1",
                            "kind": "agent",
                            "label": "网络搜索",
                            "params": {
                                "instruction": (
                                    "围绕主题进行网络调研：用 search_web 搜索 3-5 次（关键词"
                                    "多角度），对重要结果用 fetch_page 抓取正文。输出："
                                    "来源清单（标题/URL/要点），每来源 2-4 条要点。"
                                ),
                                "delegate": {
                                    "scope": {"tools": ["search_web", "fetch_page"]},
                                    "budget": {"max_turns": 12},
                                },
                                "output_key": "web_research",
                            },
                        },
                        {
                            "id": "n2",
                            "kind": "agent",
                            "label": "参考书摘录",
                            "params": {
                                "instruction": (
                                    "从参考书库检索相关章节并摘录（reference_lookup "
                                    "或 library 相关工具）。输出：相关章节/设定摘录，"
                                    "无则输出（无参考书素材）。"
                                ),
                                "delegate": {
                                    "scope": {"tools": ["reference_lookup"]},
                                    "budget": {"max_turns": 8},
                                },
                                "output_key": "book_research",
                            },
                        },
                        {
                            "id": "n3",
                            "kind": "agent",
                            "label": "整理报告",
                            "params": {
                                "instruction": (
                                    "合并网络调研与参考书摘录，整理成结构化调研报告："
                                    "① 主题概述 ② 关键发现（分点）③ 可用素材（人物/设定/"
                                    "情节灵感）④ 来源与可信度标注。引用具体内容。"
                                ),
                                "output_key": "report",
                            },
                        },
                        {
                            "id": "n4",
                            "kind": "agent",
                            "label": "落资料池",
                            "params": {
                                "instruction": (
                                    "把调研报告写入项目资料池（material_register，"
                                    "kind=inspiration）。报告标题用主题。"
                                ),
                                "delegate": {
                                    "scope": {"tools": ["material_register"]},
                                    "budget": {"max_turns": 5},
                                },
                                "output_key": "saved",
                            },
                        },
                        {
                            "id": "n5",
                            "kind": "approval",
                            "label": "人工确认",
                            "params": {"prompt": "调研报告已生成，确认入库？"},
                        },
                    ],
                    "edges": [
                        {"source": "n1", "target": "n2"},
                        {"source": "n2", "target": "n3"},
                        {"source": "n3", "target": "n4"},
                        {"source": "n4", "target": "n5"},
                    ],
                }
            )
            if not research.validate():
                # 锁内直插（不调 add_template——同锁重入死锁）；内置模板标 builtin=1
                self._conn.execute(
                    "INSERT INTO workflow_templates"
                    " (id, name, description, definition, created_at, builtin)"
                    " VALUES (?, ?, ?, ?, ?, 1)",
                    (
                        research.id,
                        research.name,
                        research.description,
                        json.dumps(research.to_dict(), ensure_ascii=False),
                        research.created_at,
                    ),
                )
                self._conn.commit()

    # ------------------------------------------------------------------
    # 模板 CRUD
    # ------------------------------------------------------------------
    def add_template(self, definition: WorkflowDef, builtin: bool = False) -> WorkflowDef:
        """添加模板。builtin=True 为系统预置（不可删，S152 保护）。"""
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO workflow_templates"
                " (id, name, description, definition, created_at, builtin)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    definition.id,
                    definition.name,
                    definition.description,
                    json.dumps(definition.to_dict(), ensure_ascii=False),
                    definition.created_at,
                    1 if builtin else 0,
                ),
            )
            self._conn.commit()
        return definition

    def list_templates(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, name, description, created_at, builtin FROM workflow_templates"
                " ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def is_builtin(self, template_id: str) -> bool:
        """S152：预置模板判定（系统模板不可删）。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT builtin FROM workflow_templates WHERE id = ?", (template_id,)
            ).fetchone()
        return bool(row and row["builtin"])

    def mark_builtin_by_name(self, name: str) -> None:
        """S152：按名补标 builtin（旧库迁移——已存在的预置模板种子不再执行）。"""
        with self._lock:
            self._conn.execute(
                "UPDATE workflow_templates SET builtin = 1 WHERE name = ? AND builtin = 0",
                (name,),
            )
            self._conn.commit()

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
        params: dict[str, Any] | None = None,
    ) -> str:
        """创建任务：冻结定义快照 + 绑定书 + 初始变量（params 供 {{var}} 引用）。"""
        task_id = _gen("task")
        now = _now()
        initial_results = json.dumps(params or {}, ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                "INSERT INTO workflow_tasks"
                " (id, template_id, name, book_id, definition, status, current_node_id,"
                "  results, error, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, 'queued', '', ?, '', ?, ?)",
                (
                    task_id,
                    template_id,
                    definition.name,
                    book_id,
                    json.dumps(definition.to_dict(), ensure_ascii=False),
                    initial_results,
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
