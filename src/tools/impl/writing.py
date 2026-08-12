"""Writing tool implementations — chapter write, delegate writing, rewrite by chain.

Extracted from executor.py to keep module sizes manageable.
"""

import asyncio
import json
import logging
import re
from contextvars import copy_context

from core.config import config
from core.content_guard import detect_model_refusal
from core.llm_client import chat as llm_chat
from core.thread_pools import llm_pool as _ai_executor
from data.json_store import json_store

logger = logging.getLogger(__name__)


def _guard_generated_prose(text: object) -> dict | None:
    """Reject provider refusal/safety notices before chapter persistence."""

    reason = detect_model_refusal(text)
    if not reason:
        return None
    return {
        "type": "writing_result",
        "text": f"写作失败·未保存：{reason}。请调整模型/提示词后重试，原章节没有被占位或覆盖。",
        "error": reason,
        "saved": False,
        "retriable": True,
    }


def _post_write_constraint_check(kb, book_id: str) -> str:
    """Run constraint check after writing, return warning text if violations found.

    Returns empty string if no violations or if constraint checking is
    unavailable (e.g. graph store unavailable, no constraints defined).
    """
    try:
        from core.narrative_logic import ConstraintChecker, ConstraintStore

        constraint_store = ConstraintStore(kb)
        constraints = constraint_store.list(active_only=True)
        if not constraints:
            return ""
        checker = ConstraintChecker(kb)
        violations = checker.check_all()
        if not violations:
            return ""
        lines = ["\n⚠️ 叙事约束检查发现违反:"]
        for v in violations:
            sev = "🔴" if v.severity == "hard" else "🟡"
            lines.append(f"  {sev} [{v.severity}] {v.description}")
            for detail in v.violations[:3]:
                lines.append(f"     - {detail}")
        lines.append("建议检查上述内容并修正，或使用 check_constraints 查看详情。")
        return "\n".join(lines)
    except Exception as e:
        logger.debug("Post-write constraint check failed: %s", e)
        return ""


def _infer_scope_entities(kb, book_id: str, instruction: str, scope) -> None:
    """Semantic entity matching fallback — use FTS + keyword matching to find
    relevant entities when the Agent didn't explicitly pass characters/locations.

    Strategy (in order):
    1. Extract keywords from instruction + chapter outline
    2. FTS search (SQLite FTS5) for matching entities
    3. Fall back to substring matching against entity names/aliases
    4. If still nothing, take top 8 characters + 4 locations by recency
    """
    from core.knowledge_scope import ExposureLevel
    from core.search import fts

    # Extract keywords: instruction + chapter outline
    keywords = instruction
    if scope.chapter_outline:
        keywords += " " + scope.chapter_outline

    entities = kb.list_entities()
    if not entities:
        return

    name_to_entity = {}
    for e in entities:
        name_to_entity[e.name] = e
        for a in e.aliases:
            name_to_entity[a] = e

    matched_chars: set[str] = set()
    matched_locs: set[str] = set()

    # Strategy 1: FTS search with outline keywords
    try:
        search_query = scope.chapter_outline[:200] if scope.chapter_outline else instruction[:200]
        fts_results = fts.search_entities(book_id, search_query, limit=20)
        for r in fts_results:
            entity = name_to_entity.get(r["name"])
            if not entity:
                continue
            if entity.type == "character" and len(matched_chars) < 15:
                matched_chars.add(entity.name)
            elif entity.type == "location" and len(matched_locs) < 8:
                matched_locs.add(entity.name)
    except Exception:
        logger.debug("FTS entity search failed, falling back to keyword matching", exc_info=True)

    # Strategy 2: Substring matching for entities not found by FTS
    if len(matched_chars) < 5:
        kw_lower = keywords.lower()
        for e in entities:
            if e.type == "character" and e.name not in matched_chars:
                names_to_check = [e.name] + list(e.aliases)
                if any(n.lower() in kw_lower for n in names_to_check):
                    matched_chars.add(e.name)
                    if len(matched_chars) >= 15:
                        break

    if len(matched_locs) < 3:
        kw_lower = keywords.lower()
        for e in entities:
            if e.type == "location" and e.name not in matched_locs:
                names_to_check = [e.name] + list(e.aliases)
                if any(n.lower() in kw_lower for n in names_to_check):
                    matched_locs.add(e.name)
                    if len(matched_locs) >= 8:
                        break

    # Strategy 3: If still nothing, take top entities by recency
    if not matched_chars and not matched_locs:
        char_count = 0
        loc_count = 0
        for e in entities:
            if e.type == "character" and char_count < 8:
                matched_chars.add(e.name)
                char_count += 1
            elif e.type == "location" and loc_count < 4:
                matched_locs.add(e.name)
                loc_count += 1

    # Apply to scope
    for name in matched_chars:
        scope.add_character(name, ExposureLevel.SUMMARY, "语义匹配")
    for name in matched_locs:
        scope.add_location(name, ExposureLevel.SUMMARY, "语义匹配")


def _build_scope_report(scope) -> str:
    """Build a human-readable knowledge scope report for the writing result."""
    lines = []
    if scope.characters:
        names = [e.entity_name for e in scope.characters]
        sources = {e.reason for e in scope.characters}
        source_label = " | ".join(sorted(sources)) if sources else ""
        lines.append(f"  角色({len(names)}): {', '.join(names[:10])}" + ("..." if len(names) > 10 else ""))
        if source_label:
            lines.append(f"  来源: {source_label}")
    if scope.locations:
        names = [e.entity_name for e in scope.locations]
        lines.append(f"  地点({len(names)}): {', '.join(names[:8])}" + ("..." if len(names) > 8 else ""))
    if scope.concepts:
        names = [e.entity_name for e in scope.concepts]
        lines.append(f"  设定({len(names)}): {', '.join(names[:5])}" + ("..." if len(names) > 5 else ""))
    if scope.forbidden_characters:
        lines.append(f"  禁止出场: {', '.join(scope.forbidden_characters)}")
    if scope.chapter_outline:
        outline_preview = scope.chapter_outline[:60]
        lines.append(
            f"  大纲: {outline_preview}..." if len(scope.chapter_outline) > 60 else f"  大纲: {scope.chapter_outline}"
        )
    if scope.writing_rules:
        rules_preview = scope.writing_rules[:80]
        lines.append(
            f"  规则: {rules_preview}..." if len(scope.writing_rules) > 80 else f"  规则: {scope.writing_rules}"
        )
    if not lines:
        return ""
    return "📋 知识范围报告:\n" + "\n".join(lines)


def _build_graph_insight_report(kb, scope) -> str:
    """Build graph insights relevant to the current writing scope.

    Returns empty string on any error — must never block the writing result.
    """
    try:
        insights = kb.get_graph_insights()
    except Exception:
        return ""

    if not insights:
        return ""

    scope_char_names = {e.entity_name for e in scope.characters} if scope.characters else set()
    lines = []

    # Forgotten characters (not in current scope)
    forgotten = insights.get("forgotten_characters", [])
    if forgotten:
        not_in_scope = [c for c in forgotten if c.get("name") not in scope_char_names]
        if not_in_scope:
            names = ", ".join(c["name"] for c in not_in_scope[:3])
            lines.append(f"  ⚠️ 遗忘角色: {names}（已多章未出场，建议安排）")

    # Unresolved foreshadows
    unresolved = insights.get("unresolved_foreshadows", [])
    if unresolved:
        lines.append(f"  🔮 待回收伏笔: {len(unresolved)} 个")
        for f in unresolved[:3]:
            lines.append(f"     - {f.get('text', '?')[:50]}")

    # Bridge characters
    bridges = insights.get("bridge_characters", [])
    if bridges:
        names = ", ".join(b.get("entity_name", "?") for b in bridges[:3])
        lines.append(f"  🔗 桥接角色: {names}（连接多条关系线，推动剧情关键）")

    # Underutilized locations
    unused_locs = insights.get("underutilized_locations", [])
    if unused_locs:
        names = ", ".join(loc.get("name", "?") for loc in unused_locs[:3])
        lines.append(f"  📍 未使用地点: {names}")

    if not lines:
        return ""
    return "📊 图谱洞察:\n" + "\n".join(lines)


