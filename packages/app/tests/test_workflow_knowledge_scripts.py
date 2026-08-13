"""工作流知识 script 函数测试（阶段1：read_settings / read_graph / query_reference）。

走 build_app + TestClient：workflow 只含 script 节点（确定性函数，不触发模型）。
数据用同一 db 直接写入（设定档/图谱/书库关联），验证 script 产出正确文本块。
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from anyspark.align.worldsettings import WorldSettingStore
from anyspark.graph import GraphStore
from anyspark.library import LibraryStore
from anyspark.server.app import build_app


def _setup_env() -> tuple[Path, TestClient]:
    d = Path(tempfile.mkdtemp())
    db = d / "test.db"
    # 直接写数据（与 build_app 同 db / 同 library 目录）
    settings = WorldSettingStore(db)
    settings.add(
        "主角顾欣桐：冷静果断，擅长心理博弈",
        category="人物卡",
        name="顾欣桐",
        book_id="main",
    )
    settings.add("雾城多雾、钟表文化兴盛", category="世界观", name="雾城", book_id="main")
    settings.close()

    graph = GraphStore(db)
    graph.upsert_entity(
        "main",
        "顾欣桐",
        "角色",
        description="主角",
        state_delta="第3章已与林默达成同盟",
    )
    graph.upsert_entity("main", "林默", "角色", description="神秘商人")
    # 关系（通过同名实体的 upsert 不建关系；直接查关系列表为空即可，不强制）
    graph.close()

    lib = LibraryStore(db)
    lib.add_book("雾城风云")
    lib.import_chapter("雾城风云", "第一章", "雨夜，陈渡推开钟表铺的门，老周正擦拭怀表。")
    lib.set_references("main", [{"type": "library", "id": "雾城风云"}])
    lib.close()

    client = TestClient(build_app(db_path=db))
    return db, client


def _run_and_wait(client: TestClient, workflow_id: str) -> dict[str, Any]:
    r = client.post(f"/api/workflows/{workflow_id}/run", json={"book_id": "main"})
    assert r.status_code == 200
    task_id = r.json()["task_id"]
    for _ in range(50):
        time.sleep(0.1)
        t = client.get(f"/api/workflows/tasks/{task_id}").json()
        if t.get("status") in {"done", "failed", "cancelled"}:
            return dict(t)
    raise AssertionError(f"workflow 未在 5s 内结束: {task_id}")


def _make_workflow(
    client: TestClient, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
) -> str:
    r = client.post(
        "/api/workflows",
        json={"name": "知识脚本测试", "description": "t", "nodes": nodes, "edges": edges},
    )
    assert r.status_code in (200, 201), r.text
    return str(r.json()["id"])


def test_read_settings_script() -> None:
    """read_settings：输出设定档文本块（分类+名称+内容）。"""
    _db, client = _setup_env()
    try:
        wf = _make_workflow(
            client,
            [
                {
                    "id": "n1",
                    "kind": "script",
                    "params": {"function": "read_settings", "output_key": "settings_block"},
                }
            ],
            [],
        )
        t = _run_and_wait(client, wf)
        assert t["status"] == "done", t
        out = t["results"]["settings_block"]
        assert "顾欣桐" in out
        assert "[人物卡]" in out
        assert "[世界观]" in out
    finally:
        client.close()


def test_read_settings_keyword_filter() -> None:
    """read_settings：keyword 过滤只返回匹配条目。"""
    _db, client = _setup_env()
    try:
        wf = _make_workflow(
            client,
            [
                {
                    "id": "n1",
                    "kind": "script",
                    "params": {
                        "function": "read_settings",
                        "keyword": "雾城",
                        "output_key": "s",
                    },
                }
            ],
            [],
        )
        t = _run_and_wait(client, wf)
        assert t["status"] == "done", t
        out = t["results"]["s"]
        assert "雾城" in out
        assert "顾欣桐" not in out
    finally:
        client.close()


def test_read_graph_script() -> None:
    """read_graph：输出图谱实体卡片（类型/状态）。"""
    _db, client = _setup_env()
    try:
        wf = _make_workflow(
            client,
            [
                {
                    "id": "n1",
                    "kind": "script",
                    "params": {"function": "read_graph", "output_key": "graph_block"},
                }
            ],
            [],
        )
        t = _run_and_wait(client, wf)
        assert t["status"] == "done", t
        out = t["results"]["graph_block"]
        assert "实体[角色] 顾欣桐" in out
        assert "同盟" in out  # 状态文本
    finally:
        client.close()


def test_query_reference_script() -> None:
    """query_reference：参考书原文检索命中。"""
    _db, client = _setup_env()
    try:
        wf = _make_workflow(
            client,
            [
                {
                    "id": "n1",
                    "kind": "script",
                    "params": {
                        "function": "query_reference",
                        "keyword": "怀表",
                        "output_key": "ref_block",
                    },
                }
            ],
            [],
        )
        t = _run_and_wait(client, wf)
        assert t["status"] == "done", t
        out = t["results"]["ref_block"]
        assert "雾城风云" in out
        assert "怀表" in out
    finally:
        client.close()


def test_workflow_auto_write_chain() -> None:
    """组合链路：读设定 → 读图谱 → 查参考书 → 变量注入 agent（假模型不触发，只看编排）。"""
    _db, client = _setup_env()
    try:
        wf = _make_workflow(
            client,
            [
                {
                    "id": "n1",
                    "kind": "script",
                    "params": {"function": "read_settings", "output_key": "settings_block"},
                },
                {
                    "id": "n2",
                    "kind": "script",
                    "params": {"function": "read_graph", "output_key": "graph_block"},
                },
                {
                    "id": "n3",
                    "kind": "script",
                    "params": {
                        "function": "query_reference",
                        "keyword": "怀表",
                        "output_key": "ref_block",
                    },
                },
            ],
            [{"source": "n1", "target": "n2"}, {"source": "n2", "target": "n3"}],
        )
        t = _run_and_wait(client, wf)
        assert t["status"] == "done", t
        assert "顾欣桐" in t["results"]["settings_block"]
        assert "实体[角色]" in t["results"]["graph_block"]
        assert "怀表" in t["results"]["ref_block"]
    finally:
        client.close()
