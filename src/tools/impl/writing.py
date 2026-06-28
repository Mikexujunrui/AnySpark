"""Writing tool implementations — chapter write, delegate writing, rewrite by chain.

Extracted from executor.py to keep module sizes manageable.
"""

import asyncio
import json
import logging
import re

from core.config import config
from core.llm_client import chat as llm_chat
from core.thread_pools import llm_pool as _ai_executor
from data.json_store import json_store

logger = logging.getLogger(__name__)


def _format_chapter_result(book_id: str, chapter_id: str, title: str,
                            content: str, extra: str = "") -> str:
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
    if preview:
        result += f"\n内容预览: {preview}"
    if extra:
        result += f"\n{extra}"
    return result


async def _write_chapter(loop, args: dict, book_id: str, msg: str) -> str:
    from core.writer import write as wr
    ref_chapters = args.get("ref_chapters", []) or None
    result = await loop.run_in_executor(
        _ai_executor,
        lambda: wr(
            args.get("instruction", msg),
            mode=args.get("mode", "strict"),
            project_id=book_id,
            ref_chapters=ref_chapters,
        )
    )
    title = args.get("chapter_title", args.get("title", ""))
    is_extra = bool(args.get("is_extra", False))
    chapter_index = args.get("chapter_index", None)
    if not title:
        chapters = json_store.load_chapters(book_id)
        if is_extra:
            title = f"番外{sum(1 for c in chapters if c.get('is_extra')) + 1}"
        else:
            title = f"第{sum(1 for c in chapters if not c.get('is_extra')) + 1}章"
    # 去重: 如果已有相同chapter_index的章节,更新而非新建
    if chapter_index is not None:
        chapters = json_store.load_chapters(book_id)
        for ch in chapters:
            existing_idx = ch.get("index", ch.get("chapter_index"))
            if existing_idx is not None and int(existing_idx) == int(chapter_index):
                # 更新已有章节
                from data.json_store import json_store as js
                js.edit_chapter(book_id, ch["id"], result, title=title, message=f"autopilot重写第{chapter_index}章")
                return _format_chapter_result(book_id, ch['id'], title, result)
    chapter = json_store.add_chapter(book_id, title, result, is_extra=is_extra)
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
    return _format_chapter_result(book_id, chapter['id'], title, result)


async def _write_chapter_streaming(
        loop, args: dict, kb, book_id: str, msg: str, queue=None) -> str:
    from core.writer import write_stream as write_stream_fn

    instruction = args.get("instruction", msg)
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
                    instruction, mode=mode, project_id=book_id,
                    ref_chapters=ref_chapters if ref_chapters else None):
                chunks.append(chunk)
                chunk_queue.put_nowait(chunk)
        except Exception as e:
            logger.exception("write_chapter_streaming failed")
            err_str = str(e).lower()
            if any(k in err_str for k in ("content_filter", "content filter",
                                            "sensitive", "policy", "moderation")):
                write_blocked = True
                write_error = f"内容审查拦截（位置: {len(''.join(chunks))}字后）"
            else:
                write_error = str(e)[:100]
        finally:
            chunk_queue.put_nowait(None)

    loop.run_in_executor(_ai_executor, _run)

    while True:
        chunk = await chunk_queue.get()
        if chunk is None:
            break
        if queue:
            await queue.put({"_writing": chunk})

    full_text = "".join(chunks)

    if write_blocked and full_text and len(full_text) > 200:
        title = args.get("chapter_title", args.get("title", ""))
        if not title:
            chapters = json_store.load_chapters(book_id)
            title = f"第{len(chapters) + 1}章"
        chapter = json_store.add_chapter(book_id, title, full_text)
        return {"type": "writing_result", "text": f"⚠️ 内容审查截断: 写入前 {len(full_text)} 字。请在截断处之后重新续写。(id: {chapter['id'][:8]})",
                "chapter_id": chapter['id'], "chapter_title": title, "word_count": len(full_text), "saved": True, "partial": True}

    if write_error:
        return {"type": "writing_result", "text": f"写作中断: {write_error}", "saved": False}

    if not full_text or len(full_text.strip()) < 50:
        return {"type": "writing_result",
                "text": f"写作未生成有效内容（{len(full_text)}字）。请检查指令或换用不同提示词重试。", "saved": False}

    title = args.get("chapter_title", args.get("title", ""))
    is_extra = bool(args.get("is_extra", False))
    chapter_index = args.get("chapter_index", None)
    if not title:
        chapters = json_store.load_chapters(book_id)
        if is_extra:
            title = f"番外{sum(1 for c in chapters if c.get('is_extra')) + 1}"
        else:
            title = f"第{sum(1 for c in chapters if not c.get('is_extra')) + 1}章"
    # 去重: 如果已有相同chapter_index的章节,更新而非新建
    if chapter_index is not None:
        chapters = json_store.load_chapters(book_id)
        for ch in chapters:
            existing_idx = ch.get("index", ch.get("chapter_index"))
            if existing_idx is not None and int(existing_idx) == int(chapter_index):
                from data.json_store import json_store as js
                js.edit_chapter(book_id, ch["id"], full_text, title=title, message=f"autopilot重写第{chapter_index}章")
                return {"type": "writing_result", "text": _format_chapter_result(book_id, ch['id'], title, full_text),
                        "chapter_id": ch['id'], "chapter_title": title, "word_count": len(full_text), "saved": True}
    chapter = json_store.add_chapter(book_id, title, full_text, is_extra=is_extra)
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
    return {"type": "writing_result", "text": _format_chapter_result(book_id, chapter['id'], title, full_text),
            "chapter_id": chapter['id'], "chapter_title": title, "word_count": len(full_text), "saved": True}


