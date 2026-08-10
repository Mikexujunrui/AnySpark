"""S72 文风参考 → skill 提炼链路测试：material_id 取原文 + skill_refine 工具。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from anyspark.core.types import Message, ModelOutput
from anyspark.server.workspace import Workspace


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "t.db"


def _ws() -> Workspace:
    return Workspace(root=Path(tempfile.mkdtemp()) / "ws")


class _ScriptedModel:
    """消化返回摘要卡；skill 提炼返回候选。"""

    model_name = "scripted"

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        prompt = messages[0].content or ""
        self.prompts.append(prompt)
        if "资料消化器" in prompt:
            return ModelOutput(
                text=json.dumps(
                    {
                        "title": "文风卡",
                        "topic": "t",
                        "key_points": ["短句"],
                        "key_settings": [],
                        "characters": [],
                        "terms": [],
                    }
                )
            )
        return ModelOutput(
            text=json.dumps(
                {
                    "candidates": [
                        {
                            "name": "克制短句",
                            "description": "用短句推进，留白",
                            "content": "技法内容",
                            "example": "原文案例",
                            "tags": ["文风"],
                        }
                    ]
                }
            )
        )


def test_skills_generate_with_material_id() -> None:
    """上传 style 资料（含原文）→ /api/skills/generate 用 material_id 取原文提炼。"""
    from fastapi.testclient import TestClient

    from anyspark.server.app import build_app

    client = TestClient(build_app(model=_ScriptedModel(), db_path=_db(), workspace=_ws()))
    # 上传 style 资料（purpose=style）
    r = client.post(
        "/api/materials",
        json={"text": "雾城雨夜，他沉默地站着。", "title": "参考书", "purpose": "style"},
    )
    assert r.status_code == 200, r.text
    mid = r.json()["id"]

    # 用 material_id 提炼（不带 source_text）
    r = client.post("/api/skills/generate", json={"material_id": mid})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["candidates"][0]["name"] == "克制短句"

    # material_id 不存在 → 404
    r = client.post("/api/skills/generate", json={"material_id": "nope"})
    assert r.status_code == 404

    # 两者都空 → 400
    r = client.post("/api/skills/generate", json={})
    assert r.status_code == 400


def test_skill_refine_tool() -> None:
    """skill_refine 工具：material_id 取原文提炼候选（不自动入库）。"""
    from anyspark.server.tools_domain import make_skill_refine_implementer

    class _FakeGenerator:
        def generate(
            self, source_text: str, hint: str = "", max_items: int = 5, mode: str = "writing"
        ) -> list[dict[str, str]]:
            assert "雨夜" in source_text  # 原文来自资料
            return [{"name": "克制短句", "description": "短句推进留白"}]

    class _FakeMaterials:
        def get(self, mid: str) -> object | None:
            if mid == "m1":
                from anyspark.template.materials import MaterialCard

                return MaterialCard(
                    title="参考书",
                    topic="t",
                    purpose="style",
                    key_points=[],
                    key_settings=[],
                    characters=[],
                    terms=[],
                    source_text="雾城雨夜，他沉默地站着。",
                )
            return None

    spec, impl = make_skill_refine_implementer(_FakeGenerator(), _FakeMaterials())
    r = impl(spec, {"material_id": "m1"})
    assert r.ok is True
    assert "克制短句" in r.content
    assert "待人工确认" in r.content  # 人工确认闸门
    # 缺参数
    r2 = impl(spec, {})
    assert r2.ok is False
    # 资料不存在
    r3 = impl(spec, {"material_id": "nope"})
    assert r3.ok is False and "不存在" in r3.content
