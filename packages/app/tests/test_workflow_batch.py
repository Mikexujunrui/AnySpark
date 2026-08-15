"""S133（WORKFLOW 第 2 批）测试：批量改写/审读 workflow 模板。

验证（PLAN-WORKFLOW-UNIFY 第 2 批）：
- 预置「批量改写」「批量审读」模板已种入（build_app 幂等）
- 集合遍历逐章（W3-A 已验证）+ approval 闸门（重操作强制）
- 批量改写：逐章 agent 改写 → write_chapter 落盘（覆盖前旧版进版本历史）
- 批量审读：轻操作无 approval，逐章检测网审读
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.core.types import Message, ModelOutput
from anyspark.server.app import build_app


class FakeBatchModel:
    """fake 模型：改写 prompt 返回新正文；审读走 review_chapter（无 LLM 判定时仍可跑）。"""

    model_name = "fake-batch"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        joined = "\n".join(m.content or "" for m in messages)
        self.prompts.append(joined)
        if "改写后正文" in joined:
            return ModelOutput(text="改写后的新正文内容。")
        if "硬伤数" in joined or "审读" in joined:
            return ModelOutput(text="硬伤数: 0\n本段通过。")
        return ModelOutput(text="好的。")


def _mk_chapters(client: TestClient, n: int = 3) -> list[str]:
    """建 n 章，返回 chapter_ids。"""
    ids = []
    for i in range(1, n + 1):
        r = client.post(
            "/api/chapters",
            json={"title": f"第{i}章", "content": f"第{i}章正文内容。"},
        )
        assert r.status_code in (200, 201), r.text
        ids.append(str(r.json()["id"]))
    return ids


def test_batch_templates_seeded() -> None:
    """预置批量改写/审读模板已种入。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=FakeBatchModel(), db_path=db))
    wfs = client.get("/api/workflows").json()
    names = {w["name"] for w in wfs}
    assert "批量改写" in names and "批量审读" in names
    # 结构断言：改写含 approval 闸门 + loop 集合遍历；审读无 approval
    rw_id = next(w["id"] for w in wfs if w["name"] == "批量改写")
    rw = client.get(f"/api/workflows/{rw_id}").json()
    kinds = [n["kind"] for n in rw["nodes"]]
    assert "approval" in kinds  # 重操作强制闸门（W2）
    loop = next(n for n in rw["nodes"] if n["kind"] == "loop")
    assert loop["params"]["collection_var"] == "chapter_ids"  # 集合遍历
    rv_id = next(w["id"] for w in wfs if w["name"] == "批量审读")
    rv = client.get(f"/api/workflows/{rv_id}").json()
    assert "approval" not in [n["kind"] for n in rv["nodes"]]  # 轻操作无闸门
    assert rw["description"] and rv["description"]


