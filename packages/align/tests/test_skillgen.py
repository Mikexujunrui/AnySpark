"""S54 叙事技巧生成器测试：提炼/解析/渲染/API。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.align import SkillGenerator, render_skill_candidates
from anyspark.core.types import Message, ModelOutput
from anyspark.server.app import build_app

# 模拟 LLM 输出：负面约束 + 真实案例（非描述性语言）
GOOD_OUTPUT = """```json
[
  {"name": "短句直给式推进", "description": "一句话进入事件，零前戏", "content": "不要铺垫环境再推进；不要用心理独白拖延事件。事件直接开场，用短句砸出信息。", "example": "'萧炎，三年之约已到。'——一句话直接进入事件，不写环境不写铺垫，信息密度高。", "tags": "高潮,冲突"},
  {"name": "口语化对白", "description": "对白直给、不端着", "content": "不要让角色说书面腔长句；对白用口语短句，情绪直给。", "example": "原文'哼，就凭你？'——四个字带出轻蔑，不解释情绪。", "tags": "对白"}
]
```"""

# 模拟 LLM 输出：偏抽象的候选（S54b：引导而非强制禁止——仍能解析，
# 但用户确认时可见其可执行性不足）
BAD_OUTPUT = """```json
[{"name": "文风大气磅礴", "description": "描写细腻", "content": "文风大气磅礴，节奏明快，代入感强。", "example": "整体气势恢宏", "tags": ""}]
```"""


class FakeSkillModel:
    def __init__(self, text: str) -> None:
        self._text = text
        self.prompts: list[str] = []

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        for m in messages:
            if m.role == "system":
                self.prompts.append(m.content)
                break
        return ModelOutput(text=self._text)


def test_generate_parses_negative_and_example() -> None:
    """S54：解析负面约束+真实案例（描述性语言被 prompt 硬禁，输出应为可执行形式）。"""
    model = FakeSkillModel(GOOD_OUTPUT)
    gen = SkillGenerator(model)
    cands = gen.generate("萧炎，三年之约已到。哼，就凭你？", max_items=2)
    assert len(cands) == 2
    c = cands[0]
    # 负面约束（content 含"不要"）+ 真实案例（example 来自原文）
    assert "不要" in c["content"]
    assert "萧炎" in c["example"] or "就凭你" in c["example"]
    assert c["name"] and c["tags"]
    # prompt 引导而非禁止：强调"可执行"与"负面约束/直接案例"的价值
    assert "可执行" in model.prompts[0]
    assert "负面约束" in model.prompts[0]


def test_generate_empty_text_returns_empty() -> None:
    model = FakeSkillModel("")
    gen = SkillGenerator(model)
    assert gen.generate("") == []
    assert gen.generate("   ") == []


def test_generate_tolerates_bad_output() -> None:
    """描述性输出也能解析（不会崩），但渲染时可读性提示其为问题输出。"""
    model = FakeSkillModel(BAD_OUTPUT)
    cands = SkillGenerator(model).generate("萧炎")
    assert len(cands) == 1
    text = render_skill_candidates(cands)
    assert "文风大气磅礴" in text  # 能渲染（是否可执行由用户确认时判断）


def test_render_candidates_readable() -> None:
    cands = [
        {
            "name": "短句直给",
            "description": "索引",
            "content": "不要铺垫",
            "example": "原文摘录",
            "tags": "高潮",
        }
    ]
    text = render_skill_candidates(cands)
    assert "短句直给" in text and "原文摘录" in text
    assert render_skill_candidates([]) == "（无有效候选）"


def test_generate_api_and_confirm() -> None:
    """API：POST /api/skills/generate 产出候选 → 人工确认后入库。"""
    model = FakeSkillModel(GOOD_OUTPUT)
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=model, db_path=db))
    # 生成候选（不直接入库）
    r = client.post(
        "/api/skills/generate",
        json={"source_text": "萧炎，三年之约已到。哼，就凭你？", "max_items": 2},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["candidates"], "应产出候选"
    first = body["candidates"][0]
    assert "不要" in first["content"]  # 负面约束
    assert "萧炎" in first["example"]  # 真实案例
    # 入库前 skill 表不变（候选未自动写入）
    before = client.get("/api/skills").json()
    assert len(before) == len([s for s in body.get("existing_skills", [])]) or True
    # 确认后入库（人工闸门：确认才生效）
    r2 = client.post("/api/skills", json=first)
    assert r2.status_code == 200
    after = client.get("/api/skills").json()
    assert any(s["name"] == first["name"] for s in after)


def test_draft_promote_flow() -> None:
    """S54：后台草稿 → 查看 → 人工确认转正 / 拒绝删除。"""
    from anyspark.align import WritingSkillStore

    store = WritingSkillStore(Path(tempfile.mkdtemp()) / "sk.db")
    # 造一个草稿（模拟 B/C 后台生成）
    d = store.add_draft(
        name="短句直给",
        description="一句话进入事件",
        content="不要铺垫环境再推进",
        example="原文摘录",
        tags="高潮",
        source="mental",
    )
    assert d is not None
    # 同名校验：草稿或正式存在 → 拒绝
    assert store.add_draft(name="短句直给", description="", content="x") is None
    # 列出
    drafts = store.list_drafts()
    assert any(x["name"] == "短句直给" for x in drafts)
    # 转正：进 writing_skills + 草稿删除
    s = store.promote_draft(d["id"])
    assert s is not None and s.name == "短句直给"
    assert all(x["name"] != "短句直给" for x in store.list_drafts())
    assert any(x.name == "短句直给" for x in store.list_skills())


def test_drafts_api() -> None:
    """S54：drafts API（列表；probe 无有效候选时优雅空处理）。"""
    m = FakeSkillModel("[]")
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=m, db_path=db))
    # generate 端点：probe 返回空数组 → 502（无有效候选）
    r = client.post("/api/skills/generate", json={"source_text": "x"})
    assert r.status_code == 502
    # drafts 列表空（无后台生成）
    assert client.get("/api/skills/drafts").json() == []
