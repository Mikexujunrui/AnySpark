"""S67 路径探索 API：起点 A → 终点 B 的串联路径候选 + archive 落树测试。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from anyspark.core.types import Message, ModelOutput
from anyspark.server.workspace import Workspace


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "t.db"


def _ws() -> Workspace:
    return Workspace(root=Path(tempfile.mkdtemp()) / "ws")


class _ScriptedModel:
    """返回两条路径候选（路径探索单次调用）。"""

    model_name = "scripted"

    def __init__(self) -> None:
        self.calls = 0

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        self.calls += 1
        return ModelOutput(
            text=json.dumps(
                {
                    "paths": [
                        {
                            "events": ["陈渡在船票背面发现水印", "水印指向废弃仓库"],
                            "note": "快速推进，适合尽快进入对峙",
                            "style": "直接推进",
                        },
                        {
                            "events": ["陈渡找到当年的船员", "船员失踪", "港口出现新线索"],
                            "note": "多层铺垫，拉满悬疑节奏",
                            "style": "多层铺垫",
                        },
                    ]
                },
                ensure_ascii=False,
            )
        )


def test_path_api_returns_candidates() -> None:
    """自然语言起终点 → N 条路径候选（事件链 + note + style）。"""
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    client = TestClient(build_app(model=_ScriptedModel(), db_path=_db(), workspace=_ws()))
    r = client.post(
        "/api/explore/path",
        json={"from_desc": "陈渡收到旧船票", "to_desc": "陈渡发现父亲没死"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["paths"]) == 2
    assert d["paths"][0]["events"][0] == "陈渡在船票背面发现水印"
    assert d["archived"] is None  # 默认不落树


def test_path_api_with_story_nodes() -> None:
    """传叙事树节点 ID → 内容自动带入；archive 落树。"""
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    client = TestClient(build_app(model=_ScriptedModel(), db_path=_db(), workspace=_ws()))
    # 建两个叙事树节点（A/B）
    r = client.post(
        "/api/story/nodes", json={"content": "陈渡收到旧船票", "kind": "main", "chosen": True}
    )
    a_id = r.json()["id"]
    client.post("/api/story/nodes", json={"content": "陈渡发现父亲没死", "kind": "anchor"})

    # 用节点 ID 探索（A 用 ID，B 用描述）
    r = client.post(
        "/api/explore/path",
        json={"from_node_id": a_id, "to_desc": "陈渡发现父亲没死", "archive_index": 1},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["archived"] is not None
    assert len(d["archived"]["node_ids"]) == 2  # 两个中间事件落树
    # 验证树里出现中间节点（candidate，挂在 A 下）
    tree = client.get("/api/story/tree").json()
    node_ids = {n["id"] for n in tree["nodes"]}
    assert all(nid in node_ids for nid in d["archived"]["node_ids"])


def test_story_tree_isolated_by_book() -> None:
    """S152：叙事树按项目（book_id）隔离——不同项目的树互不可见。

    前端此前硬编码 book_id=main，所有项目共用一棵树；后端存储本就带 book_id，
    此测试锁住隔离语义，防止回归为跨项目共享。
    """
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    client = TestClient(build_app(model=_ScriptedModel(), db_path=_db(), workspace=_ws()))
    # 项目 A 建两个节点
    r = client.post(
        "/api/story/nodes",
        json={"content": "A项目根节点", "book_id": "book-a", "kind": "root"},
    )
    assert r.status_code == 200, r.text
    client.post(
        "/api/story/nodes",
        json={
            "content": "A项目子节点",
            "book_id": "book-a",
            "parent_id": r.json()["id"],
        },
    )
    # 项目 B 建一个节点
    client.post(
        "/api/story/nodes",
        json={"content": "B项目节点", "book_id": "book-b"},
    )
    # 各项目只见自己的树
    a = client.get("/api/story/tree?book_id=book-a").json()
    b = client.get("/api/story/tree?book_id=book-b").json()
    assert {n["content"] for n in a["nodes"]} == {"A项目根节点", "A项目子节点"}
    assert {n["content"] for n in b["nodes"]} == {"B项目节点"}


def test_play_sessions_isolated_by_book() -> None:
    """S152：推演会话按项目（book_id）隔离——列表不再跨项目混显。

    此前前端 createPlaySession 硬编码 book_id=main、list_sessions 无过滤，
    所有项目的推演记录混在一处。
    """

    # 经 API 创建需要模型 → 改用 store 层验证（路由只做透传，store 过滤是核心）
    from anyspark.play.tree import PlayStore

    store = PlayStore(_db())
    store.create_session(role="侦探", seed="雨夜", book_id="book-a")
    store.create_session(role="船长", seed="海港", book_id="book-b")
    assert {s["book_id"] for s in store.list_sessions(book_id="book-a")} == {"book-a"}
    assert {s["book_id"] for s in store.list_sessions(book_id="book-b")} == {"book-b"}
    assert len(store.list_sessions(book_id="main")) == 0


def test_explore_archive_isolated_by_book() -> None:
    """S152：探索固化按项目隔离——归档列表过滤 + 落叙事树按当前项目。

    此前后端 explore_archive 写叙事树硬编码 book_id=main，探索生长的节点
    全进 main 项目（即使前端按项目传了其他树的 book_id 也白搭）。
    """
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    client = TestClient(build_app(model=_ScriptedModel(), db_path=_db(), workspace=_ws()))
    # 项目 A 固化一个方向
    r = client.post(
        "/api/explore/archive",
        json={
            "card": {
                "title": "怀表疑云",
                "summary": "陈渡发现怀表刻字与父亲有关",
                "dimension": "情节驱动",
                "source": "user",
                "term": "探案",
            },
            "book_id": "book-a",
        },
    )
    assert r.status_code == 200, r.text
    story_node_id = r.json()["story_node_id"]
    # 归档列表按项目过滤
    a = client.get("/api/explore/archive?book_id=book-a").json()
    b = client.get("/api/explore/archive?book_id=book-b").json()
    assert len(a) == 1 and a[0]["title"] == "怀表疑云"
    assert b == []
    # 落树节点在 book-a 的项目树里（此前硬编码 main 会落错项目）
    tree_a = client.get("/api/story/tree?book_id=book-a").json()
    assert any(n["id"] == story_node_id for n in tree_a["nodes"])
    tree_main = client.get("/api/story/tree").json()
    assert all(n["id"] != story_node_id for n in tree_main["nodes"])


def test_path_api_errors() -> None:
    """错误路径：节点不存在 404 / archive 无起点 400 / 越界 400。"""
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    client = TestClient(build_app(model=_ScriptedModel(), db_path=_db(), workspace=_ws()))
    # 节点不存在
    r = client.post("/api/explore/path", json={"from_node_id": "nope", "to_desc": "B"})
    assert r.status_code == 404
    # archive 但无 from_node_id
    r = client.post(
        "/api/explore/path",
        json={"from_desc": "A", "to_desc": "B", "archive_index": 1},
    )
    assert r.status_code == 400
    # archive_index 越界
    r = client.post(
        "/api/explore/path",
        json={"from_desc": "A", "to_desc": "B", "archive_index": 9},
    )
    assert r.status_code == 400


def test_patch_chapter_keeps_book() -> None:
    """S152g：定点编辑按章节所属项目写回（此前硬编码 main——A 项目章节被 upsert 到 main）。

    锁定：patch 后内容进原项目章节库，main 项目不出现该章节。
    """
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    client = TestClient(build_app(model=_ScriptedModel(), db_path=_db(), workspace=_ws()))
    # 项目 book-a 建章（经 chapters store 直插，绕模型）
    from anyspark.store.sqlite import ChapterStore

    db = _db()
    ChapterStore(str(db)).upsert("book-a", "第一章", "雨夜，陈渡抵达雾城。", 1)
    client = TestClient(build_app(model=_ScriptedModel(), db_path=db, workspace=_ws()))

    # 端点按 chapter_id 定位，先查真实 id
    chs = client.get("/api/chapters?book_id=book-a").json()
    assert len(chs) == 1
    cid = chs[0]["id"]
    r = client.post(
        f"/api/chapters/{cid}/patch",
        json={
            "operations": [{"type": "replace", "anchor": "抵达", "content": "雨夜，陈渡重返雾城。"}]
        },
    )
    assert r.status_code == 200, r.text
    # 内容进 book-a（不是 main）
    a = client.get("/api/chapters?book_id=book-a").json()
    assert a[0]["content"] == "雨夜，陈渡重返雾城。"
    m = client.get("/api/chapters?book_id=main").json()
    assert all(ch["title"] != "第一章" for ch in m)


def test_manual_isolated_by_book() -> None:
    """S152g：项目级说明书按项目隔离（此前硬编码 main——所有项目共享同一份心智）。"""
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    client = TestClient(build_app(model=_ScriptedModel(), db_path=_db(), workspace=_ws()))
    client.post(
        "/api/manual",
        json={
            "content": "作者偏好冷峻文风",
            "category": "style",
            "scope": "project",
            "book_id": "book-a",
        },
    )
    a = client.get("/api/manual?scope=project&book_id=book-a").json()
    b = client.get("/api/manual?scope=project&book_id=book-b").json()
    assert any(e["content"] == "作者偏好冷峻文风" for e in a)
    assert b == []


def test_import_txt_book_creates_and_chapterizes() -> None:
    """S156：书架页"单个 txt 直接上传成书"——建项目+GBK 解码+拆章+卷标题跳过。"""
    import base64

    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    client = TestClient(build_app(model=_ScriptedModel(), db_path=_db(), workspace=_ws()))
    novel = (
        "第一卷 序章\n\n第一章 起点\n雨夜抵达。\n\n第二章 灯塔\n钟声响起。"
        "\n\n第三章 怀表\n找到旧怀表。"
    )
    r = client.post(
        "/api/books/import-txt",
        json={
            "title": "新书",
            "filename": "新书.txt",
            "data_b64": base64.b64encode(novel.encode("gb18030")).decode(),
            "mode": "chapters",
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["book"]["id"] == "新书" and d["kind"] == "chapters" and d["count"] == 3
    # 卷标题被跳过（空章）；三章内容正确
    chs = client.get("/api/chapters?book_id=新书").json()
    assert [c["title"] for c in chs] == ["第一章 起点", "第二章 灯塔", "第三章 怀表"]
    assert "雨夜抵达" in chs[0]["content"]


def test_import_txt_book_rollback_on_failure() -> None:
    """S156：消化失败回滚——不留半成品项目。"""
    import base64

    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    client = TestClient(build_app(model=_ScriptedModel(), db_path=_db(), workspace=_ws()))
    r = client.post(
        "/api/books/import-txt",
        json={
            "title": "坏书",
            "filename": "坏.txt",
            "data_b64": base64.b64encode(b"   ").decode(),  # 空白 → 提取失败
            "mode": "chapters",
        },
    )
    assert r.status_code == 400
    # 项目目录已回滚（书架无此项目）
    books = client.get("/api/books").json()
    assert all(b["id"] != "坏书" for b in books)
