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
