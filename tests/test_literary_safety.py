"""Regression tests for the literary-safety and project-rule release."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest


def test_word_count_is_not_mistaken_for_chapter_number():
    from tools.impl.writing import _requested_regular_chapter_index

    assert _requested_regular_chapter_index({}, "续写一章，约 2500 字") is None
    assert _requested_regular_chapter_index({}, "续写第 12 章，约 2500 字") == 12
    assert _requested_regular_chapter_index({"chapter_index": 3}, "写 5000 字") == 3


def test_new_chapter_guard_protects_existing_target(monkeypatch):
    from tools.impl import writing

    chapter = {"id": "old", "title": "旧章", "protected": True}
    monkeypatch.setattr(writing.json_store, "load_chapters", lambda _book_id: [chapter])
    monkeypatch.setattr(writing.json_store, "_find_chapter", lambda _rows, ref: chapter if ref == "#2" else None)
    monkeypatch.setattr(
        writing.json_store,
        "_chapter_view",
        lambda _chapter: {"id": "old", "title": "旧章", "protected": True},
    )

    result = writing._guard_new_chapter_target("book", {}, "请写第2章")

    assert result["saved"] is False
    assert result["protected"] is True
    assert "拒绝覆盖" in result["text"]


def test_creative_constitution_is_a_system_constraint(monkeypatch):
    from core import creative_constitution

    monkeypatch.setattr(
        creative_constitution.json_store,
        "get_book",
        lambda _book_id: {
            "creativeConstitution": "必须使用第三人称限知视角。",
            "constitutionEnabled": True,
        },
    )

    section = creative_constitution.build_constitution_system_section("book")

    assert "项目级硬约束" in section
    assert "第三人称限知" in section
    assert "不得静默忽略" in section


def test_prose_parameters_only_apply_to_creative_calls(monkeypatch):
    from core import llm_client
    from core.settings import GenerationSettings

    monkeypatch.setattr(
        llm_client,
        "_settings",
        lambda: SimpleNamespace(
            generation=GenerationSettings(
                temperature=1.1,
                top_p=0.8,
                frequency_penalty=0.4,
                presence_penalty=0.2,
                max_output_tokens=9000,
            )
        ),
    )

    writing = llm_client._prose_completion_kwargs("writing", 0.3)
    extraction = llm_client._prose_completion_kwargs("extraction", 0.1)

    assert writing == {
        "temperature": 1.1,
        "top_p": 0.8,
        "frequency_penalty": 0.4,
        "presence_penalty": 0.2,
        "max_tokens": 9000,
    }
    assert extraction == {"temperature": 0.1, "max_tokens": 16384}


def test_generation_settings_are_clamped():
    from core.settings import GenerationSettings

    value = GenerationSettings(
        temperature=9,
        top_p=0,
        frequency_penalty=-9,
        presence_penalty=9,
        max_output_tokens=1,
    ).normalized()

    assert value.temperature == 2
    assert value.top_p == 0.01
    assert value.frequency_penalty == -2
    assert value.presence_penalty == 2
    assert value.max_output_tokens == 512


def test_style_only_reference_does_not_load_entities():
    from core.writer import _build_reference_context

    with (
        patch("core.writer.json_store") as store,
        patch("core.graph_store.GraphStore") as graph_store,
        patch("core.reference_analyzer.load_analysis", return_value=None),
    ):
        store.get_reference_books.return_value = ["ref"]
        store.get_reference_profiles.return_value = {"ref": "style"}
        store.get_book.return_value = {"title": "作者的另一部小说"}
        store.load_chapters.return_value = []

        result = _build_reference_context("book")

    assert "只学习作者文风" in result
    graph_store.assert_not_called()


def test_style_only_reference_blocks_fact_migration(monkeypatch):
    from tools.impl import handlers

    monkeypatch.setattr(handlers.json_store, "get_reference_books", lambda _book_id: ["ref"])
    monkeypatch.setattr(handlers.json_store, "get_reference_profiles", lambda _book_id: {"ref": "style"})

    result = handlers._handle_materials(
        "migrate_reference_knowledge",
        {"ref_book_id": "ref", "entity_name": "不应迁移的人物"},
        "book",
    )

    assert "禁止迁移" in result
    assert "只学文风" in result


def test_autonomous_mode_runs_recoverable_edits_but_still_asks_before_deletion():
    from core.permissions import PermissionManager

    manager = PermissionManager()
    manager.autonomous_mode = True

    assert manager.check("search_knowledge") == "allow"
    assert manager.check("patch_chapter") == "allow"
    assert manager.check("edit_chapter") == "allow"
    assert manager.check("delete_chapter") == "ask"


def test_autonomous_quality_failure_pauses():
    from core.quality_gate import QualityResult, should_pause_for_quality

    assert should_pause_for_quality(QualityResult(passed=False, action="pause"), "autonomous") is True


def test_every_default_skill_references_a_real_tool():
    from core.skills import manager
    from core.tools import registry

    missing = []
    for skill in manager.list_skills(source="system"):
        for step in skill["steps"]:
            if registry.get(step.get("tool", "")) is None:
                missing.append((skill["name"], step.get("tool", "")))

    assert missing == []


@pytest.mark.asyncio
async def test_planner_understands_chinese_chapter_numbers(monkeypatch):
    from core.autopilot.planner import AutopilotPlanner
    from data.json_store import json_store

    chapters = [
        {"title": "第十一章 风雪", "content": "a"},
        {"title": "第二十章 归途", "content": "b"},
    ]
    monkeypatch.setattr(json_store, "load_chapters", lambda _book_id: chapters)
    monkeypatch.setattr(json_store, "load_outline", lambda _book_id: {})
    monkeypatch.setattr(json_store, "load_detailed_outline", lambda _book_id: {})
    monkeypatch.setattr(json_store, "load_volumes", lambda _book_id: [])

    state = await AutopilotPlanner()._read_book_state("book")

    assert 11 in state["existing_indices"]
    assert 20 in state["existing_indices"]


@pytest.mark.asyncio
async def test_one_model_response_can_prepare_only_one_full_chapter_writer():
    from core.agent_loop import AgentConfig, _prepare_tool_calls
    from core.llm_client import LLMResponse, ToolCall
    from core.loop_state import LoopState
    from core.session_state import RunHandle

    response = LLMResponse(
        tool_calls=[
            ToolCall(id="first", name="delegate_writing", arguments='{"instruction":"写新章"}'),
            ToolCall(id="second", name="write_chapter", arguments='{"instruction":"再写一次"}'),
        ]
    )
    messages = []
    prepared = []
    state = LoopState(max_rounds=10, base_temperature=0.2)

    async for _event in _prepare_tool_calls(
        response,
        messages,
        AgentConfig(book_id="book", session_id="session"),
        RunHandle("session"),
        state,
        prepared,
    ):
        pass

    assert [item["tc"].id for item in prepared] == ["first"]
    assert any(message.get("tool_call_id") == "second" and "互斥保护" in message["content"] for message in messages)


def test_autopilot_never_rewrites_when_outline_is_already_complete():
    from core.autopilot.config import AutopilotConfig, PlanIntent
    from core.autopilot.planner import AutopilotPlanner

    result = AutopilotPlanner()._plan_write_new(
        "plan",
        AutopilotConfig(book_id="book", instruction="继续写"),
        {
            "existing_indices": {1, 2},
            "existing_count": 2,
            "outline_chapters": [{"title": "第一章"}, {"title": "第二章"}],
        },
        PlanIntent(intent_type="write_new"),
    )

    assert result["steps"] == []
    assert "不会" in result["plan_summary"]


def test_autopilot_reviews_before_extracting_durable_knowledge():
    from core.autopilot.config import AutopilotConfig
    from core.autopilot.planner import AutopilotPlanner

    steps = AutopilotPlanner()._build_chapter_steps(
        "plan",
        3,
        "第三章",
        AutopilotConfig(
            book_id="book",
            instruction="继续写",
            auto_review=True,
            auto_extract=True,
        ),
        0,
    )
    labels = [step.label for step in steps]

    assert labels.index("评审第三章") < labels.index("提取第三章知识")
    review = next(step for step in steps if step.label == "评审第三章")
    assert "禁止调用任何写作或修改工具" in review.config["prompt"]
