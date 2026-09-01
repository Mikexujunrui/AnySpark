"""S246：内置规则包（学术检测项种子）+ 审稿回复模板测试。

设计要点：学术检测项是内容数据（借 S195 用户骨架通道自举，尊重用户删除），
不是硬编码第二骨架；审稿回复是纯模板（既有原语接线，零新机制）。"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from anyspark.core.protocol import ToolSpec
from anyspark.core.types import Message, ModelOutput, ToolResult
from anyspark.server.app import build_app
from anyspark.server.check_store import BUILTIN_ACADEMIC_CHECKS, UserSkeletonStore
from anyspark.server.tools_check import make_check_implementer


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "t.db"


def _call(impl: Any, name: str = "t", /, **kwargs: Any) -> ToolResult:
    spec = ToolSpec(name=name, description="t", params=[])
    result = impl(spec, kwargs)
    assert isinstance(result, ToolResult)
    return result


# ---------------------------------------------------------------------------
# 学术规则包：自举 + 幂等 + 尊重用户删除
# ---------------------------------------------------------------------------
def test_academic_skeleton_seeded() -> None:
    store = UserSkeletonStore(_db())
    cats = {i.category for i in store.list_additions()}
    assert cats == {c for c, _ in BUILTIN_ACADEMIC_CHECKS}  # 七项全数入库


def test_seed_idempotent_and_respects_deletion() -> None:
    db = _db()
    store = UserSkeletonStore(db)
    store.delete_addition_by_category("术语一致性")  # 用户删除
    # 重建实例（模拟重启）：已删除类别不得复活
    store2 = UserSkeletonStore(db)
    cats = {i.category for i in store2.list_additions()}
    assert "术语一致性" not in cats
    assert len(cats) == len(BUILTIN_ACADEMIC_CHECKS) - 1


def test_check_tool_uses_merged_checks() -> None:
    """agent 自查应使用传入的合并骨架（含用户/内置添加项）——S246 接线。"""

    class FakeCheckModel:
        model_name = "fake-check"

        def respond(self, messages: list[Message], tools: object) -> ModelOutput:
            prompt = messages[0].content if messages else ""
            if "术语一致性" in prompt:
                finding = json.dumps(
                    [{"message": "同一概念前后称谓不一", "evidence": "第2段", "severity": "hard"}],
                    ensure_ascii=False,
                )
                return ModelOutput(text=finding, tool_calls=[])
            return ModelOutput(text="[]", tool_calls=[])

    custom = [
        item
        for item in (UserSkeletonStore(_db()).list_additions())  # 借种子内容当自定义项
        if item.category == "术语一致性"
    ]
    _, impl = make_check_implementer(FakeCheckModel(), checks=custom)
    r = _call(impl, "check_text", text="测试正文：A 方法与 a 方法混用。")
    assert r.ok is True
    assert "同一概念前后称谓不一" in r.content


# ---------------------------------------------------------------------------
# 审稿回复模板：预置存在 + e2e（逐条回应 → 汇编回复信）
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

    from anyspark.store.sqlite import ChapterStore

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
