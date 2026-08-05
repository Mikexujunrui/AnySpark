"""S43 写作技巧（skill 式内容载体）测试：种子/CRUD/注入。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.align import (
    DEFAULT_SKILLS,
    WritingSkillStore,
    render_skill_index,
    render_skills_content,
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


def test_skills_seed_and_render() -> None:
    store = WritingSkillStore(Path(tempfile.mkdtemp()) / "sk.db")
    skills = store.list_skills()
    # 默认种子：粒度感知/认知边界/氛围克制
    assert len(skills) == len(DEFAULT_SKILLS)
    names = [s.name for s in skills]
    assert "粒度感知" in names and "角色认知边界" in names
    # 索引（描述常驻）
    idx = render_skill_index(skills)
    assert "写作技巧" in idx and "粒度感知" in idx and "认知" in idx
    # 内容（正文按需）
    content = render_skills_content(skills)
    assert "脉络越粗" in content  # 粒度感知正文
    # 关闭一条 → 内容不再注入
    store.update(skills[0].id, enabled=False)
    content2 = render_skills_content(store.list_skills())
    assert "脉络越粗" not in content2


def test_skills_api_and_injection() -> None:
    m = ProbeModel()
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=m, db_path=db))
    # 种子默认存在
    skills = client.get("/api/skills").json()
    assert len(skills) == len(DEFAULT_SKILLS)
    # 新增自定义技巧
    r = client.post(
        "/api/skills",
        json={
            "name": "对话节奏",
            "description": "对话要有留白与停顿",
            "content": "对话段落之间留出动作/环境描写间隔。",
        },
    )
    assert r.status_code == 200
    sid = r.json()["id"]
    # 开关
    rp = client.patch(f"/api/skills/{sid}", json={"enabled": False})
    assert rp.json()["enabled"] is False
    # 注入：chat 时 system prompt 含技巧索引+启用内容（粒度感知等默认技巧）
    client.post("/api/chat", json={"message": "写一段"})
    assert m.prompts, "应捕获 system prompt"
    last = m.prompts[-1]
    assert "写作技巧" in last and "粒度感知" in last
    # 删除
    assert client.delete(f"/api/skills/{sid}").json()["ok"] is True
    assert len(client.get("/api/skills").json()) == len(DEFAULT_SKILLS)