def _format_chapter_result(
    book_id: str, chapter_id: str, title: str, content: str, extra: str = "", scope_report: str = ""
) -> str:
    """Format chapter write result with progress and content preview.

    Avoids hallucination-trigger keywords like '已保存' which could cause
    the main agent to echo them and trigger false-positive detection.
    """
    # Get progress: current chapter count vs outline total
    chapters = json_store.load_chapters(book_id)
    current = len(chapters)
    outline = json_store.get_outline(book_id)
    total = len(outline.get("chapters", []))
    progress = f"进度: {current}/{total}" if total > 0 else f"共{current}章"

    # Content preview (first 150 chars)
    preview = content[:150].replace("\n", " ")
    if len(content) > 150:
        preview += "..."

    result = f"✅ 章节: {title} (id: {chapter_id[:8]}, {len(content)}字)\n{progress}"
    if scope_report:
        result += f"\n{scope_report}"
    if preview:
        result += f"\n内容预览: {preview}"
    if extra:
        result += f"\n{extra}"
    return result


def _requested_regular_chapter_index(args: dict, instruction: str = "") -> int | None:
    """Resolve a requested regular chapter number from explicit args/text.

    Priority:
    1. Explicit ``chapter_index`` arg (the most reliable signal).
    2. A "target-style" marker: ``写/续写/新增/新建/开始第N章`` — this is what
       the agent means when asking to write chapter N.
    3. The *last* ``第N章`` occurrence. Instructions frequently mention earlier
       chapters for continuity ("承接第6章结尾，写第7章"); taking the first
       match misreads such instructions as targeting chapter 6, tripping the
       new-chapter protection guard and sending the agent into a retry loop.
    """
    if bool(args.get("is_extra", False)):
        return None
    explicit = args.get("chapter_index")
    if explicit is not None:
        try:
            value = int(explicit)
            return value if value > 0 else None
        except (TypeError, ValueError):
            return None
    text = " ".join(
        value
        for value in (
            str(args.get("chapter_title", "") or ""),
            str(args.get("title", "") or ""),
            instruction,
        )
        if value
    )
    # Only accept a real "第N章" marker. A loose first-number match mistakes
    # target word counts such as "写一章 2500 字" for chapter #2500.
    target = re.search(r"(?:写|续写|开始写|新增|新建|接着写)\s*第\s*(\d+)\s*章", text)
    if target:
        return int(target.group(1))
    matches = re.findall(r"第\s*(\d+)\s*章", text)
    return int(matches[-1]) if matches else None


def _guard_new_chapter_target(book_id: str, args: dict, instruction: str = "") -> dict | None:
    """Hard stop if a new-writing tool points at an existing chapter."""
    index = _requested_regular_chapter_index(args, instruction)
    if index is None:
        return None
    chapters = json_store.load_chapters(book_id)
    existing = json_store._find_chapter(chapters, f"#{index}")
    if not existing:
        return None
    view = json_store._chapter_view(existing)
    return {
        "type": "writing_result",
        "text": (
            f"⛔ 原稿保护：第{index}章“{view.get('title', '')}”已经存在，"
            "新章写作工具拒绝覆盖。请改用 patch_chapter 做局部版本化修改；"
            "只有用户明确要求整章重写时才使用 edit_chapter。"
            "这两种工具都会保留历史版本，自主模式下可连续执行。"
        ),
        "chapter_id": view.get("id", ""),
        "chapter_title": view.get("title", ""),
        "saved": False,
        "protected": True,
    }


async def _write_chapter(loop, args: dict, book_id: str, msg: str) -> str | dict:
    from core.writer import write as wr

    guard = _guard_new_chapter_target(book_id, args, args.get("instruction", msg))
    if guard:
        return guard
    ref_chapters = args.get("ref_chapters", []) or None
    def writer_call():
        return wr(
            args.get("instruction", msg),
            mode=args.get("mode", "strict"),
            project_id=book_id,
            ref_chapters=ref_chapters,
        )

    result = await loop.run_in_executor(_ai_executor, copy_context().run, writer_call)
    refusal = _guard_generated_prose(result)
    if refusal:
        return refusal
    title = args.get("chapter_title", args.get("title", ""))
    is_extra = bool(args.get("is_extra", False))
    chapter_index = args.get("chapter_index", None)
    if not title:
        chapters = json_store.load_chapters(book_id)
        if is_extra:
            title = f"番外{sum(1 for c in chapters if c.get('is_extra')) + 1}"
        else:
            title = f"第{sum(1 for c in chapters if not c.get('is_extra')) + 1}章"
    chapter = json_store.add_chapter(
        book_id, title, result, is_extra=is_extra, origin="ai_draft", protected=True
    )
    # 存储chapter_index用于后续追踪
    if chapter_index is not None:
        from data.json_store import json_store as js

        chapters = js.load_chapters(book_id)
        for ch in chapters:
            if ch["id"] == chapter["id"]:
                if not ch.get("index"):
                    ch["index"] = int(chapter_index)
                if not ch.get("chapter_index"):
                    ch["chapter_index"] = int(chapter_index)
                js.save_chapters(book_id, chapters)
                break
    return _format_chapter_result(book_id, chapter["id"], title, result)


async def _write_chapter_streaming(loop, args: dict, kb, book_id: str, msg: str, queue=None) -> str | dict:
    from core.writer import write_stream as write_stream_fn

    instruction = args.get("instruction", msg)
    guard = _guard_new_chapter_target(book_id, args, instruction)
    if guard:
        return guard
    mode = args.get("mode", "strict")
    ref_chapters = args.get("ref_chapters", [])

    if queue:
        tentative_title = args.get("chapter_title", args.get("title", ""))
        if not tentative_title:
            chs = json_store.load_chapters(book_id)
            if bool(args.get("is_extra", False)):
                tentative_title = f"番外{sum(1 for c in chs if c.get('is_extra')) + 1}"
            else:
                tentative_title = f"第{sum(1 for c in chs if not c.get('is_extra')) + 1}章"
        await queue.put({"_writing_meta": {"chapter_title": tentative_title, "type": "start"}})
        await queue.put({"_progress": "正在写作..."})

    chunk_queue: asyncio.Queue = asyncio.Queue()
    chunks: list[str] = []
    write_error: str | None = None
    write_blocked: bool = False

    def _run():
        nonlocal write_error, write_blocked
        try:
            for chunk in write_stream_fn(
                instruction, mode=mode, project_id=book_id, ref_chapters=ref_chapters if ref_chapters else None
            ):
                chunks.append(chunk)
                chunk_queue.put_nowait(chunk)
        except Exception as e:
            logger.exception("write_chapter_streaming failed")
            err_str = str(e).lower()
            if any(k in err_str for k in ("content_filter", "content filter", "sensitive", "policy", "moderation")):
                write_blocked = True
                write_error = f"内容审查拦截（位置: {len(''.join(chunks))}字后）"
            else:
                write_error = str(e)[:100]
        finally:
            chunk_queue.put_nowait(None)

    loop.run_in_executor(_ai_executor, copy_context().run, _run)

    while True:
        chunk = await chunk_queue.get()
        if chunk is None:
            break
        if queue:
            await queue.put({"_writing": chunk})

    full_text = "".join(chunks)

    refusal = _guard_generated_prose(full_text)
    if refusal:
        return refusal

    if write_error and full_text and len(full_text) > 200:
        title = args.get("chapter_title", args.get("title", ""))
        if not title:
            chapters = json_store.load_chapters(book_id)
            title = f"第{len(chapters) + 1}章"
        chapter = json_store.add_chapter(
            book_id, title, full_text, origin="ai_partial", protected=True
        )
        return {
            "type": "writing_result",
            "text": (
                f"⚠️ 生成中断但已保全前 {len(full_text)} 字：{write_error}。"
                f"请从截断处继续，不要从头调用另一个写作工具。(id: {chapter['id'][:8]})"
            ),
            "chapter_id": chapter["id"],
            "chapter_title": title,
            "word_count": len(full_text),
            "saved": True,
            "partial": True,
        }

    if write_error:
        return {"type": "writing_result", "text": f"写作中断: {write_error}", "saved": False}

    if not full_text or len(full_text.strip()) < 50:
        return {
            "type": "writing_result",
            "text": f"写作未生成有效内容（{len(full_text)}字）。请检查指令或换用不同提示词重试。",
            "saved": False,
        }

    title = args.get("chapter_title", args.get("title", ""))
    is_extra = bool(args.get("is_extra", False))
    chapter_index = args.get("chapter_index", None)
    if not title:
        chapters = json_store.load_chapters(book_id)
        if is_extra:
            title = f"番外{sum(1 for c in chapters if c.get('is_extra')) + 1}"
        else:
            title = f"第{sum(1 for c in chapters if not c.get('is_extra')) + 1}章"
    chapter = json_store.add_chapter(
        book_id, title, full_text, is_extra=is_extra, origin="ai_draft", protected=True
    )
    # 存储chapter_index用于后续追踪
    if chapter_index is not None:
        from data.json_store import json_store as js

        chapters = js.load_chapters(book_id)
        for ch in chapters:
            if ch["id"] == chapter["id"]:
                if not ch.get("index"):
                    ch["index"] = int(chapter_index)
                if not ch.get("chapter_index"):
                    ch["chapter_index"] = int(chapter_index)
                js.save_chapters(book_id, chapters)
                break
    return {
        "type": "writing_result",
        "text": _format_chapter_result(book_id, chapter["id"], title, full_text),
        "chapter_id": chapter["id"],
        "chapter_title": title,
        "word_count": len(full_text),
        "saved": True,
    }


