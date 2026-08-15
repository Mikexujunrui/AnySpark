"""S59 工作流 API 集成测试（app 层：真实 build_app + TestClient）。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.server.app import build_app

# 注意：build_app 默认装配真实 DeepSeek 模型——本测试只走不触发模型的路径
# （模板 CRUD / 草稿闸门 / 非法定义校验），真实链路单独用冒烟脚本验证。


def _client() -> TestClient:
    db = Path(tempfile.mkdtemp()) / "test.db"
    return TestClient(build_app(db_path=db))


def test_workflow_crud_and_validate() -> None:
    client = _client()
    # 非法定义（边引用未知节点）→ 422
    r = client.post(
        "/api/workflows",
        json={
            "name": "坏流程",
            "nodes": [{"id": "n1", "kind": "agent", "params": {"instruction": "x"}}],
            "edges": [{"source": "ghost", "target": "n1"}],
        },
    )
    assert r.status_code == 422

    # 合法定义 → 201 级成功
    r = client.post(
        "/api/workflows",
        json={
            "name": "章节审读",
            "description": "审读+按需改写",
            "nodes": [
                {
                    "id": "n1",
                    "kind": "agent",
                    "params": {"instruction": "审读", "output_key": "review"},
                },
                {"id": "g", "kind": "gate"},
                {
                    "id": "n2",
                    "kind": "agent",
                    "params": {"instruction": "改写", "output_key": "fixed"},
                },
                {"id": "n3", "kind": "approval", "params": {"prompt": "确认?"}},
            ],
            "edges": [
                {"source": "n1", "target": "g"},
                {
                    "source": "g",
                    "target": "n2",
                    "condition": {"type": "rule", "expression": "{{review}} contains '硬伤'"},
                },
                {
                    "source": "g",
                    "target": "n3",
                    "condition": {"type": "rule", "expression": "{{review}} NOT_CONTAINS '硬伤'"},
                },
                {"source": "n2", "target": "n3"},
            ],
        },
    )
    assert r.status_code == 200, r.text
    wf = r.json()
    assert wf["name"] == "章节审读"

    # 列表 / 单查 / 删除
    assert client.get("/api/workflows").json()
    assert client.get(f"/api/workflows/{wf['id']}").json()["id"] == wf["id"]
    assert client.delete(f"/api/workflows/{wf['id']}").json() == {"ok": True}
    assert client.get(f"/api/workflows/{wf['id']}").status_code == 404


def test_workflow_update_with_id() -> None:
    """S152：POST 带 id = 原地更新（upsert），不产生新副本。

    前端画布“保存模板”对已存在模板传回原 id——此前 WorkflowIn 无 id 字段，
    每次保存都生成新模板（副本堆积）。add_template 为 INSERT OR REPLACE，
    同 id 即覆盖。
    """
    client = _client()
    r = client.post(
        "/api/workflows",
        json={
            "name": "原始名",
            "nodes": [{"id": "n1", "kind": "script", "params": {"function": "noop"}}],
            "edges": [],
        },
    )
    assert r.status_code == 200, r.text
    wid = r.json()["id"]

    # 带 id 重新提交（改名）→ 同 id 返回，不新建
    r = client.post(
        "/api/workflows",
        json={
            "id": wid,
            "name": "改名后",
            "nodes": [{"id": "n1", "kind": "script", "params": {"function": "noop"}}],
            "edges": [],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == wid
    assert r.json()["name"] == "改名后"

    # 列表数量不变（更新而非复制）
    ids = [t["id"] for t in client.get("/api/workflows").json()]
    assert ids.count(wid) == 1


def test_workflow_drafts_gate() -> None:
    client = _client()
    # 草稿闸门：列表为空 + 不存在草稿的操作返回 404
    assert client.get("/api/workflows/drafts").json() == []
    assert client.post("/api/workflows/drafts/nonexist/promote").status_code == 404
    assert client.delete("/api/workflows/drafts/nonexist").status_code == 404


def test_workflow_script_write_chapter() -> None:
    """S59 补充：script write_chapter 节点——改写结果写回章节（库+盘双写）。"""
    from anyspark.core import Message, ModelOutput

    class FakeWriteModel:
        model_name = "fake-write"

        def respond(self, messages: list[Message], tools: object) -> ModelOutput:
            return ModelOutput(text="改写后的第一章内容（已修复设定冲突）", tool_calls=[])

    db = Path(tempfile.mkdtemp()) / "wf.db"
    client = TestClient(build_app(model=FakeWriteModel(), db_path=db))

    # 先建一章作为处理对象（章节仅能经 write_chapter 工具创建，这里直接写 store）
    from anyspark.store.sqlite import ChapterStore

    ChapterStore(str(db)).upsert("main", "第一章", "原文内容", 1)

    # 建流程：agent 改写 → script write_chapter 落盘（text_key 引用改写输出）
    r = client.post(
        "/api/workflows",
        json={
            "name": "改写落盘",
            "nodes": [
                {
                    "id": "n1",
                    "kind": "agent",
                    "params": {"instruction": "改写章节", "output_key": "rewritten"},
                },
                {
                    "id": "n2",
                    "kind": "script",
                    "params": {
                        "function": "write_chapter",
                        "chapter_title": "第一章",
                        "text_key": "rewritten",
                    },
                },
            ],
            "edges": [{"source": "n1", "target": "n2"}],
        },
    )
    assert r.status_code == 200, r.text
    wf = r.json()
    task_id = client.post(f"/api/workflows/{wf['id']}/run", json={"book_id": "main"}).json()[
        "task_id"
    ]

    # 等待完成
    import time

    for _ in range(30):
        t = client.get(f"/api/workflows/tasks/{task_id}").json()
        if t["status"] in ("done", "failed"):
            break
        time.sleep(0.5)
    assert t["status"] == "done", t["error"]
    # 章节被覆盖为新内容
    chs = client.get("/api/chapters").json()
    target = next(c for c in chs if c["title"] == "第一章")
    assert "改写后的第一章内容" in target["content"]


def test_workflow_agent_tools_registered() -> None:
    """S59 补充：enable_workflow 点亮时 agent 工具注册进工具集。"""
    from anyspark.core import Message, ModelOutput

    class FakeToolModel:
        model_name = "fake-tool"

        def __init__(self) -> None:
            self.calls = 0

        def respond(self, messages: list[Message], tools: object) -> ModelOutput:
            from anyspark.core import ToolCall

            self.calls += 1
            if self.calls == 1:
                # 第一轮：触发 workflow_list 工具调用
                return ModelOutput(
                    text="先看下有哪些工作流",
                    tool_calls=[ToolCall(id="c1", name="workflow_list", arguments={})],
                )
            # 第二轮（工具结果回填后）：终答
            return ModelOutput(text="工作流列表已看完", tool_calls=[])

    db = Path(tempfile.mkdtemp()) / "wf.db"
    client = TestClient(build_app(model=FakeToolModel(), db_path=db))
    # 建一个模板供 list 返回
    client.post(
        "/api/workflows",
        json={
            "name": "模板A",
            "nodes": [{"id": "n1", "kind": "agent", "params": {"instruction": "x"}}],
            "edges": [],
        },
    )
    # enable_workflow=True 的 chat 应能调 workflow_list（工具执行后模型回终答）
    r = client.post(
        "/api/chat",
        json={"message": "列一下工作流", "enable_workflow": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # 工具调用被记录（执行结果回填后模型再次响应）；name 是列表（整批工具名）
    tool_events = [e for e in data.get("events", []) if e["type"] == "tool_call"]
    assert any("workflow_list" in (e["payload"].get("name") or []) for e in tool_events)


def test_builtin_template_protected_from_delete() -> None:
    """S152：预置模板（builtin）不可删——工具收编执行路径/安全网载体受保护。

    种子模板（拆书/批量/图谱等）delete → 403；用户模板可删。
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
    wfs = client.get("/api/workflows").json()
    builtin = next(w for w in wfs if w.get("builtin"))
    users = [w for w in wfs if not w.get("builtin")]
    # 预置模板删除 → 403
    r = client.delete(f"/api/workflows/{builtin['id']}")
    assert r.status_code == 403, f"builtin 应禁删: {r.status_code} {r.text}"
    assert "不可删除" in r.json()["detail"]
    # 仍在列表（没被删）
    assert any(w["id"] == builtin["id"] for w in client.get("/api/workflows").json())
    # 用户模板删除 → 200（临时库若无用户模板则跳过该断言）
    if users:
        r2 = client.delete(f"/api/workflows/{users[0]['id']}")
        assert r2.status_code == 200


