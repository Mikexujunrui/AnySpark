"""S138 阶段 C（PLAN-SCALE-SAFETY）测试：中规模中断→重启→续跑闭环。

验证（规划阶段 C 的自动化部分）：
- 大 loop（20 章）引擎稳定：无 approval 模板全量跑完
- 中断（request_stop → cancelled）→ 同 db 新实例（模拟服务重启）→ resume 续跑完成
- 断点续跑不重复处理：用「章节加料」验证——每章只写回一次（版本历史恰 1 条；
  若续跑重跑已 done 章节则该章会出现第 2 条版本记录）
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.core.types import Message, ModelOutput
from anyspark.server.app import build_app


class FakeSlowModel:
    """fake 模型：加料返回【插入】标记内容；图谱返回实体 JSON；带 50ms 延时。"""

    model_name = "fake-slow"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        time.sleep(0.05)
        joined = "\n".join(m.content or "" for m in messages)
        if "插入后的完整正文" in joined or "【加料指令】" in joined:
            return ModelOutput(text="原章内容【插入】新增细节【/插入】。")
        if "实体" in joined or "抽取" in joined:
            return ModelOutput(
                text='{"entities": [{"name": "角色A", "type": "角色", '
                '"description": "测试角色", "aliases": []}], '
                '"relations": [], "events": []}'
            )
        return ModelOutput(text="好的。")


def _mk_chapters(client: TestClient, n: int) -> list[str]:
    ids = []
    for i in range(1, n + 1):
        r = client.post(
            "/api/chapters",
            json={"title": f"章{i}", "content": f"章{i} 原章内容。"},
        )
        assert r.status_code in (200, 201), r.text
        ids.append(str(r.json()["id"]))
    return ids


def _wf_id(client: TestClient, name: str) -> str:
    wfs = client.get("/api/workflows").json()
    return str(next(w["id"] for w in wfs if w["name"] == name))


def _wait_status(
    client: TestClient, task_id: str, want: str, timeout: float = 30.0
) -> dict[str, object]:
    t: dict[str, object] = {}
    deadline = time.time() + timeout
    while time.time() < deadline:
        t = client.get(f"/api/workflows/tasks/{task_id}").json()
        if t.get("status") == want:
            return t
        time.sleep(0.1)
    raise AssertionError(f"任务未达 {want}（当前 {t.get('status')}）: {t}")


def test_large_loop_runs_to_done() -> None:
    """20 章大 loop（无 approval）全量跑完，引擎稳定；实体同名合并（图库去重）。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=FakeSlowModel(), db_path=db))
    ids = _mk_chapters(client, 20)
    wid = _wf_id(client, "图谱抽取")
    r = client.post(
        f"/api/workflows/{wid}/run",
        json={"book_id": "main", "params": {"chapter_ids": json.dumps(ids)}},
    )
    task_id = r.json()["task_id"]
    t = _wait_status(client, task_id, "done")
    assert t["status"] == "done"
    ents = client.get("/api/graph/entities", params={"book_id": "main"}).json()
    assert len(ents) == 1, "20 章同名实体应合并为 1 条（图库按名去重）"
    assert ents[0]["name"] == "角色A"


def test_interrupt_then_restart_resume_no_duplicate_write() -> None:
    """加料 loop 中途中断 → 同 db 新实例 resume → 续跑完成且每章只写回一次。

    用「章节加料」验证断点续跑不重跑：每章版本历史恰 1 条（note 带任务标识）；
    若续跑重跑已 done 章节，该章会出现第 2 条版本记录。
    """
    db = Path(tempfile.mkdtemp()) / "t.db"
    client1 = TestClient(build_app(model=FakeSlowModel(), db_path=db))
    ids = _mk_chapters(client1, 20)
    wid = _wf_id(client1, "章节加料")
    r = client1.post(
        f"/api/workflows/{wid}/run",
        json={"book_id": "main", "params": {"chapter_ids": json.dumps(ids)}},
    )
    task_id = r.json()["task_id"]
    # 等停在 approval 闸门（加料重操作带确认）
    _wait_status(client1, task_id, "waiting_approval", timeout=15)
    # 引擎 approve（线程内跑 run_task 进 loop；主线程稍后 stop 同一引擎）
    engine1 = client1.app.state.deps.workflow_engine  # type: ignore[attr-defined]

    import contextlib

    def _approve() -> None:
        # 中断路径可能抛控制异常（_StopRequested），抑制即可
        with contextlib.suppress(Exception):
            engine1.approve(task_id, decision="ok")

    threading.Thread(target=_approve, daemon=True).start()
    time.sleep(0.35)  # loop 跑几章（每章 ~50ms+写回）
    engine1.request_stop()  # 中断（真实场景 = 服务进程被杀）
    t = _wait_status(client1, task_id, "cancelled", timeout=15)
    assert t["status"] == "cancelled"
    mid_versions = sum(
        len(client1.get(f"/api/chapters/{cid}").json().get("versions") or []) for cid in ids
    )
    assert 0 < mid_versions < 20, f"应在中途停下（已写回 {mid_versions}/20）"

    # ---- 模拟服务重启：同 db 新实例 ----
    client2 = TestClient(build_app(model=FakeSlowModel(), db_path=db))
    t2 = client2.get(f"/api/workflows/tasks/{task_id}").json()
    assert t2["status"] == "cancelled"  # DB 持久化，重启后状态可见
    client2.post(f"/api/workflows/tasks/{task_id}/resume")
    t3 = _wait_status(client2, task_id, "done")
    assert t3["status"] == "done"
    # 每章版本恰 1 条 → 续跑不重跑已 done 章节
    for cid in ids:
        ch = client2.get(f"/api/chapters/{cid}").json()
        assert len(ch.get("versions") or []) == 1, (
            f"章节 {ch['title']} 版本数 {len(ch.get('versions') or [])}，续跑应不重复写回"
        )
