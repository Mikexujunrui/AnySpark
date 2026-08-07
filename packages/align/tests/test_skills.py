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
    # 注入：chat 时 system prompt 含叙事技巧索引。S60：主循环注入全部技巧索引
    # （名字+描述，target 不限——决策者看到全部才能点名给写作调用）；完整内容不常驻，
    # 靠 skill_lookup 细看 / write_chapter 的 skills 参数点名。
    client.post("/api/chat", json={"message": "写一段"})
    assert m.prompts, "应捕获 system prompt"
    last = m.prompts[-1]
    assert "叙事技巧" in last and "节奏控制" in last  # both → 索引可见
    assert "镜头感与视角" in last  # S60：writing 技巧名也在索引（决策者可见全部）
    assert "把叙事当作镜头" not in last  # 内容不常驻注入（skill_lookup 按需）
    # 删除
    assert client.delete(f"/api/skills/{sid}").json()["ok"] is True
    assert len(client.get("/api/skills").json()) == len(DEFAULT_SKILLS)


def test_skill_target_routing() -> None:
    """S57：target 分流——main 目标只进主循环，writing 只进写作调用，both 都进。"""
    from anyspark.align import render_skill_index, render_skills_content, select_skills_for

    store = WritingSkillStore(Path(tempfile.mkdtemp()) / "sk3.db")
    # 三目标各造一条
    store.add(name="类型指导A", description="主循环用", content="结构指导", target="main")
    store.add(name="文笔技巧B", description="写作用", content="句子技法", target="writing")
    store.add(name="通用技巧C", description="都可用", content="通用", target="both")
    skills = store.list_skills()
    # 主循环：main+both
    main_sel = select_skills_for(skills, target="main")
    main_names = {s.name for s in main_sel}
    assert "类型指导A" in main_names and "通用技巧C" in main_names
    assert "文笔技巧B" not in main_names
    # 写作调用：writing+both
    write_sel = select_skills_for(skills, target="writing")
    write_names = {s.name for s in write_sel}
    assert "文笔技巧B" in write_names and "通用技巧C" in write_names
    assert "类型指导A" not in write_names
    # 渲染分流一致
    assert "类型指导A" in render_skill_index(skills, target="main")
    assert "文笔技巧B" in render_skills_content(skills, target="writing")


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


def test_skill_description_guard() -> None:
    """S55 #4 描述截断守卫：超限入库被截断。"""
    from anyspark.align import WritingSkillStore
    from anyspark.align.skills import SKILL_DESC_LIMIT

    store = WritingSkillStore(Path(tempfile.mkdtemp()) / "s.db")
    try:
        long_desc = "这是一段非常长的描述" * 20
        assert len(long_desc) > SKILL_DESC_LIMIT
        s = store.add("test-skill", long_desc, "技法内容")
        assert len(s.description) <= SKILL_DESC_LIMIT
        assert s.description.endswith("...")
        # update 同样守卫
        s2 = store.update(s.id, description="短描述")
        assert s2 is not None and s2.description == "短描述"
        s3 = store.update(s.id, description=long_desc)
        assert s3 is not None and len(s3.description) <= SKILL_DESC_LIMIT
    finally:
        store.close()


def test_skill_revision_changes_on_mutation() -> None:
    """S55 #3 注入缓存签名：内容增删改 → revision 变化（缓存失效）。"""
    from anyspark.align import WritingSkillStore

    store = WritingSkillStore(Path(tempfile.mkdtemp()) / "s2.db")
    try:
        r0 = store.revision()
        s = store.add("a", "描述A", "内容A")
        r1 = store.revision()
        assert r0 != r1
        store.update(s.id, description="描述A2")
        r2 = store.revision()
        assert r1 != r2
        store.delete(s.id)
        r3 = store.revision()
        assert r2 != r3
    finally:
        store.close()


