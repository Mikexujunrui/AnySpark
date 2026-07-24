"""Tool behavioural metadata and tool-set constants.

Extracted from tools.py to separate pure data declarations from registry
logic. The single source of truth for:
- Tool-set name constants (WRITE_TOOLS, READ_TOOLS, etc.)
- TOOL_META behavioural flags (streaming, mutates_kb, touches_chapter, context_aware)

Adding a new tool only requires an entry in TOOL_META here.
"""

# ── Tool-set name constants ──
# These sets are used by system_prompt.py to filter the tool list presented
# to the LLM based on agent type and mode.

WRITE_TOOLS = {
    "extract_knowledge",
    "store_chapter",
    "write_chapter",
    "manage_notes",
    "decompose_chapter",
    "rewrite_by_chain",
    "delete_chapter",
    "delete_all_chapters",
    "import_chapters",
    "edit_chapter",
    "revert_chapter",
    "extract_all_chapters",
    "extract_chapter",
    "prepare_writing",
    "finalize_chapter",
    "delete_version",
    "purge_chapter_history",
    "transform_book",
    "find_replace_book",
    "summarize_book",
    "generate_outline",
    "update_outline",
    "generate_timeline",
    "generate_detailed_outline",
    "generate_location_map",
    "generate_worldbuilding",
    "add_worldbuilding_entry",
    "delete_entity",
    "update_entity",
    "set_character_phase",
    "delete_worldbuilding_entry",
    "delete_timeline_event",
    "delete_foreshadow",
    "plan_foreshadow",
    "schedule_foreshadow",
    "postpone_foreshadow",
    "list_pending_foreshadows",
    "manage_volumes",
    "generate_volume_outlines",
    "manage_workflows",
    "manage_workflow_steps",
    "execute_workflow",
    "add_material",
    "subscribe_material",
    "unsubscribe_material",
    "delete_material",
    "manage_skills",
    "agent_tasks",
    # ── 以下为之前遗漏的写入工具 ──
    "delegate_writing",
    "patch_chapter",
    "migrate_reference_knowledge",
    "import_reference_chapters",
    "start_autopilot",
    "reorder_chapters",
    "define_constraint",
    "delete_constraint",
    "resolve_foreshadow",
    "update_worldbuilding_entry",
    "expand_outline_pipeline",
}

READ_TOOLS = {
    "search_knowledge",
    "list_chapters",
    "read_chapter",
    "read_document",
    "ask_user",
    "chapter_history",
    "diff_chapters",
    "get_outline",
    "get_timeline",
    "get_detailed_outline",
    "get_worldbuilding",
    "web_search",
    "web_fetch",
    "list_workflows",
    "browse_workflows",
    "browse_materials",
    "search_materials",
    "list_skills",
    "list_references",
    "list_reference_chapters",
    "import_reference_chapters",
    "search_reference",
    "migrate_reference_knowledge",
    "manage_permissions",
    "check_constraints",
    "analyze_impact",
    "score_confidence",
    "search_graph",
    "get_graph_insights",
    "verify_chapter",
    "analyze_voice",
    "get_voice_profile",
    "semantic_diff",
    "analyze_structure",
    "quantify_style",
}

EXTRACT_TOOLS = {"extract_knowledge", "search_knowledge", "read_document", "read_chapter", "extract_chapter"}

EDIT_TOOLS = {
    "decompose_chapter",
    "annotate_chain",
    "rewrite_by_chain",
    "read_chapter",
    "search_knowledge",
    "extract_style",
    "reconstruct_chapter",
    "compare_plot",
}

ANALYSIS_TOOLS = {
    "search_knowledge",
    "list_chapters",
    "read_chapter",
    "read_document",
    "get_outline",
    "get_timeline",
    "get_detailed_outline",
    "get_worldbuilding",
    "chapter_history",
    "diff_chapters",
    "ask_user",
    "define_constraint",
    "check_constraints",
    "analyze_impact",
    "score_confidence",
    "delete_constraint",
    "search_graph",
    "get_graph_insights",
    "verify_chapter",
    "analyze_voice",
    "semantic_diff",
    "analyze_structure",
    "quantify_style",
    "list_pending_foreshadows",
    "plan_foreshadow",
    "schedule_foreshadow",
    "postpone_foreshadow",
}

