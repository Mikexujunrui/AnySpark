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


def test_planner_collab_notes_disclosed() -> None:
    """S62：档位不再由关键词启发式推断（建议不自动应用）——collab 条目只做披露。"""
    store = _store_with_entries(
        [
            ManualEntry(content="先给方案再动笔，不要直接写", category="collab"),
            ManualEntry(content="写前先问我确认一下方向", category="collab"),
        ]
    )
    plan = MindPlanner(store).plan("main", base_agency=2)
    # 不再推断档位（用户主权：建议走 L2 LLM，不自动应用）
    assert plan.agency_level is None
    assert plan.collab_notes, "协作约定仍披露"
    block = plan.collab_block()
    assert "会话协作约定" in block and "先给方案再动笔" in block


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
    """S61：心智偏好不再自动选技巧注入写作调用——写作调用只接收主循环点名。

    （S53 原自动匹配已删：写作调用是被执行方，不自行按 prefs 选。心智偏好
    由主循环吸收后，通过 write_chapter 的 skills 参数显式点名传达。）
    """
    from anyspark.align import (
        WritingSkillStore,
        render_skills_by_name,
    )

    store = WritingSkillStore(Path(tempfile.mkdtemp()) / "sk.db")
    store.add(
        name="白话叙事",
        description="白话文风：口语化、平实、不文绉绉",
        content="用口语化短句与平实词汇，避免文言腔；句子结构简单直接。",
        example="'他愣了一下'而非'他怔忡半晌'。",
        tags="白话",
    )
    skills = store.list_skills()
    # 未点名 → 不注入（即使 prefs 有白话——写作调用不自行选）
    assert render_skills_by_name(skills, []) == ""
    # 主循环点名白话叙事 → 注入完整内容
    content = render_skills_by_name(skills, ["白话叙事"])
    assert "白话叙事" in content and "口语化" in content
    # 点名不存在的 → 空
    assert render_skills_by_name(skills, ["不存在的技巧"]) == ""


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


def test_planner_context_prefers_relevant_entries() -> None:
    """S61 渐进式披露：心智条目按本轮 context 动态选取（相关条目优先）。"""
    from anyspark.align.mind import _key_entries

    entries = [
        ManualEntry(content="打斗场景多用短句和动作动词", category="style", confidence=0.5),
        ManualEntry(content="对白要克制含蓄", category="style", confidence=0.9),
        ManualEntry(content="环境描写少用形容词堆砌", category="style", confidence=0.8),
    ]
    # context 命中"打斗/动作" → 打斗条目排最前（尽管置信度最低）
    sel = _key_entries(entries, limit=2, context="写一场打斗动作戏")
    assert sel[0].content.startswith("打斗")
    # 无 context → 纯置信度排序
    sel2 = _key_entries(entries, limit=2, context="")
    assert sel2[0].content.startswith("对白")


def test_planner_context_reaches_session_plan() -> None:
    """S61：MindPlanner.plan(context) 把动态选取落到 SessionPlan（截断时相关优先）。"""
    entries = [ManualEntry(content="战斗场景要干脆利落", category="style", confidence=0.3)]
    # 5 条高置信但不相关的条目——无 context 时它们占满前 5，相关条目被挤出
    for i in range(5):
        entries.append(
            ManualEntry(content=f"日常对白要细腻温馨{i}", category="style", confidence=0.9)
        )
    store = _store_with_entries(entries)
    # 无 context：相关条目（conf 0.3）被挤出前 5
    plan0 = MindPlanner(store).plan("main")
    assert not any(p.startswith("战斗") for p in plan0.style_prefs)
    # context="写战斗"：相关条目优先 → 进入披露
    plan = MindPlanner(store).plan("main", context="写一场战斗戏")
    assert plan.style_prefs and plan.style_prefs[0].startswith("战斗")