async def _delegate_writing_streaming(
        loop, args: dict, kb, book_id: str, msg: str, queue=None) -> str:
    from core.knowledge_scope import ExposureLevel, WritingKnowledgeScope, scope_manager

    instruction = args.get("instruction", msg)
    mode = args.get("mode", "strict")
    target_words = int(args.get("target_words", 2500))
    scope = WritingKnowledgeScope(
        book_id=book_id,
        target_word_count=target_words)

    for s, method in [("characters", scope.add_character), ("locations", scope.add_location),
                      ("concepts", scope.add_concept)]:
        for v in [x.strip() for x in args.get(s, "").split(",") if x.strip()]:
            method(v, ExposureLevel.FULL, "显式指定")

    for f in [x.strip() for x in args.get(
            "forbidden", "").split(",") if x.strip()]:
        if f not in scope.forbidden_characters:
            scope.forbidden_characters.append(f)
    scope.writing_rules = args.get("writing_rules", "")

    outline = json_store.get_outline(book_id)
    chapters_list = outline.get("chapters", [])
    ch_num = None
    import re
    m = re.search(r'第?\s*(\d+)', instruction)
    if m:
        ch_num = int(m.group(1))

    if ch_num and 1 <= ch_num <= len(chapters_list):
        ch = chapters_list[ch_num - 1]
        if ch.get("synopsis"):
            scope.chapter_outline = ch["synopsis"]
        for cname in ch.get("characters", []):
            scope.add_character(cname, ExposureLevel.FULL, "大纲标注")
        if ch.get("notes"):
            scope.writing_rules = (
                scope.writing_rules + "\n" + ch["notes"]).strip()

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
            scope.writing_rules = (
                scope.writing_rules + "\n" + oe["notes"]).strip()

    if not scope.characters and not scope.locations:
        entities = kb.list_entities()
        for e in entities[:12]:
            if e.type == "character":
                scope.add_character(e.name, ExposureLevel.SUMMARY, "自动纳入")

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
        await queue.put({"_progress": f"构建知识范围: {len(scope.characters)}角色 {len(scope.locations)}地点 → 开始写作..."})

    from core.context_manager import ContextBudget, ContextManager
    available = args.get("_available_tokens", 0)
    if available > 0:
        budget = ContextBudget(total_tokens=int(available / 0.3))
        cm = ContextManager(book_id, budget=budget)
    else:
        cm = ContextManager(book_id)
    scoped_context = cm.build_scoped_context(scope)

    ext_inst = instruction
    if scope.chapter_outline:
        ext_inst += f"\n\n本章大纲: {scope.chapter_outline}"

    if ch_num:
        detailed = json_store.get_detailed_outline(book_id).get("chapters", [])
        if ch_num - 1 < len(detailed) and detailed[ch_num - 1]:
            ch_detail = detailed[ch_num - 1]
            if ch_detail.get("plot_chain"):
                ext_inst += "\n\n本章细纲（剧情事件链）:\n" + "\n".join(f"  • {ev}" for ev in ch_detail["plot_chain"])
            if ch_detail.get("chapter_function"):
                ext_inst += f"\n本章叙事功能: {ch_detail['chapter_function']}"

    # 番外细纲注入
    if extra_match and extra_match["detail_entry"]:
        de = extra_match["detail_entry"]
        if de.get("plot_chain"):
            ext_inst += "\n\n本章细纲（剧情事件链）:\n" + "\n".join(f"  • {ev}" for ev in de["plot_chain"])
        if de.get("chapter_function"):
            ext_inst += f"\n本章叙事功能: {de['chapter_function']}"

    if scope.writing_rules:
        ext_inst += f"\n\n写作规则: {scope.writing_rules}"

    # Build reference book context if specified
    ref_context = ""
    ref_chapters = args.get("ref_chapters", [])
    if ref_chapters or json_store.get_reference_books(book_id):
        from core.writer import _build_reference_context
        ref_context = _build_reference_context(book_id, ref_chapters if ref_chapters else None)

    ref_prefix = '---\n\n以下是参考书（原著）的设定和章节，写作时请参考：\n\n'
    ref_block = (ref_prefix + ref_context) if ref_context else ''
    prompt = f"""以下是本章可用的知识库设定：

{scoped_context}

{ref_block}

---

写作任务：
{ext_inst}

请直接输出小说正文，不要加解释前缀。"""

    from core.writer import WRITER_STRICT_SYSTEM, WRITER_SUGGEST_SYSTEM
    system = WRITER_STRICT_SYSTEM if mode == "strict" else WRITER_SUGGEST_SYSTEM
    from core.plugin_loader import plugin_manager
    system = plugin_manager.call_hook_chain(
        "modify_system_prompt", system, context="writing")

    chunk_queue: asyncio.Queue = asyncio.Queue()
    chunks = []
    write_error = None
    write_blocked = False

    def _run():
        nonlocal write_error, write_blocked
        from core.llm_client import chat_stream as cs
        try:
            for chunk in cs(prompt, system=system,
                            temperature=0.7, task="writing"):
                chunks.append(chunk)
                chunk_queue.put_nowait(chunk)
        except Exception as e:
            logger.exception("write_chapter_streaming failed")
            err_str = str(e).lower()
            if any(k in err_str for k in ("content_filter", "content filter",
                                            "sensitive", "policy", "moderation")):
                write_blocked = True
                write_error = f"内容审查拦截（位置: {len(''.join(chunks))}字后）"
            else:
                write_error = str(e)[:100]
        finally:
            chunk_queue.put_nowait(None)

    loop.run_in_executor(_ai_executor, _run)

    while True:
        chunk = await chunk_queue.get()
        if chunk is None:
            break
        if queue:
            await queue.put({"_writing": chunk})

    if write_error:
        return {"type": "writing_result", "text": f"写作中断: {write_error}", "saved": False}

    full_text = "".join(chunks)
    if not full_text or len(full_text.strip()) < 50:
        return {"type": "writing_result",
                "text": f"写作未生成有效内容（{len(full_text)}字）。请检查指令或换用不同提示词重试。", "saved": False}

    title = args.get("chapter_title", "")
    is_extra = bool(args.get("is_extra", False))
    if not title:
        all_chapters = json_store.load_chapters(book_id)
        if is_extra:
            title = f"番外{sum(1 for c in all_chapters if c.get('is_extra')) + 1}"
        else:
            title = f"第{sum(1 for c in all_chapters if not c.get('is_extra')) + 1}章"
    chapter = json_store.add_chapter(book_id, title, full_text, is_extra=is_extra)

    scope_text = f"人物: {', '.join(e.entity_name for e in scope.characters)}"
    if scope.forbidden_characters:
        scope_text += f" | 禁止: {', '.join(scope.forbidden_characters)}"
    return {"type": "writing_result", "text": _format_chapter_result(book_id, chapter['id'], title, full_text, f"知识范围: {scope_text}"),
            "chapter_id": chapter['id'], "chapter_title": title, "word_count": len(full_text), "saved": True}


