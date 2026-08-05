"""S46 剧情计划测试：CRUD / 渲染推进 / API 注入。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.align import StoryPlanStore, render_plan
from anyspark.core.types import Message, ModelOutput
from anyspark.server.app import build_app


class ProbeModel:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        for m in messages:
            if m.role == "system":
                self.prompts.append(m.content)
                break
        return ModelOutput(text="好的。")


def test_plan_crud_and_render() -> None:
    store = StoryPlanStore(Path(tempfile.mkdtemp()) / "plan.db")
    assert store.list() == []
    store.add(2, "第二章 灯塔", "陈渡发现日记记载明天的天气")
    store.add(1, "第一章 雨夜", "陈渡接到委托")
    plans = store.list()
    assert len(plans) == 2
    # 渲染：只注入 planned，下一章=最小 order（第一章）
    block = render_plan(plans)
    assert "第一章 雨夜" in block and "下一章" in block
    # 标记第一章 done → 下一章变成第二章
    p1 = next(p for p in plans if p.chapter_order == 1)
    store.update(p1.id, status="done")
    block2 = render_plan(store.list())
    assert "第二章 灯塔" in block2 and "第一章" not in block2.split("下一章")[1]
    # 全部 done → 空
    p2 = next(p for p in store.list() if p.chapter_order == 2)
    store.update(p2.id, status="done")
    assert render_plan(store.list()) == ""


def test_plan_api_and_injection() -> None:
    m = ProbeModel()
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=m, db_path=db))
    # 新增计划
    r = client.post(
        "/api/plan", json={"chapter_order": 1, "title": "第一章 雨夜", "content": "陈渡接到委托"}
    )
    assert r.status_code == 200
    pid = r.json()["id"]
    assert len(client.get("/api/plan").json()) == 1
    # 注入：chat 时 system prompt 含计划块
    client.post("/api/chat", json={"message": "写一段"})
    assert m.prompts, "应捕获 system prompt"
    assert "剧情计划" in m.prompts[-1] and "第一章 雨夜" in m.prompts[-1]
    # 标记 done
    rp = client.patch(f"/api/plan/{pid}", json={"status": "done"})
    assert rp.json()["status"] == "done"
    # 删除
    assert client.delete(f"/api/plan/{pid}").json()["ok"] is True
    assert client.get("/api/plan").json() == []
