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


def test_path_api_errors() -> None:
    """错误路径：节点不存在 404 / archive 无起点 400 / 越界 400。"""
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    client = TestClient(build_app(model=_ScriptedModel(), db_path=_db(), workspace=_ws()))
    # 节点不存在
    r = client.post(
        "/api/explore/path", json={"from_node_id": "nope", "to_desc": "B"}
    )
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