async def _rewrite_by_chain_streaming(
        loop, args: dict, kb, book_id: str, queue=None) -> str:
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
    summary = kb.get_knowledge_summary()[:config.storage.max_knowledge_summary_chars]

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

        scene_name = node.get("scene_name", f"场景{i+1}")
        if queue:
            await queue.put({"_progress": f"场景 {i+1}/{len(nodes)}: {scene_name}"})

        # Get edit_mode for this node
        edit_mode = node.get("edit_mode", "rewrite")
        edit_instructions = node.get("edit_instructions", "")
        source_text = node.get("source_text", "")
        source_limit = config.storage.max_source_text_chars
        source_ref = f'\n原文参考:\n{source_text[:source_limit]}' if source_text else ''

        # KEEP mode: output source_text directly, no LLM call
        if edit_mode == "keep" and source_text:
            node_text = source_text
            if queue:
                await queue.put({"_progress": f"场景 {i+1}/{len(nodes)}: {scene_name} [原样保留]"})
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
{edit_instructions or '无修改要求，保持原文不变'}

请输出编辑操作JSON数组（只输出JSON，不要其他文字）："""

            if queue:
                await queue.put({"_progress": f"场景 {i+1}/{len(nodes)}: {scene_name} [微调模式 - 生成编辑指令]"})

            # Generate edit ops via LLM (non-streaming, JSON output)
            try:
                raw_ops = await loop.run_in_executor(
                    _ai_executor, llm_chat,
                    tweak_prompt, tweak_system, 0.1, "extraction"
                )

                # Parse JSON from response
                ops = None
                json_match = re.search(r'\[.*\]', raw_ops, re.DOTALL)
                if json_match:
                    try:
                        ops = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        pass

                if ops and isinstance(ops, list):
                    # Apply edit operations programmatically
                    node_text, edit_report = apply_edit_ops(source_text[:source_limit], ops)

                    # Report progress
                    ok_count = sum(1 for r in edit_report if r.get('status') == 'ok')
                    fail_count = sum(1 for r in edit_report if r.get('status') == 'failed')
                    if queue:
                        await queue.put({"_progress": f"场景 {i+1}/{len(nodes)}: {scene_name} [微调完成: {ok_count}处修改{', ' + str(fail_count) + '处失败' if fail_count else ''}]"})
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
                        await queue.put({"_progress": f"场景 {i+1}/{len(nodes)}: {scene_name} [微调指令解析失败，降级为改写模式]"})
                    use_rewrite_fallback = True
            except Exception as e:
                logger.exception("write_chapter_streaming failed")
                if queue:
                    await queue.put({"_progress": f"场景 {i+1}/{len(nodes)}: {scene_name} [微调异常: {str(e)[:50]}，降级为改写模式]"})
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
{edit_instructions and f'8. 修改指令: {edit_instructions}' or ''}
{style_profile and f'9. 文风约束: {style_profile[:1000]}' or ''}"""

            prompt = f"""知识库:
{summary if summary else '（无）'}

前文摘要:
{prev_context}

---
当前场景节点:
场景名: {scene_name}
地点: {node.get('location', '?')}
出场人物: {characters}
情节节拍:
{plot_beats}
关键对话:
{dialogues if dialogues else '（无）'}
关键事件: {node.get('key_event', '')}
情感弧线: {emotional_arc}
{i < len(nodes) - 1 and f'过渡到下一场景: {transition}' or ''}
{source_ref}

请写本场景（约{target_words}字）："""

        # Stream generate for this node
        node_chunks = []

        def _run():
            nonlocal write_error
            try:
                for chunk in chat_stream(prompt, system=system,
                                         temperature=0.7, task="writing"):
                    node_chunks.append(chunk)
                    chunk_queue.put_nowait(chunk)
            except Exception as e:
                logger.exception("write_chapter_streaming failed")
                err_str = str(e).lower()
                if any(k in err_str for k in ("content_filter", "content filter",
                                              "sensitive", "policy", "moderation")):
                    write_error = f"内容审查拦截（场景{i+1}: {scene_name}）"
                else:
                    write_error = f"LLM错误（场景{i+1}）: {str(e)[:80]}"
            finally:
                chunk_queue.put_nowait(None)

        loop.run_in_executor(_ai_executor, _run)

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

    if write_error:
        # Store partial result if we have content
        if full_text:
            title = f"{chapter_title}(部分)"
            chapter = json_store.add_chapter(book_id, title, full_text)
            return {"type": "writing_result", "text": _format_chapter_result(book_id, chapter['id'], title, full_text, f"中断: {write_error}"),
                    "chapter_id": chapter['id'], "chapter_title": title, "word_count": len(full_text), "saved": True, "partial": True}
        return {"type": "writing_result", "text": f"写作中断: {write_error}", "saved": False}

    if not full_text:
        return {"type": "writing_result", "text": "写作未生成内容。", "saved": False}

    chapter = json_store.add_chapter(book_id, chapter_title, full_text)
    return {"type": "writing_result", "text": _format_chapter_result(book_id, chapter['id'], chapter_title, full_text,
                                   f"剧情链: {len(nodes)}节点"),
            "chapter_id": chapter['id'], "chapter_title": chapter_title, "word_count": len(full_text), "saved": True}