async def _write_by_nodes_legacy(
    loop,
    scoped_context: str,
    ref_block: str,
    plot_chain: list,
    chapter_function: str,
    writing_rules: str,
    system: str,
    book_id: str,
    queue=None,
    target_words_per_node: int = 350,
    forbidden_characters: list | None = None,
) -> tuple[str, str | None]:
    """Node-by-node writing: each plot_chain event is an independent writing unit.

    Returns (full_text, error_message). error_message is None on success.
    """
    from core.llm_client import chat_stream

    full_text = ""
    prev_ending = ""
    write_error = None

    # ── Build stable system prompt (cacheable prefix) ──
    # All knowledge context, rules, and chapter-level info go into the
    # system message so it's identical across node calls. DeepSeek's prefix
    # caching can then hit the entire system message, saving input tokens
    # on nodes 2..N.
    stable_system = f"""{system}

# 本章可用知识库设定
{scoped_context}
{ref_block}
---
本章共 {len(plot_chain)} 个事件。
{f"本章叙事功能: {chapter_function}" if chapter_function else ""}
{f"写作规则: {writing_rules}" if writing_rules else ""}"""

    for i, event in enumerate(plot_chain):
        if write_error:
            break

        if queue:
            await queue.put({"_progress": f"\u8282\u70b9 {i + 1}/{len(plot_chain)}: {event[:30]}..."})

        # Build node-level prompt — only the variable parts go here
        prev_context = (
            f"\u524d\u6587\u7ed3\u5c3e\uff08\u8bf7\u81ea\u7136\u8854\u63a5\uff09: ...{prev_ending[-200:]}"
            if prev_ending
            else "\uff08\u672c\u7ae0\u5f00\u5934\uff09"
        )

        node_prompt = f"""当前写第 {i + 1} 个事件。
{prev_context}

当前事件: {event}

【字数要求】严格控制在 {target_words_per_node} 字左右，不要超过 {target_words_per_node + 150} 字。
请直接输出小说正文，不要加解释前缀、不要使用任何标题（如 ##、### 等Markdown格式）、不要给段落起小标题。本段是连续叙事的一部分，请自然衔接前文，保持叙述流畅。"""

        # Stream generate for this node
        chunk_queue: asyncio.Queue = asyncio.Queue()
        node_chunks = []

        def _run():
            nonlocal write_error
            try:
                for chunk in chat_stream(node_prompt, system=stable_system, temperature=0.7, task="writing"):
                    text = chunk if isinstance(chunk, str) else str(chunk)
                    node_chunks.append(text)
                    chunk_queue.put_nowait(text)
            except Exception as e:
                logger.exception("node writing failed")
                err_str = str(e).lower()
                if any(k in err_str for k in ("content_filter", "content filter", "sensitive", "policy", "moderation")):
                    write_error = f"\u5185\u5bb9\u5ba1\u67e5\u62e6\u622a\uff08\u8282\u70b9 {i + 1}: {event[:20]}\uff09"
                else:
                    write_error = f"LLM\u9519\u8bef\uff08\u8282\u70b9 {i + 1}\uff09: {str(e)[:80]}"
            finally:
                chunk_queue.put_nowait(None)

        loop.run_in_executor(_ai_executor, copy_context().run, _run)

        while True:
            chunk = await chunk_queue.get()
            if chunk is None:
                break
            if queue:
                await queue.put({"_writing": chunk})
            full_text += chunk

        # Save ending for next node's coherence
        if node_chunks:
            prev_ending = "".join(node_chunks)[-200:]

        # ── 节点级轻量验证：检查禁止角色是否出现 ──
        node_text = "".join(node_chunks) if node_chunks else ""
        if forbidden_characters and node_text:
            violations_found = [fc for fc in forbidden_characters if fc in node_text]
            if violations_found and queue:
                await queue.put(
                    {
                        "_progress": (
                            f"节点 {i + 1}: 检测到禁止角色 {','.join(violations_found)}；"
                            "已保留当前草稿并交给写后评审，不会在后台替换刚显示的正文"
                        )
                    }
                )

        # Add separator between nodes
        if i < len(plot_chain) - 1 and not write_error:
            sep = "\n\n"
            full_text += sep
            if queue:
                await queue.put({"_writing": sep})

    return full_text, write_error


