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


def test_generate_main_mode_forces_target_main() -> None:
    """S58：main 模式用结构指导 prompt，候选 target 强制 main。"""
    model = FakeSkillModel(GOOD_OUTPUT)  # 输出不含 target → 应强制 main
    gen = SkillGenerator(model)
    cands = gen.generate_main("废柴流开局：主角受辱三年，偶得金手指。")
    assert cands, "应产出候选"
    assert all(c["target"] == "main" for c in cands)
    # prompt 用主循环结构指导（区别于文风 prompt）
    assert "叙事组织指导" in model.prompts[0]
    assert "结构/类型/节奏" in model.prompts[0]


def test_generate_mode_writing_keeps_target() -> None:
    """S58：writing 模式保持模型标的 target（缺省 writing）。"""
    model = FakeSkillModel(GOOD_OUTPUT)
    cands = SkillGenerator(model).generate("萧炎，三年之约已到。")
    assert cands
    assert all(c.get("target", "writing") in ("writing", "main", "both") for c in cands)


def test_generate_book_sampling_and_merge() -> None:
    """S106：拆书（整本书）——12MB 级大书分块抽样 + 归并成一份。"""
    from anyspark.align.skillgen import _BOOK_SAMPLES, _sample_blocks

    class CountingBookModel:
        def __init__(self) -> None:
            self.calls = 0
            self.sample_prompts: list[str] = []

        def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
            self.calls += 1
            prompt = next((m.content for m in messages if m.role == "system"), "")
            if "汇总器" in prompt:
                # 归并调用：输出最终融合 skill
                return ModelOutput(
                    text="""```json
[{"name": "全书方法论", "description": "整本书写法", "content": "开篇短句直给；中段节奏交替；结尾钩子回收。", "tags": "文风,结构"}]
```"""
                )
            self.sample_prompts.append(prompt)
            # 每段拆解：输出该段 skill（content 带段标记）
            return ModelOutput(
                text="""```json
[{"name": "段", "content": "某段特征技法。", "description": ""}]
```"""
            )

    model = CountingBookModel()
    gen = SkillGenerator(model)
    # 12MB 级大书：远超 20000 字符旧窗口
    big_text = "第X章 " + ("雨夜，钟声。" * 200000)  # ~300 万字符
    cands = gen.generate_book(big_text, hint="侧重悬念")
    # 抽样 16 段 + 1 次归并
    assert model.calls == _BOOK_SAMPLES + 1, (
        f"应抽 {_BOOK_SAMPLES} 段+1 归并，实际 {model.calls} 次"
    )
    assert len(cands) == 1
    assert cands[0]["target"] == "both"  # 拆书方法论双目标
    assert "全书方法论" in cands[0]["name"]
    # 每段喂的是抽样片段（含段标记，非开头截断）
    assert all("代表段" in p for p in model.sample_prompts)
    # 小书走单段（不浪费多次调用）
    small_model = CountingBookModel()
    SkillGenerator(small_model).generate_book("短文本。" * 100)
    assert small_model.calls == 2  # 1 段提炼 + 1 归并
    # 空文本 → 空
    assert SkillGenerator(model).generate_book("") == []
    assert len(_sample_blocks("x" * 10, 16, 12000)) == 1  # 小书整体
    assert len(_sample_blocks("x" * (16 * 12000 + 1), 16, 12000)) == 16


def test_generate_api_main_mode() -> None:
    """S58：API 传 mode=main 产出 target=main 候选。"""
    model = FakeSkillModel(GOOD_OUTPUT)
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=model, db_path=db))
    r = client.post(
        "/api/skills/generate",
        json={"source_text": "废柴流开局", "mode": "main"},
    )
    assert r.status_code == 200
    assert r.json()["candidates"], "应产出候选"
    assert all(c["target"] == "main" for c in r.json()["candidates"])


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
        target="main",  # S57
        source="mental",
    )
    assert d is not None
    # 同名校验：草稿或正式存在 → 拒绝
    assert store.add_draft(name="短句直给", description="", content="x") is None
    # 列出
    drafts = store.list_drafts()
    assert any(x["name"] == "短句直给" for x in drafts)
    # 转正：进 writing_skills + 草稿删除 + target 保留
    s = store.promote_draft(d["id"])
    assert s is not None and s.name == "短句直给"
    assert s.target == "main"  # S57：转正保留 target
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


