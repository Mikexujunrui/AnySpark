"""S50 叙事技巧（skill 重构）测试：种子/CRUD/注入/渐进式披露。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.align import (
    DEFAULT_SKILLS,
    WritingSkillStore,
    render_skill_index,
    render_skills_by_name,
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
    # 内容（点名注入：技法 + 案例；写作调用不自行选）
    content = render_skills_by_name(skills, ["镜头感与视角"])
    assert "把叙事当作镜头" in content  # 技法正文
    assert "例：" in content  # 情形案例随内容注入
    # 关闭一条 → 点名该条不再注入
    store.update(skills[0].id, enabled=False)
    content2 = render_skills_by_name(store.list_skills(), ["镜头感与视角"])
    assert content2 == ""


def test_skills_select_by_tags() -> None:
    """S61：写作调用不自行选技巧——未点名不注入任何内容，点名只注入点名技巧。"""
    store = WritingSkillStore(Path(tempfile.mkdtemp()) / "sk2.db")
    store.list_skills()  # 触发种子
    # 补到 6 条以上（即使很多也不自动选——写作调用是被执行方）
    for i in range(3):
        store.add(
            name=f"技巧{i}",
            description=f"描述{i}",
            content=f"内容{i}",
            example="例",
            tags="打斗" if i % 2 else "心理",
        )
    skills = store.list_skills()
    # 未点名 → 不注入任何内容（render_skills_by_name 空名单返回空）
    assert render_skills_by_name(skills, []) == ""
    # 点名才注入：只渲染点名的那条
    block = render_skills_by_name(skills, ["节奏控制"])
    assert "句子长度即情绪刻度" in block
    assert "内容0" not in block  # 未点名的技巧不注入


def test_skills_api_and_injection() -> None:
    m = ProbeModel()
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=m, db_path=db))
    # S128：统一容器——种子 = 写作技巧（DEFAULT_SKILLS）+ 剧情模式（L2 默认模板并入）
    skills = client.get("/api/skills").json()
    assert len(skills) == len(DEFAULT_SKILLS) + len([s for s in skills if s["type"] == "plot"])
    # plot 类（L2 默认模板并入）已落地 skill 表
    assert any(s["type"] == "plot" for s in skills)
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
    remaining = client.get("/api/skills").json()
    assert len(remaining) == len(DEFAULT_SKILLS) + len(
        [s for s in remaining if s["type"] == "plot"]
    )


def test_skill_target_routing() -> None:
    """S57/S61/S127：type 只影响索引可见性与点名注入；写作调用不自动选。

    S127：target 语义并入 type（PLAN-SKILL-UNIFY 阶段 1）——路由等价保留：
    writing 收 writing/both；main 收 main/both；both 两消费方可达。
    """
    from anyspark.align import render_skill_index, render_skills_by_name

    store = WritingSkillStore(Path(tempfile.mkdtemp()) / "sk3.db")
    # 三类各造一条
    store.add(name="类型指导A", description="主循环用", content="结构指导", type="main")
    store.add(name="文笔技巧B", description="写作用", content="句子技法", type="writing")
    store.add(name="通用技巧C", description="都可用", content="通用", type="both")
    skills = store.list_skills()
    # 主循环索引 = 全部（type 不限，S60：决策者看全部才能点名）
    idx = render_skill_index(skills, target="")
    assert "类型指导A" in idx and "文笔技巧B" in idx and "通用技巧C" in idx
    # 点名注入：按名字精确匹配，与 type 无关（主循环点名了就该进写作调用）
    block = render_skills_by_name(skills, ["文笔技巧B"])
    assert "句子技法" in block
    block2 = render_skills_by_name(skills, ["类型指导A"])
    assert "结构指导" in block2


def test_skill_type_plot_routing() -> None:
    """S127：plot 类路由——不进主循环索引（探索消费方阶段 2 接线），
    点名注入也不进写作上下文（纪律 3：main/plot 子条绝不进写作上下文）。"""
    from anyspark.align import render_skill_index, render_skills_by_name

    store = WritingSkillStore(Path(tempfile.mkdtemp()) / "sk3b.db")
    store.add(name="护送式旅程", description="剧情模式", content="护送明线+暗线洒落", type="plot")
    store.add(name="文笔技巧B", description="写作用", content="句子技法", type="writing")
    skills = store.list_skills()
    # 主循环索引（target=""）不含 plot（阶段 1 探索未接线，防误点名进写作）
    idx = render_skill_index(skills, target="")
    assert "文笔技巧B" in idx and "护送式旅程" not in idx
    # plot 视角（阶段 2 探索用）可见 plot 子条
    idx_plot = render_skill_index(skills, target="plot")
    assert "护送式旅程" in idx_plot and "文笔技巧B" not in idx_plot
    # 点名注入：plot 子条绝不进写作上下文（纪律 3）
    block = render_skills_by_name(skills, ["护送式旅程"])
    assert block == ""
    block2 = render_skills_by_name(skills, ["文笔技巧B"])
    assert "句子技法" in block2


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


def test_skill_type_migration_from_target() -> None:
    """S127：旧库 target 列 → type 列迁移（PLAN-SKILL-UNIFY 阶段 1）。

    模拟旧代码建的库（只有 target 列，无 type 列）→ 新代码打开时 ALTER 补 type
    并迁移：target=main → type=main；target=both → type=both（过渡值保留，
    两消费方都可达——保留语义）。
    """
    import sqlite3 as _sqlite3
    import uuid as _uuid

    db = Path(tempfile.mkdtemp()) / "mig.db"
    # 手工建旧结构表（无 type 列，target 列带数据）
    conn = _sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE writing_skills ("
        "id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', "
        "content TEXT NOT NULL, example TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '', "
        "target TEXT NOT NULL DEFAULT 'writing', enabled INTEGER NOT NULL DEFAULT 1, "
        "order_index INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)"
    )
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        "INSERT INTO writing_skills (id, name, description, content, target, enabled, "
        "order_index, created_at) VALUES (?,?,?,?,?,1,0,?)",
        (_uuid.uuid4().hex, "旧技法A", "d", "c", "main", now),
    )
    conn.execute(
        "INSERT INTO writing_skills (id, name, description, content, target, enabled, "
        "order_index, created_at) VALUES (?,?,?,?,?,1,1,?)",
        (_uuid.uuid4().hex, "旧技法B", "d", "c", "both", now),
    )
    conn.commit()
    conn.close()
    store2 = WritingSkillStore(db)  # 触发 ALTER + 迁移
    by_name = {s.name: s for s in store2.list_skills()}
    assert by_name["旧技法A"].type == "main"  # target→type 迁移
    assert by_name["旧技法B"].type == "both"  # both 过渡值保留（两消费方可达）
    # 新写入 type 优先
    s = store2.add("新技法", "d", "c", type="plot")
    assert s.type == "plot"
    assert s.to_dict()["target"] == "plot"  # 兼容镜像（前端仍读 target）
    got = store2.get(s.id)
    assert got is not None and got.type == "plot" and got.ext == ""
    # plot 四要素 ext 存取
    import json as _json

    s2 = store2.add(
        "时间回环", "d", "剧情模式说明", type="plot", ext=_json.dumps({"granularity": "全书"})
    )
    got2 = store2.get(s2.id)
    assert got2 is not None and got2.ext and _json.loads(got2.ext)["granularity"] == "全书"


def test_skill_draft_type_and_ext_promote() -> None:
    """S127：plot 草稿带 type/ext → 转正保留（拆书双落产物完整落 skill 表）。"""
    from anyspark.align import WritingSkillStore

    store = WritingSkillStore(Path(tempfile.mkdtemp()) / "d.db")
    import json as _json

    d = store.add_draft(
        name="护送式旅程",
        description="护送明线+暗线洒落",
        content="剧情模式：护送为明线，暗线逐章洒落，终点汇合。",
        type="plot",
        ext=_json.dumps(
            {"granularity": "全书", "position": "发展", "function": "悬念", "params": ["护送目标"]}
        ),
        source="library",
    )
    assert d is not None and d["type"] == "plot"
    s = store.promote_draft(d["id"])
    assert s is not None and s.type == "plot"
    assert s.ext != "" and _json.loads(s.ext)["granularity"] == "全书"


def test_skill_pack_aggregation() -> None:
    """S130（阶段 3）：书名包聚合——拆书三路产出（方法论 both/架构 main/剧情 plot）
    同 pack_id；子条独立可编辑/删除（包=逻辑聚合不物理复制）。"""
    from anyspark.align import WritingSkillStore

    store = WritingSkillStore(Path(tempfile.mkdtemp()) / "p.db")
    # 模拟拆书落草稿：三路子条同 pack_id=书名
    d1 = store.add_draft(
        "斗破苍穹写作法",
        "整本书方法论",
        "文风/结构融合",
        type="both",
        pack_id="斗破苍穹",
        source="library",
    )
    d2 = store.add_draft(
        "坏档与重开", "架构技法", "时间循环", type="main", pack_id="斗破苍穹", source="library"
    )
    d3 = store.add_draft(
        "时间回环·宿命闭环", "剧情模式", "回环", type="plot", pack_id="斗破苍穹", source="library"
    )
    assert d1 and d2 and d3
    assert d1["pack_id"] == "斗破苍穹"
    # 转正保留 pack_id
    s1 = store.promote_draft(d1["id"])
    assert s1 is not None and s1.pack_id == "斗破苍穹"
    s2 = store.promote_draft(d2["id"])
    assert s2 is not None and s2.pack_id == "斗破苍穹"
    s3 = store.promote_draft(d3["id"])
    assert s3 is not None and s3.pack_id == "斗破苍穹"
    # to_dict 带 pack_id
    assert s1.to_dict()["pack_id"] == "斗破苍穹"
    # 独立可删：删 plot 子条不影响包内其他
    store.delete(s3.id)
    remaining = [s for s in store.list_skills() if s.pack_id == "斗破苍穹"]
    assert len(remaining) == 2 and all(s.pack_id == "斗破苍穹" for s in remaining)


def test_skill_pack_reference_routing() -> None:
    """S130（纪律 3）：整包引用点名=包名 → 写作上下文只注入包内 writing/both 子条，
    main/plot 子条绝不进写作上下文；单条点名仍按名精确匹配。"""
    from anyspark.align import render_skill_index, render_skills_by_name

    store = WritingSkillStore(Path(tempfile.mkdtemp()) / "pr.db")
    # 包：斗破苍穹（方法论 both + 文笔 writing + 架构 main + 剧情 plot）
    store.add("斗破苍穹写作法", "整本书方法论", "文风节奏结构融合", type="both", pack_id="斗破苍穹")
    store.add("斗破苍穹·文笔", "文笔技法", "短句直给推进", type="writing", pack_id="斗破苍穹")
    store.add("坏档与重开", "架构技法", "时间循环设计", type="main", pack_id="斗破苍穹")
    store.add("时间回环·宿命闭环", "剧情模式", "回环模板", type="plot", pack_id="斗破苍穹")
    skills = store.list_skills()
    # 整包引用「斗破苍穹」→ 注入 both 方法论 + writing 子条；main/plot 不注入
    block = render_skills_by_name(skills, ["斗破苍穹"])
    assert "斗破苍穹写作法" in block  # both 方法论（写作+主循环都要）
    assert "斗破苍穹·文笔" in block  # writing 子条
    assert "坏档与重开" not in block  # main 绝不进写作上下文（纪律 3）
    assert "时间回环·宿命闭环" not in block  # plot 绝不进写作上下文
    # 单条点名：按名精确匹配（main 仍可点名注入——S61 语义保留）
    block2 = render_skills_by_name(skills, ["坏档与重开"])
    assert "时间循环设计" in block2
    # 主循环索引（target=""）：含 writing/main/both，不含 plot
    idx = render_skill_index(skills, target="")
    assert "斗破苍穹写作法" in idx and "坏档与重开" in idx
    assert "时间回环·宿命闭环" not in idx
    # plot 视角可见 plot 子条
    idx_plot = render_skill_index(skills, target="plot")
    assert "时间回环·宿命闭环" in idx_plot


def test_skill_description_preserved_full() -> None:
    """S62：skill 描述存储永不截断（内容主权）；索引渲染层才展示省略。"""
    from anyspark.align import WritingSkillStore
    from anyspark.align.skills import (
        _INDEX_DESC_ELIDE,
        render_skill_index,
    )

    store = WritingSkillStore(Path(tempfile.mkdtemp()) / "s.db")
    try:
        long_desc = "这是一段非常长的描述" * 20
        assert len(long_desc) > _INDEX_DESC_ELIDE
        s = store.add("test-skill", long_desc, "技法内容")
        # 存储保全文（不再截断）
        assert s.description == long_desc
        # update 同样保全文
        s2 = store.update(s.id, description=long_desc)
        assert s2 is not None and s2.description == long_desc
        # 渲染层展示省略（含提示看全文），存储内容不变
        idx = render_skill_index(store.list_skills())
        assert "test-skill" in idx and "…（全文见 skill_lookup）" in idx
        assert idx.count(long_desc) == 0  # 索引行不出现超长描述
        stored = store.get(s.id)
        assert stored is not None and stored.description == long_desc  # 存储未损坏
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
    from anyspark.server.toolkit import ToolContext, build_toolkit
    from anyspark.server.tools_extensions import ExtensionToolStore

    store = WritingSkillStore(Path(tempfile.mkdtemp()) / "sk5.db")
    try:
        registry = build_toolkit(
            ToolRegistry(),
            ToolContext(
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
            ),
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
        # 未点名 → 不注入任何技巧（写作调用是被执行方，不自行选）
        model.last_system = ""
        res2 = impl(spec, {"title": "第二章 路上", "intent": "继续赶路"})
        assert res2.ok
        assert "叙事技巧" not in model.last_system
        assert "节奏控制" not in model.last_system
    finally:
        store.close()
        ch.close()
