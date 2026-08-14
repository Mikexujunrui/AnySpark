"""S48 工作区化：Workspace 文件区 + 双写（md 权威 + SQLite 镜像）+ API 端点测试。"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from anyspark.core.types import Message, ModelOutput
from anyspark.server.app import build_app
from anyspark.server.tools_writing import WritingTools
from anyspark.server.workspace import (
    CHAPTERS_DIR,
    UPLOAD_DIR,
    Workspace,
    chapter_filename,
    parse_chapter_filename,
)
from anyspark.store import ChapterStore


def _ws() -> Workspace:
    return Workspace(root=Path(tempfile.mkdtemp()) / "ws")


# ---------------------------------------------------------------------------
# Workspace：目录结构与文件操作
# ---------------------------------------------------------------------------


def test_workspace_structure() -> None:
    ws = _ws()
    d = ws.project_dir("main")
    assert (d / UPLOAD_DIR).exists() or True  # 目录惰性创建，describe 时确保
    ws.describe("main")
    assert (d / UPLOAD_DIR).is_dir()
    assert (d / CHAPTERS_DIR).is_dir()
    assert (d / "卡片").is_dir()


def test_chapter_filename_roundtrip() -> None:
    fn = chapter_filename(3, "第一章 雨夜：开始")
    assert fn == "003-第一章 雨夜：开始.md"
    assert parse_chapter_filename(fn) == (3, "第一章 雨夜：开始")
    # 非法字符消毒
    assert "/" not in chapter_filename(1, "a/b:c")
    assert parse_chapter_filename("hello.md") is None  # 不匹配规范


def test_workspace_chapter_read_write() -> None:
    ws = _ws()
    f = ws.write_chapter("main", 1, "第一章", "雨夜，陈渡抵达雾城站。")
    assert f.exists()
    assert ws.read_chapter("main", 1, "第一章") == "雨夜，陈渡抵达雾城站。"
    items = ws.list_chapter_files("main")
    assert len(items) == 1 and items[0]["order"] == 1 and items[0]["title"] == "第一章"
    # 覆盖写
    ws.write_chapter("main", 1, "第一章", "改后。")
    assert ws.read_chapter("main", 1, "第一章") == "改后。"


def test_workspace_upload_and_cards() -> None:
    ws = _ws()
    dest = ws.save_upload("main", "设定素材.pdf", b"%PDF-fake")
    assert dest.exists() and dest.name == "设定素材.pdf"
    # 重名自动加后缀
    dest2 = ws.save_upload("main", "设定素材.pdf", b"x")
    assert dest2.name == "设定素材-1.pdf"
    assert len(ws.list_uploads("main")) == 2

    card = ws.write_card("main", "角色卡", "陈渡", "# 陈渡\n侦探。")
    assert card.exists() and card.name == "角色卡-陈渡.md"
    assert len(ws.list_cards("main")) == 1


# ---------------------------------------------------------------------------
# 双写：WritingTools + workspace → 文件权威 + SQLite 镜像
# ---------------------------------------------------------------------------


def _make_spec(name: str) -> Any:
    from anyspark.core.protocol import ToolSpec

    return ToolSpec(
        name=name,
        description="t",
        params=[],
    )


def test_write_chapter_dual_roundtrip() -> None:
    db = Path(tempfile.mkdtemp()) / "t.db"
    store = ChapterStore(db)
    ws = _ws()
    tools = WritingTools(store, workspace=ws)

    r = tools.write_chapter(_make_spec("write_chapter"), {"title": "第一章", "content": "正文A"})
    assert r.ok
    # 文件权威存在
    assert ws.read_chapter("main", 0, "第一章") == "正文A"
    # 库镜像可读
    ch = store.list_by_book("main")[0]
    assert ch.content == "正文A"

    # 覆盖：文件与库都更新，版本历史记录旧版
    tools.write_chapter(_make_spec("write_chapter"), {"title": "第一章", "content": "正文B"})
    assert ws.read_chapter("main", 0, "第一章") == "正文B"
    assert store.list_by_book("main")[0].content == "正文B"
    assert len(store.get(store.list_by_book("main")[0].id).versions) >= 1  # type: ignore[union-attr]


def test_patch_chapter_dual() -> None:
    db = Path(tempfile.mkdtemp()) / "t.db"
    store = ChapterStore(db)
    ws = _ws()
    tools = WritingTools(store, workspace=ws)
    tools.write_chapter(
        _make_spec("write_chapter"), {"title": "第一章", "content": "第一段。\n第二段。"}
    )
    r = tools.patch_chapter(
        _make_spec("patch_chapter"),
        {
            "title": "第一章",
            "operations": ('[{"type":"replace","anchor":"第二段","content":"改写段。"}]'),
        },
    )
    assert r.ok
    assert ws.read_chapter("main", 0, "第一章") == "第一段。\n改写段。"
    assert store.list_by_book("main")[0].content == "第一段。\n改写段。"


# ---------------------------------------------------------------------------
# API 端点
# ---------------------------------------------------------------------------


class _FakeModel:
    model_name = "fake"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        return ModelOutput(text="ok")


class _FakeUncModel:
    """S70 破限 API 测试用（无工具调用）。"""

    model_name = "fake-unc"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        return ModelOutput(text="ok")


def test_workspace_api() -> None:
    db = Path(tempfile.mkdtemp()) / "t.db"
    ws = _ws()
    client = TestClient(build_app(model=_FakeModel(), db_path=db, workspace=ws))

    # 结构总览
    r = client.get("/api/workspace").json()
    assert "uploads" in r and "chapters" in r and "cards" in r

    # 上传存档（base64）
    r = client.post(
        "/api/upload",
        json={"filename": "设定.pdf", "data_b64": base64.b64encode(b"%PDF-fake").decode()},
    ).json()
    assert r["ok"] is True and r["name"] == "设定.pdf"
    assert ws.list_uploads("main")[0]["name"] == "设定.pdf"

    # 人工编辑 md → import 同步入库（内容变化才写版本）
    ws.write_chapter("main", 1, "第一章", "人工手写的正文。")
    r = client.post("/api/workspace/import").json()
    assert r["ok"] is True and r["changed"] == 1
    from anyspark.store import ChapterStore

    store = ChapterStore(db)
    assert store.list_by_book("main")[0].content == "人工手写的正文。"
    # 再次 import：无变化
    r2 = client.post("/api/workspace/import").json()
    assert r2["changed"] == 0


# ---------------------------------------------------------------------------
# S70：破限模式开关（书籍级，写作自由度）
# ---------------------------------------------------------------------------
def test_uncensored_flag_default_off() -> None:
    ws = _ws()
    assert ws.is_uncensored("main") is False
    assert ws.is_uncensored("other_book") is False


def test_uncensored_flag_set_and_unset() -> None:
    ws = _ws()
    assert ws.set_uncensored("main", True) is True
    assert ws.is_uncensored("main") is True
    # 书籍级隔离：其他书不受影响
    assert ws.is_uncensored("other_book") is False
    assert ws.set_uncensored("main", False) is False
    assert ws.is_uncensored("main") is False


def test_uncensored_api() -> None:
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=_FakeUncModel(), db_path=db))
    # 默认关
    assert client.get("/api/uncensored?book_id=main").json()["enabled"] is False
    # 开
    r = client.post("/api/uncensored", json={"book_id": "main", "enabled": True})
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    assert client.get("/api/uncensored?book_id=main").json()["enabled"] is True
    # 书籍级隔离
    assert client.get("/api/uncensored?book_id=other").json()["enabled"] is False
    # 关
    r = client.post("/api/uncensored", json={"book_id": "main", "enabled": False})
    assert r.json()["enabled"] is False


def test_sandbox_api_lists_and_reads() -> None:
    """S141（审计缺口①修复）：AI 文件沙箱浏览 API——列文件树 + 读内容。

    read_file/write_file 产物（笔记/灵感）前端可见；路径防穿越。
    """
    import tempfile
    from pathlib import Path

    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    class _M:
        model_name = "fake"

        def respond(self, messages, tools):  # type: ignore[no-untyped-def]
            from anyspark.core.types import ModelOutput

            return ModelOutput(text="好的。")

    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=_M(), db_path=db))
    # 沙箱列表接口可用（空库也可能有历史文件；只验接口形态）
    r = client.get("/api/sandbox")
    assert r.status_code == 200
    d = r.json()
    assert "files" in d and "count" in d and "root" in d
    assert isinstance(d["files"], list)
    # 防穿越：越界路径 400
    r2 = client.get("/api/sandbox/file", params={"path": "../../etc/passwd"})
    assert r2.status_code == 400
    # 不存在文件 404
    r3 = client.get("/api/sandbox/file", params={"path": "no_such_file_xyz.md"})
    assert r3.status_code == 404
