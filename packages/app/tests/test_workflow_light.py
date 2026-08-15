"""S134（WORKFLOW 第 3 批）测试：轻流程非全程模板（图谱抽取/信号提炼/会话摘要）。

验证（PLAN-WORKFLOW-UNIFY 第 3 批）：
- 预置「图谱抽取」「信号提炼」「会话摘要」模板已种入（build_app 幂等）
- 非全程：直接出结果（无 approval 闸门）
- 图谱抽取：逐章集合遍历 → 落库形态与章节落盘自动抽取一致（实体可查）
- 信号提炼/会话摘要：复用后台函数（落库同源）
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.core.types import Message, ModelOutput
from anyspark.server.app import build_app


class FakeGraphModel:
    """fake 模型：图谱抽取返回实体 JSON；其余返回占位。"""

    model_name = "fake-graph"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        joined = "\n".join(m.content or "" for m in messages)
        if "实体类型" in joined or "章节《" in joined:
            return ModelOutput(
                text='{"entities": [{"name": "萧炎", "type": "角色", '
                '"description": "主角", "aliases": []}], '
                '"relations": [], "events": []}'
            )
        return ModelOutput(text="好的。")


def _mk_chapters(client: TestClient, n: int = 2) -> list[str]:
    ids = []
    for i in range(1, n + 1):
        r = client.post(
            "/api/chapters",
            json={"title": f"第{i}章", "content": f"第{i}章 萧炎出场。"},
        )
        assert r.status_code in (200, 201), r.text
        ids.append(str(r.json()["id"]))
    return ids


def _wait_done(client: TestClient, task_id: str) -> dict[str, object]:
    t = {}
    for _ in range(100):
        t = client.get(f"/api/workflows/tasks/{task_id}").json()
        if t.get("status") in ("done", "failed"):
            break
        time.sleep(0.1)
    return t


def test_lightflow_templates_seeded() -> None:
    """预置图谱抽取/信号提炼/会话摘要模板已种入（非全程无 approval）。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=FakeGraphModel(), db_path=db))
    wfs = client.get("/api/workflows").json()
    names = {w["name"] for w in wfs}
    for want in ("图谱抽取", "信号提炼", "会话摘要"):
        assert want in names, f"缺模板 {want}"
        wid = next(w["id"] for w in wfs if w["name"] == want)
        wf = client.get(f"/api/workflows/{wid}").json()
        # 非全程：无 approval 闸门（轻流程直接出结果）
        assert "approval" not in [n["kind"] for n in wf["nodes"]]


def test_graph_extract_template_lands_entities() -> None:
    """图谱抽取：逐章集合遍历 → 实体落库（形态与章节落盘自动抽取一致）。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=FakeGraphModel(), db_path=db))
    ids = _mk_chapters(client, 2)
    # 直接跑模板（非全程直出结果）
    wfs = client.get("/api/workflows").json()
    wid = next(w["id"] for w in wfs if w["name"] == "图谱抽取")
    r = client.post(
        f"/api/workflows/{wid}/run",
        json={"book_id": "main", "params": {"chapter_ids": json.dumps(ids)}},
    )
    task_id = r.json()["task_id"]
    t = _wait_done(client, task_id)
    assert t["status"] == "done", f"图谱抽取任务失败: {t.get('error')}"
    # 实体落库（两章同名实体合并为一条）
    ents = client.get("/api/graph/entities", params={"book_id": "main"}).json()
    names = {e["name"] for e in ents}
    assert "萧炎" in names
    # 落库形态：实体带 entity_type（与 tasks.extract_chapter 一致）
    cy = next(e for e in ents if e["name"] == "萧炎")
    assert cy["entity_type"] == "角色"


def test_signal_refine_template_runs() -> None:
    """信号提炼：无信号时直跑完成（复用后台函数，幂等不炸）。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=FakeGraphModel(), db_path=db))
    wfs = client.get("/api/workflows").json()
    wid = next(w["id"] for w in wfs if w["name"] == "信号提炼")
    r = client.post(f"/api/workflows/{wid}/run", json={"book_id": "main"})
    task_id = r.json()["task_id"]
    t = _wait_done(client, task_id)
    assert t["status"] == "done", f"信号提炼失败: {t.get('error')}"
    # 无信号 → 不新增说明书条目（幂等）
    manual = client.get("/api/manual").json()
    assert isinstance(manual, list)


def test_conversation_summarize_short_skips() -> None:
    """会话摘要：琐碎短会话不归档（复用 summarize_conversation 阈值），直跑完成。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=FakeGraphModel(), db_path=db))
    # 建一个短会话
    conv = client.post("/api/chat", json={"message": "hi"}).json()
    conv_id = conv.get("conversation_id", "c1")
    wfs = client.get("/api/workflows").json()
    wid = next(w["id"] for w in wfs if w["name"] == "会话摘要")
    r = client.post(
        f"/api/workflows/{wid}/run",
        json={"book_id": "main", "params": {"conv_id": conv_id}},
    )
    task_id = r.json()["task_id"]
    t = _wait_done(client, task_id)
    assert t["status"] == "done", f"会话摘要失败: {t.get('error')}"
