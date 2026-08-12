"""S56（C 架构）写作工具测试：write_chapter 意图模式（干净写作调用）/ 直写兼容 / 降级。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from anyspark.core import ToolRegistry
from anyspark.core.types import Message, ModelOutput, ToolResult
from anyspark.server.tools_writing import register_writing_tools
from anyspark.server.workspace import Workspace
from anyspark.store import ChapterStore


class CleanWriteModel:
    """模拟写作模型：记录收到的干净上下文，返回固定正文。"""

    def __init__(self) -> None:
        self.clean_contexts: list[str] = []
        self.model_name = "clean-writer"

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        for m in messages:
            if m.role == "system":
                self.clean_contexts.append(m.content)
                break
        return ModelOutput(
            text="海格把门板从门框上扯下来，雨水灌进小屋。他弯下腰，借着闪电看清了哈利。"
        )


class EmptyWriterModel:
    """模拟写作模型返回空正文（测试降级）。"""

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        return ModelOutput(text="")


class _Skills:
    """最小 skills store（满足 list_skills 接口）。"""

    def list_skills(self) -> list[object]:
        return []


def _registry(model: object | None = None) -> tuple[ToolRegistry, ChapterStore]:
    db = Path(tempfile.mkdtemp()) / "ch.db"
    chapters = ChapterStore(db)
    reg = ToolRegistry()
    register_writing_tools(reg, chapters, model=model, skills_store=_Skills())
    return reg, chapters


def _invoke(reg: ToolRegistry, name: str, args: dict[str, object]) -> ToolResult:
    from anyspark.core.protocol import execute
    from anyspark.core.types import ToolCall

    return execute(reg, ToolCall(name=name, arguments=args))


def test_write_chapter_intent_mode_uses_clean_call() -> None:
    """意图模式：传 intent+references → 干净写作调用生成正文 → 落盘。"""
    model = CleanWriteModel()
    reg, chapters = _registry(model=model)
    r = _invoke(
        reg,
        "write_chapter",
        {
            "title": "第4章",
            "intent": "海格破门接走哈利，告知巫师身份",
            "references": "海格（角色）：霍格沃茨猎场看守；哈利 11 岁，在礁石小屋",
        },
    )
    assert r.ok is True
    assert "意图模式" in str(r.content)
    # 干净上下文：含意图+参考+写作系统提示，无对话历史
    ctx = model.clean_contexts[-1]
    assert "写作意图" in ctx and "海格破门接走哈利" in ctx
    assert "写作参考" in ctx and "霍格沃茨猎场看守" in ctx
    # 落盘成功
    chs = chapters.list_by_book("main")
    assert len(chs) == 1 and "海格把门板" in chs[0].content


def test_write_chapter_direct_mode_still_works() -> None:
    """直写模式兼容：传 content 直接落盘（无 model 也可）。"""
    reg, chapters = _registry(model=None)
    r = _invoke(reg, "write_chapter", {"title": "第1章", "content": "哈利住在女贞路。"})
    assert r.ok is True
    assert "直写" in str(r.content)
    assert chapters.list_by_book("main")[0].content == "哈利住在女贞路。"


def test_write_chapter_intent_without_model_degrades() -> None:
    """意图模式但无 model 注入（测试环境）→ 明确报错，可降级。"""
    reg, _ = _registry(model=None)
    r = _invoke(
        reg,
        "write_chapter",
        {"title": "第4章", "intent": "海格接走哈利"},
    )
    assert r.ok is False
    assert "写作引擎生成失败" in str(r.content)


def test_write_chapter_empty_writer_degrades() -> None:
    """写作模型返回空正文 → 报错降级（不落盘空章）。"""
    reg, chapters = _registry(model=EmptyWriterModel())
    r = _invoke(
        reg,
        "write_chapter",
        {"title": "第4章", "intent": "海格接走哈利"},
    )
    assert r.ok is False
    assert chapters.list_by_book("main") == []  # 未落盘


def test_write_chapter_missing_both_args() -> None:
    """既无 content 也无 intent → 提示用意图模式或直写。"""
    reg, _ = _registry(model=None)
    r = _invoke(reg, "write_chapter", {"title": "第4章"})
    assert r.ok is False
    assert "intent" in str(r.content)


# ---------------------------------------------------------------------------
# S70：破限模式注入（干净写作调用）
# ---------------------------------------------------------------------------
def _unc_registry(model: object, workspace: Workspace) -> ToolRegistry:
    db = Path(tempfile.mkdtemp()) / "ch.db"
    chapters = ChapterStore(db)
    reg = ToolRegistry()
    register_writing_tools(reg, chapters, model=model, skills_store=_Skills(), workspace=workspace)
    return reg


def test_clean_write_injects_uncensored_when_flag_on() -> None:
    """S70：破限开关开 → 写作调用注入破限提示词。"""
    from anyspark.server.tools_writing import UNCENSORED_PROMPT
    from anyspark.server.workspace import Workspace

    ws = Workspace(root=Path(tempfile.mkdtemp()) / "ws")
    ws.set_uncensored("main", True)
    model = CleanWriteModel()
    reg = _unc_registry(model, ws)
    r = _invoke(reg, "write_chapter", {"title": "测试章", "intent": "写一段黑暗氛围的场景"})
    assert r.ok is True
    assert UNCENSORED_PROMPT in model.clean_contexts[0]


def test_clean_write_no_inject_when_flag_off() -> None:
    """S70：破限开关关 → 不注入（默认行为不变）。"""
    from anyspark.server.workspace import Workspace

    ws = Workspace(root=Path(tempfile.mkdtemp()) / "ws")
    model = CleanWriteModel()
    reg = _unc_registry(model, ws)
    _invoke(reg, "write_chapter", {"title": "测试章", "intent": "写一段黑暗氛围的场景"})
    assert all("创作模式声明" not in c for c in model.clean_contexts)


def test_read_file_lists_directory(tmp_path) -> None:
    """S108：read_file 传目录 → 列出内容（此前 Errno 13 误导为权限错误）。"""
    from anyspark.server.tools_writing import SANDBOX_DIR, _resolve_sandbox_path
    from anyspark.server.tools_writing import WritingTools
    from anyspark.core import ToolSpec, ToolCall

    # 真实沙箱目录（测试环境 data/sandbox 已存在）
    sd = SANDBOX_DIR
    if not sd.exists():
        sd.mkdir(parents=True)
    # 建一个测试文件
    probe = sd / "_read_file_dir_test.txt"
    probe.write_text("内容", encoding="utf-8")

    tools = WritingTools(chapters=None, book_id="main")  # type: ignore[arg-type]
    r = tools.read_file(ToolSpec(name="read_file"), {"path": "."})
    assert r.ok is True
    assert "_read_file_dir_test.txt" in r.content  # 目录列出包含测试文件
    assert r.content.startswith("目录")  # 不再是 Errno 13

    probe.unlink(missing_ok=True)