def test_agency_generate_api_candidates() -> None:
    """S61 L3：自然语言描述 → 档位候选（fake model 返回 JSON，候选不进库）。"""
    import json as _json

    class GenModel:
        def __init__(self) -> None:
            self.prompts: list[str] = []

        def respond(self, messages, tools) -> ModelOutput:  # type: ignore[no-untyped-def]
            for m in messages:
                if m.role == "system":
                    self.prompts.append(m.content)
            return ModelOutput(
                text=_json.dumps(
                    [
                        {
                            "name": "自主推进",
                            "description": "AI 自主续写推进，重大转折前询问。",
                            "temperature": 0.9,
                        },
                        {
                            "name": "全程确认",
                            "description": "每步先给方案等确认。",
                            "temperature": 0.3,
                        },
                    ]
                )
            )

    m = GenModel()
    db = Path(tempfile.mkdtemp()) / "tgen.db"
    client = TestClient(build_app(model=m, db_path=db))
    r = client.post("/api/agency/generate", json={"description": "多给方案别直接写"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["candidates"]) == 2
    assert data["candidates"][0]["name"] == "自主推进"
    assert 0 <= data["candidates"][0]["temperature"] <= 1
    # 候选不进库：档位列表仍是默认五级
    levels = client.get("/api/agency").json()["levels"]
    assert len(levels) == 5


def test_mind_agency_suggest_api() -> None:
    """S61 L2：AI 看 collab 心智 → 建议档位（fake model 返回建议 JSON）。"""
    import json as _json

    class SuggestModel:
        def __init__(self) -> None:
            self.prompts: list[str] = []

        def respond(self, messages, tools) -> ModelOutput:  # type: ignore[no-untyped-def]
            for m in messages:
                if m.role == "system":
                    self.prompts.append(m.content)
            return ModelOutput(
                text=_json.dumps(
                    {"level_id": "default-0", "reason": "用户明确要求先给方案再动笔", "note": ""}
                )
            )

    m = SuggestModel()
    db = Path(tempfile.mkdtemp()) / "tsug.db"
    client = TestClient(build_app(model=m, db_path=db))
    client.post("/api/manual", json={"content": "先给方案再动笔，不要直接写", "category": "collab"})
    r = client.post("/api/mind/agency-suggest", json={"book_id": "main"})
    assert r.status_code == 200
    data = r.json()
    assert data["suggested_level"]["id"] == "default-0"
    assert "先给方案" in data["reason"]
    assert data["heuristic_agency"] is None  # 档位推断已移除（S62：不自动应用，用户主权）
    assert data["heuristic_reason"]  # 披露统计仍返回
    # 无 collab 条目 → 不调 LLM，返回规则推断
    m2 = ProbeModel()
    db2 = Path(tempfile.mkdtemp()) / "tsug2.db"
    client2 = TestClient(build_app(model=m2, db_path=db2))
    r2 = client2.post("/api/mind/agency-suggest", json={"book_id": "main"})
    assert r2.json()["suggested_level"] is None


def test_manual_decay_api() -> None:
    """S61：/api/manual/decay 显式触发衰减，返回冷条目列表。"""
    m = ProbeModel()
    db = Path(tempfile.mkdtemp()) / "tdecay.db"
    client = TestClient(build_app(model=m, db_path=db))
    client.post("/api/manual", json={"content": "旧条目"})
    # 时间边界防 flaky：decay 用 updated_at < now——同秒插入会因相等不降级，
    # 先把条目时间戳改为过去（直接改 db，测试专用）
    import sqlite3
    from datetime import UTC, datetime, timedelta

    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE manual_entries SET updated_at=? WHERE content='旧条目'",
            ((datetime.now(UTC) - timedelta(days=30)).isoformat(),),
        )
        conn.commit()
    r = client.post("/api/manual/decay", json={"days_high": 0, "days_medium": 0})
    assert r.status_code == 200
    data = r.json()
    assert data["decayed"] >= 1
    assert any(e["activity"] == "low" for e in data["cold_entries"])
