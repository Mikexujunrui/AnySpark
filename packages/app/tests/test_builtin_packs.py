"""S246/S247：内置规则包（按文体选择）+ 审稿回复模板 + 文体 profile 测试。

演化说明：S246 曾以"种子入库用户骨架"交付学术检测项，S247 修正为内置双骨架
按文体选择——种子无法表达体裁维度，导致小说检测被学术项污染。"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from anyspark.check import ACADEMIC_CHECKS, SKELETON_CHECKS, get_pack
from anyspark.check.skeleton import SkeletonCheckItem
from anyspark.core import ToolRegistry
from anyspark.core.protocol import ToolSpec, execute
from anyspark.core.types import Message, ModelOutput, ToolCall, ToolResult
from anyspark.server.app import build_app
from anyspark.server.tools_check import make_check_implementer
from anyspark.server.tools_writing import register_writing_tools
from anyspark.server.workspace import Workspace
from anyspark.store import ChapterStore


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "t.db"


def _call(impl: Any, name: str = "t", /, **kwargs: Any) -> ToolResult:
    spec = ToolSpec(name=name, description="t", params=[])
    result = impl(spec, kwargs)
    assert isinstance(result, ToolResult)
    return result


# ---------------------------------------------------------------------------
# 规则包选择：内置双骨架 + 未知回退
# ---------------------------------------------------------------------------
def test_get_pack_selection() -> None:
    assert get_pack(None) is SKELETON_CHECKS  # 缺省 novel（历史行为不变）
    assert get_pack("novel") is SKELETON_CHECKS
    assert get_pack("academic") is ACADEMIC_CHECKS
    assert get_pack("未知体裁") is SKELETON_CHECKS  # 未知回退
    assert len(ACADEMIC_CHECKS) == 7
    assert isinstance(ACADEMIC_CHECKS[0], SkeletonCheckItem)


def test_check_route_genre_aware() -> None:
    """项目文体=academic 时，/api/check 的检测者提示应含学术项、不含小说项。"""

    class CapturingModel:
        model_name = "capture"

        def __init__(self) -> None:
            self.prompts: list[str] = []

        def respond(self, messages: list[Message], tools: object) -> ModelOutput:
            for m in messages:
                if m.role == "system" and m.content:
                    self.prompts.append(m.content)
            return ModelOutput(text="[]", tool_calls=[])

    model = CapturingModel()
    client = TestClient(build_app(model=model, db_path=_db()))
    client.post("/api/genre", json={"genre": "academic", "book_id": "main"})
    r = client.post(
        "/api/check",
        json={"text": "本文提出一种方法。实验表明效果很好。", "book_id": "main"},
    )
    assert r.status_code == 200, r.text
    joined = "\n".join(model.prompts)
    assert "术语一致性" in joined  # 学术项参与检测
    assert "动机因果" not in joined  # 小说项不再污染（S246 缺陷修复）


# ---------------------------------------------------------------------------
# 文体 profile：写作引擎人设按项目文体切换（运行时读工作区文件）
# ---------------------------------------------------------------------------
class _Skills:
    def list_skills(self) -> list[object]:
        return []


class CleanWriteModel:
    def __init__(self) -> None:
        self.systems: list[str] = []
        self.model_name = "writer"

    def respond(self, messages: list[Message], tools: object) -> ModelOutput:
        for m in messages:
            if m.role == "system" and m.content:
                self.systems.append(m.content)
        return ModelOutput(text="正文内容。")


def test_write_chapter_genre_persona() -> None:
    root = Path(tempfile.mkdtemp())
    workspace = Workspace(root=root)
    chapters = ChapterStore(_db())
    model = CleanWriteModel()
    reg = ToolRegistry()
    register_writing_tools(
        reg, chapters, book_id="main", workspace=workspace, model=model, skills_store=_Skills()
    )

    def _invoke() -> ToolResult:
        reg2 = ToolRegistry()
        register_writing_tools(
            reg2, chapters, book_id="main", workspace=workspace, model=model, skills_store=_Skills()
        )
        return execute(
            reg2,
            ToolCall(
                name="write_chapter",
                arguments={
                    "title": "第一章",
                    "intent": "写一段引言",
                    "references": "",
                },
            ),
        )

    workspace.write_genre("main", "academic")
    r = _invoke()
    assert r.ok is True
    assert "学术写作引擎" in model.systems[-1]

    workspace.write_genre("main", "fiction")
    r2 = _invoke()
    assert r2.ok is True
    assert "小说写作引擎" in model.systems[-1]  # fiction 回到原文人设（逐字一致）


def test_genre_api_roundtrip() -> None:
    client = TestClient(build_app(model=_Skills(), db_path=_db()))  # type: ignore[arg-type]  # 占位：genre 端点不触模型
    g = client.get("/api/genre").json()
    assert g["genre"] == "fiction"  # 无文件=缺省
    r = client.post("/api/genre", json={"genre": "academic", "book_id": "main"})
    assert r.status_code == 200 and "学术" in r.json()["label"]
    assert client.get("/api/genre").json()["genre"] == "academic"


def test_check_tool_accepts_custom_checks() -> None:
    """check_text 的 checks 注入仍生效（S246 接线保留，基准集由调用方按文体给）。"""

    class FakeCheckModel:
        model_name = "fake-check"

        def respond(self, messages: list[Message], tools: object) -> ModelOutput:
            prompt = messages[0].content if messages else ""
            if "自定义项" in prompt:
                return ModelOutput(
                    text=json.dumps(
                        [{"message": "命中", "evidence": "第1段", "severity": "hard"}],
                        ensure_ascii=False,
                    ),
                    tool_calls=[],
                )
            return ModelOutput(text="[]", tool_calls=[])

    custom = [SkeletonCheckItem("自定义项", "检测自定义问题")]
    _, impl = make_check_implementer(FakeCheckModel(), checks=custom)
    r = _call(impl, "check_text", text="测试正文。")
    assert r.ok is True and "命中" in r.content


# ---------------------------------------------------------------------------
# 审稿回复模板：e2e（逐条回应 → 汇编回复信）
# ---------------------------------------------------------------------------
def test_review_reply_template_runs() -> None:
    class FakeReplyModel:
        model_name = "fake-reply"

        def respond(self, messages: list[Message], tools: object) -> ModelOutput:
            prompt = messages[-1].content if messages else ""
            if "汇编" in prompt:
                return ModelOutput(
                    text="尊敬的审稿人：感谢您的意见。逐条回应如下……（完整回复信）",
                    tool_calls=[],
                )
            return ModelOutput(
                text="【意见解读】…\n【回应策略】接受\n【修改方案】…\n【回复措辞】感谢指出…",
                tool_calls=[],
            )

    db = _db()
    client = TestClient(build_app(model=FakeReplyModel(), db_path=db))

    ChapterStore(str(db)).upsert("main", "第一章 引言", "本文研究……", 1)

    tpls = client.get("/api/workflows").json()
    tpl = next(t for t in tpls if t["name"] == "审稿回复")
    task_id = client.post(
        f"/api/workflows/{tpl['id']}/run",
        json={
            "book_id": "main",
            "params": {
                "comments": json.dumps(["创新性不足", "实验对比缺失"], ensure_ascii=False),
                "manuscript_title": "第一章 引言",
            },
        },
    ).json()["task_id"]
    t: dict[str, Any] = {}
    for _ in range(30):
        t = client.get(f"/api/workflows/tasks/{task_id}").json()
        if t["status"] in ("done", "failed"):
            break
        time.sleep(0.5)
    assert t["status"] == "done", t.get("error")


# ---------------------------------------------------------------------------
# S248：校园模板包（拆论文/文献综述/申报书起草/多平台改写）预置 + e2e
# ---------------------------------------------------------------------------
def test_campus_templates_seeded() -> None:
    client = TestClient(build_app(model=_Skills(), db_path=_db()))  # type: ignore[arg-type]  # 占位：genre 端点不触模型
    names = {t["name"] for t in client.get("/api/workflows").json()}
    assert {"拆论文", "文献综述", "申报书起草", "多平台改写"} <= names


def test_multi_platform_template_runs() -> None:
    class FakeAdaptModel:
        model_name = "fake-adapt"

        def respond(self, messages: list[Message], tools: object) -> ModelOutput:
            prompt = messages[-1].content if messages else ""
            if "整理为交付稿" in prompt:
                return ModelOutput(text="【公众号】…\n【小红书】…", tool_calls=[])
            return ModelOutput(text="平台版本正文。", tool_calls=[])

    db = _db()
    client = TestClient(build_app(model=FakeAdaptModel(), db_path=db))
    ChapterStore(str(db)).upsert("main", "第一章", "原稿内容。", 1)

    tpls = client.get("/api/workflows").json()
    tpl = next(t for t in tpls if t["name"] == "多平台改写")
    task_id = client.post(
        f"/api/workflows/{tpl['id']}/run",
        json={
            "book_id": "main",
            "params": {
                "chapter_title": "第一章",
                "platforms": "公众号,小红书",
            },
        },
    ).json()["task_id"]
    t: dict[str, Any] = {}
    for _ in range(30):
        t = client.get(f"/api/workflows/tasks/{task_id}").json()
        if t["status"] in ("done", "failed"):
            break
        time.sleep(0.5)
    assert t["status"] == "done", t.get("error")


def test_list_split_comma_line() -> None:
    """S250 实测回潮防护：单行逗号串必须切开（假模型 e2e 曾掩盖）。"""
    from dataclasses import dataclass, field

    from anyspark.server.wf_scripts import wf_script_list_split
    from anyspark.workflow.engine import NodeResult

    @dataclass
    class _Ctx:
        task_id: str = "t"
        book_id: str = "main"
        definition: Any = None
        results: dict[str, Any] = field(default_factory=dict)

    node = type("N", (), {"id": "s", "kind": "script", "params": {"text": "a b,c d，e；f"}})()
    r = wf_script_list_split(None, _Ctx(), node)  # type: ignore[arg-type]
    assert isinstance(r, NodeResult) and r.output
    import json as _j

    assert _j.loads(r.output) == ["a b", "c d", "e", "f"]