async def _write_by_nodes(
    loop,
    scoped_context: str,
    ref_block: str,
    plot_chain: list,
    chapter_function: str,
    writing_rules: str,
    system: str,
    book_id: str,
    queue=None,
    target_words_per_node: int = 350,
    forbidden_characters: list | None = None,
    target_words: int | None = None,
    max_segment_words: int | None = None,
    enforce_segment_boundaries: bool = False,
) -> tuple[str, str | None]:
    """Write plot events under explicit prose and narrative budgets.

    When boundary enforcement is active, a segment stays buffered until a
    separate judge confirms it has not consumed future beats.  Rejected prose
    is therefore never flashed in the preview and then silently replaced.
    """

    from core.llm_client import chat_stream, normalize_content_text
    from core.narrative_budget import build_segment_contracts, check_segment_boundary

    total_target = int(target_words or max(target_words_per_node * len(plot_chain), target_words_per_node))
    hard_limit = int(max_segment_words or target_words_per_node + 150)
    contracts = build_segment_contracts(
        plot_chain,
        target_chars=total_target,
        max_segment_chars=hard_limit,
    )
    if not contracts:
        return "", "没有可执行的分段创作合同"

    stable_system = f"""{system}

# 本章可用知识库设定
{scoped_context}
{ref_block}
---
本章共 {len(contracts)} 个叙事分段。每次只执行当前合同，后续事件只是禁止越过的边界。
{f"本章叙事功能: {chapter_function}" if chapter_function else ""}
{f"写作规则: {writing_rules}" if writing_rules else ""}"""

    async def _generate(prompt_text: str, stream_live: bool) -> tuple[str, str | None]:
        chunk_queue: asyncio.Queue = asyncio.Queue()
        chunks: list[str] = []
        errors: list[str] = []

        def _run():
            try:
                for chunk in chat_stream(prompt_text, system=stable_system, temperature=0.7, task="writing"):
                    text = normalize_content_text(chunk)
                    if not text:
                        continue
                    chunks.append(text)
                    loop.call_soon_threadsafe(chunk_queue.put_nowait, text)
            except Exception as exc:
                logger.exception("segment writing failed")
                err_str = str(exc).lower()
                if any(k in err_str for k in ("content_filter", "content filter", "sensitive", "policy", "moderation")):
                    errors.append("内容审查拦截")
                else:
                    errors.append(f"LLM 错误: {str(exc)[:100]}")
            finally:
                loop.call_soon_threadsafe(chunk_queue.put_nowait, None)

        loop.run_in_executor(_ai_executor, copy_context().run, _run)
        while True:
            chunk = await chunk_queue.get()
            if chunk is None:
                break
            if stream_live and queue:
                await queue.put({"_writing": chunk})
        return "".join(chunks), errors[0] if errors else None

    full_text = ""
    prev_ending = ""
    write_error: str | None = None

    for contract in contracts:
        if queue:
            await queue.put(
                {
                    "_progress": (
                        f"分段 {contract.index}/{contract.total}: {contract.beat[:30]}... "
                        f"（硬上限 {contract.max_chars} 字）"
                    )
                }
            )

        prompt = contract.render_prompt(prev_ending)
        node_text, node_error = await _generate(prompt, stream_live=not enforce_segment_boundaries)
        if node_error:
            write_error = f"{node_error}（分段 {contract.index}: {contract.beat[:20]}）"
            break

        if enforce_segment_boundaries:
            boundary = await check_segment_boundary(loop, node_text, contract)
            if not boundary.check_available and queue:
                await queue.put({"_progress": f"分段 {contract.index}: ⚠️ {boundary.reason}，已保留本次结果"})
            if not boundary.passed:
                if queue:
                    await queue.put(
                        {
                            "_progress": (
                                f"分段 {contract.index}: 检测到剧情预算透支（{boundary.reason[:80]}），"
                                "正在限定原边界重试一次..."
                            )
                        }
                    )
                retry_prompt = (
                    prompt
                    + "\n\n# 边界校正\n"
                    + f"上一版越界：{boundary.reason}；证据：{boundary.evidence[:200]}。\n"
                    + "请重新完整输出本段，只展开当前事件，提前停在合同指定状态。"
                )
                node_text, node_error = await _generate(retry_prompt, stream_live=False)
                if node_error:
                    write_error = f"{node_error}（分段 {contract.index} 边界重试）"
                    break
                boundary = await check_segment_boundary(loop, node_text, contract)
                if not boundary.passed:
                    write_error = (
                        f"剧情边界检查未通过（分段 {contract.index}/{contract.total}）: "
                        f"{boundary.reason or '模型提前消耗了后续事件'}"
                    )
                    break

            if queue and node_text:
                await queue.put({"_writing": node_text})

        full_text += node_text
        prev_ending = node_text[-350:]

        if forbidden_characters and node_text:
            violations = [name for name in forbidden_characters if name in node_text]
            if violations and queue:
                await queue.put(
                    {
                        "_progress": (
                            f"分段 {contract.index}: 检测到禁止角色 {','.join(violations)}；"
                            "已保留当前草稿并交给写后评审"
                        )
                    }
                )

        if contract.index < contract.total:
            full_text += "\n\n"
            if queue:
                await queue.put({"_writing": "\n\n"})

    return full_text, write_error


