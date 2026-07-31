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
async def test_writing_result_not_saved_emits_truthful_failure_event():
    events, text, updated, terminal = await flow_writing_result(
        {"type": "writing_result", "saved": False, "text": "失败"}, "b1"
    )
    assert len(events) == 1 and events[0].type == "writing_end"
    assert events[0].data["saved"] is False
    assert events[0].data["error"] == "失败"
    assert text == "失败"
    assert not updated and terminal is None


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
