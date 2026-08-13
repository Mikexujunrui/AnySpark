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


def test_run_params_feed_gate_condition() -> None:
    """阶段2：run 传 params → gate rule 条件引用 {{param}} 命中正确分支。"""
    from anyspark.core import Message, ModelOutput

    class _FakeModel:
        model_name = "fake"

        def respond(self, messages: list[Message], tools: object) -> ModelOutput:
            return ModelOutput(text="ok", tool_calls=[])

    db = Path(tempfile.mkdtemp()) / "wf.db"
    client = TestClient(build_app(model=_FakeModel(), db_path=db))
    try:
        wf = _make_workflow(
            client,
            [
                {"id": "n1", "kind": "script", "params": {"function": "noop"}},
                {"id": "g", "kind": "gate", "params": {}},
                {"id": "n_ok", "kind": "script", "params": {"function": "noop"}},
                {"id": "n_fail", "kind": "script", "params": {"function": "noop"}},
            ],
            [
                {"source": "n1", "target": "g"},
                {
                    "source": "g",
                    "target": "n_ok",
                    "condition": {
                        "type": "rule",
                        "expression": "{{style_guide}} == '简洁'",
                    },
                },
                {"source": "g", "target": "n_fail"},
            ],
        )
        # 传 params：{{style_guide}} 应为 '简洁' → 走 n_ok
        r = client.post(
            f"/api/workflows/{wf}/run", json={"book_id": "main", "params": {"style_guide": "简洁"}}
        )
        assert r.status_code == 200
        task_id = r.json()["task_id"]
        for _ in range(50):
            time.sleep(0.1)
            t = client.get(f"/api/workflows/tasks/{task_id}").json()
            if t.get("status") in {"done", "failed", "cancelled"}:
                break
        assert t["status"] == "done", t
        states = {s["node_id"]: s["status"] for s in t["node_states"]}
        assert states["n_ok"] == "done"
        assert states["n_fail"] == "pending"  # 条件命中 n_ok，n_fail 未执行
    finally:
        client.close()


def test_run_params_feed_agent_instruction() -> None:
    """阶段2：run 传 params → agent 节点 instruction 里 {{param}} 被解析为传值。"""
    from anyspark.core import Message, ModelOutput

    captured: dict[str, object] = {}

    class _FakeModel:
        model_name = "fake"

        def respond(self, messages: list[Message], tools: object) -> ModelOutput:
            captured["instruction"] = messages[-1].content
            return ModelOutput(text="已写", tool_calls=[])

    db = Path(tempfile.mkdtemp()) / "wf.db"
    client = TestClient(build_app(model=_FakeModel(), db_path=db))
    try:
        wf = _make_workflow(
            client,
            [
                {
                    "id": "n1",
                    "kind": "agent",
                    "params": {
                        "instruction": "按风格指导【{{style_guide}}】续写",
                        "output_key": "out",
                    },
                }
            ],
            [],
        )
        r = client.post(
            f"/api/workflows/{wf}/run",
            json={"book_id": "main", "params": {"style_guide": "短句直给"}},
        )
        assert r.status_code == 200
        task_id = r.json()["task_id"]
        for _ in range(50):
            time.sleep(0.1)
            t = client.get(f"/api/workflows/tasks/{task_id}").json()
            if t.get("status") in {"done", "failed", "cancelled"}:
                break
        assert t["status"] == "done", t
        assert captured["instruction"] == "按风格指导【短句直给】续写"
    finally:
        client.close()


def test_auto_write_full_chain() -> None:
    """阶段3：完整自动续写链路（假模型）——读知识→写→落盘→审→质量门→循环。

    链路：read_settings → read_graph → agent写下一章（{{var}}注入知识）→
    write_chapter落盘 → review_chapter审读 → gate判断（无硬伤=done，有=loop重写）。
    """
    from anyspark.core import Message, ModelOutput
    from anyspark.store.sqlite import ChapterStore

    db = Path(tempfile.mkdtemp()) / "wf.db"
    # 先写设定+图谱（同 db）
    settings = WorldSettingStore(db)
    settings.add("主角顾欣桐：冷静果断", category="人物卡", name="顾欣桐", book_id="main")
    settings.close()
    graph = GraphStore(db)
    graph.upsert_entity("main", "顾欣桐", "角色", description="主角", state_delta="第3章达成同盟")
    graph.close()
    ChapterStore(str(db)).upsert("main", "第一章", "顾欣桐在雾城车站下车。", 1)

    calls: list[str] = []

    class _FakeModel:
        model_name = "fake"

        def respond(self, messages: list[Message], tools: object) -> ModelOutput:
            instruction = messages[-1].content
            calls.append(str(instruction)[:40])
            if "审读" in str(instruction):
                return ModelOutput(text="硬伤数: 0\n第一章无硬伤。", tool_calls=[])
            return ModelOutput(
                text="第二章 同盟者的代价\n顾欣桐在钟表铺与林默密谈，达成新的约定。",
                tool_calls=[],
            )

    client = TestClient(build_app(model=_FakeModel(), db_path=db))
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
                    "id": "loop",
                    "kind": "loop",
                    "params": {
                        "body": ["n3", "n4", "n5"],
                        "max_iterations": 2,
                        "continue_condition": "{{review}} contains '硬伤'",
                    },
                },
                {
                    "id": "n3",
                    "kind": "agent",
                    "params": {
                        "instruction": "按设定{{settings_block}}与图谱{{graph_block}}续写下一章",
                        "output_key": "chapter_text",
                    },
                },
                {
                    "id": "n4",
                    "kind": "script",
                    "params": {
                        "function": "write_chapter",
                        "chapter_title": "第二章",
                        "text_key": "chapter_text",
                    },
                },
                {
                    "id": "n5",
                    "kind": "script",
                    "params": {
                        "function": "review_chapter",
                        "chapter_title": "第二章",
                        "output_key": "review",
                    },
                },
                {"id": "end", "kind": "script", "params": {"function": "noop"}},
            ],
            [
                {"source": "n1", "target": "n2"},
                {"source": "n2", "target": "loop"},
                {"source": "loop", "target": "end"},
            ],
        )
        r = client.post(f"/api/workflows/{wf}/run", json={"book_id": "main"})
        assert r.status_code == 200
        task_id = r.json()["task_id"]
        for _ in range(60):
            time.sleep(0.1)
            t = client.get(f"/api/workflows/tasks/{task_id}").json()
            if t.get("status") in {"done", "failed", "cancelled"}:
                break
        assert t["status"] == "done", t
        # 第二章已落盘
        chs = ChapterStore(str(db)).list_by_book("main")
        titles = [c.title for c in chs]
        assert "第二章" in titles
        # agent 指令里注入了知识（设定/图谱）
        assert any("顾欣桐" in c for c in calls)
    finally:
        client.close()
