"""S74c 心智变更通知 API 测试：/api/manual/notices + 会话注入提醒。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from anyspark.core.types import Message, ModelOutput


class ProbeModel:
    def __init__(self) -> None:
        self.model_name = "probe"
        self.prompts: list[str] = []

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        self.prompts.append(messages[0].content or "")
        return ModelOutput(text="好的。")


def test_notices_api_and_injection() -> None:
    """修改心智 → 通知可见（API）+ 会话注入提醒块 + 注入后标已读。"""
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    model = ProbeModel()
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=model, db_path=db))

    # 建一条 + 修改（触发通知）
    r = client.post("/api/manual", json={"content": "对话克制", "category": "style"})
    eid = r.json()["id"]
    client.patch(f"/api/manual/{eid}", json={"content": "对话克制，少用感叹号"})

    # API 可见
    n = client.get("/api/manual/notices").json()
    assert len(n) == 1
    assert n[0]["action"] == "update"
    assert n[0]["old_content"] == "对话克制"
    assert "感叹号" in n[0]["new_content"]

    # 会话注入提醒块（agent 读到）+ 注入后标已读（S158c 标题改为「通知」）
    client.post("/api/chat", json={"message": "写一段"})
    joined = "\n".join(model.prompts)
    assert "# 通知" in joined
    assert "对话克制" in joined and "感叹号" in joined
    n_after = client.get("/api/manual/notices").json()
    assert len(n_after) == 1 and n_after[0]["read"] == 1  # 已标读（未读为空）

    # 删除也通知
    client.delete(f"/api/manual/{eid}")
    n2 = client.get("/api/manual/notices").json()
    assert len(n2) == 2  # update + delete 都留痕
    assert n2[0]["action"] == "delete"  # 最新在前
