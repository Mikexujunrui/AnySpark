"""
anyspark.server.tools_extensions — 扩展工具注册表（S48-P4/B：Agent 给自己加工具）。

主人设计：扩展工具 = 数据（SQLite 存储），**人工批准才生效**（不做全自动——
工具进 Agent 工具集后模型每轮可见，错误/幻觉代码会污染主链路；S32 实证）。
生命周期：draft（草稿，不生效）→ pending（待审）→ active（用户批准，注入工具集）。

机制：
- 工具定义：name/description/params(JSON)/code（Python 函数 `run(args: dict) -> str`）
- 执行：复用 codex 沙箱（白名单 + 只读数据环境 ws_* + 超时）——**双保险**：
  即使批准，扩展工具执行仍在沙箱，不接触文件系统原始能力
- 装配：_make_agent 每请求从 active 加载注入工具集——注册/批准后**无需重启**生效
- 用户主权：批准/禁用/删除随时可；用户是最终编辑者（DESIGN 校准仪式同类机制）
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anyspark.core.protocol import ParamSpec, ToolResult, ToolSpec
from anyspark.core.types import ToolCall

_STATUSES = ("draft", "pending", "active")
# 扩展工具默认超时（沙箱执行上限）
EXT_TIMEOUT = 20

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tools_extensions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    params_json TEXT NOT NULL DEFAULT '[]',
    code TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ExtensionTool:
    """一条扩展工具定义（工具=数据）。"""

    id: str
    name: str
    description: str
    params: list[dict[str, Any]] = field(default_factory=list)
    code: str = ""
    status: str = "draft"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "params": self.params,
            "code_preview": self.code[:200],
            "status": self.status,
            "created_at": self.created_at,
        }


class ExtensionToolStore:
    """扩展工具注册表（SQLite 单连接 + 锁，与既有 store 一致）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute(_SCHEMA)
            self._conn.commit()

    def _row(self, row: sqlite3.Row) -> ExtensionTool:
        return ExtensionTool(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            params=json.loads(row["params_json"] or "[]"),
            code=row["code"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def add(
        self, name: str, description: str, params: list[dict[str, Any]], code: str
    ) -> ExtensionTool:
        """登记扩展工具（status=draft，人工批准后生效）。"""
        tid = uuid.uuid4().hex[:12]
        now = _now()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO tools_extensions "
                "(id, name, description, params_json, code, status, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    tid,
                    name,
                    description,
                    json.dumps(params, ensure_ascii=False),
                    code,
                    "draft",
                    now,
                    now,
                ),
            )
            self._conn.commit()
        return ExtensionTool(
            id=tid, name=name, description=description, params=params, code=code, status="draft"
        )

    def list_all(self) -> list[ExtensionTool]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tools_extensions ORDER BY created_at"
            ).fetchall()
        return [self._row(r) for r in rows]

    def get(self, tool_id: str) -> ExtensionTool | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tools_extensions WHERE id=?", (tool_id,)
            ).fetchone()
        return self._row(row) if row else None

    def set_status(self, tool_id: str, status: str) -> ExtensionTool | None:
        if status not in _STATUSES:
            return None
        with self._lock:
            self._conn.execute(
                "UPDATE tools_extensions SET status=?, updated_at=? WHERE id=?",
                (status, _now(), tool_id),
            )
            self._conn.commit()
        return self.get(tool_id)

    def update(
        self,
        tool_id: str,
        name: str | None = None,
        description: str | None = None,
        params: list[dict[str, Any]] | None = None,
        code: str | None = None,
    ) -> ExtensionTool | None:
        """更新扩展工具（S49：工具迭代日常路径）。

        安全：改内容后 **自动回 draft 重新人工批准**（改了就要再审）。
        """
        existing = self.get(tool_id)
        if existing is None:
            return None
        now = _now()
        new_name = name if name is not None else existing.name
        new_desc = description if description is not None else existing.description
        new_params = params if params is not None else existing.params
        new_code = code if code is not None else existing.code
        with self._lock:
            sql = (
                "UPDATE tools_extensions SET name=?, description=?, params_json=?, "
                "code=?, status='draft', updated_at=? WHERE id=?"
            )
            self._conn.execute(
                sql,
                (
                    new_name,
                    new_desc,
                    json.dumps(new_params, ensure_ascii=False),
                    new_code,
                    now,
                    tool_id,
                ),
            )
            self._conn.commit()
        return self.get(tool_id)

    def delete(self, tool_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM tools_extensions WHERE id=?", (tool_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def active_tools(self) -> list[ExtensionTool]:
        return [t for t in self.list_all() if t.status == "active"]


def tool_spec_from_ext(ext: ExtensionTool) -> ToolSpec:
    """扩展工具 → core ToolSpec（Agent 工具集装配用）。"""
    params = []
    for p in ext.params or []:
        params.append(
            ParamSpec(
                name=str(p.get("name", "")),
                type=str(p.get("type", "string")),
                required=bool(p.get("required", False)),
                description=str(p.get("description", "")),
            )
        )
    return ToolSpec(name=ext.name, description=ext.description, params=params)


def execute_extension(
    ext: ExtensionTool, arguments: dict[str, Any], data_env: dict[str, Any] | None = None
) -> ToolResult:
    """在沙箱执行扩展工具代码（双保险：批准后仍在受限环境）。

    代码契约：定义 `run(args: dict) -> str`，返回文本作为 ToolResult 内容。
    复用 codex 沙箱（白名单 + ws_* 数据环境 + 超时），stdout 兜底。
    """
    from anyspark.server.codex import run_code

    call = ToolCall(name=ext.name, arguments=arguments)
    # 包装：注入 args 调用 run()，返回字符串（print 兜底已输出）
    wrapped = (
        f"{ext.code}\n\n"
        f"__args = {json.dumps(arguments, ensure_ascii=False)}\n"
        f"__res = run(__args)\n"
        f"print(__res if isinstance(__res, str) else str(__res), end='')\n"
    )
    r = run_code(wrapped, timeout=EXT_TIMEOUT, data_env=data_env)
    if not r["ok"]:
        return ToolResult(call=call, ok=False, content=f"扩展工具执行失败：{r['error']}")
    out = (r["stdout"] or "").strip()
    if not out:
        return ToolResult(call=call, ok=True, content="（无输出）")
    return ToolResult(call=call, ok=True, content=out)
