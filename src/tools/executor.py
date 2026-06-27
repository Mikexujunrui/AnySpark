import difflib
import json
import logging
import re
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
    _manage_scope,
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
)
from tools.impl.plot import (
    _annotate_chain,
    _compare_plot,
    _compare_versions,
    _decompose_chapter,
    _extract_style,
    _read_document,
    _reconstruct_chapter,
    _suggest_plot_directions,
)
from tools.impl.review import _manage_reviewers, _run_review
from tools.impl.styles import _get_style, _list_styles, _manage_styles, _set_style, _suggest_style
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
        "execute_workflow": lambda: _execute_workflow_streaming,
    })


async def execute_tool_streaming(loop, name: str, args: dict, kb,
                                 book_id: str, msg: str, session_id: str, queue,
                                 context: AgentContext | None = None) -> str | dict:
    try:
        if not _STREAMING_DISPATCH:
            _register_streaming()

        # Chapter-tools: lazily imported for whole-book transform
        if name == "apply_directive_globally":
            from chapter_tools import apply_directive_globally
            return await apply_directive_globally(loop, args, book_id)
        if name == "find_replace_book":
            from chapter_tools import find_replace_book
            return await find_replace_book(loop, args, book_id)
        if name == "transform_chapters_batch":
            from chapter_tools import transform_chapters_batch
            return await transform_chapters_batch(loop, args, book_id)
        if name == "restyle_book":
            from chapter_tools import restyle_book
            return await restyle_book(loop, args, book_id)
        if name == "summarize_book":
            from chapter_tools import summarize_book
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
    except Exception as e:
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
    except ToolExecutionError:
        bus.emit_sync(
            Event(
                type=EventType.TOOL_FAILED,
                data={
                    "tool": name,
                    "error": "ToolExecutionError"},
                source="executor"))
        raise
    except Exception as e:
        err = str(e)
        err_lower = err.lower()
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

    elif name == "compare_versions":
        return await _compare_versions(loop, args, kb, msg)

    elif name == "ask_user":
        return _ask_user(args)

    elif name == "decompose_chapter":
        return await _decompose_chapter(loop, args, msg, book_id)

    elif name == "annotate_chain":
        return _annotate_chain(args, book_id)

    elif name == "extract_style":
        return await _extract_style(loop, args, kb, book_id, msg)

    elif name == "reconstruct_chapter":
        return await _reconstruct_chapter(loop, args, kb, book_id)

    elif name == "compare_plot":
        return await _compare_plot(loop, args)

    elif name == "count_words":
        return _count_words(args)

    elif name == "list_chapters":
        return _list_chapters(book_id)

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
        return await _generate_timeline(loop, args, book_id)

    elif name == "get_timeline":
        return _get_timeline_tool(book_id)

    elif name == "add_timeline_event":
        return _add_timeline_event_tool(args, book_id)

    elif name == "extract_all_chapters":
        return await _extract_all_chapters(loop, args, kb, book_id)

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

    elif name in ("create_volume", "update_volume", "list_volumes",
                  "delete_volume", "move_chapter_to_volume",
                  "generate_volume_outlines"):
        return _handle_volume(name, args, book_id)

    elif name in ("add_material", "search_materials", "browse_materials",
                  "subscribe_material", "unsubscribe_material", "delete_material",
                  "set_reference_books", "list_books", "list_references", "list_reference_chapters",
                  "search_reference", "migrate_reference_knowledge"):
        return _handle_materials(name, args, book_id)

    elif name in ("delete_entity", "update_entity", "delete_worldbuilding_entry",
                  "delete_timeline_event", "delete_foreshadow", "set_character_phase"):
        return _handle_knowledge_edit(name, args, book_id)

    elif name in ("generate_workflow", "list_workflows", "delete_workflow",
                  "browse_workflows", "subscribe_workflow", "unsubscribe_workflow",
                  "execute_workflow", "update_workflow", "list_workflow_steps",
                  "update_workflow_step"):
        return await _handle_workflow_tool(name, args, book_id)

    elif name in ("list_skills", "create_skill", "update_skill", "delete_skill"):
        return _handle_skill_tool(name, args)

    elif name == "agent_tasks":
        return _handle_agent_tasks(args, book_id)

    elif name == "delegate_writing":
        return await _delegate_writing(loop, args, kb, book_id, session_id, msg)

    elif name == "manage_scope":
        return _manage_scope(args, book_id)
    elif name == "manage_permissions":
        return _manage_permissions(args)

    elif name == "web_search":
        return await _web_search(loop, args, book_id)

    elif name == "web_fetch":
        return await _web_fetch(loop, args)

    elif name == "task":
        return await _run_sub_agent(args, book_id, session_id, context=context)

    elif name == "list_styles":
        return _list_styles(book_id)

    elif name == "set_style":
        return _set_style(args, book_id)

    elif name == "suggest_style":
        return _suggest_style(args)

    elif name == "get_style":
        return _get_style(book_id)

    elif name == "manage_styles":
        return _manage_styles(args)

    # ── Whole-book transform tools (fallback for non-streaming calls) ──
    elif name in ("apply_directive_globally", "find_replace_book",
                   "transform_chapters_batch", "restyle_book", "summarize_book"):
        from chapter_tools import (
            apply_directive_globally,
            find_replace_book,
            restyle_book,
            summarize_book,
            transform_chapters_batch,
        )
        if name == "apply_directive_globally":
            return await apply_directive_globally(loop, args, book_id)
        elif name == "find_replace_book":
            return await find_replace_book(loop, args, book_id)
        elif name == "transform_chapters_batch":
            return await transform_chapters_batch(loop, args, book_id)
        elif name == "restyle_book":
            return await restyle_book(loop, args, book_id)
        elif name == "summarize_book":
            return await summarize_book(loop, args, book_id)

    elif name == "start_autopilot":
            return await _start_autopilot(args, book_id)

    return f"工具 {name} 未注册 (params: {json.dumps(args, ensure_ascii=False)[:100]})"

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
        for r in fts_results:
            e = entity_map.get(r["id"])
            if e:
                data_preview = ", ".join(
                    f"{k}: {str(v)[:30]}" for k, v in list(e.data.items())[:5]
                    if v
                )
                lines.append(f"- **{e.name}** [{e.type}]")
                if data_preview:
                    lines.append(f"  {data_preview}")
                if r.get("snippet"):
                    lines.append(f"  匹配: {r['snippet']}")
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