def test_batch_review_workflow_light() -> None:
    """批量审读：轻操作无 approval → 直接跑完（逐章审读报告落任务 results）。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=FakeBatchModel(), db_path=db))
    ids = _mk_chapters(client, 2)
    wfs = client.get("/api/workflows").json()
    wf_id = next(w["id"] for w in wfs if w["name"] == "批量审读")
    r = client.post(
        f"/api/workflows/{wf_id}/run",
        json={"book_id": "main", "params": {"chapter_ids": json.dumps(ids)}},
    )
    assert r.status_code == 200
    task_id = r.json()["task_id"]
    status = ""
    for _ in range(100):
        t = client.get(f"/api/workflows/tasks/{task_id}").json()
        status = t.get("status", "")
        if status in ("done", "failed"):
            break
        time.sleep(0.1)
    assert status == "done", f"审读任务未完成: {status}"
    # 逐章审读报告（review_chapter 产出）
    states = {s["node_id"]: s for s in t.get("node_states", [])}
    assert states["review"]["status"] == "done"
    assert "硬伤数" in states["review"]["output"] or states["review"]["output"].strip()


def test_batch_rewrite_workflow_approval_gate() -> None:
    """批量改写：重操作 → loop 前 approval 闸门（确认后才逐章覆盖）。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    model = FakeBatchModel()
    client = TestClient(build_app(model=model, db_path=db))
    ids = _mk_chapters(client, 2)
    wfs = client.get("/api/workflows").json()
    wf_id = next(w["id"] for w in wfs if w["name"] == "批量改写")
    r = client.post(
        f"/api/workflows/{wf_id}/run",
        json={
            "book_id": "main",
            "params": {
                "chapter_ids": json.dumps(ids),
                "instruction": "改成悬疑风格",
            },
        },
    )
    task_id = r.json()["task_id"]
    # 应停在 approval（waiting_approval，后台线程推进），未执行改写（prompts 无改写调用）
    t = {}
    for _ in range(50):
        t = client.get(f"/api/workflows/tasks/{task_id}").json()
        if t.get("status") == "waiting_approval":
            break
        time.sleep(0.1)
    assert t.get("status") == "waiting_approval", f"未停在闸门: {t.get('status')}"
    assert t.get("current_node_id") == "gate_confirm"
    assert not any("改写后正文" in p for p in model.prompts)  # 确认前未执行改写
    # 人工确认 → 逐章改写落盘
    r = client.post(f"/api/workflows/tasks/{task_id}/approve", json={"decision": "ok"})
    assert r.status_code == 200
    for _ in range(100):
        t = client.get(f"/api/workflows/tasks/{task_id}").json()
        if t.get("status") in ("done", "failed"):
            break
        time.sleep(0.1)
    assert t["status"] == "done", f"改写任务未完成: {t.get('error')}"
    # 章节被改写（write_chapter 落盘）
    chs = client.get("/api/chapters").json()
    assert any("改写后的新正文内容" in (c.get("content") or "") for c in chs)
    # 改写 agent 被调（每章一次）
    assert sum(1 for p in model.prompts if "改写后正文" in p) >= 2


def test_batch_rewrite_reject_aborts() -> None:
    """批量改写 approval 驳回 → 任务失败，章节未被覆盖。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=FakeBatchModel(), db_path=db))
    ids = _mk_chapters(client, 1)
    before = client.get("/api/chapters").json()
    wfs = client.get("/api/workflows").json()
    wf_id = next(w["id"] for w in wfs if w["name"] == "批量改写")
    r = client.post(
        f"/api/workflows/{wf_id}/run",
        json={"book_id": "main", "params": {"chapter_ids": json.dumps(ids), "instruction": "x"}},
    )
    task_id = r.json()["task_id"]
    for _ in range(20):
        t = client.get(f"/api/workflows/tasks/{task_id}").json()
        if t.get("status") == "waiting_approval":
            break
        time.sleep(0.1)
    r = client.post(f"/api/workflows/tasks/{task_id}/approve", json={"decision": "reject"})
    assert r.status_code == 200
    t = client.get(f"/api/workflows/tasks/{task_id}").json()
    assert t["status"] == "failed"
    assert "驳回" in t.get("error", "")
    # 章节未被改写
    after = client.get("/api/chapters").json()
    assert after == before


def test_batch_review_loop_items_keep_each_chapter() -> None:
    """S147 回归：批量审读 2 章 → loop items 保留**每章**审读报告（此前覆盖只留最后）。"""
    import json as _json

    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=FakeBatchModel(), db_path=db))
    ids = _mk_chapters(client, 2)
    wfs = client.get("/api/workflows").json()
    wf_id = next(w["id"] for w in wfs if w["name"] == "批量审读")
    r = client.post(
        f"/api/workflows/{wf_id}/run",
        json={"book_id": "main", "params": {"chapter_ids": json.dumps(ids)}},
    )
    task_id = r.json()["task_id"]
    status = ""
    for _ in range(100):
        t = client.get(f"/api/workflows/tasks/{task_id}").json()
        status = t.get("status", "")
        if status in ("done", "failed"):
            break
        time.sleep(0.1)
    assert status == "done", f"审读任务未完成: {status}"
    # loop 迭代明细：2 章各一条（每章 read/title/review 全保留，不是覆盖只留最后）
    loop = next(s for s in t.get("node_states", []) if s["node_id"] == "loop")
    out = _json.loads(loop["output"])
    assert len(out["items"]) == 2, f"应 2 章明细，实际 {len(out['items'])}"
    for item in out["items"]:
        assert item.get("review"), "每迭代应有审读报告"
        assert item.get("title"), "每迭代应有章名"
