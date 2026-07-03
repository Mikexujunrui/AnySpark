import difflib
import json
import logging
import re
import traceback
from concurrent.futures import ThreadPoolExecutor

from core.agent_context import AgentContext
from core.errors import ToolExecutionError
from core.event_bus import Event, EventType, bus
from core.thread_pools import llm_pool as _ai_executor
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
    _add_timeline_event_tool,
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

# ── Streaming tool dispatch map ──
# Each tool function receives (loop, args, kb, book_id, msg, queue) and returns result.
# Use functools.partial or lambda to adapt signatures where needed.
_STREAMING_DISPATCH: dict[str, callable] = {}


def _register_streaming():
    """Lazily build the streaming dispatch map (avoids import-time circular deps)."""
    _STREAMING_DISPATCH.update({
        "extract_all_chapters": lambda: _extract_all_chapters,
        "batch_edit_chapters": lambda: _batch_edit_chapters,
        "transform_book": lambda: _transform_book_streaming,
        "generate_outline": lambda: _generate_outline,
        "generate_worldbuilding": lambda: _generate_worldbuilding,
        "generate_location_map": lambda: _generate_location_map,
        "generate_detailed_outline": lambda: _generate_detailed_outline,
        "generate_timeline": lambda: _generate_timeline,
        "run_review": lambda: _run_review,
        "write_chapter": lambda: _write_chapter_streaming,
        "delegate_writing": lambda: _delegate_writing_streaming,
        "rewrite_by_chain": lambda: _rewrite_by_chain_streaming,
        "generate_workflow": lambda: _generate_workflow_streaming,
        "manage_workflows": lambda: _manage_workflows_streaming,
        "execute_workflow": lambda: _execute_workflow_streaming,
    })


async def execute_tool_streaming(loop, name: str, args: dict, kb,
                                 book_id: str, msg: str, session_id: str, queue,
                                 context: AgentContext | None = None) -> str | dict:
    try:
        if not _STREAMING_DISPATCH:
            _register_streaming()

        # Chapter-tools: lazily imported for whole-book transform
        if name == "transform_book":
            return await _transform_book_dispatcher(loop, args, book_id)
        if name == "find_replace_book":
            from tools.chapter_tools import find_replace_book
            return await find_replace_book(loop, args, book_id)
        if name == "apply_directive_globally":
            from tools.chapter_tools import apply_directive_globally
            return await apply_directive_globally(loop, args, book_id)
        if name == "transform_chapters_batch":
            from tools.chapter_tools import transform_chapters_batch
            return await transform_chapters_batch(loop, args, book_id)
        if name == "restyle_book":
            from tools.chapter_tools import restyle_book
            return await restyle_book(loop, args, book_id)
        if name == "summarize_book":
            from tools.chapter_tools import summarize_book
            return await summarize_book(loop, args, book_id)

        # Autopilot (no streaming deps)
        if name == "start_autopilot":
            return await _start_autopilot(args, book_id)

        # Streaming dispatch map
        if name in _STREAMING_DISPATCH:
            fn = _STREAMING_DISPATCH[name]()
            return await fn(loop, args, kb, book_id, msg, queue)

        # Fallback to non-streaming dispatch
        return await _dispatch(loop, name, args, kb, book_id, msg, session_id, context=context)
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
    try:
        result = await _dispatch(loop, name, args, kb, book_id, msg, session_id, context=context)
        bus.emit_sync(
            Event(
                type=EventType.TOOL_EXECUTED,
                data={
                    "tool": name,
                    "book_id": book_id},
                source="executor"))
        return result
    except ToolExecutionError as e:
        bus.emit_sync(
            Event(
                type=EventType.TOOL_FAILED,
                data={"tool": name, "error": str(e)[:100]},
                source="executor"))
        logger.error("Tool %s failed with ToolExecutionError: %s", name, e)
        return f"\\u274c 工具 {name} 执行失败: {str(e)[:150]}"
    except BaseException as e:
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        err = str(e)
        err_lower = err.lower()
        logger.error("Tool %s failed with args=%s: %s\n%s",
                     name, {k: str(v)[:200] for k, v in args.items()},
                     e, traceback.format_exc())
        bus.emit_sync(Event(type=EventType.TOOL_FAILED, data={
                      "tool": name, "error": err[:100]}, source="executor"))

        if "timeout" in err_lower or "timed out" in err_lower:
            return f"⏱ 工具 {name} 超时: 请求超过180秒未响应。可重试或缩短输入内容。"
        if any(k in err_lower for k in [
               "content_filter", "content filter", "sensitive", "policy", "moderation"]):
            return f"🚫 工具 {name} 被内容审查拦截: {err[:100]}。可尝试调整指令措辞。"
        if "rate" in err_lower or "429" in err or "too many" in err_lower:
            return f"⚠️ 工具 {name} 速率限制: {err[:80]}。请稍后重试。"
        if any(k in err_lower for k in [
               "connection", "network", "refused", "reset", "eof"]):
            return f"🌐 工具 {name} 网络错误: {err[:80]}。请检查网络后重试。"
        return f"❌ 工具 {name} 执行失败: {err[:150]}"

