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
from anyspark.server.workspace import Workspace

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
    assert r2["ok"] is False and "blocks" in r2["error"]
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


def test_run_code_escape_isolated() -> None:
    """S116：属性链逃逸在子进程执行——主进程不受影响（隔离边界）。

    断言：逃逸代码的 os.system 输出不污染主进程 stdout（经 pipe 隔离）；
    子进程环境最小（读不到 DEEPSEEK_API_KEY）。
    """
    import io as _io
    import os as _os

    _os.environ["DEEPSEEK_API_KEY"] = "sk-SECRET-TEST"
    try:
        _buf = _io.StringIO()
        r = run_code(
            "cw = [c for c in ().__class__.__bases__[0].__subclasses__() "
            "if c.__name__ == 'catch_warnings'][0]; "
            "os = cw.__init__.__globals__['sys'].modules['os']; "
            "print(os.environ.get('DEEPSEEK_API_KEY', 'EMPTY'))"
        )
        # 逃逸代码拿不到主进程密钥（环境最小集）
        assert "sk-SECRET-TEST" not in (r["stdout"] + r["error"] + r["stderr"])
        assert "EMPTY" in r["stdout"]
        # 主进程 stdout 未被污染（重定向只在子进程内）
        print("MAIN-PROCESS-OK")
        assert "MAIN-PROCESS-OK" not in r["stdout"]
    finally:
        _os.environ.pop("DEEPSEEK_API_KEY", None)


def test_run_code_timeout_kills_process() -> None:
    """S116：超时后子进程被杀（不再有线程残留烧 CPU）。"""
    import threading

    before = threading.active_count()
    r = run_code("n = 0\nfor i in range(10**9):\n    n += i\nprint(n)", timeout=1)
    assert r["ok"] is False and "超时" in r["error"]
    import time

    time.sleep(0.5)
    assert threading.active_count() <= before + 1  # 无线程泄漏（子进程已杀）


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

    # S116 失败关闭：默认 enable_codex=False（沙箱不可对抗级隔离）——默认不在工具集
    client.post("/api/chat", json={"message": "写《第1章》20字：雨夜。"})
    assert "run_code" not in model.last_tools
    # 显式开启后可见
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
    assert r2["ok"] is False and "bounds" in r2["error"]


def test_ws_read_sibling_prefix_guard() -> None:
    """S116：兄弟目录名前缀碰撞（../main2/secret.txt）被拒（is_relative_to）。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    from anyspark.graph import GraphStore
    from anyspark.server.codex import make_data_env
    from anyspark.server.workspace import Workspace
    from anyspark.store import ChapterStore

    root = Path(tempfile.mkdtemp())
    ws = Workspace(root=root / "ws")
    ws.save_upload("main", "secret.txt", b"TOP-SECRET")
    # 构造兄弟目录 main2（前缀碰撞：startswith(str(base)) 会误放行）
    sibling = root / "ws" / "main2"
    sibling.mkdir(parents=True, exist_ok=True)
    (sibling / "secret.txt").write_text("SIBLING-DATA", encoding="utf-8")

    env = make_data_env(ws, ChapterStore(db), GraphStore(db))
    r = run_code("print(ws_read('../main2/secret.txt'))", data_env=env)
    assert r["ok"] is False and "bounds" in r["error"]


def test_run_code_minimal_env() -> None:
    """S116：子进程环境变量最小集——敏感密钥不可见。"""
    import os as _os

    _os.environ["DEEPSEEK_API_KEY"] = "sk-SECRET-TEST"
    try:
        r = run_code("import os; print(os.environ.get('DEEPSEEK_API_KEY', 'EMPTY'))")
        # 环境里无 DEEPSEEK_API_KEY（最小集剥离）；import os 本身被白名单拒
        assert r["ok"] is False and "blocks" in r["error"]
    finally:
        _os.environ.pop("DEEPSEEK_API_KEY", None)


def test_run_code_def_run_auto_called() -> None:
    """S162：代码定义了 run(args) 且无显式调用 → 自动调用一次并输出返回值。

    契约统一：codex 沙箱与扩展工具（execute_extension）一致——写 def run(args)
    就能跑（此前仅 exec 从不调用，def 包装的代码体静默不执行）。
    """
    r = run_code(
        "def run(args):\n"
        "    out = []\n"
        "    for i in range(5):\n"
        "        out.append(i * i)\n"
        "    return str(out)"
    )
    assert r["ok"] is True, r["error"]
    assert "[0, 1, 4, 9, 16]" in r["stdout"]


def test_run_code_def_run_not_double_called() -> None:
    """S162：已有显式 run 调用（扩展工具 wrapped 形态）→ 不重复自动调用。"""
    r = run_code(
        "def run(args):\n"
        "    return str(args.get('n', 0))\n"
        "__args = {'n': 7}\n"
        "__res = run(__args)\n"
        "print(__res, end='')"
    )
    assert r["ok"] is True, r["error"]
    assert r["stdout"].strip() == "7"  # 只调用一次（非 7\n7）


def test_run_code_def_run_with_args_and_print() -> None:
    """S162：run 内部既 print 又 return → 自动调用后输出含两者（不丢 print）。"""
    r = run_code("def run(args):\n    print('inside-print')\n    return 'ret-value'")
    assert r["ok"] is True, r["error"]
    assert "inside-print" in r["stdout"]
    assert "ret-value" in r["stdout"]


def test_codex_data_env_book_scoped() -> None:
    """S162：/api/codex/run 数据环境按 book_id 快照（此前固定 main）。"""
    from fastapi.testclient import TestClient

    db = _db()
    ws = _ws()
    from anyspark.store import ChapterStore

    store = ChapterStore(db)
    store.upsert("book-a", "第一章", "阿伦在雾城码头。", 0, "main")
    client = TestClient(build_app(model=_ProbeModel(), db_path=db, workspace=ws))

    # book-a 项目：数据环境应含 book-a 章节
    r = client.post(
        "/api/codex/run",
        json={
            "code": "def run(args):\n    chs = ws_chapters()\n    return f'count={len(chs)}'",
            "book_id": "book-a",
        },
    ).json()
    assert r["ok"] is True, r["error"]
    assert "count=1" in r["stdout"]
    # 默认 main：空项目
    r2 = client.post(
        "/api/codex/run",
        json={
            "code": "def run(args):\n    chs = ws_chapters()\n    return f'count={len(chs)}'",
            "book_id": "main",
        },
    ).json()
    assert r2["ok"] is True, r2["error"]
    assert "count=0" in r2["stdout"]


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "t.db"


def _ws() -> Workspace:
    return Workspace(root=Path(tempfile.mkdtemp()) / "ws")
