"""Tool executor — dispatch table based on ``_DISPATCH`` (97 direct tools).

This module replaces the old ``_dispatch()`` if/elif chain (60+ branches) with
a unified dispatch table ``_DISPATCH`` that maps tool names to handler functions.
Handlers are registered via ``_build_dispatch()`` and support signature adaptation
via ``_call_handler()`` (inspect-based parameter injection).

Two execution paths:
- ``execute_tool()`` — non-streaming (default). Looks up ``_DISPATCH``, then
  falls back to compound-tool routing (workflows, volumes, chapter transforms)
  and lazy-imported whole-book tools.
- ``execute_tool_streaming()`` — streaming tools that emit progress via a queue.
  Uses ``_STREAMING_DISPATCH`` (15 tools) for queue-aware handlers.

Adding a new tool:
  1. Implement the handler function (in ``tools/impl/`` or inline).
  2. Add it to ``_build_dispatch()`` via ``_register_in_dispatch()``.
  3. If streaming, also add to ``_register_streaming()``.
"""

import difflib
import functools
import inspect
import json
import logging
import re
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from core.agent_context import AgentContext
from core.errors import ToolExecutionError
from core.event_bus import Event, EventType, bus
from core.thread_pools import llm_pool as _ai_executor
from core.tools import Tool, registry
from data.json_store import json_store
from tools.impl.admin import (
    _handle_agent_tasks,
    _handle_skill_tool,
    _manage_permissions,
)
from tools.impl.chapters import (
    _chapter_history,
    _count_words,
    _delete_all_chapters,
    _delete_chapter,
    _delete_version,
    _diff_chapters,
    _edit_chapter,
    _list_chapters,
    _patch_chapter,
    _purge_chapter_history,
    _read_chapter,
    _revert_chapter,
)
from tools.impl.generation import (
    _add_entity_tool,
    _add_relation_tool,
    _add_worldbuilding_entry_tool,
    _generate_detailed_outline,
    _generate_location_map,
    _generate_outline,
    _generate_timeline,
    _generate_worldbuilding,
    _get_detailed_outline_tool,
    _get_outline,
    _get_timeline_tool,
    _get_worldbuilding_tool,
    _update_detailed_outline,
    _update_outline,
)
from tools.impl.handlers import _handle_knowledge_edit, _handle_materials, _handle_volume
from tools.impl.imports import (
    _import_chapters,
    _import_reference_chapters,
    _store_inspiration,
)
from tools.impl.knowledge import (
    _batch_edit_chapters,
    _extract_all_chapters,
    _extract_chapter,
    _finalize_chapter,
    _prepare_writing,
)
from tools.impl.narrative_logic import (
    _analyze_impact,
    _check_constraints,
    _define_constraint,
    _delete_constraint,
    _get_graph_insights,
    _score_confidence,
    _search_graph,
    _verify_chapter,
)
from tools.impl.plot import (
    _annotate_chain,
    _compare_plot,
    _decompose_chapter,
    _extract_style,
    _read_document,
    _reconstruct_chapter,
    _suggest_plot_directions,
)
from tools.impl.reference_analysis import (
    _analyze_deep_style_tool,
    _analyze_emotional_curve_tool,
    _analyze_structure_tool,
    _quantify_style_tool,
)
from tools.impl.review import _manage_reviewers, _run_review
from tools.impl.styles import _get_style, _list_styles, _manage_styles, _set_style
from tools.impl.workflow_tools import _execute_workflow_streaming, _generate_workflow_streaming, _handle_workflow_tool
from tools.impl.writing import (
    _delegate_writing,
    _delegate_writing_streaming,
    _rewrite_by_chain_streaming,
    _store_chapter,
    _write_chapter,
    _write_chapter_streaming,
)

logger = logging.getLogger(__name__)


def get_executor() -> ThreadPoolExecutor:
    return _ai_executor

def _split_paragraphs(text: str) -> list[str]:
    """Split text into paragraph segments, preserving separators."""
    parts = re.split(r'(\n\s*\n)', text)
    segments = []
    for part in parts:
        stripped = part.strip()
        if stripped:
            segments.append(stripped)
    return segments

def _fuzzy_find(text: str, target: str, threshold: float = 0.75) -> str | None:
    """Fuzzy match: find best matching substring in text using sliding window."""
    if not target or not text:
        return None
    t_len = len(target)
    if t_len < 4:
        return None
    # Fast path: exact substring match
    if target in text:
        return target
    # Sliding window: compare same-length substrings (exact t_len)
    best_ratio = 0.0
    best_start = -1
    for i in range(len(text) - t_len + 1):
        chunk = text[i:i + t_len]
        ratio = difflib.SequenceMatcher(None, target, chunk).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_start = i
            if best_ratio > 0.98:
                break
    if best_ratio >= threshold and best_start >= 0:
        return text[best_start:best_start + t_len]
    return None

