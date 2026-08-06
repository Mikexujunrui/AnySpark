"""S50 氛围维度内容化 + 数值语义化测试：维度 CRUD / 注入语义 / API。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.align import DEFAULT_MOOD_DIMS, MoodDimStore, build_mood_block
from anyspark.core.types import Message, ModelOutput
from anyspark.server.app import build_app


def test_mood_seed_and_semantic_render() -> None:
    store = MoodDimStore(Path(tempfile.mkdtemp()) / "mood.db")
    dims = store.list_dims()
    # 默认 4 维种子
    assert len(dims) == len(DEFAULT_MOOD_DIMS)
    keys = {d.key for d in dims}
    assert {"tension", "warmth", "calm", "dread"} <= keys
    # 数值语义化：不进模型
    block = build_mood_block({"tension": 80}, dims)
    assert "紧张感：较强" in block
    assert "80" not in block  # 工程量纲不裸传
    # 每档程度词
    assert "极轻微" in build_mood_block({"warmth": 10}, dims)
    assert "中等" in build_mood_block({"calm": 55}, dims)
    assert "强烈" in build_mood_block({"dread": 95}, dims)
    # 维度描述+情景样例随注入（内容化：可编辑）
    assert "短促节奏" in build_mood_block({"tension": 80}, dims)


def test_mood_dim_crud_and_skip_disabled() -> None:
    store = MoodDimStore(Path(tempfile.mkdtemp()) / "mood2.db")
    # 新增维度（内容化：用户可扩展）
    d = store.add("hope", "希望感", "明亮、向上的暗示", "绝处逢生")
    assert d is not None and d.key == "hope"
    assert store.get_by_key("hope") is not None
    # 重复 key 拒绝
    assert store.add("hope", "重复") is None
    # 开关：禁用后不注入
    block_on = build_mood_block({"hope": 70}, store.list_dims())
    assert "希望感：较强" in block_on
    store.update(d.id, enabled=False)
    block_off = build_mood_block({"hope": 70}, store.list_dims())
    assert "希望感" not in block_off
    # 删除
    assert store.delete(d.id) is True


def test_mood_api() -> None:
    m = ProbeModel()
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=m, db_path=db))
    # 默认维度列表
    dims = client.get("/api/mood/dims").json()
    assert len(dims) == len(DEFAULT_MOOD_DIMS)
    # 新增
    r = client.post(
        "/api/mood/dims",
        json={"key": "hope", "label": "希望感", "description": "明亮向上", "example": "绝处逢生"},
    )
    assert r.status_code == 200
    did = r.json()["id"]
    # 注入：tension 80 → 语义化（无裸数值）
    client.post("/api/chat", json={"message": "写", "mood": {"tension": 80}})
    assert m.prompts
    assert "紧张感：较强" in m.prompts[-1] and "80/100" not in m.prompts[-1]
    # 开关/删除
    rp = client.patch(f"/api/mood/dims/{did}", json={"enabled": False})
    assert rp.json()["enabled"] is False
    assert client.delete(f"/api/mood/dims/{did}").json()["ok"] is True


class ProbeModel:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        for m in messages:
            if m.role == "system":
                self.prompts.append(m.content)
                break
        return ModelOutput(text="好的。")
