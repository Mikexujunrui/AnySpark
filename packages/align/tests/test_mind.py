"""S50 心智模型=会话规划器测试：collab 条目 → 协作策略；文风不再注入写作。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.align import ManualEntry, ManualStore, MindPlanner
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


def _store_with_entries(entries: list[ManualEntry]) -> ManualStore:
    store = ManualStore(Path(tempfile.mkdtemp()) / "m.db")
    for e in entries:
        store.add(e)
    return store


def test_planner_empty_no_plan() -> None:
    store = _store_with_entries([])
    plan = MindPlanner(store).plan("main")
    assert plan.agency_level is None
    assert plan.collab_notes == []
    assert plan.collab_block() == ""


def test_planner_collab_infers_agency_and_notes() -> None:
    store = _store_with_entries(
        [
            ManualEntry(content="先给方案再动笔，不要直接写", category="collab"),
            ManualEntry(content="写前先问我确认一下方向", category="collab"),
        ]
    )
    plan = MindPlanner(store).plan("main", base_agency=2)
    # 两个"要确认"条目 → 档位降
    assert plan.agency_level is not None and plan.agency_level <= 1
    assert plan.collab_notes, "协作约定应提取"
    block = plan.collab_block()
    assert "会话协作约定" in block and "先给方案再动笔" in block


def test_planner_agency_up_hint() -> None:
    store = _store_with_entries(
        [ManualEntry(content="直接写别啰嗦，一口气给我全章", category="collab")]
    )
    plan = MindPlanner(store).plan("main", base_agency=2)
    # "直接写/别啰嗦" → 档位升
    assert plan.agency_level is not None and plan.agency_level >= 3


def test_style_entries_injected_as_guidance() -> None:
    """S53：文风偏好保留指导性——以心智指导块注入（渐进式披露，非全量堆砌）。"""
    m = ProbeModel()
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=m, db_path=db))
    # 文风条目 + 协作条目
    client.post(
        "/api/manual",
        json={"content": "喜欢白话文风，语言要克制", "category": "style"},
    )
    client.post(
        "/api/manual",
        json={"content": "先给方案再动笔", "category": "collab"},
    )
    client.post("/api/chat", json={"message": "写一段"})
    assert m.prompts
    last = m.prompts[-1]
    # 协作约定注入（心智=会话规划器）
    assert "会话协作约定" in last and "先给方案再动笔" in last
    # 文风偏好注入（S53：指导性保留，心智指导块）
    assert "用户文风偏好" in last and "喜欢白话文风" in last
    assert "写作说明书" not in last and "本书写作偏好" not in last  # 仍是模块化块，非全量说明书


def test_style_pref_matches_skill() -> None:
    """S53 心智与能力联动：用户文风偏好 → 匹配对应叙事技巧注入。

    作者偏好白话 → 白话相关 skill（tags 含'白话'）被选中注入。
    """
    from anyspark.align import (
        WritingSkillStore,
        render_skills_content,
        select_skills_for,
    )

    store = WritingSkillStore(Path(tempfile.mkdtemp()) / "sk.db")
    # 补到 6 条以上（触发按需选取），其中一条 tags 含'白话'
    store.add(
        name="白话叙事",
        description="白话文风：口语化、平实、不文绉绉",
        content="用口语化短句与平实词汇，避免文言腔；句子结构简单直接。",
        example="'他愣了一下'而非'他怔忡半晌'。",
        tags="白话",
    )
    skills = store.list_skills()
    # 用户偏好'白话' → 优先选中白话 skill
    sel = select_skills_for(skills, context="", prefs=["白话"], limit=3)
    assert any(s.name == "白话叙事" for s in sel), "白话偏好应命中白话 skill"
    content = render_skills_content(skills, prefs=["白话"])
    assert "白话叙事" in content and "口语化" in content
    # 无偏好 → 保底前 limit（不含白话 skill，若排序不在前）
    sel2 = select_skills_for(skills, context="", prefs=None, limit=3)
    assert sel2


def test_habit_entries_injected() -> None:
    """S53：习惯条目保留指导性（心智指导块注入）。"""
    m = ProbeModel()
    db = Path(tempfile.mkdtemp()) / "t3.db"
    client = TestClient(build_app(model=m, db_path=db))
    client.post(
        "/api/manual",
        json={"content": "每章两千字左右", "category": "habit"},
    )
    client.post("/api/chat", json={"message": "写"})
    assert m.prompts
    last = m.prompts[-1]
    assert "用户写作习惯" in last and "每章两千字左右" in last


def test_manual_category_api() -> None:
    m = ProbeModel()
    db = Path(tempfile.mkdtemp()) / "t2.db"
    client = TestClient(build_app(model=m, db_path=db))
    # 新增带 category
    r = client.post("/api/manual", json={"content": "多问再写", "category": "collab"})
    assert r.status_code == 200
    eid = r.json()["id"]
    assert r.json()["category"] == "collab"
    # 修改 category
    r2 = client.patch(f"/api/manual/{eid}", json={"category": "style"})
    assert r2.json()["category"] == "style"
    # 非法 category 回退
    r3 = client.post("/api/manual", json={"content": "x", "category": "bogus"})
    assert r3.json()["category"] == "style"
