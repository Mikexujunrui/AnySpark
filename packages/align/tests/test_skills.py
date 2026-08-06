"""S50 叙事技巧（skill 重构）测试：种子/CRUD/注入/渐进式披露。"""

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
    # S50 新种子：叙事技巧（镜头感/对白机锋/节奏控制），旧三条已归位移除
    assert len(skills) == len(DEFAULT_SKILLS)
    names = [s.name for s in skills]
    assert "镜头感与视角" in names and "对白机锋" in names and "节奏控制" in names
    assert "粒度感知" not in names and "角色认知边界" not in names
    # 种子带情形案例（example）与场景标签（tags）
    assert all(s.example for s in skills), "叙事技巧种子应带情形案例"
    assert all(s.tags for s in skills), "叙事技巧种子应带场景标签"
    # 索引（描述常驻）
    idx = render_skill_index(skills)
    assert "叙事技巧" in idx and "镜头感与视角" in idx
    # 内容（技法 + 案例注入）
    content = render_skills_content(skills)
    assert "把叙事当作镜头" in content  # 技法正文
    assert "例：" in content  # 情形案例随内容注入
    # 关闭一条 → 内容不再注入
    store.update(skills[0].id, enabled=False)
    content2 = render_skills_content(store.list_skills())
    assert "镜头语言" not in content2


def test_skills_select_by_tags() -> None:
    """渐进式披露：技巧多后按 tags 匹配会话意图选取，不全量注入。"""
    store = WritingSkillStore(Path(tempfile.mkdtemp()) / "sk2.db")
    store.list_skills()  # 触发种子
    # 补到 6 条（超过全量阈值 5），触发按需选取
    for i in range(3):
        store.add(
            name=f"技巧{i}",
            description=f"描述{i}",
            content=f"内容{i}",
            example="例",
            tags="打斗" if i % 2 else "心理",
        )
    skills = store.list_skills()
    # 会话含"打斗" → 只选中打斗标签的技巧（≤3 条）
    sel = render_skills_content(skills, context="写一场雨夜打斗", limit=3)
    assert "内容0" not in sel  # 心理标签的不该被选中
    assert "例：" in sel
    # 无 context → 保底前 3 条（不全量）
    sel2 = render_skills_content(skills, context="", limit=3)
    assert len(sel2) > 0


def test_skills_api_and_injection() -> None:
    m = ProbeModel()
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=m, db_path=db))
    # 种子默认存在
    skills = client.get("/api/skills").json()
    assert len(skills) == len(DEFAULT_SKILLS)
    # 新增自定义技巧（带案例与标签）
    r = client.post(
        "/api/skills",
        json={
            "name": "对话留白",
            "description": "对话要有留白与停顿",
            "content": "对话段落之间留出动作/环境描写间隔。",
            "example": "他说完便沉默，只有杯沿的水汽在动。",
            "tags": "对白",
        },
    )
    assert r.status_code == 200
    sid = r.json()["id"]
    assert r.json()["example"] and r.json()["tags"] == "对白"
    # 开关
    rp = client.patch(f"/api/skills/{sid}", json={"enabled": False})
    assert rp.json()["enabled"] is False
    # 注入：chat 时 system prompt 含叙事技巧索引+启用内容（镜头感等默认技巧）
    client.post("/api/chat", json={"message": "写一段"})
    assert m.prompts, "应捕获 system prompt"
    last = m.prompts[-1]
    assert "叙事技巧" in last and "镜头感与视角" in last
    # 删除
    assert client.delete(f"/api/skills/{sid}").json()["ok"] is True
    assert len(client.get("/api/skills").json()) == len(DEFAULT_SKILLS)


def test_skills_legacy_seed_migration() -> None:
    """S50：旧库（粒度感知等旧种子）重建为新叙事技巧种子。"""
    db = Path(tempfile.mkdtemp()) / "legacy.db"
    store = WritingSkillStore(db)
    # 模拟旧库：先删新种子，插入旧种子特征名
    for s in store.list_skills():
        store.delete(s.id)
    import sqlite3 as _sqlite3
    import uuid as _uuid

    conn = _sqlite3.connect(str(db))
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        "INSERT INTO writing_skills (id, name, description, content, enabled, "
        "order_index, created_at) VALUES (?,?,?,?,1,0,?)",
        (_uuid.uuid4().hex, "粒度感知", "旧", "旧内容", now),
    )
    conn.commit()
    conn.close()
    # 重建后：旧种子被清除，新种子重播
    store2 = WritingSkillStore(db)
    names = [s.name for s in store2.list_skills()]
    assert "粒度感知" not in names
    assert "镜头感与视角" in names
