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

WRITE_TOOLS = {"extract_knowledge", "store_chapter", "write_chapter", "store_inspiration",
               "compare_versions", "decompose_chapter", "reconstruct_chapter", "compare_plot",
               "rewrite_by_chain",
               "delete_chapter", "delete_all_chapters", "import_chapters",
               "edit_chapter", "revert_chapter", "extract_all_chapters",
               "delete_version", "purge_chapter_history", "batch_edit_chapters",
               "generate_outline", "update_outline",
               "generate_timeline", "add_timeline_event",
               "generate_detailed_outline", "generate_location_map",
                "generate_worldbuilding", "add_worldbuilding_entry",
                "delete_entity", "update_entity", "set_character_phase",
                 "delete_worldbuilding_entry",
                "delete_timeline_event", "delete_foreshadow",
                "generate_workflow", "delete_workflow", "execute_workflow", "update_workflow",
                "subscribe_workflow", "unsubscribe_workflow",
                "add_material", "subscribe_material", "unsubscribe_material",
                "delete_material",
                "create_skill", "update_skill", "delete_skill", "agent_tasks"}

READ_TOOLS = {"search_knowledge", "list_chapters", "read_chapter", "read_document",
              "count_words", "ask_user", "chapter_history", "diff_chapters", "get_outline",
              "get_timeline", "get_detailed_outline", "get_worldbuilding",
              "web_search", "web_fetch", "list_workflows", "browse_workflows",
              "browse_materials", "search_materials", "list_skills",
              "list_references", "list_reference_chapters", "import_reference_chapters",
              "search_reference", "migrate_reference_knowledge", "manage_permissions"}

EXTRACT_TOOLS = {"extract_knowledge", "search_knowledge", "read_document",
                 "read_chapter", "compare_versions"}

EDIT_TOOLS = {"decompose_chapter", "annotate_chain", "extract_style", "reconstruct_chapter",
              "compare_plot", "rewrite_by_chain", "count_words", "read_chapter", "search_knowledge"}

ANALYSIS_TOOLS = {"search_knowledge", "list_chapters", "read_chapter", "read_document",
                  "get_outline", "get_timeline", "get_detailed_outline", "get_worldbuilding",
                  "chapter_history", "diff_chapters", "count_words", "ask_user"}

TASK_TOOLS = {"agent_tasks"}
STYLE_TOOLS = {"list_styles", "set_style", "suggest_style", "get_style", "manage_styles"}
RESEARCH_TOOLS = {"web_search", "web_fetch"}


# ── Tool behavioural metadata — single source of truth.
# Replaces the four ad-hoc tool-name sets previously hardcoded inside
# agent_loop (_STREAMING_TOOLS / _CONTEXT_AWARE_TOOLS / _KB_MUTATE_TOOLS /
# CHAPTER_TOOLS). Adding a new tool only requires an entry here.
# ──────────────────────────────────────────────────────────────────────────

TOOL_META: dict[str, dict[str, bool]] = {
    # Streaming tools: emit progress via the executor queue
    "extract_all_chapters":   {"streaming": True, "mutates_kb": True},
    "batch_edit_chapters":    {"streaming": True, "touches_chapter": True},
    "generate_outline":       {"streaming": True},
    "generate_timeline":      {"streaming": True},
    "generate_detailed_outline": {"streaming": True},
    "generate_location_map":  {"streaming": True},
    "generate_worldbuilding": {"streaming": True},
    "run_review":             {"streaming": True},
    "write_chapter":          {"streaming": True, "touches_chapter": True, "context_aware": True},
    "delegate_writing":       {"streaming": True, "touches_chapter": True, "context_aware": True},
    "rewrite_by_chain":       {"streaming": True, "touches_chapter": True},
    "generate_workflow":      {"streaming": True},
    "execute_workflow":       {"streaming": True},
    "edit_chapter":           {"streaming": True, "touches_chapter": True},
    "patch_chapter":          {"streaming": True, "touches_chapter": True},
    # KB-mutating tools: irreversible, guarded by the sliding-window counter
    "delete_entity":              {"mutates_kb": True},
    "update_entity":              {"mutates_kb": True},
    "set_character_phase":        {"mutates_kb": True},
    "extract_knowledge":          {"mutates_kb": True},
    "migrate_reference_knowledge": {"mutates_kb": True},
    # Chapter-touching (non-streaming): notify frontend to refresh
    "store_chapter":          {"touches_chapter": True},
    "import_chapters":         {"touches_chapter": True},
    "import_reference_chapters": {"touches_chapter": True},
    "delete_chapter":         {"touches_chapter": True},
    "delete_all_chapters":    {"touches_chapter": True},
    "revert_chapter":         {"touches_chapter": True},
    # Whole-book transform tools (Work Package D)
    "apply_directive_globally": {"streaming": True, "touches_chapter": True, "context_aware": True},
    "find_replace_book":     {"streaming": True, "touches_chapter": True},
    "transform_chapters_batch": {"streaming": True, "touches_chapter": True},
    "restyle_book":           {"streaming": True, "touches_chapter": True},
    "summarize_book":         {"streaming": True, "mutates_kb": True},
    # Autopilot launcher
    "start_autopilot":        {"streaming": True, "touches_chapter": True},
}