def apply_edit_ops(text: str, ops: list[dict]) -> tuple[str, list[dict]]:
    """Apply edit operations to text using segment-based addressing.

    Each op targets a paragraph segment by index, with optional confirm text
    for fine-grained positioning within the segment.

    Ops format:
      - {op: "replace", segment: 0, confirm: "片段", to: "新文本"}
      - {op: "delete", segment: 0, confirm: "片段"}
      - {op: "insert_after", segment: 0, text: "新增文本"}
      - {op: "insert_before", segment: 0, text: "新增文本"}

    Returns (modified_text, report) where report details each op's outcome.
    """
    segments = _split_paragraphs(text)
    if not segments:
        return text, [{"status": "skipped", "reason": "原文为空"}]

    report = []
    insert_offset = 0  # track inserted segments to adjust indices

    for op in ops:
        op_type = op.get("op")
        seg_idx = op.get("segment", 0)
        confirm = op.get("confirm", "")
        actual_idx = seg_idx + insert_offset  # adjust for prior inserts

        if actual_idx < 0 or actual_idx >= len(segments):
            report.append({"op": op_type, "segment": seg_idx, "status": "failed",
                          "reason": f"段落索引{seg_idx}超出范围(共{len(segments) - insert_offset}段)"})
            continue

        seg_text = segments[actual_idx]
        result_info = {"op": op_type, "segment": seg_idx, "seg_title": seg_text[:30]}

        if op_type == "replace":
            new_text = op.get("to", "")
            applied = False
            if confirm and confirm in seg_text:
                segments[actual_idx] = seg_text.replace(confirm, new_text, 1)
                applied = True
            elif confirm:
                fuzzy = _fuzzy_find(seg_text, confirm)
                if fuzzy:
                    segments[actual_idx] = seg_text.replace(fuzzy, new_text, 1)
                    result_info["fuzzy"] = True
                    applied = True
            if not applied and not confirm:
                segments[actual_idx] = new_text
                applied = True
            result_info["status"] = "ok" if applied else "failed"

        elif op_type == "delete":
            if confirm and confirm in seg_text:
                segments[actual_idx] = seg_text.replace(confirm, "", 1)
                result_info["status"] = "ok"
            elif confirm:
                fuzzy = _fuzzy_find(seg_text, confirm)
                if fuzzy:
                    segments[actual_idx] = seg_text.replace(fuzzy, "", 1)
                    result_info["status"] = "ok"
                    result_info["fuzzy"] = True
                else:
                    result_info["status"] = "failed"
            else:
                segments[actual_idx] = ""
                result_info["status"] = "ok"

        elif op_type == "insert_after":
            insert_text = op.get("text", "")
            segments.insert(actual_idx + 1, insert_text)
            insert_offset += 1
            result_info["status"] = "ok"

        elif op_type == "insert_before":
            insert_text = op.get("text", "")
            segments.insert(actual_idx, insert_text)
            insert_offset += 1
            result_info["status"] = "ok"

        else:
            result_info["status"] = "failed"
            result_info["reason"] = f"未知操作: {op_type}"

        report.append(result_info)

    result = "\n\n".join(s for s in segments if s.strip())
    return result, report

# ── Unified dispatch table ──
# Single source of truth mapping tool names to handler functions.
# Each entry is a callable with standardised signature:
#     (loop, args, kb, book_id, msg, session_id, context) -> str | dict
# Build once, used by both execute_tool() and execute_tool_streaming().

_DISPATCH: dict[str, Callable] = {}
_dispatch_built = False


async def _call_handler(
    handler: Callable,
    loop,
    args: dict,
    kb,
    book_id: str,
    msg: str,
    session_id: str,
    context: AgentContext | None = None,
) -> str | dict:
    """Call an arbitrary handler, adapting to its parameter signature via
    reflection.  Supports sync and async handlers with any subset of the
    standard keyword arguments."""
    params = {}
    sig = inspect.signature(handler)
    for pname in sig.parameters:
        if pname == "loop":
            params["loop"] = loop
        elif pname == "args":
            params["args"] = args
        elif pname == "kb":
            params["kb"] = kb
        elif pname == "book_id":
            params["book_id"] = book_id
        elif pname == "msg":
            params["msg"] = msg
        elif pname == "session_id":
            params["session_id"] = session_id
        elif pname == "context":
            params["context"] = context
        elif pname == "queue":
            params["queue"] = None  # streaming tools provide queue separately
    result = handler(**params)
    if inspect.iscoroutine(result):
        result = await result
    return result


def _register_in_dispatch(
    table: dict[str, Callable],
    handler: Callable,
    *names: str,
) -> None:
    """Register *handler* under each *name* in *table*."""
    for n in names:
        table[n] = handler