def test_skills_by_name_render() -> None:
    """S60：点名渲染——按名字精确匹配注入完整内容（write_chapter skills 参数用）。"""
    from anyspark.align import render_skills_by_name

    store = WritingSkillStore(Path(tempfile.mkdtemp()) / "sk4.db")
    skills = store.list_skills()  # 种子：镜头感与视角/对白机锋/节奏控制
    try:
        # 点名一条 → 只渲染该条完整内容
        block = render_skills_by_name(skills, ["节奏控制"])
        assert "节奏控制" in block and "句子长度即情绪刻度" in block
        assert "镜头感" not in block
        # 点名多条 → 多条都渲染
        block2 = render_skills_by_name(skills, ["节奏控制", "对白机锋"])
        assert "节奏控制" in block2 and "对白机锋" in block2
        # 未命中名字 → 忽略（不报错）
        block3 = render_skills_by_name(skills, ["不存在的技巧"])
        assert block3 == ""
        # 空名单 → 空
        assert render_skills_by_name(skills, []) == ""
        assert render_skills_by_name(skills, [""]) == ""
        # 禁用技巧不注入
        store.update(skills[2].id, enabled=False)
        skills2 = store.list_skills()
        block4 = render_skills_by_name(skills2, ["节奏控制"])
        assert block4 == ""  # 已禁用
    finally:
        store.close()


def test_skill_lookup_tool() -> None:
    """S60：skill_lookup 工具——按名细看完整内容（索引配套的按需查证）。"""
    from anyspark.align import WritingSkillStore
    from anyspark.core.protocol import ToolRegistry
    from anyspark.server.toolkit import build_toolkit
    from anyspark.server.tools_extensions import ExtensionToolStore

    store = WritingSkillStore(Path(tempfile.mkdtemp()) / "sk5.db")
    try:
        registry = build_toolkit(
            ToolRegistry(),
            chapters=None,
            workspace=None,
            model=None,
            graph=None,
            plots=None,
            plans=None,
            settings=None,
            materials=None,
            ext_tools=ExtensionToolStore(Path(tempfile.mkdtemp()) / "ext.db"),
            manual=None,
            skills_store=store,
        )
        spec, impl = registry.get("skill_lookup") or (None, None)
        assert spec is not None, "skill_lookup 应注册"
        assert impl is not None
        # 精确命中
        res = impl(spec, {"name": "节奏控制"})
        assert res.ok and "句子长度即情绪刻度" in res.content
        # 包含匹配兜底
        res2 = impl(spec, {"name": "节奏"})
        assert res2.ok and "节奏控制" in res2.content
        # 未命中
        res3 = impl(spec, {"name": "不存在的技巧"})
        assert not res3.ok
        # 缺参数
        res4 = impl(spec, {})
        assert not res4.ok
    finally:
        store.close()


def test_write_chapter_skills_param() -> None:
    """S60：write_chapter 的 skills 参数——主循环点名技巧进干净写作调用。"""
    import tempfile
    from pathlib import Path

    from anyspark.align import WritingSkillStore
    from anyspark.core.protocol import ToolRegistry
    from anyspark.core.types import ModelOutput
    from anyspark.server.tools_writing import register_writing_tools

    class CaptureModel:
        def __init__(self) -> None:
            self.last_system = ""

        def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
            for m in messages:
                if m.role == "system":
                    self.last_system = m.content
            return ModelOutput(text="正文内容。")

    model = CaptureModel()
    store = WritingSkillStore(Path(tempfile.mkdtemp()) / "sk6.db")
    # 章节存储（用真实 ChapterStore 落临时库）
    from anyspark.store import ChapterStore

    db_path = Path(tempfile.mkdtemp()) / "ch.db"
    ch = ChapterStore(db_path)
    try:
        reg = ToolRegistry()
        register_writing_tools(
            reg, ch, workspace=None, model=model, skills_store=store, style_prefs=[]
        )
        spec, impl = reg.get("write_chapter") or (None, None)
        assert spec is not None and impl is not None
        # 点名节奏控制 → 写作调用 system 含该技巧内容，且不含未点名的
        res = impl(
            spec,
            {
                "title": "第一章 启程",
                "intent": "主角在雨夜启程",
                "skills": "节奏控制",
            },
        )
        assert res.ok
        assert "节奏控制" in model.last_system
        assert "句子长度即情绪刻度" in model.last_system
        assert "镜头感" not in model.last_system  # 未点名不注入
        # 未点名 → 自动匹配兜底（无 prefs 时保底前 limit 条，此处种子仅 3 条全量注入）
        model.last_system = ""
        res2 = impl(spec, {"title": "第二章 路上", "intent": "继续赶路"})
        assert res2.ok
        assert "叙事技巧" in model.last_system  # 兜底注入（选择策略不同，内容仍在）
    finally:
        store.close()
        ch.close()
