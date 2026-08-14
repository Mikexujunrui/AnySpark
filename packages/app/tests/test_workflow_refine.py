"""S129（WORKFLOW 第 1 批）测试：拆书模板化——workflow 表达多步 LLM 管道。

对拍验证（PLAN-WORKFLOW-UNIFY 第 1 批标准：模板结果与现工具一致，同输入同模型）：
- 预置「拆书提炼」模板已种入（build_app 时幂等）
- 模板含集合遍历（loop collection_var 分批拆解，W3-A 遍历原语）
- 运行模板（fake 模型按 prompt 特征返回对应 JSON）→ 落草稿
- 与 SkillGenerator.generate_book 同模型直接调用对比：草稿名/type 一致
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from anyspark.core.types import Message, ModelOutput
from anyspark.server.app import build_app


class FakeRefineModel:
    """fake 模型：按 prompt 特征返回对应拆书 JSON（对齐 skillgen 各步骤输出）。"""

    def __init__(self) -> None:
        self.model_name = "fake-refine"
        self.prompts: list[str] = []

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        # workflow agent 节点把指令放 user 消息（system 可选）；全消息合并判 prompt 特征
        joined = "\n".join(m.content or "" for m in messages)
        self.prompts.append(joined)
        prompt = joined
        # 判定顺序：特征词越具体越先判——定点精读 prompt 内嵌骨架笔记（含"结构分析师"字样），
        # 必须先于骨架扫描判定（否则误命中）；剧情模式 prompt 同理含"剧情模式提炼器"
        if "关键章节原文" in prompt:  # 定点精读 → 架构技法（main）
            return ModelOutput(
                text='[{"name": "坏档与重开", "description": "时间循环式叙事", '
                '"content": "负面：不要先验告知；正面：伏笔-揭示-回收。", '
                '"example": "原文摘录", "tags": "科幻", "type": "main"}]'
            )
        if "剧情模式提炼器" in prompt and "结构分析笔记" in prompt:  # 剧情模式双落（plot）
            return ModelOutput(
                text='[{"name": "时间回环·宿命闭环", "description": "主角反复回到起点，'
                '每轮携带记忆增量，终点揭示闭环成因。可变参数：回环触发点、记忆保留方式。", '
                '"granularity": "全书", "position": "发展", "function": "悬念", '
                '"params": ["回环触发点", "记忆保留方式"]}]'
            )
        if "汇总器" in prompt:  # 归并 → 书名方法论（both）
            return ModelOutput(
                text='[{"name": "测试书写作法", "description": "整本书写法", '
                '"content": "开篇短句；中段节奏交替；结尾钩子回收。", '
                '"tags": "文风,结构", "type": "both"}]'
            )
        if "结构分析师" in prompt:  # 骨架扫描 → 结构笔记
            return ModelOutput(text="第2章到第3章揭示了时间回环结构。第6章主角最终目的：重启世界。")
        # 分批拆解 → 该批 skill（拆书器 prompt）
        return ModelOutput(
            text='[{"name": "批特征", "description": "批特征", "content": "某批特征技法。", '
            '"type": "writing"}]'
        )


def _mk_book(client: TestClient) -> str:
    r = client.post("/api/library", json={"name": "测试书"})
    bid = str(r.json()["id"])
    chaps = "\n".join(f"第{i}章 章节{i}\n正文内容用于测试。" for i in range(1, 9))
    r = client.post(
        "/api/library/import",
        json={"book_id": bid, "content": chaps, "title": "测试书"},
    )
    assert r.status_code == 200
    return bid


def test_book_refine_template_seeded() -> None:
    """预置拆书模板已种入（build_app 幂等种子）。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    client = TestClient(build_app(model=FakeRefineModel(), db_path=db))
    wfs = client.get("/api/workflows").json()
    assert any(w["name"] == "拆书提炼" for w in wfs)
    wf_id = next(w["id"] for w in wfs if w["name"] == "拆书提炼")
    full = client.get(f"/api/workflows/{wf_id}").json()
    kinds = {n["id"]: n["kind"] for n in full["nodes"]}
    # 多步 LLM 管道：prep script → loop 集合遍历 → 3+ agent LLM 步骤 → finish script
    assert kinds["prep"] == "script" and kinds["loop"] == "loop"
    assert kinds["decompose"] == "agent" and kinds["merge"] == "agent"
    assert kinds["skeleton"] == "agent" and kinds["refine"] == "agent"
    assert kinds["plot"] == "agent" and kinds["finish"] == "script"
    # loop 用集合遍历原语（W3-A）：collection_var=prepared，body=[decompose, accumulate]
    loop = next(n for n in full["nodes"] if n["id"] == "loop")
    assert loop["params"]["collection_var"] == "prepared"
    assert loop["params"]["body"] == ["decompose", "accumulate"]
    assert full["edges"]  # 有向无环链