async def _dispatch(loop, name: str, args: dict, kb,
                    book_id: str, msg: str, session_id: str,
                    context: AgentContext | None = None) -> str | dict:
    if name == "search_knowledge":
        return _search_knowledge(args, kb)

    elif name == "extract_knowledge":
        return await _extract_knowledge(loop, args, kb, book_id, msg)

    elif name == "store_inspiration":
        return _store_inspiration(args, book_id, msg)

    elif name == "write_chapter":
        return await _write_chapter(loop, args, book_id, msg)

    elif name == "store_chapter":
        return _store_chapter(args, book_id, msg)

    elif name == "import_chapters":
        return await _import_chapters(loop, args, kb, book_id, session_id)

    elif name == "import_reference_chapters":
        return await _import_reference_chapters(loop, args, kb, book_id)

    elif name == "ask_user":
        return _ask_user(args)

    elif name == "decompose_chapter":
        return await _decompose_chapter(loop, args, msg, book_id)

    elif name == "annotate_chain":
        return _annotate_chain(args, book_id)

    elif name == "list_chapters":
        return _list_chapters(book_id)

    elif name == "count_words":
        return _count_words(args)

    elif name == "read_chapter":
        return _read_chapter(args, book_id)

    elif name == "delete_chapter":
        return _delete_chapter(args, book_id)

    elif name == "delete_all_chapters":
        return _delete_all_chapters(book_id)

    elif name == "delete_version":
        return _delete_version(args, book_id)

    elif name == "purge_chapter_history":
        return _purge_chapter_history(args, book_id)

    elif name == "generate_outline":
        return await _generate_outline(loop, args, book_id)

    elif name == "get_outline":
        return _get_outline(book_id, args)

    elif name == "update_outline":
        return _update_outline(args, book_id)

    elif name == "generate_worldbuilding":
        return await _generate_worldbuilding(loop, args, kb, book_id)

    elif name == "get_worldbuilding":
        return _get_worldbuilding_tool(book_id)

    elif name == "add_worldbuilding_entry":
        return _add_worldbuilding_entry_tool(args, book_id)

    elif name == "generate_location_map":
        return await _generate_location_map(loop, args, kb, book_id)

    elif name == "generate_detailed_outline":
        return await _generate_detailed_outline(loop, args, book_id)

    elif name == "get_detailed_outline":
        return _get_detailed_outline_tool(book_id)

    elif name == "update_detailed_outline":
        return _update_detailed_outline(args, book_id)

    elif name == "generate_timeline":
        return await _generate_timeline(loop, args, kb, book_id)

    elif name == "get_timeline":
        return _get_timeline_tool(book_id)

    elif name == "add_timeline_event":
        return _add_timeline_event_tool(args, book_id)
    elif name == "add_entity":
        return _add_entity_tool(args, book_id)
    elif name == "add_relation":
        return _add_relation_tool(args, book_id)

    elif name == "extract_all_chapters":
        return await _extract_all_chapters(loop, args, kb, book_id)

    elif name == "extract_chapter":
        return await _extract_chapter(loop, args, kb, book_id)

    elif name == "prepare_writing":
        return await _prepare_writing(loop, args, kb, book_id)

    elif name == "finalize_chapter":
        return await _finalize_chapter(loop, args, kb, book_id)

    elif name == "read_document":
        return _read_document(args, session_id, book_id)

    elif name == "edit_chapter":
        return _edit_chapter(args, book_id)

    elif name == "patch_chapter":
        return _patch_chapter(args, book_id)

    elif name == "chapter_history":
        return _chapter_history(args, book_id)

    elif name == "revert_chapter":
        return _revert_chapter(args, book_id)

    elif name == "diff_chapters":
        return await _diff_chapters(loop, args, book_id)

    elif name == "suggest_plot_directions":
        return await _suggest_plot_directions(loop, args, kb, book_id)

    elif name == "run_review":
        return await _run_review(loop, args, kb, book_id)

    elif name == "manage_reviewers":
        return _manage_reviewers(args)

    elif name in ("manage_volumes", "generate_volume_outlines", "list_volumes"):
        if name == "manage_volumes":
            action = args.get("action", "list")
            internal_map = {"list": "list_volumes", "create": "create_volume",
                           "update": "update_volume", "delete": "delete_volume",
                           "move": "move_chapter_to_volume"}
            internal = internal_map.get(action, "list_volumes")
            return _handle_volume(internal, args, book_id)
        return _handle_volume(name, args, book_id)

    elif name in ("add_material", "search_materials", "browse_materials",
                  "subscribe_material", "unsubscribe_material", "delete_material",
                  "set_reference_books", "list_books", "list_references", "list_reference_chapters",
                  "search_reference", "migrate_reference_knowledge"):
        return _handle_materials(name, args, book_id)

    elif name in ("delete_entity", "update_entity", "delete_worldbuilding_entry",
                  "delete_timeline_event", "delete_foreshadow", "set_character_phase"):
        return _handle_knowledge_edit(name, args, book_id)

    elif name in ("manage_workflows", "manage_workflow_steps", "execute_workflow",
                  "list_workflows", "browse_workflows"):
        if name == "manage_workflows":
            action = args.get("action", "list")
            if action == "generate":
                return await _generate_workflow_streaming(loop, args, kb, book_id, msg)
            return await _handle_workflow_tool(action, args, book_id)
        elif name == "manage_workflow_steps":
            action = args.get("action", "list")
            internal = "list_workflow_steps" if action == "list" else "update_workflow_step"
            return await _handle_workflow_tool(internal, args, book_id)
        else:
            return await _handle_workflow_tool(name, args, book_id)

    elif name == "manage_skills":
        action = args.get("action", "list")
        internal_map = {"list": "list_skills", "create": "create_skill",
                       "update": "update_skill", "delete": "delete_skill"}
        internal = internal_map.get(action, "list_skills")
        return _handle_skill_tool(internal, args)

    elif name == "list_skills":
        return _handle_skill_tool("list_skills", args)

    elif name == "agent_tasks":
        return _handle_agent_tasks(args, book_id)

    elif name == "delegate_writing":
        return await _delegate_writing(loop, args, kb, book_id, session_id, msg)

    elif name == "manage_permissions":
        return _manage_permissions(args)

    elif name == "web_search":
        return await _web_search(loop, args, book_id)

    elif name == "web_fetch":
        return await _web_fetch(loop, args)

    elif name == "task":
        return await _run_sub_agent(args, book_id, session_id, context=context)

    elif name == "set_style":
        return _set_style(args, book_id)

    elif name == "get_style":
        return _get_style(book_id)

    elif name == "list_styles":
        return _list_styles(book_id)

    elif name == "manage_styles":
        return _manage_styles(args)

    elif name == "extract_style":
        return await _extract_style(loop, args, kb, book_id, msg)

    elif name == "reconstruct_chapter":
        return await _reconstruct_chapter(loop, args, kb, book_id)

    elif name == "compare_plot":
        return await _compare_plot(loop, args)

    # ── Whole-book transform tools (fallback for non-streaming calls) ──
    elif name in ("transform_book", "find_replace_book", "summarize_book",
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
        if name == "find_replace_book":
            return await find_replace_book(loop, args, book_id)
        elif name == "apply_directive_globally":
            return await apply_directive_globally(loop, args, book_id)
        elif name == "summarize_book":
            return await summarize_book(loop, args, book_id)
        elif name == "transform_chapters_batch":
            return await transform_chapters_batch(loop, args, book_id)
        elif name == "restyle_book":
            return await restyle_book(loop, args, book_id)

    elif name == "start_autopilot":
            return await _start_autopilot(args, book_id)

    # ── Narrative logic tools ──
    elif name == "define_constraint":
        return await _define_constraint(loop, args, kb, book_id, msg)
    elif name == "check_constraints":
        return await _check_constraints(loop, args, kb, book_id, msg)
    elif name == "delete_constraint":
        return await _delete_constraint(loop, args, kb, book_id, msg)
    elif name == "analyze_impact":
        return await _analyze_impact(loop, args, kb, book_id, msg)
    elif name == "score_confidence":
        return await _score_confidence(loop, args, kb, book_id, msg)

    # ── Graph tools ──
    elif name == "search_graph":
        return await _search_graph(loop, args, kb, book_id, msg)
    elif name == "get_graph_insights":
        return await _get_graph_insights(loop, args, kb, book_id, msg)
    elif name == "verify_chapter":
        return await _verify_chapter(loop, args, kb, book_id, msg)

    # ── Voice fingerprint tools ──
    elif name == "analyze_voice":
        return await _analyze_voice_tool(loop, args, book_id)
    elif name == "get_voice_profile":
        return await _get_voice_profile_tool(loop, book_id)

    # ── Semantic diff tool ──
    elif name == "semantic_diff":
        return await _semantic_diff_tool(loop, args, book_id)

    # ── Outline pipeline tool ──
    elif name == "expand_outline_pipeline":
        return await _expand_outline_pipeline_tool(loop, args, book_id)

    return f"工具 {name} 未注册 (params: {json.dumps(args, ensure_ascii=False)[:100]})"

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
