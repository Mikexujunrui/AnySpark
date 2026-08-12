# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Phase-aware tool disclosure for the main Agent.

The project has more than one hundred tools.  Sending every schema to the
model on every turn wastes context and makes similar tools compete with one
another.  This module keeps every tool reachable, but exposes only the packs
that match the user's current task.  Explicit Skills bypass keyword routing
and expose exactly the tools declared by the Skill.
"""

from dataclasses import dataclass

# Small navigation set shared by ordinary turns.  These tools let the Agent
# inspect the current project and ask for a missing decision without opening
# all mutation tools.
CORE_TOOLS = {
    "ask_user",
    "list_chapters",
    "read_chapter",
    "search_knowledge",
    "get_outline",
    "agent_tasks",
}


CAPABILITY_PACKS: dict[str, set[str]] = {
    "writing": {
        "prepare_writing",
        "delegate_writing",
        "write_chapter",
        # A generated draft remains protected from accidental *new chapter*
        # writers, but the same run must still be able to apply a versioned,
        # recoverable correction when requested.
        "patch_chapter",
        "edit_chapter",
        "finalize_chapter",
        "verify_chapter",
        "get_detailed_outline",
        "get_style",
        "list_pending_foreshadows",
        "check_constraints",
        "get_graph_insights",
        "search_graph",
        "list_references",
        "list_reference_chapters",
        "search_reference",
        "start_autopilot",
    },
    "editing": {
        "edit_chapter",
        "patch_chapter",
        "decompose_chapter",
        "annotate_chain",
        "rewrite_by_chain",
        "reconstruct_chapter",
        "compare_plot",
        "semantic_diff",
        "chapter_history",
        "diff_chapters",
        "revert_chapter",
        "delete_chapter",
        "count_words",
        "find_replace_book",
        "transform_book",
        "restyle_book",
        "transform_chapters_batch",
        "apply_directive_globally",
    },
    "review": {
        "run_review",
        "manage_reviewers",
        "verify_chapter",
        "check_constraints",
        "score_confidence",
        "analyze_impact",
        "analyze_voice",
        "get_voice_profile",
        "semantic_diff",
        "get_detailed_outline",
        "get_timeline",
        "get_worldbuilding",
        "search_graph",
    },
    "knowledge_read": {
        "read_document",
        "search_graph",
        "get_graph_insights",
        "get_worldbuilding",
        "get_timeline",
        "check_constraints",
        "score_confidence",
    },
    "knowledge_manage": {
        "extract_knowledge",
        "extract_chapter",
        "extract_all_chapters",
        "read_document",
        "import_chapters",
        "add_entity",
        "add_relation",
        "update_entity",
        "delete_entity",
        "set_character_phase",
        "memory_write",
        "search_graph",
        "get_graph_insights",
        "define_constraint",
        "delete_constraint",
        "check_constraints",
        "analyze_impact",
        "score_confidence",
    },
    "ideation": {
        "suggest_plot_directions",
        "manage_notes",
        "manage_inspirations",
        "get_detailed_outline",
        "task",
    },
    "outline": {
        "generate_outline",
        "update_outline",
        "generate_detailed_outline",
        "update_detailed_outline",
        "expand_outline_pipeline",
        "suggest_plot_directions",
        "manage_volumes",
        "list_volumes",
        "generate_volume_outlines",
        "task",
    },
    "worldbuilding": {
        "generate_timeline",
        "get_timeline",
        "generate_worldbuilding",
        "get_worldbuilding",
        "add_worldbuilding_entry",
        "update_worldbuilding_entry",
        "delete_worldbuilding_entry",
        "delete_timeline_event",
        "generate_location_map",
        "manage_volumes",
        "list_volumes",
        "generate_volume_outlines",
    },
    "reference": {
        "set_reference_books",
        "list_books",
        "list_references",
        "list_reference_chapters",
        "import_reference_chapters",
        "search_reference",
        "migrate_reference_knowledge",
        "analyze_structure",
        "quantify_style",
        "analyze_deep_style",
    },
    "style": {
        "set_style",
        "get_style",
        "list_styles",
        "manage_styles",
        "extract_style",
        "analyze_structure",
        "quantify_style",
        "analyze_deep_style",
        "analyze_emotional_curve",
        "run_review",
    },
    "materials": {
        "add_material",
        "search_materials",
        "browse_materials",
        "subscribe_material",
        "unsubscribe_material",
        "delete_material",
    },
    "foreshadow": {
        "list_pending_foreshadows",
        "plan_foreshadow",
        "schedule_foreshadow",
        "postpone_foreshadow",
        "resolve_foreshadow",
        "delete_foreshadow",
        "get_timeline",
    },
    "project_admin": {
        "store_chapter",
        "delete_chapter",
        "delete_all_chapters",
        "reorder_chapters",
        "delete_version",
        "purge_chapter_history",
        "summarize_book",
        "manage_workflows",
        "list_workflows",
        "browse_workflows",
        "execute_workflow",
        "manage_workflow_steps",
        "list_skills",
        "manage_skills",
        "manage_permissions",
    },
    "research": {"web_search", "web_fetch", "task"},
    "general": {
        "manage_notes",
        "manage_inspirations",
        "suggest_plot_directions",
        "list_skills",
        "list_styles",
        "list_references",
        "task",
    },
}


PACK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "writing": ("写", "续写", "正文", "成稿", "新章", "番外", "自动创作", "autopilot"),
    "editing": ("改", "润色", "重写", "替换", "删除", "撤销", "回退", "补写", "精修"),
    "review": ("评审", "审稿", "审核", "一致性", "检查", "检验", "ai味", "八股", "幻觉"),
    "knowledge_read": ("知识库", "设定", "角色", "人物", "地点", "关系", "实体"),
    "knowledge_manage": ("提取", "导入", "写入知识库", "建立知识库", "填充知识库", "更新设定", "删除设定"),
    "ideation": ("剧情", "构思", "方向", "脑暴", "灵感", "接下来怎么"),
    "outline": ("大纲", "细纲", "剧情骨架", "章节规划"),
    "worldbuilding": ("世界观", "时间线", "地图", "分卷", "地点图"),
    "reference": ("参考书", "原著", "语料", "样本"),
    "style": ("文风", "风格", "句式", "节奏", "叙事视角"),
    "materials": ("素材", "材料库", "订阅材料"),
    "foreshadow": ("伏笔", "悬念", "回收", "暗线"),
    "project_admin": ("工作流", "skill", "技能", "权限", "清空", "排序", "版本历史", "批量"),
    "research": ("网上", "搜索网络", "查资料", "调研", "web"),
}


@dataclass(frozen=True)
class CapabilitySelection:
    packs: tuple[str, ...]
    tool_names: frozenset[str]
    reason: str


def select_capabilities(
    message: str,
    *,
    skill_tools: set[str] | None = None,
    max_packs: int = 3,
) -> CapabilitySelection:
    """Return capability packs and tool names for one Agent run.

    Explicit Skills are authoritative: their declared tools are exposed with
    ``ask_user`` for recovery, and unrelated mutation tools remain hidden.
    """

    if skill_tools is not None:
        names = set(skill_tools)
        names.add("ask_user")
        return CapabilitySelection(("skill",), frozenset(names), "显式 Skill 步骤")

    lowered = (message or "").lower()
    scores: list[tuple[int, str]] = []
    for pack, keywords in PACK_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword.lower() in lowered)
        if score:
            scores.append((score, pack))

    scores.sort(key=lambda item: (-item[0], item[1]))
    selected = [pack for _, pack in scores[:max_packs]] or ["general"]
    names = set(CORE_TOOLS)
    for pack in selected:
        names.update(CAPABILITY_PACKS[pack])
    return CapabilitySelection(tuple(selected), frozenset(names), "按当前消息语义路由")


def tools_missing_from_packs(all_tool_names: set[str]) -> set[str]:
    """Diagnostic helper used by tests to stop new tools becoming unreachable."""

    covered = set(CORE_TOOLS)
    for tools in CAPABILITY_PACKS.values():
        covered.update(tools)
    return set(all_tool_names) - covered