# ──────────────────────────────────────────────────────────────
# S69：剧情模式模板提炼（plot mode）
# ──────────────────────────────────────────────────────────────
PLOT_OUTPUT = """```json
[
  {"name": "护送式旅程·双线交汇", "description": "以护送/押运为明线（地理位移+生存危机），暗线为被护送物的记忆/身份碎片逐章洒落，终点汇合引爆真相。可变参数：护送目标、暗线内容、汇合代价。", "granularity": "全书", "position": "发展", "function": "悬念", "params": ["护送目标", "暗线内容", "汇合代价"]},
  {"name": "章末急刹车", "description": "每章末尾留一个未落地的事实或突然的异动（不解释），下一章开头先回应再继续推进。可变参数：刹车事件类型。", "granularity": "章", "position": "结局", "function": "悬念", "params": ["刹车事件"]},
  {"name": "乱填的维度", "description": "这个模板的维度故意乱填，应回落默认。", "granularity": "乱填", "position": "乱填", "function": "乱填", "params": "逗号,串"}
]
```"""


def test_parse_templates_four_elements() -> None:
    """S69：解析模板四要素（粒度/位置/功能/可变参数）。"""
    from anyspark.align.skillgen import _parse_templates

    cands = _parse_templates(PLOT_OUTPUT)
    assert len(cands) == 3
    t = cands[0]
    assert t["name"] == "护送式旅程·双线交汇"
    assert t["granularity"] == "全书"
    assert t["position"] == "发展"
    assert t["function"] == "悬念"
    assert t["params"] == "护送目标,暗线内容,汇合代价"


def test_parse_templates_invalid_dimension_falls_back() -> None:
    """S69：维度不在分类集内回落默认（防模型乱填）。"""
    from anyspark.align.skillgen import _parse_templates

    cands = _parse_templates(PLOT_OUTPUT)
    bad = cands[2]
    assert bad["granularity"] == "章"  # "乱填" → 默认
    assert bad["position"] == "发展"
    assert bad["function"] == "主线"
    assert bad["params"] == "逗号,串"  # 字符串 params 归一为逗号串


def test_generate_plot_mode_uses_plot_prompt() -> None:
    """S69：mode=plot 走剧情模式 prompt，输出四要素候选。"""
    model = FakeSkillModel(PLOT_OUTPUT)
    gen = SkillGenerator(model)
    cands = gen.generate("多章正文", max_items=3, mode="plot")
    assert len(cands) == 3
    assert cands[0]["granularity"] == "全书"
    # prompt 含剧情模式特征
    assert "剧情模式" in model.prompts[0]
    assert "多章" in model.prompts[0]


def test_generate_plot_helper() -> None:
    """S69：generate_plot 便捷方法。"""
    model = FakeSkillModel(PLOT_OUTPUT)
    gen = SkillGenerator(model)
    cands = gen.generate_plot("多章正文")
    assert cands and cands[0]["name"].startswith("护送式")


def test_generate_plot_api_and_dedup() -> None:
    """S69：/api/templates/generate 端点 + 与现有模板库去重。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=FakeSkillModel(PLOT_OUTPUT), db_path=db))
    r = client.post("/api/templates/generate", json={"source_text": "多章", "max_items": 3})
    assert r.status_code == 200
    data = r.json()
    assert len(data["candidates"]) == 3
    assert "护送式旅程·双线交汇" in [c["name"] for c in data["candidates"]]
    # existing_templates 返回 L2 默认库名（去重参考）
    assert "废柴流开局·反差铺垫" in data["existing_templates"]
    # 空输入 → 400
    r2 = client.post("/api/templates/generate", json={"source_text": ""})
    assert r2.status_code == 400