TASK_TOOLS = {"agent_tasks"}
STYLE_TOOLS = {"set_style", "manage_styles"}
RESEARCH_TOOLS = {"web_search", "web_fetch"}


# ── Tool behavioural metadata — single source of truth.
# Replaces the four ad-hoc tool-name sets previously hardcoded inside
# agent_loop (_STREAMING_TOOLS / _CONTEXT_AWARE_TOOLS / _KB_MUTATE_TOOLS /
# CHAPTER_TOOLS). Adding a new tool only requires an entry here.
# ──────────────────────────────────────────────────────────────────────────

TOOL_META: dict[str, dict[str, bool]] = {
    # Streaming tools: emit progress via the executor queue
    "extract_all_chapters": {"streaming": True, "mutates_kb": True},
    "generate_outline": {"streaming": True, "mutates_kb": True},
    "generate_timeline": {"streaming": True, "mutates_kb": True},
    "generate_detailed_outline": {"streaming": True, "mutates_kb": True},
    "generate_location_map": {"streaming": True, "mutates_kb": True},
    "generate_worldbuilding": {"streaming": True, "mutates_kb": True},
    "run_review": {"streaming": True},
    "write_chapter": {"streaming": True, "touches_chapter": True, "context_aware": True},
    "delegate_writing": {"streaming": True, "touches_chapter": True, "context_aware": True},
    "rewrite_by_chain": {"streaming": True, "touches_chapter": True},
    "manage_workflows": {"streaming": True, "touches_chapter": True},
    "execute_workflow": {"streaming": True, "touches_chapter": True},
    "edit_chapter": {"streaming": True, "touches_chapter": True},
    "patch_chapter": {"streaming": True, "touches_chapter": True},
    # KB-mutating tools: irreversible, guarded by the sliding-window counter
    "delete_entity": {"mutates_kb": True},
    "update_entity": {"mutates_kb": True},
    "set_character_phase": {"mutates_kb": True},
    "extract_knowledge": {"mutates_kb": True},
    "extract_chapter": {"mutates_kb": True},
    "migrate_reference_knowledge": {"mutates_kb": True},
    # Chapter-touching (non-streaming): notify frontend to refresh
    "store_chapter": {"touches_chapter": True},
    "import_chapters": {"touches_chapter": True},
    "import_reference_chapters": {"touches_chapter": True},
    "delete_chapter": {"touches_chapter": True},
    "delete_all_chapters": {"touches_chapter": True},
    "revert_chapter": {"touches_chapter": True},
    # Whole-book transform tools (transform_book dispatches to underlying functions)
    "transform_book": {"streaming": True, "touches_chapter": True, "context_aware": True},
    "find_replace_book": {"streaming": True, "touches_chapter": True},
    "summarize_book": {"streaming": True, "mutates_kb": True},
    "apply_directive_globally": {"streaming": True, "touches_chapter": True},
    "restyle_book": {"streaming": True, "touches_chapter": True},
    "transform_chapters_batch": {"streaming": True, "touches_chapter": True},
    # Autopilot launcher
    "start_autopilot": {"streaming": True, "touches_chapter": True},
    # Narrative logic — constraint checking, impact analysis, confidence scoring
    "define_constraint": {"mutates_kb": True},
    "delete_constraint": {"mutates_kb": True},
    # Foreshadow resolution
    "resolve_foreshadow": {"mutates_kb": True},
    # Worldbuilding & timeline CRUD
    "update_worldbuilding_entry": {"mutates_kb": True, "dangerous": True},
    # Outline expansion pipeline — streaming multi-level outline generation
    "expand_outline_pipeline": {"streaming": True, "mutates_kb": True},
    # Reference work analysis — read-only, no streaming needed
    "analyze_structure": {},
    "quantify_style": {},
    "analyze_deep_style": {},
    "analyze_emotional_curve": {},
}
