"""Regression tests for capability routing, Skill runtime, and plot budgets."""

import asyncio

from core.capability_router import select_capabilities, tools_missing_from_packs
from core.narrative_budget import (
    NarrativeSegmentContract,
    build_segment_contracts,
    check_segment_boundary,
    plan_segment_contracts,
)
from core.skills import SkillManager
from core.system_prompt import AGENT_PROMPTS


def test_writing_prompt_separates_total_target_from_segment_limit():
    prompt = AGENT_PROMPTS["write"]
    assert "target_words=8000" in prompt
    assert "max_segment_words=2000" in prompt
    assert "绝对不能把单段上限当成整章目标" in prompt
    assert "不得越过当前段落的剧情预算" in prompt or "每段只能消耗对应的剧情预算" in prompt


def test_capability_router_keeps_writing_turn_small_and_relevant():
    selected = select_capabilities("请续写第五章正文，写完检查一致性")
    assert "writing" in selected.packs
    assert "delegate_writing" in selected.tool_names
    assert "prepare_writing" in selected.tool_names
    assert "run_review" in selected.tool_names
    assert "delete_all_chapters" not in selected.tool_names
    assert len(selected.tool_names) < 45


def test_explicit_skill_exposes_only_declared_tools_plus_recovery():
    selected = select_capabilities(
        "渲染后的长提示不应再触发其他能力包",
        skill_tools={"list_chapters", "delegate_writing", "run_review"},
    )
    assert selected.packs == ("skill",)
    assert selected.tool_names == {"ask_user", "list_chapters", "delegate_writing", "run_review"}


def test_every_registered_tool_is_reachable_from_a_pack():
    from core.tools import registry

    assert tools_missing_from_packs(set(registry.list_names())) == set()


def test_skill_runtime_blocks_skipping_and_advances(tmp_path, monkeypatch):
    import core.skills as skills_module

    system_dir = tmp_path / "skills"
    user_dir = tmp_path / "data" / "skills"
    system_dir.mkdir(parents=True)
    user_dir.mkdir(parents=True)
    monkeypatch.setattr(skills_module, "SYSTEM_SKILLS_DIR", system_dir)
    monkeypatch.setattr(skills_module, "USER_SKILLS_DIR", user_dir)
    manager = SkillManager()
    manager.add_user_skill(
        "strict_flow",
        {
            "steps": [
                {"tool": "prepare_writing", "label": "准备"},
                {"tool": "delegate_writing", "label": "写作", "params": {"mode": "strict"}},
                {"tool": "run_review", "label": "评审"},
            ]
        },
    )

    run = manager.start_run("strict_flow")
    assert run.allow_tool("delegate_writing")[0] is False
    assert run.allow_tool("prepare_writing")[0] is True
    assert run.record_result("prepare_writing", True) is True
    assert run.current.tool == "delegate_writing"
    run.record_result("delegate_writing", False, "provider timeout")
    assert run.failed is True
    assert run.allow_tool("run_review")[0] is False


def test_long_plot_contracts_forbid_future_beats():
    contracts = build_segment_contracts(
        ["进入旧宅", "发现密门", "追踪幕后人", "决战"],
        target_chars=8000,
        max_segment_chars=2000,
    )
    assert len(contracts) == 4
    assert contracts[0].target_chars == 2000
    assert contracts[0].max_chars == 2000
    assert contracts[0].forbidden_future == ["发现密门", "追踪幕后人", "决战"]
    prompt = contracts[0].render_prompt("")
    assert "剧情预算" in prompt
    assert "不得越过" in prompt


async def test_boundary_check_rejects_hard_character_overflow():
    contract = NarrativeSegmentContract(
        index=1,
        total=4,
        beat="进入旧宅",
        target_chars=20,
        max_chars=20,
        forbidden_future=["找到凶手"],
    )
    result = await check_segment_boundary(asyncio.get_running_loop(), "字" * 21, contract)
    assert result.passed is False
    assert "21 > 20" in result.reason


async def test_contract_writer_discards_rejected_draft_before_accepting_retry(monkeypatch):
    from core.narrative_budget import BoundaryCheck
    from tools.impl.writing import _write_by_nodes

    generated = iter(["越界初稿", "合规重试", "第二段正文"])

    def fake_stream(*_args, **_kwargs):
        yield next(generated)

    checks = iter(
        [
            BoundaryCheck(False, "提前完成后续事件", "越界证据"),
            BoundaryCheck(True),
            BoundaryCheck(True),
        ]
    )

    async def fake_check(*_args, **_kwargs):
        return next(checks)

    monkeypatch.setattr("core.llm_client.chat_stream", fake_stream)
    monkeypatch.setattr("core.narrative_budget.check_segment_boundary", fake_check)

    full_text, error = await _write_by_nodes(
        asyncio.get_running_loop(),
        scoped_context="ctx",
        ref_block="",
        plot_chain=["只进入旧宅", "之后才发现密门"],
        chapter_function="",
        writing_rules="",
        system="sys",
        book_id="book",
        target_words_per_node=20,
        target_words=40,
        max_segment_words=50,
        enforce_segment_boundaries=True,
    )

    assert error is None
    assert "越界初稿" not in full_text
    assert "合规重试" in full_text
    assert "第二段正文" in full_text


async def test_segment_planner_keeps_book_provider_context_across_thread(monkeypatch):
    import json

    from core import llm_client

    seen_book_ids = []

    def fake_chat(*_args, **_kwargs):
        seen_book_ids.append(llm_client._active_book_id.get())
        return json.dumps(
            {
                "segments": [
                    {"beat": "第一段", "end_state": "停在线索出现"},
                    {"beat": "第二段", "end_state": "完成本章"},
                ]
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(llm_client, "chat", fake_chat)
    with llm_client.llm_book_context("book-provider-a"):
        segments = await plan_segment_contracts(
            asyncio.get_running_loop(),
            source_beats=["发现线索", "追查"],
            instruction="写4000字",
            target_chars=4000,
            max_segment_chars=2000,
        )

    assert len(segments) == 2
    assert seen_book_ids == ["book-provider-a"]


def test_provider_content_normalizer_extracts_text_without_dict_repr():
    from core.llm_client import normalize_content_text

    assert normalize_content_text({"text": "正文"}) == "正文"
    assert normalize_content_text({"content": [{"type": "text", "text": "第一"}, {"text": "第二"}]}) == "第一第二"
    assert normalize_content_text({"usage": {"input_tokens": 10}}) == ""
