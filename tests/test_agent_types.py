"""Tests for Agent type separation — tool filtering, temperature, task_label."""

from core.agent_loop import AgentConfig
from core.system_prompt import resolve_tools_for_agent


def test_write_agent_has_many_tools():
    tools = resolve_tools_for_agent("write", "write")
    names = {t["name"] for t in tools}
    assert "write_chapter" in names
    assert "extract_knowledge" in names
    assert "read_chapter" in names
    # ``task`` tool is now exposed to main agents (including write).
    # Nesting is prevented at the code level by is_subagent filtering
    # in ``resolve_tools_for_agent`` and a hard plan-mode guard in
    # ``_run_sub_agent`` (defense in depth for sub-agents).
    assert "task" in names


def test_subagent_cannot_see_task_tool():
    """Sub-agents must never see the task tool (nesting prevention)."""
    tools = resolve_tools_for_agent("write", "write", is_subagent=True)
    names = {t["name"] for t in tools}
    assert "task" not in names
    assert "read_chapter" in names  # other tools still available

    tools_research = resolve_tools_for_agent("research", "write", is_subagent=True)
    names_r = {t["name"] for t in tools_research}
    assert "task" not in names_r

    tools_general = resolve_tools_for_agent("general", "write", is_subagent=True)
    names_g = {t["name"] for t in tools_general}
    assert "task" not in names_g


def test_plan_agent_has_read_only():
    tools = resolve_tools_for_agent("plan")
    names = {t["name"] for t in tools}
    assert "read_chapter" in names
    assert "ask_user" in names
    assert "write_chapter" not in names
    assert "extract_knowledge" not in names
    assert "delete_chapter" not in names


def test_extract_agent_has_limited_tools():
    tools = resolve_tools_for_agent("extract")
    names = {t["name"] for t in tools}
    assert "extract_knowledge" in names
    assert "search_knowledge" in names
    assert "read_document" in names
    assert "read_chapter" in names
    assert "write_chapter" not in names
    assert "delete_chapter" not in names


def test_edit_agent_has_edit_tools():
    tools = resolve_tools_for_agent("edit")
    names = {t["name"] for t in tools}
    assert "decompose_chapter" in names
    assert "extract_style" in names
    assert "reconstruct_chapter" in names
    assert "compare_plot" in names
    assert "delete_chapter" not in names


def test_consistency_agent_has_analysis_tools():
    tools = resolve_tools_for_agent("consistency")
    names = {t["name"] for t in tools}
    assert "search_knowledge" in names
    assert "read_chapter" in names
    assert "list_chapters" in names
    assert "chapter_history" in names
    assert "write_chapter" not in names
    assert "delete_chapter" not in names
    assert "extract_knowledge" not in names
    assert "compare_versions" not in names


def test_agent_config_temperature():
    cfg = AgentConfig(agent_type="write")
    assert cfg.temperature == 0.3  # lowered from 0.7 for better tool-calling decisions

    cfg2 = AgentConfig(agent_type="extract")
    assert cfg2.temperature == 0.1

    cfg3 = AgentConfig(agent_type="consistency")
    assert cfg3.temperature == 0.1


def test_agent_config_task_label():
    cfg = AgentConfig(agent_type="write")
    assert cfg.task_label == "writing"

    cfg2 = AgentConfig(agent_type="extract")
    assert cfg2.task_label == "extraction"

    cfg3 = AgentConfig(agent_type="edit")
    assert cfg3.task_label == "editing"
