"""Unit tests for domain result flows (core/flows).

M3.5 — each flow gets direct coverage so future changes to the loop
dispatcher are validated against flow behaviour, not just e2e.
"""

import pytest

from core.flows import RESULT_FLOWS
from core.flows.engine_signal import flow_task_list
from core.flows.user_interaction import flow_ask_user, flow_plot_cards
from core.flows.work_product import flow_patch_result, flow_review_result, flow_writing_result


def test_dispatch_table_has_all_known_types():
    assert set(RESULT_FLOWS) == {
        "plot_cards",
        "autopilot_plan",
        "writing_result",
        "task_list",
        "patch_result",
        "review_result",
        "question",
    }


@pytest.mark.asyncio
async def test_writing_result_saved_emits_event():
    events, text, updated, terminal = await flow_writing_result(
        {"type": "writing_result", "saved": True, "chapter_id": "#3", "chapter_title": "章三", "text": "写好了"}, "b1"
    )
    assert len(events) == 1 and events[0].type == "writing_end"
    assert text == "写好了"
    assert not updated and terminal is None


@pytest.mark.asyncio
async def test_writing_result_not_saved_no_event():
    events, text, updated, terminal = await flow_writing_result(
        {"type": "writing_result", "saved": False, "text": "失败"}, "b1"
    )
    assert events == []


@pytest.mark.asyncio
async def test_patch_result_error_path():
    events, text, updated, terminal = await flow_patch_result(
        {"type": "patch_result", "error": "锚点未找到", "text": "部分失败"}, "b1"
    )
    assert events == []
    assert "部分失败" in text


@pytest.mark.asyncio
async def test_patch_result_success_emits_event():
    events, text, updated, terminal = await flow_patch_result(
        {"type": "patch_result", "patched_count": 2, "total_count": 2, "text": "ok"}, "b1"
    )
    assert len(events) == 1 and events[0].type == "patch_result"
    assert events[0].data["patched_count"] == 2


@pytest.mark.asyncio
async def test_review_result_is_terminal():
    events, text, updated, terminal = await flow_review_result(
        {"type": "review_result", "text": "评审报告"}, "b1"
    )
    assert updated is True
    assert terminal == "评审报告"


@pytest.mark.asyncio
async def test_task_list_emits_event():
    events, text, updated, terminal = await flow_task_list(
        {"type": "task_list", "items": [{"label": "a"}], "text": "计划"}, "b1"
    )
    assert len(events) == 1 and events[0].type == "task_list"
    assert events[0].data["items"] == [{"label": "a"}]


@pytest.mark.asyncio
async def test_ask_user_flow(monkeypatch):
    from core import question as qmod

    monkeypatch.setattr(
        qmod.manager,
        "create_question",
        lambda qs, book_id="": type("R", (), {"id": "q_test", "questions": qs})(),
    )
    async def fake_wait(qid):
        return [["是的"]]
    monkeypatch.setattr(qmod.manager, "wait_for_answer", fake_wait)

    events, text, updated, terminal = await flow_ask_user(
        {"type": "question", "questions": [{"question": "继续吗？"}]}, "b1"
    )
    assert len(events) == 1 and events[0].type == "question"
    assert "是的" in text


@pytest.mark.asyncio
async def test_plot_cards_flow(monkeypatch):
    from core import question as qmod

    monkeypatch.setattr(
        qmod.manager,
        "create_question",
        lambda qs, book_id="": type("R", (), {"id": "q_cards", "questions": qs})(),
    )
    async def fake_wait(qid):
        return [["方向A"]]
    monkeypatch.setattr(qmod.manager, "wait_for_answer", fake_wait)

    events, text, updated, terminal = await flow_plot_cards(
        {"type": "plot_cards", "cards": [{"title": "方向A"}], "context_summary": "ctx"}, "b1"
    )
    assert len(events) == 1 and events[0].type == "plot_cards"
    assert "方向A" in text


@pytest.mark.asyncio
async def test_ask_user_emit_yields_event_before_waiting(monkeypatch):
    """Regression: the SSE question event must be produced BEFORE blocking
    on the user's answer, or the frontend never renders the options."""
    from core import question as qmod

    created = {}

    def fake_create(qs, book_id=""):
        req = type("R", (), {"id": "q_early", "questions": qs})()
        created["id"] = req.id
        return req

    monkeypatch.setattr(qmod.manager, "create_question", fake_create)

    from core.flows.user_interaction import flow_ask_user_emit, flow_ask_user_wait

    events = await flow_ask_user_emit({"type": "question", "questions": [{"question": "选一个？"}]}, "b1")
    # Event must be available immediately — no waiting.
    assert events is not None and len(events) == 1
    assert events[0].type == "question"
    assert events[0].data["id"] == created["id"]

    text = await flow_ask_user_wait({"type": "question", "questions": [{"question": "选一个？"}]}, "b1", [["红色"]])
    assert "红色" in text


@pytest.mark.asyncio
async def test_ask_user_emit_no_questions_returns_none():
    from core.flows.user_interaction import flow_ask_user_emit

    assert await flow_ask_user_emit({"type": "question", "questions": []}, "b1") is None


@pytest.mark.asyncio
async def test_ask_user_normalizes_string_options(monkeypatch):
    """LLM may pass options as plain strings; frontend needs {label} objects."""
    from core import question as qmod

    captured = {}

    def fake_create(qs, book_id=""):
        captured["qs"] = qs
        return type("R", (), {"id": "q_norm", "questions": qs})()

    monkeypatch.setattr(qmod.manager, "create_question", fake_create)

    from core.flows.user_interaction import flow_ask_user_emit

    await flow_ask_user_emit(
        {"type": "question", "questions": [{"question": "继续？", "options": ["是", "否"]}]}, "b1"
    )
    opts = captured["qs"][0]["options"]
    assert opts == [{"label": "是", "description": ""}, {"label": "否", "description": ""}]