def _build_dispatch() -> None:
    """Build the unified dispatch table. Safe to call multiple times."""
    global _dispatch_built
    if _dispatch_built:
        return
    _dispatch_built = True

    D = _DISPATCH

    # ── Simple 1:1 tool name → handler mappings ──
    _register_in_dispatch(D, _search_knowledge, "search_knowledge")
    _register_in_dispatch(D, _extract_knowledge, "extract_knowledge")
    _register_in_dispatch(D, _store_inspiration, "store_inspiration")
    _register_in_dispatch(D, _write_chapter, "write_chapter")
    _register_in_dispatch(D, _store_chapter, "store_chapter")
    _register_in_dispatch(D, _import_chapters, "import_chapters")
    _register_in_dispatch(D, _import_reference_chapters, "import_reference_chapters")
    _register_in_dispatch(D, _ask_user, "ask_user")
    _register_in_dispatch(D, _decompose_chapter, "decompose_chapter")
    _register_in_dispatch(D, _annotate_chain, "annotate_chain")
    _register_in_dispatch(D, _list_chapters, "list_chapters")
    _register_in_dispatch(D, _count_words, "count_words")
    _register_in_dispatch(D, _read_chapter, "read_chapter")
    _register_in_dispatch(D, _delete_chapter, "delete_chapter")
    _register_in_dispatch(D, _delete_all_chapters, "delete_all_chapters")
    _register_in_dispatch(D, _delete_version, "delete_version")
    _register_in_dispatch(D, _purge_chapter_history, "purge_chapter_history")
    _register_in_dispatch(D, _generate_outline, "generate_outline")
    _register_in_dispatch(D, _get_outline, "get_outline")
    _register_in_dispatch(D, _update_outline, "update_outline")
    _register_in_dispatch(D, _generate_worldbuilding, "generate_worldbuilding")
    _register_in_dispatch(D, _get_worldbuilding_tool, "get_worldbuilding")
    _register_in_dispatch(D, _add_worldbuilding_entry_tool, "add_worldbuilding_entry")
    _register_in_dispatch(D, _generate_location_map, "generate_location_map")
    _register_in_dispatch(D, _generate_detailed_outline, "generate_detailed_outline")
    _register_in_dispatch(D, _get_detailed_outline_tool, "get_detailed_outline")
    _register_in_dispatch(D, _update_detailed_outline, "update_detailed_outline")
    _register_in_dispatch(D, _generate_timeline, "generate_timeline")
    _register_in_dispatch(D, _get_timeline_tool, "get_timeline")
    _register_in_dispatch(D, _add_entity_tool, "add_entity")
    _register_in_dispatch(D, _add_relation_tool, "add_relation")
    _register_in_dispatch(D, _batch_edit_chapters, "batch_edit_chapters")
    _register_in_dispatch(D, _extract_all_chapters, "extract_all_chapters")
    _register_in_dispatch(D, _extract_chapter, "extract_chapter")
    _register_in_dispatch(D, _prepare_writing, "prepare_writing")
    _register_in_dispatch(D, _finalize_chapter, "finalize_chapter")
    _register_in_dispatch(D, _read_document, "read_document")
    _register_in_dispatch(D, _edit_chapter, "edit_chapter")
    _register_in_dispatch(D, _patch_chapter, "patch_chapter")
    _register_in_dispatch(D, _chapter_history, "chapter_history")
    _register_in_dispatch(D, _revert_chapter, "revert_chapter")
    _register_in_dispatch(D, _diff_chapters, "diff_chapters")
    _register_in_dispatch(D, _suggest_plot_directions, "suggest_plot_directions")
    _register_in_dispatch(D, _run_review, "run_review")
    _register_in_dispatch(D, _manage_reviewers, "manage_reviewers")
    _register_in_dispatch(D, _delegate_writing, "delegate_writing")
    _register_in_dispatch(D, _manage_permissions, "manage_permissions")
    _register_in_dispatch(D, _web_search, "web_search")
    _register_in_dispatch(D, _web_fetch, "web_fetch")
    _register_in_dispatch(D, _run_sub_agent, "task")
    _register_in_dispatch(D, _set_style, "set_style")
    _register_in_dispatch(D, _get_style, "get_style")
    _register_in_dispatch(D, _list_styles, "list_styles")
    _register_in_dispatch(D, _manage_styles, "manage_styles")
    _register_in_dispatch(D, _extract_style, "extract_style")
    _register_in_dispatch(D, _reconstruct_chapter, "reconstruct_chapter")
    _register_in_dispatch(D, _compare_plot, "compare_plot")
    _register_in_dispatch(D, _define_constraint, "define_constraint")
    _register_in_dispatch(D, _check_constraints, "check_constraints")
    _register_in_dispatch(D, _delete_constraint, "delete_constraint")
    _register_in_dispatch(D, _analyze_impact, "analyze_impact")
    _register_in_dispatch(D, _score_confidence, "score_confidence")
    _register_in_dispatch(D, _search_graph, "search_graph")
    _register_in_dispatch(D, _get_graph_insights, "get_graph_insights")
    _register_in_dispatch(D, _verify_chapter, "verify_chapter")
    _register_in_dispatch(D, _analyze_voice_tool, "analyze_voice")
    _register_in_dispatch(D, _get_voice_profile_tool, "get_voice_profile")
    _register_in_dispatch(D, _semantic_diff_tool, "semantic_diff")
    _register_in_dispatch(D, _expand_outline_pipeline_tool, "expand_outline_pipeline")
    _register_in_dispatch(D, _analyze_structure_tool, "analyze_structure")
    _register_in_dispatch(D, _quantify_style_tool, "quantify_style")
    _register_in_dispatch(D, _analyze_deep_style_tool, "analyze_deep_style")
    _register_in_dispatch(D, _analyze_emotional_curve_tool, "analyze_emotional_curve")
    _register_in_dispatch(D, _handle_agent_tasks, "agent_tasks")
    _register_in_dispatch(D, functools.partial(_handle_skill_tool, "list_skills"), "list_skills")

    # ── Compound tools (single function handles multiple names, name pre-bound via partial) ──
    _materials_names = ("add_material", "search_materials", "browse_materials",
                        "subscribe_material", "unsubscribe_material", "delete_material",
                        "set_reference_books", "list_books", "list_references",
                        "list_reference_chapters", "search_reference",
                        "migrate_reference_knowledge")
    for _mn in _materials_names:
        _register_in_dispatch(D, functools.partial(_handle_materials, _mn), _mn)

    _knowledge_edit_names = ("delete_entity", "update_entity", "delete_worldbuilding_entry",
                             "update_worldbuilding_entry",
                             "delete_timeline_event",
                             "delete_foreshadow", "set_character_phase",
                             "plan_foreshadow", "schedule_foreshadow", "postpone_foreshadow",
                             "list_pending_foreshadows", "resolve_foreshadow")
    for _kn in _knowledge_edit_names:
        _register_in_dispatch(D, functools.partial(_handle_knowledge_edit, _kn), _kn)

    # ── Memory tools ──
    _register_in_dispatch(D, _handle_memory_write, "memory_write")

    # ── Update Tool.handler on registry objects so the metadata layer
    #     also has access to the handler (previously unused field). ──
    for _name, _handler in _DISPATCH.items():
        _tool = registry.get(_name)
        if _tool is not None:
            _tool.handler = _handler

    # ── Auto-register orphan tools (tools with a handler but no Tool entry) ──
    _auto_register_tools()