def test_book_refine_workflow_dual_landing() -> None:
    """拆书模板全链路：运行 → 落草稿（书名方法论 both + 架构 main + 剧情模式 plot）。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    model = FakeRefineModel()
    client = TestClient(build_app(model=model, db_path=db))
    bid = _mk_book(client)
    wfs = client.get("/api/workflows").json()
    wf_id = next(w["id"] for w in wfs if w["name"] == "拆书提炼")
    r = client.post(
        f"/api/workflows/{wf_id}/run",
        json={"book_id": "main", "params": {"library_book_id": bid}},
    )
    assert r.status_code == 200
    task_id = r.json()["task_id"]
    # 等待后台任务完成（fake 模型瞬时）
    status = ""
    for _ in range(50):
        t = client.get(f"/api/workflows/tasks/{task_id}").json()
        status = t.get("status", "")
        if status in ("done", "failed"):
            break
        time.sleep(0.1)
    assert status == "done", f"任务未完成: {status}"
    # 草稿落库：三种 type 齐（双落 + 方法论）
    drafts = client.get("/api/skills/drafts").json()
    by_name = {d["name"]: d for d in drafts}
    assert "测试书写作法" in by_name and by_name["测试书写作法"]["type"] == "both"
    assert "坏档与重开" in by_name and by_name["坏档与重开"]["type"] == "main"
    assert "时间回环·宿命闭环" in by_name and by_name["时间回环·宿命闭环"]["type"] == "plot"
    # plot 子条四要素进 ext
    import json as _json

    ext = _json.loads(by_name["时间回环·宿命闭环"]["ext"])
    assert ext["granularity"] == "全书" and ext["function"] == "悬念"
    # S130：三路产出同书名一包（pack_id 从书库解析）
    assert by_name["测试书写作法"]["pack_id"] == "测试书"
    assert by_name["坏档与重开"]["pack_id"] == "测试书"
    assert by_name["时间回环·宿命闭环"]["pack_id"] == "测试书"


def test_book_refine_workflow_matches_generator() -> None:
    """对拍：同一 fake 模型，模板产出的草稿与 SkillGenerator.generate_book 一致。"""
    from anyspark.align import SkillGenerator

    db = Path(tempfile.mkdtemp()) / "t.db"
    model = FakeRefineModel()
    client = TestClient(build_app(model=model, db_path=db))
    bid = _mk_book(client)
    # 参考：直接调 generate_book（同模型、同库原文）——
    # LibraryStore 默认 root = db.parent/library（与 app 装配一致，同源可读）
    from anyspark.library import LibraryStore

    lib2 = LibraryStore(db)
    assert lib2.get_book(bid) is not None
    source = lib2.read_book(bid, max_chars=None)
    assert source.strip(), "书库原文为空——对拍前提不成立"
    gen = SkillGenerator(model)
    ref = gen.generate_book(source, book_name="测试书")
    assert ref, "generate_book 直出为空（fake 模型链路未跑通）"
    ref_names = {c["name"]: c["type"] for c in ref}
    # 参考应含三路（both/main/plot）——fake 模型全链路
    assert "测试书写作法" in ref_names and ref_names["测试书写作法"] == "both"
    assert "坏档与重开" in ref_names and ref_names["坏档与重开"] == "main"
    assert "时间回环·宿命闭环" in ref_names and ref_names["时间回环·宿命闭环"] == "plot"

    # 跑模板 → 草稿
    wfs = client.get("/api/workflows").json()
    wf_id = next(w["id"] for w in wfs if w["name"] == "拆书提炼")
    r = client.post(
        f"/api/workflows/{wf_id}/run",
        json={"book_id": "main", "params": {"library_book_id": bid}},
    )
    task_id = r.json()["task_id"]
    for _ in range(50):
        t = client.get(f"/api/workflows/tasks/{task_id}").json()
        status = t.get("status", "")
        if status in ("done", "failed"):
            break
        time.sleep(0.1)
    assert status == "done"
    drafts = client.get("/api/skills/drafts").json()
    wf_names = {d["name"]: d["type"] for d in drafts}
    # 对拍：模板落草稿与生成器直出同名同 type（三路覆盖）
    for n, t in ref_names.items():
        assert wf_names.get(n) == t, f"对拍不一致: {n} 模板={wf_names.get(n)} 参考={t}"


def test_skill_refine_tool_uses_template_when_wired() -> None:
    """S135（WORKFLOW 收尾）：skill_refine(mode=book) 装配 workflow 时走「拆书提炼」模板
    （快捷入口→底层统一 workflow），草稿由模板 finish 落库不重复 add_draft。"""
    db = Path(tempfile.mkdtemp()) / "t.db"
    model = FakeRefineModel()
    app = build_app(model=model, db_path=db)
    deps = app.state.deps
    client = TestClient(app)
    bid = _mk_book(client)
    from anyspark.server.tools_domain import make_skill_refine_implementer

    spec, impl = make_skill_refine_implementer(
        None,
        None,
        library=deps.library,
        skills=deps.skills,
        workflow_store=deps.workflow_store,
        workflow_engine=deps.workflow_engine,
    )
    drafts_before = len(deps.skills.list_drafts())
    res = impl(spec, {"library_book_id": bid, "mode": "book"})
    assert res.ok, res.content
    assert "workflow" in res.content  # 走模板路径
    drafts_after = deps.skills.list_drafts()
    new_names = {d["name"] for d in drafts_after[: max(0, len(drafts_after) - drafts_before)]}
    assert "测试书写作法" in new_names  # 模板 finish 落库（不重复 add_draft）
    assert "坏档与重开" in new_names and "时间回环·宿命闭环" in new_names
