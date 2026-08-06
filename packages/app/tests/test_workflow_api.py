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


def test_workflow_drafts_gate() -> None:
    client = _client()
    # 草稿闸门：列表为空 + 不存在草稿的操作返回 404
    assert client.get("/api/workflows/drafts").json() == []
    assert client.post("/api/workflows/drafts/nonexist/promote").status_code == 404
    assert client.delete("/api/workflows/drafts/nonexist").status_code == 404
