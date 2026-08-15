"""S102 批量提议工具测试——agent 批量改写/批量审读工具（提议模式，不直接执行）。"""

from __future__ import annotations

from pathlib import Path

from anyspark.server.tools_domain import make_batch_implementer
from anyspark.store import ChapterStore


def _store_with_chapters() -> ChapterStore:
    store = ChapterStore(":memory:")
    store.upsert("main", "第一章 雨夜", "雨夜，陈渡抵达雾城站。", order_index=1)
    store.upsert("main", "第二章 雾城", "雾城的老钟表铺。", order_index=2)
    store.upsert("main", "第三章 钟表铺", "老周欲言又止。", order_index=3)
    return store


def test_batch_rewrite_suggests_and_does_not_execute() -> None:
    """S102：批量改写工具返回待确认申请（含指令与匹配章节），不执行批量。"""
    specs, impls = make_batch_implementer(_store_with_chapters(), book_id="main")
    rewrite_spec = next(s for s in specs if s.name == "batch_rewrite")
    rewrite_impl = impls[specs.index(rewrite_spec)]

    res = rewrite_impl(
        rewrite_spec, {"chapter_titles": "第一章,雨夜", "instruction": "统一为冷峻克制"}
    )
    assert res.ok is True
    content = res.content
    assert "待用户批准" in content
    assert "统一为冷峻克制" in content
    assert "第一章 雨夜" in content
    assert "不直接执行" not in content  # 描述在 spec，不在结果
    assert "批准" in content


def test_batch_review_suggests() -> None:
    specs, impls = make_batch_implementer(_store_with_chapters(), book_id="main")
    review_spec = next(s for s in specs if s.name == "batch_review")
    review_impl = impls[specs.index(review_spec)]

    res = review_impl(review_spec, {"chapter_titles": "第三章,不存在章"})
    assert res.ok is True
    assert "待用户批准" in res.content
    assert "第三章 钟表铺" in res.content
    assert "不存在章" in res.content  # 未匹配提示


def test_batch_tool_missing_params() -> None:
    specs, impls = make_batch_implementer(_store_with_chapters(), book_id="main")
    rewrite_spec = next(s for s in specs if s.name == "batch_rewrite")
    rewrite_impl = impls[specs.index(rewrite_spec)]

    # 缺指令
    res = rewrite_impl(rewrite_spec, {"chapter_titles": "第一章"})
    assert res.ok is False
    assert "参数不完整" in res.content

    # 标题全不匹配
    res = rewrite_impl(rewrite_spec, {"chapter_titles": "完全不存在", "instruction": "改"})
    assert res.ok is False
    assert "未匹配到任何章节" in res.content


def test_batch_tool_accepts_json_array_string() -> None:
    """S102：chapter_titles 兼容 JSON 数组字符串（agent 可能传数组字面量）。"""
    specs, impls = make_batch_implementer(_store_with_chapters(), book_id="main")
    rewrite_spec = next(s for s in specs if s.name == "batch_rewrite")
    rewrite_impl = impls[specs.index(rewrite_spec)]

    res = rewrite_impl(
        rewrite_spec, {"chapter_titles": '["第一章 雨夜","第二章 雾城"]', "instruction": "改"}
    )
    assert res.ok is True
    assert "第一章 雨夜" in res.content
    assert "第二章 雾城" in res.content


def test_agent_can_invoke_batch_tool(tmp_path: Path) -> None:
    """S102 集成：agent 循环中真实调用 batch_rewrite 工具（注册链路完整，提议不执行）。"""
    from anyspark.core import ModelOutput, ToolCall
    from anyspark.server.app import build_app
    from anyspark.store import ChapterStore

    class FakeBatchModel:
        def __init__(self) -> None:
            self.calls = 0
            self.model_name = "fake-batch"

        def respond(self, messages, tools) -> ModelOutput:  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                return ModelOutput(
                    tool_calls=[
                        ToolCall(
                            name="batch_rewrite",
                            arguments={
                                "chapter_titles": "第一章,第二章",
                                "instruction": "统一文风",
                            },
                        )
                    ]
                )
            return ModelOutput(text="已提交批量改写申请，等待用户批准。")

    from fastapi.testclient import TestClient

    db = tmp_path / "t.db"
    shared = ChapterStore(db)
    shared.upsert("main", "第一章 雨夜", "内容1", order_index=1)
    shared.upsert("main", "第二章 雾城", "内容2", order_index=2)

    client = TestClient(build_app(db_path=db, model=FakeBatchModel()))
    r = client.post("/api/conversations", json={"title": "会话", "book_id": "main"})
    conv_id = r.json()["id"]

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "把前两章统一文风", "conversation_id": conv_id},
    ) as resp:
        body = "".join(resp.iter_text())

    # 工具被调用（SSE tool_call 帧含 batch_rewrite）+ 文本回复
    assert "batch_rewrite" in body
    assert "批准" in body
