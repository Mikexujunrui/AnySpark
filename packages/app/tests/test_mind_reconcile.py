"""S132c 跨会话对账工具测试：mind_reconcile（条目 vs 最近信号 → 冲突提示，只读）。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from anyspark.align import ManualEntry, ManualStore, SignalStore
from anyspark.core.types import Message, ModelOutput
from anyspark.server.tools_domain import make_mind_reconcile_implementer


class FakeModel:
    """可脚本化的假模型：respond 返回预设文本。"""

    def __init__(self) -> None:
        self.model_name = "fake"
        self.last_prompt = ""
        self._reply = '[]'

    def set_reply(self, text: str) -> None:
        self._reply = text

    def respond(self, messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        self.last_prompt = messages[0].content or ""
        return ModelOutput(text=self._reply)


def _stores() -> tuple[ManualStore, SignalStore]:
    db = Path(tempfile.mkdtemp()) / "t.db"
    return ManualStore(db), SignalStore(db)


def _seed(manual: ManualStore, signals: SignalStore) -> None:
    manual.add(
        ManualEntry(
            content="避免使用破折号",
            source="user",
            confidence=0.9,
            category="habit",
            scope="project",
            book_id="main",
        )
    )
    from anyspark.align import Signal

    signals.record(
        Signal(
            kind="modified",
            content="原文：他——走了。\n改为：他走了。",
            context="稿纸保存",
            book_id="main",
        )
    )


def test_reconcile_no_entries() -> None:
    manual, signals = _stores()
    model = FakeModel()
    spec, impl = make_mind_reconcile_implementer(manual, signals, model)
    assert spec.name == "mind_reconcile"
    r = impl(spec, {})
    assert r.ok is True and "暂无条目" in r.content


def test_reconcile_conflict_found() -> None:
    manual, signals = _stores()
    _seed(manual, signals)
    model = FakeModel()
    model.set_reply(
        '[{"entry": "避免使用破折号", "verdict": "一致", "note": "最近修改确实去掉了破折号"}, '
        '{"entry": "打斗场景要多用动词", "verdict": "需更新", "note": "最近两次修改与动词偏好无关"}]'
    )
    spec, impl = make_mind_reconcile_implementer(manual, signals, model)
    r = impl(spec, {})
    assert r.ok is True
    # 只读：结果自然语言化返回，含冲突详情
    assert "对账" in r.content
    assert "打斗场景要多用动词" in r.content
    assert r.data is not None and len(r.data["results"]) == 2


def test_reconcile_no_conflict() -> None:
    manual, signals = _stores()
    _seed(manual, signals)
    model = FakeModel()
    model.set_reply("[]")
    spec, impl = make_mind_reconcile_implementer(manual, signals, model)
    r = impl(spec, {})
    assert r.ok is True and "未发现" in r.content


def test_reconcile_prompt_contains_entries_and_signals() -> None:
    manual, signals = _stores()
    _seed(manual, signals)
    model = FakeModel()
    spec, impl = make_mind_reconcile_implementer(manual, signals, model)
    impl(spec, {})
    assert "避免使用破折号" in model.last_prompt  # 条目进了 prompt
    assert "他——走了" in model.last_prompt  # 信号内容进了 prompt（build_reconcile_prompt 只含 kind+content）


def test_reconcile_failure_graceful() -> None:
    manual, signals = _stores()
    _seed(manual, signals)
    model = FakeModel()

    def boom(messages: list[Message], tools) -> ModelOutput:  # type: ignore[no-untyped-def]
        raise RuntimeError("llm down")

    model.respond = boom  # type: ignore[method-assign]
    spec, impl = make_mind_reconcile_implementer(manual, signals, model)
    r = impl(spec, {})
    assert r.ok is False and "对账失败" in r.content