def _auto_register_tools() -> None:
    """Auto-register tools that have handlers in the dispatch table but no
    corresponding ``Tool`` object in the registry yet.

    This is the key enabler of the "just add a handler function" workflow:
    add a function to ``tools/impl/`` and wire it into ``_build_dispatch()``,
    and the rest (registration, schema, description) is handled automatically.
    Manual ``registry.register(Tool(...))`` calls in ``tools.py`` still take
    priority — an existing Tool object is never overwritten.

    For tools without a manual ``description``, the function's docstring (first
    paragraph) is used.  Parameter schemas are derived from type hints where
    possible; otherwise a minimal ``{"type": "string"}`` placeholder is set so
    the LLM can still call the tool with free-text arguments.
    """
    _inspect = inspect  # local alias to avoid name collision
    for _name, _handler in _DISPATCH.items():
        if registry.get(_name) is not None:
            continue  # already has a manual Tool entry — keep it

        # Derive description from docstring
        _doc = getattr(_handler, "__doc__", "") or ""
        _desc = _doc.split("\n\n")[0].strip() if _doc else f"工具 {_name}"
        _desc = _desc.replace("    ", "").strip()  # clean indentation

        # Derive basic parameter schema from function signature
        _sig = _inspect.signature(_handler)
        _params: dict[str, dict] = {}
        for _pname, _p in _sig.parameters.items():
            if _pname in ("loop", "kb", "queue", "context"):
                continue  # injected params, not user-provided
            _py_type = _p.annotation if _p.annotation is not _inspect.Parameter.empty else str
            _ts_type = {str: "string", int: "integer", float: "number",
                        bool: "boolean", dict: "object"}.get(_py_type, "string")
            _params[_pname] = {"type": _ts_type, "description": _pname,
                               "required": _p.default is _inspect.Parameter.empty}

        registry.register(Tool(
            name=_name,
            description=_desc[:500],
            parameters=_params,
        ))
        logger.info("Auto-registered tool: %s (from %s.%s)", _name,
                    getattr(_handler, "__module__", "?"),
                    getattr(_handler, "__name__", "?"))


# ── Error formatting helper used by both execute paths ──

def _fmt_tool_error(name: str, err: BaseException, detail: str = "") -> str:
    """Return a user-facing Chinese error string for the given exception."""
    err_str = str(err)[:150]
    err_lower = err_str.lower()
    if "timeout" in err_lower or "timed out" in err_lower:
        return f"⏱ 工具 {name} 超时: 请求超过180秒未响应。可重试或缩短输入内容。"
    if any(k in err_lower for k in
           ["content_filter", "content filter", "sensitive", "policy", "moderation"]):
        return f"🚫 工具 {name} 被内容审查拦截: {err_str[:100]}。可尝试调整指令措辞。"
    if "rate" in err_lower or "429" in err or "too many" in err_lower:
        return f"⚠️ 工具 {name} 速率限制: {err_str[:80]}。请稍后重试。"
    if any(k in err_lower for k in ["connection", "network", "refused", "reset", "eof"]):
        return f"🌐 工具 {name} 网络错误: {err_str[:80]}。请检查网络后重试。"
    if detail:
        return f"❌ 工具 {name} 执行失败: {detail[:150]}"
    return f"❌ 工具 {name} 执行失败: {err_str[:150]}"


# ── Streaming dispatch ──
# Each tool function receives (loop, args, kb, book_id, msg, queue) and returns result.
_STREAMING_DISPATCH: dict[str, Callable] = {}


