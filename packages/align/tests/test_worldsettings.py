"""S41 设定档测试：CRUD / 渲染 / API 注入。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.align import (
    WorldSetting,
    WorldSettingStore,
    render_settings,
    render_settings_adaptive,
)
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


def test_settings_crud_and_render() -> None:
    store = WorldSettingStore(Path(tempfile.mkdtemp()) / "ws.db")
    assert store.list() == []
    s = store.add("猎人职业以诅咒为根源能量，滥用会反噬。", category="能力体系", name="猎人职业")
    assert s.source == "manual"
    assert len(store.list()) == 1
    # 更新
    store.update(s.id, content="猎人职业以诅咒为根源能量。")
    got = store.get(s.id)
    assert got is not None and "滥用" not in got.content
    # 渲染
    block = render_settings(store.list())
    assert "本书设定档" in block and "猎人职业" in block and "能力体系" in block
    # 删除
    assert store.delete(s.id)
    assert store.list() == []


def test_settings_api_and_injection() -> None:
    m = ProbeModel()
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=m, db_path=db))
    # 新增设定
    r = client.post(
        "/api/settings",
        json={
            "content": "见习猎人可规避必死局面，欺骗同级及以下敌人。",
            "category": "能力体系",
            "name": "假死",
        },
    )
    assert r.status_code == 200
    sid = r.json()["id"]
    assert len(client.get("/api/settings").json()) == 1
    # 修改
    rp = client.patch(f"/api/settings/{sid}", json={"content": "自动规避必死局面。"})
    assert "自动规避" in rp.json()["content"]
    # 注入：chat 时 system prompt 含设定档
    client.post("/api/chat", json={"message": "写一段"})
    assert m.prompts, "应捕获 system prompt"
    assert "本书设定档" in m.prompts[-1] and "假死" in m.prompts[-1]
    # 删除
    assert client.delete(f"/api/settings/{sid}").json()["ok"] is True
    assert client.get("/api/settings").json() == []


def test_render_settings_adaptive_full_below_threshold() -> None:
    """≤20 条：全量渲染（与 render_settings 一致）。"""
    entries = [
        WorldSetting(content=f"设定{i}", category="世界观", name=f"名{i}") for i in range(5)
    ]
    full = render_settings(entries)
    adaptive = render_settings_adaptive(entries)
    assert adaptive == full
    assert "设定0" in adaptive and "read_setting" not in adaptive


def test_render_settings_adaptive_index_over_threshold() -> None:
    """超 20 条：注入索引（含 read_setting 提示 + 截断），不注入全量。"""
    entries = [
        WorldSetting(
            content=(
                f"这是第{i}号设定的超长内容用来验证渐进式披露时的截断行为"
                "确保索引足够轻量不占上下文且写作引用前先用工具查证具体条目"
            ),
            category="能力体系",
            name=f"技{i}",
        )
        for i in range(25)
    ]
    adaptive = render_settings_adaptive(entries)
    assert "共 25 条" in adaptive
    assert "read_setting" in adaptive  # 按需查询提示
    assert "技0" in adaptive and "技24" in adaptive
    assert "先用工具查证具体条目" not in adaptive  # 内容超 40 字被截断
    # 全量版本不含索引提示
    full = render_settings(entries)
    assert "read_setting" not in full