def _store_chapter(args: dict, book_id: str, msg: str) -> str:
    title = args.get("title", "章节")
    content = args.get("content", msg)
    is_extra = bool(args.get("is_extra", False))
    chapter_index = args.get("chapter_index", None)
    # 去重: 如果已有相同chapter_index的章节,更新而非新建
    if chapter_index is not None:
        chapters = json_store.load_chapters(book_id)
        for ch in chapters:
            existing_idx = ch.get("index", ch.get("chapter_index"))
            if existing_idx is not None and int(existing_idx) == int(chapter_index):
                json_store.edit_chapter(book_id, ch["id"], content, title=title, message=f"autopilot重写第{chapter_index}章")
                return _format_chapter_result(book_id, ch['id'], title, content)
    chapter = json_store.add_chapter(book_id, title, content, is_extra=is_extra)
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
    return _format_chapter_result(book_id, chapter['id'], title, content)


async def _delegate_writing(
        loop, args: dict, kb, book_id: str, session_id: str, msg: str) -> str:
    from core.context_manager import ContextManager
    from core.knowledge_scope import ExposureLevel, WritingKnowledgeScope, scope_manager

    instruction = args.get("instruction", msg)
    mode = args.get("mode", "strict")
    target_words = int(args.get("target_words", 2500))

    scope = WritingKnowledgeScope(
        book_id=book_id,
        target_word_count=target_words)

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
        ch_num = None
        import re
        m = re.search(r'第?\s*(\d+)', instruction)
        if m:
            ch_num = int(m.group(1))
        if ch_num and 1 <= ch_num <= len(chapters):
            ch_outline = chapters[ch_num - 1]
            if ch_outline.get("synopsis"):
                scope.chapter_outline = ch_outline["synopsis"]
            if ch_outline.get("characters"):
                for cname in ch_outline["characters"]:
                    scope.add_character(cname, ExposureLevel.FULL, "大纲标注")
            if ch_outline.get("notes"):
                scope.writing_rules = (
                    scope.writing_rules + "\n" + ch_outline["notes"]).strip()

    # ── 前情提要 ──
    if ch_num and ch_num > 1 and 0 <= ch_num - 2 < len(chapters):
        prev = chapters[ch_num - 2]
        if prev.get("synopsis"):
            scope.prev_chapter_summary = prev["synopsis"]

    # ── 如果范围仍为空，放宽到全部实体 ──
    if not scope.characters and not scope.locations:
        entities = kb.list_entities()
        for e in entities[:12]:
            if e.type == "character":
                scope.add_character(e.name, ExposureLevel.SUMMARY, "自动纳入")
            elif e.type == "location":
                scope.add_location(e.name, ExposureLevel.SUMMARY, "自动纳入")

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

    # Build reference book context if specified
    ref_context = ""
    ref_chapters = args.get("ref_chapters", [])
    if ref_chapters or json_store.get_reference_books(book_id):
        from core.writer import _build_reference_context
        ref_context = _build_reference_context(book_id, ref_chapters if ref_chapters else None)

    ref_prefix2 = '---\n\n以下是参考书（原著）的设定和章节，写作时请参考：\n\n'
    ref_block2 = (ref_prefix2 + ref_context) if ref_context else ''
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
    from core.plugin_loader import plugin_manager
    system = plugin_manager.call_hook_chain(
        "modify_system_prompt", system, context="writing")

    result = await loop.run_in_executor(
        _ai_executor, llm_chat, prompt, system, 0.7, "writing")

    title = args.get("chapter_title", "")
    if not title:
        chapters = json_store.load_chapters(book_id)
        title = f"第{len(chapters) + 1}章"
    chapter = json_store.add_chapter(book_id, title, result)

    scope_text = f"人物: {', '.join(e.entity_name for e in scope.characters)}"
    if scope.locations:
        scope_text += f" | 地点: {', '.join(e.entity_name for e in scope.locations)}"
    if scope.forbidden_characters:
        scope_text += f" | 禁止: {', '.join(scope.forbidden_characters)}"

    return _format_chapter_result(book_id, chapter['id'], title, result, f"知识范围: {scope_text}")