def _register_streaming():
    """Lazily build the streaming dispatch map (avoids import-time circular deps)."""
    _STREAMING_DISPATCH.update({
        "extract_all_chapters": _extract_all_chapters,
        "batch_edit_chapters": _batch_edit_chapters,
        "transform_book": _transform_book_streaming,
        "generate_outline": _generate_outline,
        "generate_worldbuilding": _generate_worldbuilding,
        "generate_location_map": _generate_location_map,
        "generate_detailed_outline": _generate_detailed_outline,
        "generate_timeline": _generate_timeline,
        "run_review": _run_review,
        "write_chapter": _write_chapter_streaming,
        "delegate_writing": _delegate_writing_streaming,
        "rewrite_by_chain": _rewrite_by_chain_streaming,
        "generate_workflow": _generate_workflow_streaming,
        "manage_workflows": _manage_workflows_streaming,
        "execute_workflow": _execute_workflow_streaming,
    })


async def execute_tool_streaming(loop, name: str, args: dict, kb,
                                 book_id: str, msg: str, session_id: str, queue,
                                 context: AgentContext | None = None) -> str | dict:
    try:
        _build_dispatch()
        if not _STREAMING_DISPATCH:
            _register_streaming()

        # Streaming dispatch map (tools that emit progress via queue)
        if name in _STREAMING_DISPATCH:
            fn = _STREAMING_DISPATCH[name]
            return await fn(loop, args, kb, book_id, msg, queue)

        # Fallback to non-streaming dispatch
        return await execute_tool(loop, name, args, kb, book_id, msg, session_id,
                                  context=context)
    except BaseException as e:
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        logger.error("Streaming tool %s failed with args=%s: %s\n%s",
                     name, {k: str(v)[:200] for k, v in args.items()},
                     e, traceback.format_exc())
        return f"工具 {name} 执行失败: {str(e)[:200]}"


async def execute_tool(loop, name: str, args: dict, kb, book_id: str,
                       msg: str, session_id: str = "", confirmed: bool = False,
                       context: AgentContext | None = None) -> str | dict:
    _build_dispatch()
    try:
        # ── 1. Main dispatch table lookup ──
        handler = _DISPATCH.get(name)
        if handler is not None:
            result = await _call_handler(handler, loop, args, kb, book_id,
                                         msg, session_id, context)
            bus.emit_sync(Event(type=EventType.TOOL_EXECUTED,
                                data={"tool": name, "book_id": book_id},
                                source="executor"))
            return result

        # ── 2. Compound tools with sub-action routing ──
        if name in ("manage_volumes", "generate_volume_outlines", "list_volumes"):
            result = _handle_volume(
                name if name != "manage_volumes"
                else {"list": "list_volumes", "create": "create_volume",
                      "update": "update_volume", "delete": "delete_volume",
                      "move": "move_chapter_to_volume"}.get(args.get("action", "list"), "list_volumes"),
                args, book_id)
            return result

        if name in ("manage_workflows", "manage_workflow_steps", "execute_workflow",
                    "list_workflows", "browse_workflows"):
            if name == "manage_workflows":
                action = args.get("action", "list")
                if action == "generate":
                    result = await _generate_workflow_streaming(loop, args, kb, book_id, msg)
                else:
                    result = await _handle_workflow_tool(action, args, book_id)
            elif name == "manage_workflow_steps":
                action = args.get("action", "list")
                internal = "list_workflow_steps" if action == "list" else "update_workflow_step"
                result = await _handle_workflow_tool(internal, args, book_id)
            else:
                result = await _handle_workflow_tool(name, args, book_id)
            return result

        if name == "manage_skills":
            action = args.get("action", "list")
            internal = {"list": "list_skills", "create": "create_skill",
                        "update": "update_skill", "delete": "delete_skill"}.get(action, "list_skills")
            return _handle_skill_tool(internal, args)

        if name == "start_autopilot":
            return await _start_autopilot(args, book_id)

        # ── 3. Whole-book transform tools (lazily imported) ──
        if name in ("transform_book", "find_replace_book", "summarize_book",
                    "apply_directive_globally", "transform_chapters_batch", "restyle_book"):
            if name == "transform_book":
                return await _transform_book_dispatcher(loop, args, book_id)
            from tools.chapter_tools import (
                apply_directive_globally,
                find_replace_book,
                restyle_book,
                summarize_book,
                transform_chapters_batch,
            )
            _lazy = {"find_replace_book": find_replace_book,
                     "apply_directive_globally": apply_directive_globally,
                     "summarize_book": summarize_book,
                     "transform_chapters_batch": transform_chapters_batch,
                     "restyle_book": restyle_book}
            return await _lazy[name](loop, args, book_id)

        return f"工具 {name} 未注册 (params: {json.dumps(args, ensure_ascii=False)[:100]})"

    except ToolExecutionError as e:
        bus.emit_sync(Event(type=EventType.TOOL_FAILED,
                            data={"tool": name, "error": str(e)[:100]},
                            source="executor"))
        logger.error("Tool %s failed with ToolExecutionError: %s", name, e)
        return f"❌ 工具 {name} 执行失败: {str(e)[:150]}"
    except BaseException as e:
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        logger.error("Tool %s failed with args=%s: %s\n%s",
                     name, {k: str(v)[:200] for k, v in args.items()},
                     e, traceback.format_exc())
        bus.emit_sync(Event(type=EventType.TOOL_FAILED,
                            data={"tool": name, "error": str(e)[:100]},
                            source="executor"))
        return _fmt_tool_error(name, e)

