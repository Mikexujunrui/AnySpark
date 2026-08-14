"""S103 书库 → skill 提炼端点测试（拆书模式：多维拆解成「书名」skill 草稿）。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.core import ModelOutput
from anyspark.server.app import build_app


class _FakeRefineModel:
    """fake model：返回拆书 skill JSON（mode=book 单候选）。"""

    def __init__(self) -> None:
        self.model_name = "fake-refine"

    def respond(self, messages, tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        return ModelOutput(
            text='[{"name": "斗破苍穹写作法", '
            '"description": "爽文升级流的节奏与冲突组织方法论", '
            '"content": "升级流节奏：每卷先抑后扬，冲突逐级升级；对白推进信息", '
            '"example": "示例", "tags": "爽文,升级流", "target": "both"}]'
        )


def _client(tmp_path: Path) -> TestClient:
    return TestClient(build_app(db_path=tmp_path / "t.db", model=_FakeRefineModel()))


def test_library_refine_skill_full_chain(tmp_path: Path) -> None:
    """S103 全链路：建书 → 导入 → 提炼（草稿）→ 确认转正（生效）。"""
    client = _client(tmp_path)
    # 建书 + 导入两章
    r = client.post("/api/library", json={"name": "斗破苍穹"})
    book_id = r.json()["id"]
    r = client.post(
        "/api/library/import",
        json={
            "book_id": book_id,
            "content": "第一章 萧炎\n这里是正文。\n第二章 三年之约\n继续。",
            "title": "斗破苍穹",
        },
    )
    assert r.json()["chapters"] == 2

    # 提炼 → 草稿出现
    r = client.post(f"/api/library/{book_id}/refine-skill")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    draft = body["draft"]
    assert draft["name"] == "斗破苍穹写作法"
    assert draft["source"] == "library"
    assert draft["type"] == "both"  # S127：拆书方法论双目标（文风给写作、结构给主循环）

    # 草稿列表可见
    drafts = client.get("/api/skills/drafts").json()
    assert any(d["id"] == draft["id"] for d in drafts)

    # 重复提炼 → 409（同名草稿已存在）
    r = client.post(f"/api/library/{book_id}/refine-skill")
    assert r.status_code == 409

    # 确认转正 → 进正式技能
    r = client.post(f"/api/skills/drafts/{draft['id']}/promote")
    assert r.status_code == 200
    skills = client.get("/api/skills").json()
    assert any(s["name"] == "斗破苍穹写作法" for s in skills)


def test_library_refine_empty_book_400(tmp_path: Path) -> None:
    client = _client(tmp_path)
    r = client.post("/api/library", json={"name": "空书"})
    book_id = r.json()["id"]
    r = client.post(f"/api/library/{book_id}/refine-skill")
    assert r.status_code == 400


def test_library_refine_missing_book_404(tmp_path: Path) -> None:
    client = _client(tmp_path)
    r = client.post("/api/library/not-exist/refine-skill")
    assert r.status_code == 404


def test_library_refine_plot_dual_landing(tmp_path: Path) -> None:
    """S127：拆书双落——骨架笔记除架构技法（type=main）外，还派生剧情模式
    plot 子条（type=plot，四要素进 ext）——一次拆书产出整包各 type 草稿。

    走真实链路：respond-based fake 模型（SkillGenerator 包装）+ 结构选章路径
    （8 章 > _MIN_CHAPTERS），四步调用（拆解批/骨架/精读/剧情模式）各自产出。
    """
    from anyspark.core import ModelOutput

    class _RespondModel:
        def __init__(self) -> None:
            self.calls = 0

        def respond(self, messages, tools):  # type: ignore[no-untyped-def]
            self.calls += 1
            prompt = next((m.content for m in messages if m.role == "system"), "")
            if "关键章节原文" in prompt:  # 定点精读 → 架构技法（main）
                return ModelOutput(
                    text='[{"name": "坏档与重开", "description": "时间循环式叙事", '
                    '"content": "负面：不要先验告知；正面：伏笔-揭示-回收。", '
                    '"example": "原文摘录", "tags": "科幻", "type": "main"}]'
                )
            if "剧情模式提炼器" in prompt and "结构分析笔记" in prompt:  # S127 双落
                return ModelOutput(
                    text='[{"name": "时间回环·宿命闭环", '
                    '"description": "主角反复回到起点，每轮携带记忆增量，终点揭示闭环成因。'
                    '可变参数：回环触发点、记忆保留方式。", "granularity": "全书", '
                    '"position": "发展", "function": "悬念", '
                    '"params": ["回环触发点", "记忆保留方式"]}]'
                )
            if "结构分析师" in prompt:  # 骨架扫描
                return ModelOutput(
                    text="第5章到第6章揭示了时间回环结构。第8章主角最终目的：重启世界。"
                )
            if "汇总器" in prompt:  # 归并 → 书名方法论
                return ModelOutput(
                    text='[{"name": "斗破苍穹写作法", "description": "爽文升级流节奏", '
                    '"content": "冲突逐级升级；对白推进信息", "example": "", '
                    '"tags": "爽文", "type": "both"}]'
                )
            return ModelOutput(
                text='[{"name": "批", "content": "某批特征技法。", "description": ""}]'
            )

    client = TestClient(build_app(db_path=tmp_path / "t.db", model=_RespondModel()))
    r = client.post("/api/library", json={"name": "斗破苍穹"})
    book_id = r.json()["id"]
    # 8 章（结构选章路径，触发骨架扫描+精读+剧情模式双落）
    chaps = "\n".join(f"第{i}章 章节{i}\n正文内容用于测试。" for i in range(1, 9))
    client.post(
        "/api/library/import",
        json={"content": chaps, "title": "斗破苍穹", "book_id": book_id},
    )
    r = client.post(f"/api/library/{book_id}/refine-skill")
    assert r.status_code == 200, r.text
    drafts = client.get("/api/skills/drafts").json()
    by_name = {d["name"]: d for d in drafts}
    assert "斗破苍穹写作法" in by_name and by_name["斗破苍穹写作法"]["type"] == "both"
    assert "坏档与重开" in by_name and by_name["坏档与重开"]["type"] == "main"
    assert "时间回环·宿命闭环" in by_name and by_name["时间回环·宿命闭环"]["type"] == "plot"
    # S130：三路产出同书名一包（pack_id=书名，整包引用路由前提）
    assert by_name["斗破苍穹写作法"]["pack_id"] == "斗破苍穹"
    assert by_name["坏档与重开"]["pack_id"] == "斗破苍穹"
    assert by_name["时间回环·宿命闭环"]["pack_id"] == "斗破苍穹"
    # plot 草稿四要素进 ext（阶段 2 探索消费方读取）
    import json as _json

    ext = _json.loads(by_name["时间回环·宿命闭环"]["ext"])
    assert ext["granularity"] == "全书" and ext["function"] == "悬念"
    # 转正后 type/ext 保留
    pid = by_name["时间回环·宿命闭环"]["id"]
    r = client.post(f"/api/skills/drafts/{pid}/promote")
    assert r.status_code == 200
    skills = client.get("/api/skills").json()
    plot_skill = next(s for s in skills if s["name"] == "时间回环·宿命闭环")
    assert plot_skill["type"] == "plot" and "全书" in plot_skill["ext"]
    # 主循环索引不含 plot（阶段 1 防误点名进写作）；writing 子条可见
    from anyspark.align import render_skill_index
    from anyspark.align.skills import WritingSkill

    skills = client.get("/api/skills").json()
    ws = [
        WritingSkill(
            name=s["name"], description=s["description"], content=s["content"], type=s["type"]
        )
        for s in skills
    ]
    idx = render_skill_index(ws, target="")
    assert "时间回环·宿命闭环" not in idx  # plot 不进主循环索引
    assert "镜头感与视角" in idx  # 种子 writing 子条仍可见（等价保留）


def test_skill_refine_tool_library_source_creates_draft(tmp_path: Path) -> None:
    """S103：skill_refine 工具支持 library_book_id（书库取原文）+ 候选存草稿。"""
    from anyspark.align import WritingSkillStore
    from anyspark.library import LibraryStore
    from anyspark.server.tools_domain import make_skill_refine_implementer

    class _Gen:
        def generate(self, source_text, hint, max_items, mode):  # type: ignore[no-untyped-def]
            assert mode in ("writing", "main")
            return []

        def generate_book(self, source_text, hint="", book_name=""):  # type: ignore[no-untyped-def]
            # S106/S114：拆书走三层接口（分块抽样+骨架扫描+定点精读）；原文来自书库全文
            assert "第一章" in source_text
            assert book_name == "斗破苍穹"  # S114：书名注入（name=书名引用单位）
            return [
                {
                    "name": "斗破苍穹写作法",
                    "description": "爽文节奏方法论",
                    "content": "冲突逐级升级；对白推进信息",
                    "example": "",
                    "tags": "",
                    "type": "both",
                }
            ]

    lib = LibraryStore(tmp_path / "lib.db", library_root=tmp_path / "libroot")
    book = lib.add_book("斗破苍穹")
    lib.import_chapter(book["id"], "第一章", "第一章 萧炎 正文", 0)
    skills = WritingSkillStore(tmp_path / "sk.db")

    spec, impl = make_skill_refine_implementer(_Gen(), None, library=lib, skills=skills)
    res = impl(spec, {"library_book_id": book["id"], "mode": "book"})
    assert res.ok is True
    assert "草稿已生成" in res.content

    drafts = skills.list_drafts()
    assert len(drafts) == 1
    assert drafts[0]["name"] == "斗破苍穹写作法"
    assert drafts[0]["source"] == "agent"

    # 再次提炼 → 同名草稿去重（不重复堆叠）
    res2 = impl(spec, {"library_book_id": book["id"], "mode": "book"})
    assert res2.ok is True
    assert "同名草稿" in res2.content
    assert len(skills.list_drafts()) == 1


def test_skill_refine_tool_missing_library_book(tmp_path: Path) -> None:
    from anyspark.library import LibraryStore
    from anyspark.server.tools_domain import make_skill_refine_implementer

    class _Gen:
        def generate(self, source_text, hint, max_items, mode):  # type: ignore[no-untyped-def]
            raise AssertionError("不应调用")

    lib = LibraryStore(tmp_path / "lib2.db", library_root=tmp_path / "lib2root")
    spec, impl = make_skill_refine_implementer(_Gen(), None, library=lib, skills=None)
    res = impl(spec, {"library_book_id": "not-exist", "mode": "book"})
    assert res.ok is False
    assert "书库无此书" in res.content
