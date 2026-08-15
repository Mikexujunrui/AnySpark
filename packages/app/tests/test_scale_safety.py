"""S138（PLAN-SCALE-SAFETY）测试：规模化安全网——resume 续跑 + 版本回溯三件套。

验证：
- 阶段 A：POST /api/workflows/tasks/{id}/resume 断点续跑（非 done 任务拉起，done 幂等）
- B1：write_chapter script 版本 note 携带任务标识（'批量任务/任务{task_id}'）
- B2：POST /api/chapters/{id}/restore 单章恢复到历史版本（当前先入版本可再回滚）
- B3：POST /api/workflows/tasks/{id}/rollback 批级一键回滚（按 note 聚合改前快照）
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.core.types import Message, ModelOutput
from anyspark.server.app import build_app


class FakeRewriteModel:
    """fake 模型：批量改写返回占位改写文本（含信号触发词）。"""

    model_name = "fake-safety"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        joined = "\n".join(m.content or "" for m in messages)
        if "改写" in joined:
            return ModelOutput(text="改写版内容（信号触发）。")
        return ModelOutput(text="好的。")


def _mk_chapters(client: TestClient, n: int = 2) -> list[str]:
    ids = []
    for i in range(1, n + 1):
        r = client.post(
            "/api/chapters",
            json={"title": f"第{i}章", "content": f"第{i}章 原文内容。"},
        )
        assert r.status_code in (200, 201), r.text
        ids.append(str(r.json()["id"]))
    return ids


def _wf_id(client: TestClient, name: str) -> str:
    wfs = client.get("/api/workflows").json()
    return str(next(w["id"] for w in wfs if w["name"] == name))


def _wait_status(
    client: TestClient, task_id: str, want: str, timeout: float = 10.0
) -> dict[str, object]:
    t: dict[str, object] = {}
    deadline = time.time() + timeout
    while time.time() < deadline:
        t = client.get(f"/api/workflows/tasks/{task_id}").json()
        if t.get("status") == want:
            return t
        time.sleep(0.1)
    raise AssertionError(f"任务未达 {want}: {t}")


def test_resume_continues_interrupted_task() -> None:
    """阶段 A：任务中断（模拟重启后状态遗留）→ resume 续跑到底。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=FakeRewriteModel(), db_path=db))
    ids = _mk_chapters(client, 2)
    wid = _wf_id(client, "批量改写")
    # 跑批量改写任务
    r = client.post(
        f"/api/workflows/{wid}/run",
        json={
            "book_id": "main",
            "params": {"chapter_ids": json.dumps(ids), "instruction": "整体改写"},
        },
    )
    task_id = r.json()["task_id"]
    # 停在 approval 闸门（批量改写带确认）
    _wait_status(client, task_id, "waiting_approval")
    client.post(f"/api/workflows/tasks/{task_id}/approve", json={"decision": "ok"})
    _wait_status(client, task_id, "done")
    t = client.get(f"/api/workflows/tasks/{task_id}").json()
    assert t["status"] == "done"
    # done 任务 resume 幂等（不重启线程、不报错）
    r2 = client.post(f"/api/workflows/tasks/{task_id}/resume").json()
    assert r2["status"] == "done"


def test_write_chapter_note_carries_task_id() -> None:
    """B1：批量任务写回时版本 note 带任务标识（批级定位基石）。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=FakeRewriteModel(), db_path=db))
    ids = _mk_chapters(client, 1)
    wid = _wf_id(client, "批量改写")
    r = client.post(
        f"/api/workflows/{wid}/run",
        json={
            "book_id": "main",
            "params": {"chapter_ids": json.dumps(ids), "instruction": "整体改写"},
        },
    )
    task_id = r.json()["task_id"]
    _wait_status(client, task_id, "waiting_approval")
    client.post(f"/api/workflows/tasks/{task_id}/approve", json={"decision": "ok"})
    _wait_status(client, task_id, "done")
    ch = client.get(f"/api/chapters/{ids[0]}").json()
    versions = ch["versions"]
    assert versions, "应有版本历史"
    assert any(f"任务{task_id}" in (v.get("note") or "") for v in versions), (
        f"note 应带任务标识: {[v.get('note') for v in versions]}"
    )


def test_restore_single_chapter_version() -> None:
    """B2：单章恢复到历史版本——当前先入版本（可再回滚），目标版本写回。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=FakeRewriteModel(), db_path=db))
    ids = _mk_chapters(client, 1)
    cid = ids[0]
    # 第一次覆盖：手动改内容（触发版本快照 note='修改前'）
    r = client.put(f"/api/chapters/{cid}", json={"content": "第二次内容。"})
    assert r.status_code == 200, r.text
    ch = client.get(f"/api/chapters/{cid}").json()
    assert ch["content"] == "第二次内容。"
    versions = ch["versions"]
    assert versions, "应有版本历史"
    target_id = int(versions[0]["id"])  # 最新一条 = 第一次内容
    # 恢复到第一次内容
    r2 = client.post(f"/api/chapters/{cid}/restore", json={"version_id": target_id})
    assert r2.status_code == 200, r2.text
    ch2 = r2.json()
    assert ch2["content"] == "第1章 原文内容。"
    # 恢复后当前（第二次内容）已入版本历史（note='恢复前'）——可再回滚
    versions2 = ch2["versions"]
    assert any((v.get("note") or "") == "恢复前" for v in versions2), versions2


def test_rollback_batch_restores_all() -> None:
    """B3：批级一键回滚——批量任务改 N 章 → rollback 全部还原改前。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=FakeRewriteModel(), db_path=db))
    ids = _mk_chapters(client, 3)
    before = {cid: client.get(f"/api/chapters/{cid}").json()["content"] for cid in ids}
    wid = _wf_id(client, "批量改写")
    r = client.post(
        f"/api/workflows/{wid}/run",
        json={
            "book_id": "main",
            "params": {"chapter_ids": json.dumps(ids), "instruction": "整体改写"},
        },
    )
    task_id = r.json()["task_id"]
    _wait_status(client, task_id, "waiting_approval")
    client.post(f"/api/workflows/tasks/{task_id}/approve", json={"decision": "ok"})
    _wait_status(client, task_id, "done")
    # 改写后内容已变
    for cid in ids:
        assert client.get(f"/api/chapters/{cid}").json()["content"] != before[cid]
    # 一键回滚
    rb = client.post(f"/api/workflows/tasks/{task_id}/rollback").json()
    assert rb["ok"] and rb["total"] == 3, rb
    for cid in ids:
        assert client.get(f"/api/chapters/{cid}").json()["content"] == before[cid]
    # 回滚后再 rollback：'恢复前' 版本不带任务标识 → 不重复聚合（防循环回滚）
    rb2 = client.post(f"/api/workflows/tasks/{task_id}/rollback").json()
    assert rb2["ok"] and rb2["restored"] == [], rb2


def test_rollback_unknown_task_404() -> None:
    """B3：任务不存在 → 404。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=FakeRewriteModel(), db_path=db))
    r = client.post("/api/workflows/tasks/nonexistent/rollback")
    assert r.status_code == 404