async def _transform_book_dispatcher(loop, args: dict, book_id: str, queue=None) -> str:
    """Unified dispatcher for transform_book — routes to the appropriate
    underlying function based on the ``mode`` parameter.

    - mode='restyle' → restyle_book (applies a style profile)
    - mode='rewrite' → transform_chapters_batch with mode='rewrite'
    - mode='patch' (default) → apply_directive_globally (auto serial/parallel)
    """
    from tools.chapter_tools import (
        apply_directive_globally,
        restyle_book,
        transform_chapters_batch,
    )

    mode = args.get("mode", "patch")
    instruction = args.get("instruction", "")
    scope = args.get("scope", "all")
    dry_run = bool(args.get("dry_run", False))
    execution_mode = args.get("execution_mode", "auto")

    if mode == "restyle":
        style_id = args.get("style_id", "")
        if not style_id:
            return "错误: mode=restyle 时需要 style_id 参数"
        restyle_args = {
            "style_id": style_id,
            "scope": scope,
            "dry_run": dry_run,
            "_queue": queue,
        }
        return await restyle_book(loop, restyle_args, book_id)

    elif mode == "rewrite":
        transform_args = {
            "chapter_ids": scope,
            "instruction": instruction,
            "mode": "rewrite",
            "dry_run": dry_run,
            "_queue": queue,
        }
        return await transform_chapters_batch(loop, transform_args, book_id)

    else:  # patch (default)
        directive = args.get("directive", "") or instruction
        if not directive:
            return "错误: 需要 instruction 参数"
        directive_args = {
            "directive": directive,
            "scope": scope,
            "execution_mode": execution_mode,
            "dry_run": dry_run,
            "_queue": queue,
        }
        return await apply_directive_globally(loop, directive_args, book_id)


async def _transform_book_streaming(loop, args: dict, kb, book_id: str, msg: str = "", queue=None) -> str:
    """Streaming wrapper for transform_book — passes queue to the dispatcher."""
    return await _transform_book_dispatcher(loop, args, book_id, queue=queue)


async def _manage_workflows_streaming(loop, args: dict, kb, book_id: str, msg: str = "", queue=None) -> str:
    """Streaming wrapper for manage_workflows — routes generate to streaming, others to handler."""
    action = args.get("action", "list")
    if action == "generate":
        return await _generate_workflow_streaming(loop, args, kb, book_id, msg, queue)
    return await _handle_workflow_tool(action, args, book_id)


async def _web_search(loop, args: dict, book_id: str) -> str:
    from core.web_search import web_search_sync
    query = args.get("query", "")
    if not query:
        return "错误: 需要 query 参数"
    num_results = int(args.get("num_results", 8))
    return await loop.run_in_executor(
        _ai_executor, web_search_sync, query, book_id, num_results
    )

async def _web_fetch(loop, args: dict) -> str:
    from core.web_search import web_fetch_sync
    url = args.get("url", "")
    if not url:
        return "错误: 需要 url 参数"
    # SSRF protection: validate URL before fetching
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "错误: 只支持 http/https 协议"
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return "错误: 无法解析 URL 主机名"
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return "错误: 不允许访问本地地址"
    import ipaddress
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
            return "错误: 不允许访问内网/保留地址"
    except ValueError:
        pass  # not an IP address, allow
    fmt = args.get("format", "text")
    timeout = int(args.get("timeout", 30))
    if timeout > 60:
        timeout = 60  # cap timeout
    return await loop.run_in_executor(
        _ai_executor, web_fetch_sync, url, fmt, timeout
    )

async def _run_sub_agent(args: dict, book_id: str, session_id: str,
                        context: AgentContext | None = None) -> str:
    from core.sub_agent import spawn_sub_agent
    prompt = args.get("prompt", "")
    agent_type = args.get("agent_type", "general")
    task_id = args.get("task_id")

    if not prompt:
        return "错误: task 工具需要 prompt 参数"

    # ── Plan mode: only read-only sub-agents allowed ──
    # Plan-mode constraint: a plan-mode main agent may
    # NOT spawn any sub-agent whose toolset could write to the project. This
    # is the HARD runtime guard; the system prompt also nudges the model to
    # only request read-only types in plan mode, but we enforce it here
    # regardless of what the model asks for.
    READONLY_SUBAGENT_TYPES = {"research", "plan", "consistency", "reviewer"}
    if context is not None and context.is_plan_mode and agent_type not in READONLY_SUBAGENT_TYPES:
        # Track blocked attempts for observability.
        if context.extra and "metrics" in context.extra:
            context.extra["metrics"].subagent_blocked += 1
        logger.warning(
            "Plan-mode guard blocked spawn of write-type sub-agent %r", agent_type
        )
        return (
            f"❌ 当前是 Plan 模式，禁止 spawn 写入型子 Agent 「{agent_type}」。\n"
            f"Plan 模式下只允许使用只读型子 Agent: {', '.join(sorted(READONLY_SUBAGENT_TYPES))}。\n"
            f"如需使用 「{agent_type}」 子 Agent，请提示用户切换到 Write 模式后再调用。"
        )

    result = await spawn_sub_agent(
        prompt=prompt,
        agent_type=agent_type,
        book_id=book_id,
        parent_session_id=session_id,
        task_id=task_id,
    )

    # Track successful spawn via shared LoopMetrics in context.extra.
    if result.success and context is not None and context.extra:
        metrics = context.extra.get("metrics")
        if metrics is not None:
            metrics.subagent_spawned += 1
            metrics.subagent_types[agent_type] = metrics.subagent_types.get(agent_type, 0) + 1

    if result.success:
        output = result.output
        if result.session_id:
            output += f"\n\n[task_id: {result.session_id} — 可用此 ID 恢复会话]"
        return output
    else:
        return f"子任务失败: {result.error}"

