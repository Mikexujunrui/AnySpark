"""S48-P4/B：search_chapters 正文检索 + 扩展工具注册表（人工批准）测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.core.protocol import ToolSpec
from anyspark.core.types import Message, ModelOutput, ToolResult
from anyspark.server.app import build_app
from anyspark.server.codex import run_code
from anyspark.server.tools_domain import (
    make_search_chapters_implementer,
)
from anyspark.server.tools_extensions import (
    ExtensionToolStore,
    execute_extension,
)
from anyspark.store import ChapterStore


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "t.db"


def _seed_chapters() -> ChapterStore:
    store = ChapterStore(_db())
    store.upsert("main", "第一章", "雨夜，陈渡撑伞走过雾城。陈渡低声念着父亲的名字。", 0, "main")
    store.upsert("main", "第二章", "钟楼敲响，雾中走出一个身影。", 1, "main")
    return store


def _call(impl: object, **kwargs: object) -> ToolResult:
    spec = ToolSpec(name="t", description="t", params=[])
    result = impl(spec, kwargs)  # type: ignore[operator]
    assert isinstance(result, ToolResult)
    return result


# ---------------------------------------------------------------------------
# search_chapters：正文定位 + 计数
# ---------------------------------------------------------------------------


def test_search_chapters_hits_and_context() -> None:
    store = _seed_chapters()
    _, impl = make_search_chapters_implementer(store)
    r = _call(impl, keyword="陈渡")
    assert r.ok is True
    assert "命中 1 章共 2 次" in r.content  # 第一章出现 2 次
    assert "第一章" in r.content
    assert r.data and r.data["total"] == 2

    # 未命中
    r2 = _call(impl, keyword="红绳")
    assert r2.ok is True and "未找到" in r2.content


# ---------------------------------------------------------------------------
# 扩展工具注册表：draft → approve → active → 沙箱执行
# ---------------------------------------------------------------------------


def test_extension_store_lifecycle() -> None:
    store = ExtensionToolStore(_db())
    t = store.add(
        "word_count",
        "统计章节字数",
        [{"name": "kw", "type": "string"}],
        "def run(args):\n    return 'ok'",
    )
    assert t.status == "draft"
    # draft 不注入
    assert store.active_tools() == []
    # approve → active
    store.set_status(t.id, "active")
    assert len(store.active_tools()) == 1
    assert store.active_tools()[0].name == "word_count"
    # disable → 回 draft
    store.set_status(t.id, "draft")
    assert store.active_tools() == []
    # delete
    assert store.delete(t.id) is True
    assert store.list_all() == []


def test_extension_execute_in_sandbox() -> None:
    store = ExtensionToolStore(_db())
    t = store.add(
        "dialogue_ratio",
        "计算对话占比",
        [],
        (
            "def run(args):\n"
            "    chs = ws_chapters()\n"
            "    total = sum(len(c['content']) for c in chs)\n"
            "    quotes = sum(c['content'].count('「') for c in chs)\n"
            "    return f'总字数 {total}，引号 {quotes} 处'\n"
        ),
    )
    from anyspark.graph import GraphStore
    from anyspark.server.codex import make_data_env
    from anyspark.server.workspace import Workspace

    chapters = _seed_chapters()
    env = make_data_env(
        Workspace(root=Path(tempfile.mkdtemp()) / "ws"), chapters, GraphStore(_db())
    )
    r = execute_extension(t, {}, env)
    assert r.ok is True, r.content
    assert "总字数" in r.content

    # 参数注入
    t2 = store.add(
        "echo_kw",
        "回显关键词出现次数",
        [{"name": "kw", "type": "string", "required": True}],
        "def run(args):\n    return f\"kw={args.get('kw')}\"",
    )
    r2 = execute_extension(t2, {"kw": "陈渡"}, env)
    assert r2.ok is True and "kw=陈渡" in r2.content


def test_extension_bad_code_fails_gracefully() -> None:
    store = ExtensionToolStore(_db())
    t = store.add("bad_tool", "坏工具", [], "def run(args):\n    raise ValueError('boom')")
    r = execute_extension(t, {}, None)
    assert r.ok is False and "boom" in r.content


# ---------------------------------------------------------------------------
# API：register/approve/装配（Probe 验证工具注入）
# ---------------------------------------------------------------------------


class _ProbeModel:
    model_name = "probe"

    def __init__(self) -> None:
        self.last_tools: list[str] = []

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        self.last_tools = [getattr(t, "name", "") for t in tools or []]
        return ModelOutput(text="ok")


def test_ext_tools_api_and_assembly() -> None:
    db = _db()
    model = _ProbeModel()
    client = TestClient(build_app(model=model, db_path=db))

    # 登记 → draft
    r = client.post(
        "/api/tools/register",
        json={
            "name": "chapter_stats",
            "description": "统计全书章节字数",
            "params_json": "[]",
            "code": "def run(args):\n    chs = ws_chapters()\n    return str(len(chs))",
        },
    ).json()
    assert r["status"] == "draft"
    tid = r["id"]

    # draft 不注入工具集
    client.post("/api/chat", json={"message": "写《第1章》20字：雨。"})
    assert "chapter_stats" not in model.last_tools

    # 批准 → active → 注入
    client.post(f"/api/tools/{tid}/approve")
    client.post("/api/chat", json={"message": "写《第2章》20字：灯。"})
    assert "chapter_stats" in model.last_tools

    # disable → 不再注入
    client.post(f"/api/tools/{tid}/disable")
    client.post("/api/chat", json={"message": "写《第3章》20字：钟。"})
    assert "chapter_stats" not in model.last_tools

    # 列表 + 删除
    assert len(client.get("/api/tools").json()) >= 1
    client.delete(f"/api/tools/{tid}")
    assert client.get("/api/tools").json() == []


def test_register_requires_run_function() -> None:
    db = _db()
    client = TestClient(build_app(model=_ProbeModel(), db_path=db))
    r = client.post(
        "/api/tools/register",
        json={"name": "no_func", "description": "x", "params_json": "[]", "code": "print('hi')"},
    )
    assert r.status_code == 400


def test_search_chapters_exclude_and_fragment() -> None:
    """exclude 排除否定语境；fragment 控制上下文宽度（默认小片段定位用）。"""
    store = _seed_chapters()
    _, impl = make_search_chapters_implementer(store)
    # 默认：小片段（前后 20 字）
    r = _call(impl, keyword="陈渡")
    assert r.ok is True and "命中 1 章共 2 次" in r.content
    # fragment=0：只要章节和次数，无片段
    r0 = _call(impl, keyword="陈渡", fragment="0")
    assert r0.ok is True and "×2" in r0.content and "…" not in r0.content
    # exclude：片段内含排除词的命中跳过
    store2 = _seed_chapters()
    store2.upsert("main", "第三章", "他没有陈渡的消息，也找不到陈渡。", 2, "main")
    _, impl2 = make_search_chapters_implementer(store2)
    r_ex = _call(impl2, keyword="陈渡", exclude="没有")
    # 第一章 2 次 + 第三章 1 次（"他没有陈渡的消息"被排除，剩"也找不到陈渡"）
    assert "命中 2 章共 3 次" in r_ex.content


def test_search_chapters_regex() -> None:
    """regex 模糊匹配：多形/跨字。"""
    store = _seed_chapters()
    store.upsert("main", "第三章", "他攥着怀表盖，怀表链在指间转。", 2, "main")
    _, impl = make_search_chapters_implementer(store)
    r = _call(impl, keyword="怀表(盖|链)", regex="true")
    assert r.ok is True
    assert "命中 1 章共 2 次" in r.content  # 怀表盖 + 怀表链
    # 非法正则 → 报错
    r2 = _call(impl, keyword="怀表(", regex="true")
    assert r2.ok is False and "正则" in r2.content


def test_read_context_paragraphs() -> None:
    """read_context：锚点定位读前后段落（不读全文）。"""
    store = _seed_chapters()
    store.upsert(
        "main",
        "第三章",
        "第一段。\n\n第二段提到怀表。\n\n第三段。\n\n第四段。",
        2,
        "main",
    )
    from anyspark.server.tools_domain import make_read_context_implementer

    _, impl = make_read_context_implementer(store)
    r = _call(impl, title="第三章", anchor="怀表")
    assert r.ok is True
    assert "第二段提到怀表" in r.content
    assert "第一段" in r.content  # 前 2 段
    assert "第四段" in r.content  # 后 2 段（含第三段）
    # 锚点未命中 → 返回开头提示
    r2 = _call(impl, title="第三章", anchor="不存在的锚点")
    assert r2.ok is False and "未找到锚点" in r2.content


def test_extension_update_goes_back_to_draft() -> None:
    """S49：更新扩展工具 → 自动回 draft 重新批准。"""
    db = _db()
    model = _ProbeModel()
    client = TestClient(build_app(model=model, db_path=db))
    r = client.post(
        "/api/tools/register",
        json={
            "name": "ver_tool",
            "description": "v1",
            "params_json": "[]",
            "code": "def run(args):\n    return 'v1'",
        },
    ).json()
    tid = r["id"]
    client.post(f"/api/tools/{tid}/approve")
    client.post("/api/chat", json={"message": "写《第1章》20字：雨。"})
    assert "ver_tool" in model.last_tools

    # 更新代码 → 回 draft，不再注入
    r2 = client.patch(
        f"/api/tools/{tid}",
        json={"code": "def run(args):\n    return 'v2'", "description": "v2"},
    ).json()
    assert r2["status"] == "draft"
    client.post("/api/chat", json={"message": "写《第2章》20字：灯。"})
    assert "ver_tool" not in model.last_tools
    # 重新批准生效（执行新代码）
    client.post(f"/api/tools/{tid}/approve")
    # 404 处理
    assert (
        client.patch("/api/tools/nonexist", json={"code": "def run(args): return 'x'"}).status_code
        == 404
    )


def test_src_read_inside_sandbox() -> None:
    """S49：沙箱只读源码（修 bug 辅助）；越界拒绝。"""
    from anyspark.graph import GraphStore
    from anyspark.server.codex import make_data_env
    from anyspark.server.workspace import Workspace
    from anyspark.store import ChapterStore

    db = _db()
    env = make_data_env(
        Workspace(root=Path(tempfile.mkdtemp()) / "ws"), ChapterStore(db), GraphStore(db)
    )
    r = run_code("print(src_read('core/src/anyspark/core/types.py')[:30])", data_env=env)
    assert r["ok"] is True, r["error"]
    # 越界
    r2 = run_code("print(src_read('../../etc/passwd'))", data_env=env)
    assert r2["ok"] is False and "越界" in r2["error"]
