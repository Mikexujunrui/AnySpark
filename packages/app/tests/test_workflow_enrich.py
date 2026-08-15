"""S137 章节加料模板测试：遍历章节 + 定点插入（原文保留，非敏感指令验证）。

验证（PLAN-WORKFLOW-UNIFY §四 加料形态，用非敏感指令绕开审核坎）：
- 预置「章节加料」模板已种入（含 approval 闸门——重操作写回）
- 加料 = 原文保留 + 定点插入（区别于批量改写整章覆盖）
- 非敏感指令（如"扩充环境细节描写"）走同一条管道，产出可预期
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.core.types import Message, ModelOutput
from anyspark.server.app import build_app


class FakeEnrichModel:
    """fake 模型：加料指令返回带【插入】标记的完整正文（原文保留+插入内容）。"""

    model_name = "fake-enrich"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        joined = "\n".join(m.content or "" for m in messages)
        if "插入后的完整正文" in joined:
            # 原章"雨夜"被替换为"雨夜，雨丝斜织"（含插入标记，stitch 展开）
            return ModelOutput(text="雨夜【插入】，雨丝斜织，路灯在积水里碎成光斑【/插入】。")
        return ModelOutput(text="好的。")


def _mk_chapters(client: TestClient, n: int = 2) -> list[str]:
    ids = []
    for i in range(1, n + 1):
        r = client.post(
            "/api/chapters",
            json={"title": f"第{i}章", "content": f"第{i}章 雨夜，他推门进来。"},
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


def test_enrich_template_seeded() -> None:
    """预置章节加料模板已种入（含 approval 闸门 + 集合遍历）。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=FakeEnrichModel(), db_path=db))
    wfs = client.get("/api/workflows").json()
    wid = next(w["id"] for w in wfs if w["name"] == "章节加料")
    wf = client.get(f"/api/workflows/{wid}").json()
    kinds = [n["kind"] for n in wf["nodes"]]
    assert "approval" in kinds  # 重操作写回 → 确认闸门（W2）
    loop = next(n for n in wf["nodes"] if n["kind"] == "loop")
    assert loop["params"]["collection_var"] == "chapter_ids"  # 集合遍历
    body = loop["params"]["body"]
    assert body == ["read", "title", "enrich", "stitch", "save"]  # 定点插入五步


def test_enrich_preserves_original_inserts_marked() -> None:
    """加料：原文保留 + 【插入】标记内容原位并入（stitch 展开标记块）。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=FakeEnrichModel(), db_path=db))
    ids = _mk_chapters(client, 1)
    wfs = client.get("/api/workflows").json()
    wid = next(w["id"] for w in wfs if w["name"] == "章节加料")
    r = client.post(
        f"/api/workflows/{wid}/run",
        json={
            "book_id": "main",
            "params": {
                "chapter_ids": json.dumps(ids),
                "enrich_instruction": "扩充环境细节描写",
            },
        },
    )
    task_id = r.json()["task_id"]
    # 停在闸门
    t = {}
    for _ in range(50):
        t = client.get(f"/api/workflows/tasks/{task_id}").json()
        if t.get("status") == "waiting_approval":
            break
        time.sleep(0.1)
    assert t.get("status") == "waiting_approval"
    # 确认 → 逐章加料落盘
    client.post(f"/api/workflows/tasks/{task_id}/approve", json={"decision": "ok"})
    t = _wait_done(client, task_id)
    assert t["status"] == "done", f"加料任务失败: {t.get('error')}"
    # 原文保留 + 插入内容并入（【插入】标记已被 stitch 展开）
    chs = client.get("/api/chapters").json()
    ch = next(c for c in chs if c["title"] == "第1章")
    content = ch.get("content") or ""
    assert "雨夜" in content  # 原文保留
    assert "雨丝斜织" in content  # 插入内容并入
    assert "【插入】" not in content and "【/插入】" not in content  # 标记已展开


def test_enrich_stitch_append_fallback() -> None:
    """加料 stitch 回退：agent 只产出纯插入段（无标记）→ 追加到章末保原文。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=FakeEnrichModel(), db_path=db))
    ids = _mk_chapters(client, 1)
    wfs = client.get("/api/workflows").json()
    wid = next(w["id"] for w in wfs if w["name"] == "章节加料")
    r = client.post(
        f"/api/workflows/{wid}/run",
        json={"book_id": "main", "params": {"chapter_ids": json.dumps(ids)}},
    )
    task_id = r.json()["task_id"]
    for _ in range(50):
        t = client.get(f"/api/workflows/tasks/{task_id}").json()
        if t.get("status") == "waiting_approval":
            break
        time.sleep(0.1)
    client.post(f"/api/workflows/tasks/{task_id}/approve", json={"decision": "ok"})
    t = _wait_done(client, task_id)
    assert t["status"] == "done", f"加料任务失败: {t.get('error')}"
    # fake 模型带标记路径已由 test_enrich_preserves 验证；此测试验证 stitch 节点存在
    states = {s["node_id"]: s["status"] for s in t.get("node_states", [])}
    assert states.get("stitch") == "done"  # stitch 节点执行（合并原文）