def test_workflow_agent_run_passes_params() -> None:
    """S157：agent workflow_run 透传模板运行参数（chapter_ids 等）→ 任务变量。

    8-15 事故配套：agent 跑「图谱抽取」模板需能指定章节范围；此前 workflow_run
    工具不透传 params（create_task 无 params），agent 只能跑模板缺省（全部章节）。
    HTTP 端点 run_workflow 早已支持 params（WorkflowRunIn.params），工具层补齐对齐。
    """
    import json as _json

    from anyspark.core.protocol import ToolSpec
    from anyspark.server.tools_workflow import make_workflow_tools
    from anyspark.workflow.definition import WorkflowDef, WorkflowNode
    from anyspark.workflow.store import WorkflowStore

    db = Path(tempfile.mkdtemp()) / "wf.db"
    store = WorkflowStore(db)
    wf = WorkflowDef(
        id="wf-extract-test",
        name="图谱抽取",
        description="逐章图谱抽取（实体/关系/事件）。运行参数：chapter_ids=章节id数组或逗号串（缺省全部）。",
        nodes=[
            WorkflowNode(
                id="prep",
                kind="script",
                label="收集章节",
                params={
                    "function": "batch_prepare",
                    "chapter_ids": "{{chapter_ids}}",
                    "output_key": "chapter_ids",
                },
            )
        ],
    )
    store.add_template(wf, builtin=True)

    tools = make_workflow_tools(
        store, workflow_engine=None, workflow_generator=None, book_id="main"
    )
    run_impl = {spec.name: impl for spec, impl in tools}["workflow_run"]
    res = run_impl(
        ToolSpec(name="workflow_run"),
        {"template_id": "wf-extract-test", "params": '{"chapter_ids": ["c1", "c2"]}'},
    )
    assert res.ok, res.content
    tid = store.list_tasks(limit=1)[0]["id"]
    task = store.get_task(tid)
    assert task is not None
    # get_task 已把 results 解析为 dict（初始变量 = 模板运行参数）
    assert task["results"] == {"chapter_ids": ["c1", "c2"]}

    # 非法 params → 明确报错（不静默忽略）
    res2 = run_impl(ToolSpec(name="workflow_run"), {"template_id": "wf-extract-test", "params": "不是json"})
    assert not res2.ok
    assert "JSON" in res2.content or "不是合法" in res2.content