async def _delegate_writing_streaming(loop, args: dict, kb, book_id: str, msg: str, queue=None) -> str | dict:
    from core.knowledge_scope import ExposureLevel, WritingKnowledgeScope, scope_manager

    instruction = args.get("instruction", msg)
    guard = _guard_new_chapter_target(book_id, args, instruction)
    if guard:
        return guard
    mode = args.get("mode", "strict")
    target_words = int(args.get("target_words", 2500))
    scope = WritingKnowledgeScope(book_id=book_id, target_word_count=target_words)

    for s, method in [
        ("characters", scope.add_character),
        ("locations", scope.add_location),
        ("concepts", scope.add_concept),
    ]:
        for v in [x.strip() for x in args.get(s, "").split(",") if x.strip()]:
            method(v, ExposureLevel.FULL, "显式指定")

    for f in [x.strip() for x in args.get("forbidden", "").split(",") if x.strip()]:
        if f not in scope.forbidden_characters:
            scope.forbidden_characters.append(f)
    scope.writing_rules = args.get("writing_rules", "")

    outline = json_store.get_outline(book_id)
    chapters_list = outline.get("chapters", [])
    ch_num = _requested_regular_chapter_index(args, instruction)

    if ch_num and 1 <= ch_num <= len(chapters_list):
        ch = chapters_list[ch_num - 1]
        if ch.get("synopsis"):
            scope.chapter_outline = ch["synopsis"]
        for cname in ch.get("characters", []):
            scope.add_character(cname, ExposureLevel.FULL, "大纲标注")
        if ch.get("notes"):
            scope.writing_rules = (scope.writing_rules + "\n" + ch["notes"]).strip()

    if ch_num and ch_num > 1 and 0 <= ch_num - 2 < len(chapters_list):
        prev = chapters_list[ch_num - 2]
        if prev.get("synopsis"):
            scope.prev_chapter_summary = prev["synopsis"]

    # ── 番外大纲匹配 ──
    from tools.impl.generation import _match_extra_outline

    extra_match = _match_extra_outline(book_id, instruction, bool(args.get("is_extra", False)))
    if extra_match and extra_match["outline_entry"]:
        oe = extra_match["outline_entry"]
        if oe.get("synopsis"):
            scope.chapter_outline = oe["synopsis"]
        for cname in oe.get("characters", []):
            scope.add_character(cname, ExposureLevel.FULL, "番外大纲标注")
        if oe.get("notes"):
            scope.writing_rules = (scope.writing_rules + "\n" + oe["notes"]).strip()

    if not scope.characters and not scope.locations:
        _infer_scope_entities(kb, book_id, instruction, scope)

    scope_manager.set_scope(book_id, scope)

    if queue:
        tentative_title = args.get("chapter_title", "")
        if not tentative_title:
            chs = json_store.load_chapters(book_id)
            if bool(args.get("is_extra", False)):
                tentative_title = f"番外{sum(1 for c in chs if c.get('is_extra')) + 1}"
            else:
                tentative_title = f"第{sum(1 for c in chs if not c.get('is_extra')) + 1}章"
        await queue.put({"_writing_meta": {"chapter_title": tentative_title, "type": "start"}})
        await queue.put(
            {"_progress": f"构建知识范围: {len(scope.characters)}角色 {len(scope.locations)}地点 → 开始写作..."}
        )

    from core.context_manager import ContextBudget, ContextManager

    available = args.get("_available_tokens", 0)
    if available > 0:
        budget = ContextBudget(total_tokens=int(available / 0.3))
        cm = ContextManager(book_id, budget=budget)
    else:
        cm = ContextManager(book_id)

    # ── 伏笔调度检查：检查是否有待处理的伏笔 ──
    pending_fores = cm.get_pending_foreshadows(scope)
    if pending_fores and queue:
        due_count = sum(1 for f in pending_fores if f["status"] == "due")
        planned_count = len(pending_fores) - due_count
        fs_lines = ["\n⚠️ 伏笔调度提醒:"]
        if due_count > 0:
            fs_lines.append(f"  {due_count} 个伏笔已到达规划回收弧，等待确认。")
        if planned_count > 0:
            fs_lines.append(f"  {planned_count} 个伏笔已规划回收弧，尚未到期。")
        fs_lines.append("  使用 schedule_foreshadow 工具确认在本章回收，或 postpone_foreshadow 推迟。")
        for f in pending_fores[:5]:
            arc_info = f" [弧: {f['planned_resolve_arc']}]" if f.get("planned_resolve_arc") else ""
            status_label = "🔴 到期" if f["status"] == "due" else "🟡 已规划"
            fs_lines.append(f"  {status_label} {f['text'][:40]}{arc_info}")
        await queue.put({"_progress": "\n".join(fs_lines)})

    scoped_context = cm.build_scoped_context(scope)

    ext_inst = instruction
    if scope.chapter_outline:
        ext_inst += f"\n\n本章大纲: {scope.chapter_outline}"

    # ── 读取细纲，提取 plot_chain 用于逐节点写作 ──
    plot_chain = None
    chapter_function = ""

    if ch_num:
        detailed = json_store.get_detailed_outline(book_id).get("chapters", [])
        if ch_num - 1 < len(detailed) and detailed[ch_num - 1]:
            ch_detail = detailed[ch_num - 1]
            if ch_detail.get("plot_chain"):
                plot_chain = ch_detail["plot_chain"]
                ext_inst += "\n\n本章细纲（剧情事件链）:\n" + "\n".join(f"  • {ev}" for ev in ch_detail["plot_chain"])
            if ch_detail.get("chapter_function"):
                chapter_function = ch_detail["chapter_function"]
                ext_inst += f"\n本章叙事功能: {ch_detail['chapter_function']}"

    # 番外细纲注入
    if extra_match and extra_match["detail_entry"]:
        de = extra_match["detail_entry"]
        if de.get("plot_chain"):
            plot_chain = de["plot_chain"]
            ext_inst += "\n\n本章细纲（剧情事件链）:\n" + "\n".join(f"  • {ev}" for ev in de["plot_chain"])
        if de.get("chapter_function"):
            chapter_function = de["chapter_function"]
            ext_inst += f"\n本章叙事功能: {de['chapter_function']}"

    if scope.writing_rules:
        ext_inst += f"\n\n写作规则: {scope.writing_rules}"

    from core.plot_norms import build_plot_norms_prompt

    plot_norms_prompt = build_plot_norms_prompt(book_id)
    if plot_norms_prompt:
        ext_inst += f"\n\n{plot_norms_prompt}"

    # ── 长章剧情预算：先分段，再写正文 ──
    # A token/character cap alone makes models compress the whole chapter into
    # the first response.  Long tasks are converted to semantic contracts so
    # each model call may consume only one slice of the plot.
    max_segment_words = max(500, int(args.get("max_segment_words", 2000) or 2000))
    explicit_boundary_setting = args.get("enforce_segment_boundaries")
    enforce_segment_boundaries = (
        bool(explicit_boundary_setting)
        if explicit_boundary_setting is not None
        else target_words > max_segment_words
    )
    explicit_segment_plan = args.get("segment_plan")
    if isinstance(explicit_segment_plan, list) and explicit_segment_plan:
        plot_chain = explicit_segment_plan

    required_segments = max(1, (target_words + max_segment_words - 1) // max_segment_words)
    if enforce_segment_boundaries and target_words > max_segment_words and (
        not plot_chain or len(plot_chain) < required_segments
    ):
        from core.narrative_budget import plan_segment_contracts

        source_beats = plot_chain or [scope.chapter_outline or instruction]
        if queue:
            await queue.put(
                {
                    "_progress": (
                        f"正在分配剧情预算: 目标 {target_words} 字，"
                        f"拆为 {required_segments} 段，单段不超过 {max_segment_words} 字..."
                    )
                }
            )
        plot_chain = await plan_segment_contracts(
            loop,
            source_beats=source_beats,
            instruction=ext_inst,
            target_chars=target_words,
            max_segment_chars=max_segment_words,
        )

    # ── 注入前3章连续性卡片 ──
    if ch_num and ch_num > 1:
        cards = json_store.get_recent_continuity_cards(book_id, ch_num, count=3)
        if cards:
            from core.continuity import format_continuity_cards

            continuity_text = format_continuity_cards(cards)
            ext_inst += f"\n\n## ⚠️ 前情连续性（请严格保持时间线和状态一致）\n{continuity_text}"

    # Build reference book context if specified
    ref_context = ""
    ref_chapters = args.get("ref_chapters", [])
    if ref_chapters or json_store.get_reference_books(book_id):
        from core.writer import _build_reference_context

        ref_context = _build_reference_context(book_id, ref_chapters if ref_chapters else None)

    ref_prefix = "---\n\n以下是按用途隔离后的参考证据；严格遵守每本书标注的用途：\n\n"
    ref_block = (ref_prefix + ref_context) if ref_context else ""
    prompt = f"""以下是本章可用的知识库设定：

{scoped_context}

{ref_block}

---

写作任务：
{ext_inst}

请直接输出小说正文，不要加解释前缀。"""

    from core.writer import WRITER_STRICT_SYSTEM, WRITER_SUGGEST_SYSTEM

    system = WRITER_STRICT_SYSTEM if mode == "strict" else WRITER_SUGGEST_SYSTEM
    from core.creative_constitution import build_constitution_system_section

    constitution_section = build_constitution_system_section(book_id)
    if constitution_section:
        system = f"{system}\n\n{constitution_section}"
    from core.plugin_loader import plugin_manager

    system = plugin_manager.call_hook_chain("modify_system_prompt", system, context="writing")

    # ── 逐节点写作分支：有细纲 plot_chain (≥2 事件) 时自动启用 ──
    if plot_chain and len(plot_chain) >= 2:
        requested_per_node = args.get("target_words_per_node")
        target_words_per_node = (
            int(requested_per_node)
            if requested_per_node
            else max(350, min(max_segment_words, (target_words + len(plot_chain) - 1) // len(plot_chain)))
        )
        if queue:
            await queue.put(
                {
                    "_progress": (
                        f"分段合同写作: {len(plot_chain)} 段，每段约 {target_words_per_node} 字"
                        + (f"，剧情边界硬上限 {max_segment_words} 字" if enforce_segment_boundaries else "")
                    )
                }
            )

        full_text, write_error = await _write_by_nodes(
            loop,
            scoped_context,
            ref_block,
            plot_chain,
            chapter_function,
            scope.writing_rules,
            system,
            book_id,
            queue,
            target_words_per_node,
            forbidden_characters=scope.forbidden_characters,
            target_words=target_words,
            max_segment_words=max_segment_words if enforce_segment_boundaries else target_words_per_node + 150,
            enforce_segment_boundaries=enforce_segment_boundaries,
        )

        refusal = _guard_generated_prose(full_text)
        if refusal:
            return refusal

        if write_error:
            if full_text:
                title = args.get("chapter_title", "")
                if not title:
                    title = (
                        f"第{sum(1 for c in json_store.load_chapters(book_id) if not c.get('is_extra')) + 1}章(部分)"
                    )
                chapter = json_store.add_chapter(
                    book_id, title, full_text, origin="ai_partial", protected=True
                )
                scope_report = _build_scope_report(scope)
                graph_insight = _build_graph_insight_report(kb, scope)
                if graph_insight:
                    scope_report += "\n\n" + graph_insight
                result_text = _format_chapter_result(
                    book_id,
                    chapter["id"],
                    title,
                    full_text,
                    f"逐节点写作中断: {write_error}",
                    scope_report=scope_report,
                )
                return {
                    "type": "writing_result",
                    "text": result_text,
                    "chapter_id": chapter["id"],
                    "chapter_title": title,
                    "word_count": len(full_text),
                    "saved": True,
                    "partial": True,
                }
            return {"type": "writing_result", "text": f"写作中断: {write_error}", "saved": False}

        if not full_text or len(full_text.strip()) < 50:
            return {
                "type": "writing_result",
                "text": f"写作未生成有效内容（{len(full_text)}字）。请检查指令或换用不同提示词重试。",
                "saved": False,
            }

        if queue:
            await queue.put({"_progress": f"写作完成 ({len(full_text)}字)，正在验证..."})

        # ── 先验证后保存为草稿；hard 约束由 finalize_chapter 阻断定稿 ──
        title = args.get("chapter_title", "")
        is_extra = bool(args.get("is_extra", False))
        if not title:
            all_chapters = json_store.load_chapters(book_id)
            if is_extra:
                title = f"番外{sum(1 for c in all_chapters if c.get('is_extra')) + 1}"
            else:
                title = f"第{sum(1 for c in all_chapters if not c.get('is_extra')) + 1}章"

        scope_report = _build_scope_report(scope)
        graph_insight = _build_graph_insight_report(kb, scope)
        if graph_insight:
            scope_report += "\n\n" + graph_insight

        from tools.impl.narrative_logic import _verify_chapter

        verify_result = await _verify_chapter(
            loop,
            {
                "text": full_text,
                "title": title,
                "chapter_num": ch_num,
                "scope_entities": ",".join(e.entity_name for e in scope.characters),
            },
            kb,
            book_id,
            msg,
        )

        # Advisory findings remain visible while the editable draft is saved.
        chapter = json_store.add_chapter(
            book_id, title, full_text, is_extra=is_extra, origin="ai_draft", protected=True
        )
        extra_info = ""
        if verify_result:
            extra_info = verify_result
        result_text = _format_chapter_result(
            book_id, chapter["id"], title, full_text, extra_info, scope_report=scope_report
        )
        return {
            "type": "writing_result",
            "text": result_text,
            "chapter_id": chapter["id"],
            "chapter_title": title,
            "word_count": len(full_text),
            "saved": True,
        }

    # ── 一次性写作路径（无细纲或 plot_chain < 2 时回退） ──

    chunk_queue: asyncio.Queue = asyncio.Queue()
    chunks = []
    write_error = None
    write_blocked = False

    def _run():
        nonlocal write_error, write_blocked
        from core.llm_client import chat_stream as cs
        from core.llm_client import normalize_content_text

        try:
            for chunk in cs(prompt, system=system, temperature=0.7, task="writing"):
                text = normalize_content_text(chunk)
                if not text:
                    continue
                chunks.append(text)
                loop.call_soon_threadsafe(chunk_queue.put_nowait, text)
        except Exception as e:
            logger.exception("write_chapter_streaming failed")
            err_str = str(e).lower()
            if any(k in err_str for k in ("content_filter", "content filter", "sensitive", "policy", "moderation")):
                write_blocked = True
                write_error = f"内容审查拦截（位置: {len(''.join(chunks))}字后）"
            else:
                write_error = str(e)[:100]
        finally:
            loop.call_soon_threadsafe(chunk_queue.put_nowait, None)

    loop.run_in_executor(_ai_executor, copy_context().run, _run)

    while True:
        chunk = await chunk_queue.get()
        if chunk is None:
            break
        if queue:
            await queue.put({"_writing": chunk})

    full_text = "".join(chunks)
    refusal = _guard_generated_prose(full_text)
    if refusal:
        return refusal
    if write_error:
        if len(full_text.strip()) >= 200:
            title = args.get("chapter_title", "")
            if not title:
                all_chapters = json_store.load_chapters(book_id)
                title = f"第{sum(1 for c in all_chapters if not c.get('is_extra')) + 1}章(部分)"
            chapter = json_store.add_chapter(
                book_id,
                title,
                full_text,
                is_extra=bool(args.get("is_extra", False)),
                origin="ai_partial",
                protected=True,
            )
            return {
                "type": "writing_result",
                "text": (
                    f"⚠️ 写作中断但已保全 {len(full_text)} 字：{write_error}。"
                    "请从截断处继续，不要重新生成整章。"
                ),
                "chapter_id": chapter["id"],
                "chapter_title": title,
                "word_count": len(full_text),
                "saved": True,
                "partial": True,
            }
        return {"type": "writing_result", "text": f"写作中断: {write_error}", "saved": False}

    if not full_text or len(full_text.strip()) < 50:
        return {
            "type": "writing_result",
            "text": f"写作未生成有效内容（{len(full_text)}字）。请检查指令或换用不同提示词重试。",
            "saved": False,
        }

    title = args.get("chapter_title", "")
    is_extra = bool(args.get("is_extra", False))
    if not title:
        all_chapters = json_store.load_chapters(book_id)
        if is_extra:
            title = f"番外{sum(1 for c in all_chapters if c.get('is_extra')) + 1}"
        else:
            title = f"第{sum(1 for c in all_chapters if not c.get('is_extra')) + 1}章"

    scope_report = _build_scope_report(scope)
    graph_insight = _build_graph_insight_report(kb, scope)
    if graph_insight:
        scope_report += "\n\n" + graph_insight
    from tools.impl.narrative_logic import _verify_chapter

    verify_result = await _verify_chapter(
        loop,
        {
            "text": full_text,
            "title": title,
            "chapter_num": ch_num,
            "scope_entities": ",".join(e.entity_name for e in scope.characters),
        },
        kb,
        book_id,
        msg,
    )
    # Save as draft; finalize_chapter is the authoritative final-state gate.
    chapter = json_store.add_chapter(
        book_id, title, full_text, is_extra=is_extra, origin="ai_draft", protected=True
    )
    extra_info = ""
    if verify_result:
        extra_info = verify_result
    result_text = _format_chapter_result(
        book_id, chapter["id"], title, full_text, extra_info, scope_report=scope_report
    )
    return {
        "type": "writing_result",
        "text": result_text,
        "chapter_id": chapter["id"],
        "chapter_title": title,
        "word_count": len(full_text),
        "saved": True,
    }


async def _rewrite_by_chain_streaming(loop, args: dict, kb, book_id: str, msg: str = "", queue=None) -> str | dict:
    """Rewrite chapter by plot chain, node by node with streaming output."""
    # Late import to avoid circular dependency with executor.py
    from tools.executor import _split_paragraphs, apply_edit_ops

    # Get plot chain
    chain_id = args.get("chain_id", "")
    try:
        if chain_id:
            chain = json_store.get_plot_chain(book_id, chain_id)
        else:
            chain = json_store.get_latest_plot_chain(book_id)
            if not chain:
                return "❌ 没有可用的剧情链。请先使用 decompose_chapter 拆解章节。"
    except Exception as e:
        logger.exception("get plot chain failed")
        return f"❌ 无法获取剧情链: {str(e)[:100]}"

    nodes = chain.get("nodes", [])
    if not nodes:
        return "❌ 剧情链为空，没有场景节点"

    style_profile = args.get("style_profile", "")
    target_words = int(args.get("target_words_per_node", 300))
    chapter_title = args.get("chapter_title", chain.get("chapter_title", "复写章节"))

    # Get knowledge summary
    summary = kb.get_knowledge_summary()[: config.storage.max_knowledge_summary_chars]

    if queue:
        await queue.put({"_writing_meta": {"chapter_title": chapter_title, "type": "start", "node_count": len(nodes)}})
        await queue.put({"_progress": f"开始按链复写: {len(nodes)} 个场景节点"})

    from core.llm_client import chat_stream

    full_text = ""
    chunk_queue: asyncio.Queue = asyncio.Queue()
    write_error = None

    for i, node in enumerate(nodes):
        if write_error:
            break

        scene_name = node.get("scene_name", f"场景{i + 1}")
        if queue:
            await queue.put({"_progress": f"场景 {i + 1}/{len(nodes)}: {scene_name}"})

        # Get edit_mode for this node
        edit_mode = node.get("edit_mode", "rewrite")
        edit_instructions = node.get("edit_instructions", "")
        source_text = node.get("source_text", "")
        source_limit = config.storage.max_source_text_chars
        source_ref = f"\n原文参考:\n{source_text[:source_limit]}" if source_text else ""

        # KEEP mode: output source_text directly, no LLM call
        if edit_mode == "keep" and source_text:
            node_text = source_text
            if queue:
                await queue.put({"_progress": f"场景 {i + 1}/{len(nodes)}: {scene_name} [原样保留]"})
                await queue.put({"_writing": node_text})
            full_text += node_text
            if i < len(nodes) - 1:
                sep = "\n\n"
                full_text += sep
                if queue:
                    await queue.put({"_writing": sep})
            continue

        # Build prompt for this node
        prev_context = full_text[-500:] if full_text else "（开篇）"
        characters = ", ".join(node.get("characters", []))
        plot_beats = "\n".join(f"- {b}" for b in node.get("plot_beats", []))
        dialogues = "\n".join(f"- {d}" for d in node.get("dialogues", []))
        emotional_arc = node.get("emotional_arc", "")
        transition = node.get("transition_to_next", "")

        # Different prompt strategies based on edit_mode
        use_rewrite_fallback = False
        if edit_mode == "tweak" and source_text:
            # TWEAK mode: diff-patch — LLM outputs edit operations, not full text
            segments = _split_paragraphs(source_text[:source_limit])
            numbered = "\n".join(f"[段落{i}] {seg}" for i, seg in enumerate(segments))

            tweak_system = """你是文本精准编辑专家。你的任务是根据修改指令，输出精确的编辑操作。

规则:
1. **只输出JSON数组**，不要输出任何其他文字、解释或代码块标记
2. find/confirm 字段必须从原文中精确复制，一字不差
3. 每个操作只修改一处
4. 不修改的部分不要出现在输出中

可用操作:
- {"op": "replace", "segment": 段落编号, "confirm": "原文片段", "to": "替换后文本"}
- {"op": "delete", "segment": 段落编号, "confirm": "要删除的原文片段"}
- {"op": "insert_after", "segment": 段落编号, "text": "要插入的文本"}
- {"op": "insert_before", "segment": 段落编号, "text": "要插入的文本"}"""

            tweak_prompt = f"""原文（已分段编号）:
{numbered}

【修改指令】
{edit_instructions or "无修改要求，保持原文不变"}

请输出编辑操作JSON数组（只输出JSON，不要其他文字）："""

            if queue:
                await queue.put({"_progress": f"场景 {i + 1}/{len(nodes)}: {scene_name} [微调模式 - 生成编辑指令]"})

            # Generate edit ops via LLM (non-streaming, JSON output)
            try:
                raw_ops = await loop.run_in_executor(
                    _ai_executor,
                    copy_context().run,
                    llm_chat,
                    tweak_prompt,
                    tweak_system,
                    0.1,
                    "extraction",
                )

                # Parse JSON from response
                ops = None
                json_match = re.search(r"\[.*\]", raw_ops, re.DOTALL)
                if json_match:
                    try:
                        ops = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        pass

                if ops and isinstance(ops, list):
                    # Apply edit operations programmatically
                    node_text, edit_report = apply_edit_ops(source_text[:source_limit], ops)

                    # Report progress
                    ok_count = sum(1 for r in edit_report if r.get("status") == "ok")
                    fail_count = sum(1 for r in edit_report if r.get("status") == "failed")
                    if queue:
                        await queue.put(
                            {
                                "_progress": f"场景 {i + 1}/{len(nodes)}: {scene_name} [微调完成: {ok_count}处修改{', ' + str(fail_count) + '处失败' if fail_count else ''}]"
                            }
                        )
                        await queue.put({"_writing": node_text})

                    full_text += node_text
                    if i < len(nodes) - 1:
                        sep = "\n\n"
                        full_text += sep
                        if queue:
                            await queue.put({"_writing": sep})
                    continue
                else:
                    # JSON parse failed, fall through to rewrite
                    if queue:
                        await queue.put(
                            {"_progress": f"场景 {i + 1}/{len(nodes)}: {scene_name} [微调指令解析失败，降级为改写模式]"}
                        )
                    use_rewrite_fallback = True
            except Exception as e:
                logger.exception("write_chapter_streaming failed")
                if queue:
                    await queue.put(
                        {
                            "_progress": f"场景 {i + 1}/{len(nodes)}: {scene_name} [微调异常: {str(e)[:50]}，降级为改写模式]"
                        }
                    )
                use_rewrite_fallback = True

        if edit_mode == "rewrite" or use_rewrite_fallback or (edit_mode == "tweak" and not source_text):
            # REWRITE mode: significant changes, keep structure
            system = f"""你是小说场景写作专家。请严格按照以下场景节点的要求，写出一段小说正文。

规则:
1. 只写本场景的内容，不要涉及后续场景
2. 必须覆盖所有情节节拍，不遗漏
3. 关键对话必须以自然的方式呈现
4. 知识库中的角色设定必须严格遵守
5. 注意与前文的衔接
6. 直接输出正文，不加说明前缀
7. 原文参考提供了原始素材，改写时应保留其核心信息和氛围
{edit_instructions and f"8. 修改指令: {edit_instructions}" or ""}
{style_profile and f"9. 文风约束: {style_profile[:1000]}" or ""}"""
            from core.creative_constitution import build_constitution_system_section

            constitution_section = build_constitution_system_section(book_id)
            if constitution_section:
                system = f"{system}\n\n{constitution_section}"

            prompt = f"""知识库:
{summary if summary else "（无）"}

前文摘要:
{prev_context}

---
当前场景节点:
场景名: {scene_name}
地点: {node.get("location", "?")}
出场人物: {characters}
情节节拍:
{plot_beats}
关键对话:
{dialogues if dialogues else "（无）"}
关键事件: {node.get("key_event", "")}
情感弧线: {emotional_arc}
{i < len(nodes) - 1 and f"过渡到下一场景: {transition}" or ""}
{source_ref}

请写本场景（约{target_words}字）："""

        # Stream generate for this node
        node_chunks = []

        def _run():
            nonlocal write_error
            try:
                for chunk in chat_stream(prompt, system=system, temperature=0.7, task="writing"):
                    from core.llm_client import normalize_content_text

                    text = normalize_content_text(chunk)
                    if not text:
                        continue
                    node_chunks.append(text)
                    loop.call_soon_threadsafe(chunk_queue.put_nowait, text)
            except Exception as e:
                logger.exception("write_chapter_streaming failed")
                err_str = str(e).lower()
                if any(k in err_str for k in ("content_filter", "content filter", "sensitive", "policy", "moderation")):
                    write_error = f"内容审查拦截（场景{i + 1}: {scene_name}）"
                else:
                    write_error = f"LLM错误（场景{i + 1}）: {str(e)[:80]}"
            finally:
                loop.call_soon_threadsafe(chunk_queue.put_nowait, None)

        loop.run_in_executor(_ai_executor, copy_context().run, _run)

        while True:
            chunk = await chunk_queue.get()
            if chunk is None:
                break
            if queue:
                await queue.put({"_writing": chunk})
            full_text += chunk

        # Add separator between nodes
        if i < len(nodes) - 1 and not write_error:
            sep = "\n\n"
            full_text += sep
            if queue:
                await queue.put({"_writing": sep})

    refusal = _guard_generated_prose(full_text)
    if refusal:
        return refusal

    if write_error:
        # Store partial result if we have content
        if full_text:
            title = f"{chapter_title}(部分)"
            chapter = json_store.add_chapter(
                book_id, title, full_text, origin="ai_partial", protected=True
            )
            return {
                "type": "writing_result",
                "text": _format_chapter_result(book_id, chapter["id"], title, full_text, f"中断: {write_error}"),
                "chapter_id": chapter["id"],
                "chapter_title": title,
                "word_count": len(full_text),
                "saved": True,
                "partial": True,
            }
        return {"type": "writing_result", "text": f"写作中断: {write_error}", "saved": False}

    if not full_text:
        return {"type": "writing_result", "text": "写作未生成内容。", "saved": False}

    chapter = json_store.add_chapter(
        book_id, chapter_title, full_text, origin="ai_draft", protected=True
    )
    return {
        "type": "writing_result",
        "text": _format_chapter_result(book_id, chapter["id"], chapter_title, full_text, f"剧情链: {len(nodes)}节点"),
        "chapter_id": chapter["id"],
        "chapter_title": chapter_title,
        "word_count": len(full_text),
        "saved": True,
    }


def _store_chapter(args: dict, book_id: str, msg: str) -> str | dict:
    title = args.get("title", "章节")
    content = args.get("content", msg)
    is_extra = bool(args.get("is_extra", False))
    chapter_index = args.get("chapter_index", None)
    guard = _guard_new_chapter_target(book_id, args, content)
    if guard:
        return guard
    chapter = json_store.add_chapter(
        book_id,
        title,
        content,
        is_extra=is_extra,
        origin="user_supplied",
        protected=True,
    )
    # 存储chapter_index用于后续追踪
    if chapter_index is not None:
        chapters = json_store.load_chapters(book_id)
        for ch in chapters:
            if ch["id"] == chapter["id"]:
                if not ch.get("index"):
                    ch["index"] = int(chapter_index)
                if not ch.get("chapter_index"):
                    ch["chapter_index"] = int(chapter_index)
                json_store.save_chapters(book_id, chapters)
                break
    return _format_chapter_result(book_id, chapter["id"], title, content)


async def _delegate_writing(loop, args: dict, kb, book_id: str, session_id: str, msg: str) -> str | dict:
    from core.context_manager import ContextManager
    from core.knowledge_scope import ExposureLevel, WritingKnowledgeScope, scope_manager

    instruction = args.get("instruction", msg)
    guard = _guard_new_chapter_target(book_id, args, instruction)
    if guard:
        return guard
    mode = args.get("mode", "strict")
    target_words = int(args.get("target_words", 2500))
    ch_num = _requested_regular_chapter_index(args, instruction)

    scope = WritingKnowledgeScope(book_id=book_id, target_word_count=target_words)

    # ── 解析参数，构建作用域 ──
    chars_str = args.get("characters", "")
    locs_str = args.get("locations", "")
    concepts_str = args.get("concepts", "")
    forbidden_str = args.get("forbidden", "")
    writing_rules = args.get("writing_rules", "")

    for c in [x.strip() for x in chars_str.split(",") if x.strip()]:
        scope.add_character(c, ExposureLevel.FULL, "显式指定")
    for loc in [x.strip() for x in locs_str.split(",") if x.strip()]:
        scope.add_location(loc, ExposureLevel.FULL, "显式指定")
    for c in [x.strip() for x in concepts_str.split(",") if x.strip()]:
        scope.add_concept(c, ExposureLevel.FULL, "显式指定")
    for f in [x.strip() for x in forbidden_str.split(",") if x.strip()]:
        if f not in scope.forbidden_characters:
            scope.forbidden_characters.append(f)
    scope.writing_rules = writing_rules

    # ── 如果 Agent 没有显式列出角色，自动从知识库 + 大纲推断 ──
    if not scope.characters and not scope.locations:
        outline = json_store.get_outline(book_id)
        chapters = outline.get("chapters", [])
        # 尝试匹配当前章节
        args.get("chapter_title", "")
        if ch_num and 1 <= ch_num <= len(chapters):
            ch_outline = chapters[ch_num - 1]
            if ch_outline.get("synopsis"):
                scope.chapter_outline = ch_outline["synopsis"]
            if ch_outline.get("characters"):
                for cname in ch_outline["characters"]:
                    scope.add_character(cname, ExposureLevel.FULL, "大纲标注")
            if ch_outline.get("notes"):
                scope.writing_rules = (scope.writing_rules + "\n" + ch_outline["notes"]).strip()

    # ── 前情提要 ──
    if ch_num and ch_num > 1 and 0 <= ch_num - 2 < len(chapters):
        prev = chapters[ch_num - 2]
        if prev.get("synopsis"):
            scope.prev_chapter_summary = prev["synopsis"]

    # ── 如果范围仍为空，使用语义匹配推断 ──
    if not scope.characters and not scope.locations:
        _infer_scope_entities(kb, book_id, instruction, scope)

    # ── 保存作用域 ──
    scope_manager.set_scope(book_id, scope)

    # ── 构建精选上下文并写作 ──
    cm = ContextManager(book_id)
    scoped_context = cm.build_scoped_context(scope)
    extended_instruction = instruction
    if scope.chapter_outline:
        extended_instruction += f"\n\n本章大纲: {scope.chapter_outline}"
    if scope.writing_rules:
        extended_instruction += f"\n\n写作规则: {scope.writing_rules}"

    from core.plot_norms import build_plot_norms_prompt

    plot_norms_prompt = build_plot_norms_prompt(book_id)
    if plot_norms_prompt:
        extended_instruction += f"\n\n{plot_norms_prompt}"

    # ── 注入前3章连续性卡片 ──
    if ch_num and ch_num > 1:
        cards = json_store.get_recent_continuity_cards(book_id, ch_num, count=3)
        if cards:
            from core.continuity import format_continuity_cards

            continuity_text = format_continuity_cards(cards)
            extended_instruction += f"\n\n## ⚠️ 前情连续性（请严格保持时间线和状态一致）\n{continuity_text}"

    # Build reference book context if specified
    ref_context = ""
    ref_chapters = args.get("ref_chapters", [])
    if ref_chapters or json_store.get_reference_books(book_id):
        from core.writer import _build_reference_context

        ref_context = _build_reference_context(book_id, ref_chapters if ref_chapters else None)

    ref_prefix2 = "---\n\n以下是按用途隔离后的参考证据；严格遵守每本书标注的用途：\n\n"
    ref_block2 = (ref_prefix2 + ref_context) if ref_context else ""
    prompt = f"""以下是本章可用的知识库设定：

{scoped_context}

{ref_block2}

---

写作任务：
{extended_instruction}

请直接输出小说正文，不要加解释前缀。"""

    # Use writer's system prompt
    from core.writer import WRITER_STRICT_SYSTEM, WRITER_SUGGEST_SYSTEM

    system = WRITER_STRICT_SYSTEM if mode == "strict" else WRITER_SUGGEST_SYSTEM
    from core.creative_constitution import build_constitution_system_section

    constitution_section = build_constitution_system_section(book_id)
    if constitution_section:
        system = f"{system}\n\n{constitution_section}"
    from core.plugin_loader import plugin_manager

    system = plugin_manager.call_hook_chain("modify_system_prompt", system, context="writing")

    result = await loop.run_in_executor(
        _ai_executor,
        copy_context().run,
        llm_chat,
        prompt,
        system,
        0.7,
        "writing",
    )

    refusal = _guard_generated_prose(result)
    if refusal:
        return refusal

    title = args.get("chapter_title", "")
    is_extra = bool(args.get("is_extra", False))
    if not title:
        chapters = json_store.load_chapters(book_id)
        if is_extra:
            title = f"番外{sum(1 for c in chapters if c.get('is_extra')) + 1}"
        else:
            title = f"第{sum(1 for c in chapters if not c.get('is_extra')) + 1}章"

    from tools.impl.narrative_logic import _verify_chapter

    verify_result = await _verify_chapter(
        loop,
        {
            "text": result,
            "title": title,
            "chapter_num": ch_num,
            "scope_entities": ",".join(e.entity_name for e in scope.characters),
        },
        kb,
        book_id,
        msg,
    )
    # Save as draft; finalize_chapter is the authoritative final-state gate.
    chapter = json_store.add_chapter(
        book_id, title, result, is_extra=is_extra, origin="ai_draft", protected=True
    )
    scope_report = _build_scope_report(scope)
    graph_insight = _build_graph_insight_report(kb, scope)
    if graph_insight:
        scope_report += "\n\n" + graph_insight
    extra_info = ""
    if verify_result:
        extra_info = verify_result
    return _format_chapter_result(book_id, chapter["id"], title, result, extra_info, scope_report=scope_report)