def _handle_memory_write(args: dict, book_id: str = "") -> str:
    """Handle memory_write tool calls.

    Writes to project memory or user preferences depending on target.
    Silently ignores when memory system is disabled.
    """
    try:
        from core.memory import get_memory_manager
        mm = get_memory_manager()
        if not mm:
            return "（记忆系统已关闭，操作已忽略）"
    except Exception:
        return "（记忆系统不可用）"

    target = args.get("target", "")
    title = args.get("title", "")
    content = args.get("content", "")

    if not title and not content:
        return "请提供 title 或 content"

    text = content or title

    if target == "decision":
        mm.project.record_decision(book_id, title=title, rationale=content)
        return f"已记录创作决策: {title[:40]}"
    elif target == "issue":
        mm.project.add_progress_note(book_id, content=text)
        return f"已记录进度: {text[:40]}"
    elif target == "feature":
        parts = [p.strip() for p in (title or "").split("|")]
        fid = parts[0] if len(parts) > 0 else ""
        ftitle = parts[1] if len(parts) > 1 else content[:40]
        if fid:
            mm.project.add_note(book_id, title=ftitle, content=content)
            return f"已记录笔记: {ftitle[:30]}"
        return "需要提供目标名称"
    elif target == "preference":
        keywords_str = args.get("keywords", "")
        keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
        confidence = args.get("confidence", "pending")
        entry = mm.preferences.add_entry(
            category="user_preference",
            content=text,
            summary=title or text[:40],
            keywords=keywords,
            confidence=confidence,
            source="conversation",
        )
        return f"已记录偏好: {entry.summary[:40]} (状态: {entry.confidence})"
    else:
        return f"未知目标类别: {target}"


def _search_knowledge(args: dict, kb) -> str:
    from core.search import fts as fts_engine
    query = args.get("query", "")
    entities = kb.list_entities()
    # Use FTS for indexed search, fall back to linear scan
    fts_results = fts_engine.search_entities(kb.project_id, query, limit=15)
    lines = [f"知识库共 {len(entities)} 个实体。搜索 '{query}':\n"]
    if fts_results:
        entity_map = {e.id: e for e in entities}
        matched_entities = []
        for r in fts_results:
            e = entity_map.get(r["id"])
            if e:
                matched_entities.append(e)
                # Show key attributes
                key_attrs = []
                for attr in ("role", "personality", "abilities", "location",
                              "description", "function", "effect"):
                    val = e.data.get(attr, "")
                    if val:
                        key_attrs.append(f"{attr}={str(val)[:40]}")
                        if len(key_attrs) >= 3:
                            break
                lines.append(f"- **{e.name}** [{e.type}]")
                if key_attrs:
                    lines.append(f"  {', '.join(key_attrs)}")
                if r.get("snippet"):
                    lines.append(f"  匹配: {r['snippet']}")
        # Show relations among matched entities
        if len(matched_entities) >= 2:
            try:
                shared = kb.find_share_connections(
                    [e.id for e in matched_entities])
                if shared:
                    rel_lines = ["\n  🔗 匹配实体间的关系:"]
                    for conn in shared[:5]:
                        from_e = entity_map.get(conn["from"])
                        to_e = entity_map.get(conn["to"])
                        if from_e and to_e:
                            rel_lines.append(
                                f"    {from_e.name} --[{conn['type']}]--> {to_e.name}")
                    lines.extend(rel_lines)
            except Exception:
                pass
    else:
        matching = [e.name for e in entities if query.lower()
                    in e.name.lower() or query in str(e.data).lower()]
        lines.append(", ".join(matching[:10]) or "无匹配")
    return "\n".join(lines)

async def _extract_knowledge(
        loop, args: dict, kb, book_id: str, msg: str) -> str:
    from core.extractor import accept_proposal, extract_from_text
    text = args.get("text", msg)
    proposal = await loop.run_in_executor(_ai_executor, extract_from_text, text, "", book_id)
    if proposal.entities:
        result = await loop.run_in_executor(_ai_executor, accept_proposal, proposal, book_id)
        entities = kb.list_entities()
        json_store.update_book_stats(book_id, entity_count=len(entities))
        return result
    return "未检测到可提取的设定信息"

def _ask_user(args: dict) -> dict:
    qs = args.get("questions", [])
    if not qs:
        qs = [{"question": args.get("question", "请确认"), "header": "确认",
               "options": [{"label": o, "description": ""} for o in args.get("options", [])]}]
    for q in qs:
        if "custom" not in q:
            q["custom"] = True
    return {"type": "question", "questions": qs}

