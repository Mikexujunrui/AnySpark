"""S48-P5 代码扩展（anyspark-codex）：沙箱执行器 + API + agent 工具测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from anyspark.core.protocol import ToolSpec
from anyspark.core.types import Message, ModelOutput, ToolResult
from anyspark.server.app import build_app
from anyspark.server.codex import run_code
from anyspark.server.tools_domain import make_codex_implementer

# ---------------------------------------------------------------------------
# 沙箱执行器
# ---------------------------------------------------------------------------


def test_run_code_basic() -> None:
    r = run_code("print(1 + 2)")
    assert r["ok"] is True and r["stdout"].strip() == "3"


def test_run_code_modules_whitelist() -> None:
    r = run_code("import math\nprint(math.sqrt(16))")
    assert r["ok"] is True and "4.0" in r["stdout"]
    r2 = run_code("import json\nprint(json.dumps({'a': 1}))")
    assert r2["ok"] is True and '{"a": 1}' in r2["stdout"]


def test_run_code_blocks_dangerous() -> None:
    # 文件访问被拒
    r = run_code("open('x.txt', 'w')")
    assert r["ok"] is False
    # 任意 import 被拒
    r2 = run_code("import os")
    assert r2["ok"] is False and "禁止" in r2["error"]
    r3 = run_code("import socket")
    assert r3["ok"] is False
    # __import__ 逃逸被拒
    r4 = run_code("__import__('os').listdir('.')")
    assert r4["ok"] is False


def test_run_code_error_and_timeout() -> None:
    r = run_code("raise ValueError('boom')")
    assert r["ok"] is False and "boom" in r["error"]
    r2 = run_code("while True: pass", timeout=1)
    assert r2["ok"] is False and "超时" in r2["error"]


# ---------------------------------------------------------------------------
# agent 工具
# ---------------------------------------------------------------------------


def _call_tool(impl: Any, **kwargs: object) -> ToolResult:
    spec = ToolSpec(name="run_code", description="t", params=[])
    result = impl(spec, kwargs)
    assert isinstance(result, ToolResult)
    return result


def test_run_code_tool() -> None:
    from anyspark.graph import GraphStore
    from anyspark.server.workspace import Workspace
    from anyspark.store import ChapterStore

    db = Path(tempfile.mkdtemp()) / "t.db"
    _, impl = make_codex_implementer(
        Workspace(root=Path(tempfile.mkdtemp()) / "ws"),
        ChapterStore(db),
        GraphStore(db),
    )
    r = _call_tool(impl, code="print('hi' * 3)")
    assert r.ok is True and "hihihi" in r.content
    r2 = _call_tool(impl, code="import os")
    assert r2.ok is False


# ---------------------------------------------------------------------------
# API + 开关
# ---------------------------------------------------------------------------


class _ProbeModel:
    model_name = "probe"

    def __init__(self) -> None:
        self.last_tools: list[str] = []

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        self.last_tools = [getattr(t, "name", "") for t in tools or []]
        return ModelOutput(text="ok")


def test_codex_api_and_switch() -> None:
    db = Path(tempfile.mkdtemp()) / "t.db"
    model = _ProbeModel()
    client = TestClient(build_app(model=model, db_path=db))

    # API 直接执行
    r = client.post("/api/codex/run", json={"code": "print(sum(range(101)))", "timeout": 5}).json()
    assert r["ok"] is True and "5050" in r["stdout"]

    # 默认 enable_codex=False：run_code 不在工具集
    client.post("/api/chat", json={"message": "写《第1章》20字：雨夜。"})
    assert "run_code" not in model.last_tools
    # 点亮后可见
    client.post("/api/chat", json={"message": "写《第2章》20字：灯塔。", "enable_codex": True})
    assert "run_code" in model.last_tools


# ---------------------------------------------------------------------------
# S48-P4/A：沙箱只读数据环境（真实统计/自定义分析）
# ---------------------------------------------------------------------------


def test_run_code_with_data_env() -> None:
    """沙箱代码可调用 ws_chapters 等做真实统计（数据进沙箱内存，不占 token）。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    from anyspark.graph import GraphStore
    from anyspark.server.codex import make_data_env
    from anyspark.server.workspace import Workspace
    from anyspark.store import ChapterStore

    store = ChapterStore(db)
    store.upsert("main", "第一章", "雨夜，陈渡抵达雾城站。陈渡撑伞。", 0, "main")
    store.upsert("main", "第二章", "钟楼敲了十三下。", 1, "main")
    graph = GraphStore(db)
    graph.upsert_entity("main", "陈渡", "角色", description="侦探")
    ws = Workspace(root=Path(tempfile.mkdtemp()) / "ws")

    env = make_data_env(ws, store, graph)
    r = run_code(
        """
chapters = ws_chapters()
total = sum(len(c['content']) for c in chapters)
print('章节数:', len(chapters))
print('总字数:', total)
print('陈渡出现章数:', sum(1 for c in chapters if '陈渡' in c['content']))
entities = ws_entities()
print('实体数:', len(entities), '| 类型:', entities[0]['entity_type'])
""",
        timeout=10,
        data_env=env,
    )
    assert r["ok"] is True, r["error"]
    assert "章节数: 2" in r["stdout"]
    assert "总字数:" in r["stdout"]
    assert "陈渡出现章数: 1" in r["stdout"]
    assert "实体数: 1" in r["stdout"]


def test_ws_read_path_guard() -> None:
    """ws_read 路径限制：越界抛错；项目内可读。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    from anyspark.graph import GraphStore
    from anyspark.server.codex import make_data_env
    from anyspark.server.workspace import Workspace
    from anyspark.store import ChapterStore

    ws = Workspace(root=Path(tempfile.mkdtemp()) / "ws")
    ws.save_upload("main", "设定.txt", "雾城是江边之城。".encode())
    env = make_data_env(ws, ChapterStore(db), GraphStore(db))

    r = run_code("print(ws_read('上传/设定.txt'))", data_env=env)
    assert r["ok"] is True and "江边之城" in r["stdout"]

    r2 = run_code("print(ws_read('../../etc/passwd'))", data_env=env)
    assert r2["ok"] is False and "越界" in r2["error"]
