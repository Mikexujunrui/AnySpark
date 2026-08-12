"""Regression tests for evidence-grounded review panels."""

from unittest.mock import MagicMock, patch


def test_continuation_style_reviewer_requires_knowledge():
    from core.review_panel import ReviewPanel

    panel = ReviewPanel()
    reviewer = panel.get_reviewer("continuation_style_expert")
    assert reviewer is not None
    assert reviewer.needs_knowledge is True


def test_unsupported_work_title_detection():
    from core.review_panel import _unsupported_work_titles

    evidence = "当前项目《本书》；参考样本《风格样本》。"
    response = "这段像《红楼梦》，但也接近《风格样本》。"
    assert _unsupported_work_titles(response, evidence) == ["红楼梦"]


@patch("tools.impl.review.json_store")
def test_review_evidence_labels_style_reference_as_non_canon(mock_store):
    from tools.impl.review import _build_review_evidence

    books = {"book": {"title": "当前作品"}, "ref": {"title": "作者其他作品"}}
    mock_store.get_book.side_effect = lambda bid: books[bid]
    mock_store.get_reference_books.return_value = ["ref"]
    mock_store.get_reference_profiles.return_value = {"ref": "style"}
    mock_store.get_chapter.side_effect = Exception("no target")
    mock_store.load_chapters.side_effect = lambda bid: [{"id": "c1"}] if bid == "book" else [{"id": "r1"}]
    mock_store._chapter_view.side_effect = lambda raw: {
        "id": raw["id"],
        "title": "样本章",
        "content": "这是可核验的正文样本。",
    }
    kb = MagicMock()
    kb.get_knowledge_summary.return_value = "角色甲：谨慎"

    with patch("core.writer._build_reference_context", return_value=""):
        result = _build_review_evidence("book", "#2", kb)

    assert "当前项目：当前作品" in result
    assert "[当前书知识库·事实]" in result
    assert "参考书·只学文风·不得作为当前书原著事实" in result
    assert "作者其他作品" in result
    assert "这是可核验的正文样本" in result


@patch("core.review_panel.llm_chat")
def test_reviewer_rejects_ungrounded_work_title(mock_chat):
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    from core.review_panel import ReviewerDef, ReviewPanel

    mock_chat.return_value = (
        '{"scores":{"\u4e00\u81f4\u6027":5},"overall_score":5,'
        '"highlights":["\u5c1a\u53ef"],"issues":["\u50cf\u300a\u7ea2\u697c\u68a6\u300b"],'
        '"suggestions":["\u8c03\u6574"],"comment":"\u50cf\u300a\u7ea2\u697c\u68a6\u300b"}'
    )
    reviewer = ReviewerDef(
        id="grounding_test",
        name="测试评审",
        persona="只检查一致性",
        category="test",
        needs_knowledge=True,
    )
    panel = ReviewPanel()
    loop = asyncio.new_event_loop()
    try:
        executor = ThreadPoolExecutor(max_workers=1)
        result = loop.run_until_complete(
            panel._single_review(reviewer, "当前章节正文足够长。" * 10, "当前项目：测试书", loop, executor, None)
        )
        executor.shutdown(wait=True)
    finally:
        loop.close()

    assert "证据中不存在的作品名" in result.error
    assert mock_chat.call_count == 2