async def _start_autopilot(args: dict, book_id: str) -> dict:
    """Prepare an autopilot plan and return it for user confirmation.

    The actual confirmation (question → user answer → start) is handled by
    _process_tool_result in agent_loop.py which handles the autopilot_plan type.
    """
    from core.autopilot import AutopilotConfig
    from core.autopilot_runner import autopilot

    instruction = args.get("instruction", "按大纲写完这本书")
    max_chapters = int(args.get("max_chapters", 10))
    audit_mode = args.get("audit_mode", "soft")
    auto_review = args.get("auto_review", True)
    if isinstance(auto_review, str):
        auto_review = auto_review.lower() not in ("false", "no", "0")
    auto_extract = args.get("auto_extract", True)
    if isinstance(auto_extract, str):
        auto_extract = auto_extract.lower() not in ("false", "no", "0")

    config = AutopilotConfig(
        book_id=book_id,
        instruction=instruction,
        max_chapters_per_run=max_chapters,
        audit_mode=audit_mode,
        auto_review=auto_review,
        auto_extract=auto_extract,
        confirm_before_start=True,
    )

    result = await autopilot.start(config)
    if not result or not result.get("task_id"):
        return {"error": "创建 Autopilot 计划失败"}

    return {
        "type": "autopilot_plan",
        "task_id": result["task_id"],
        "plan_summary": result.get("plan_summary", ""),
        "chapters": result.get("chapters", []),
        "total_steps": result.get("total_steps", 0),
        "audit_mode": audit_mode,
        "needs_confirm": True,
    }

# ── Plot Card Tools ──


# ── New tool handlers: voice, semantic diff, outline pipeline ──


async def _analyze_voice_tool(loop, args: dict, book_id: str) -> str:
    """Analyze a character's voice fingerprint."""
    from core.voice_fingerprint import get_character_voice
    char_name = args.get("character_name", "")
    if not char_name:
        return "错误: 需要 character_name 参数"
    fp = await loop.run_in_executor(_ai_executor, get_character_voice, book_id, char_name)
    from core.voice_fingerprint import build_voice_prompt
    prompt = build_voice_prompt(fp)
    return f"角色「{char_name}」语言指纹分析完成：\n\n{fp.to_dict()}\n\n写作提示词：\n{prompt}"


async def _get_voice_profile_tool(loop, book_id: str) -> str:
    """Get voice fingerprints for all characters."""
    from core.voice_fingerprint import get_all_voice_fingerprints
    fingerprints = await loop.run_in_executor(_ai_executor, get_all_voice_fingerprints, book_id)
    if not fingerprints:
        return "当前书籍无角色数据，无法分析语言指纹"
    lines = [f"共 {len(fingerprints)} 个角色的语言指纹：\n"]
    for fp in fingerprints:
        if fp.dialogue_count > 0:
            lines.append(f"- **{fp.character_name}**：{fp.emotional_tendency}，平均句长{fp.avg_sentence_length:.0f}字，{fp.dialogue_count}句对话")
        else:
            lines.append(f"- **{fp.character_name}**：无对话数据")
    return "\n".join(lines)


async def _semantic_diff_tool(loop, args: dict, book_id: str) -> str:
    """Compute semantic diff between two chapter versions."""
    from core.semantic_diff import compute_semantic_diff
    chapter_id = args.get("chapter_id", "")
    old_vid = args.get("old_version_id", "")
    new_vid = args.get("new_version_id", "")
    if not chapter_id or not old_vid or not new_vid:
        return "错误: 需要 chapter_id, old_version_id, new_version_id 参数"
    chapters = json_store.load_chapters(book_id)
    ch = json_store._resolve_by_id(chapters, chapter_id)
    if not ch:
        return f"错误: 章节 {chapter_id} 不存在"
    versions = ch.get("versions", [])
    old_v = next((v for v in versions if v.get("id") == old_vid), None)
    new_v = next((v for v in versions if v.get("id") == new_vid), None)
    if not old_v or not new_v:
        return "错误: 版本ID不存在"
    result = await compute_semantic_diff(
        old_content=old_v.get("content", ""),
        new_content=new_v.get("content", ""),
        chapter_title=new_v.get("title", ""),
    )
    import json as _json
    return _json.dumps(result.to_dict(), ensure_ascii=False, indent=2)


async def _expand_outline_pipeline_tool(loop, args: dict, book_id: str) -> str:
    """Run the outline expansion pipeline."""
    from core.outline_pipeline import expand_pipeline_to_json
    seed = args.get("seed", "")
    levels = int(args.get("levels", 4))
    if not seed:
        return "错误: 需要 seed 参数（一句话故事设定）"
    results = await expand_pipeline_to_json(book_id, seed, levels)
    lines = [f"大纲逐级展开完成（{levels}级）：\n"]
    for r in results:
        if r.get("event") == "level_completed":
            lines.append(f"\n## Level {r['level']}: {r['level_name']}（{r['word_count']}字）")
            lines.append(r.get("output", "")[:500] + "...")
        elif r.get("event") == "pipeline_complete":
            lines.append(f"\n完成！总字数：{r.get('final_word_count', 0)}")
    return "\n".join(lines)
