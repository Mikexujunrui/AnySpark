import asyncio
import re
from datetime import datetime

from ._common import (
    _call_edit_llm,
    _parse_chapter_range,
    ai_executor,
    json_store,
    llm_chat,
)

_DANGEROUS_REGEX = re.compile(r"\([^)]*[\+*][^)]*\)[\+*]")

def _is_dangerous_regex(pattern: str) -> bool:
    """Check for regex patterns that could cause exponential backtracking (ReDoS)."""
    return bool(_DANGEROUS_REGEX.search(pattern))


# ══════════════════════════════════════════════════════════════════════
# Work Package D — Whole-book Transform Tools
# ══════════════════════════════════════════════════════════════════════


async def summarize_book(loop, args: dict, book_id: str) -> str:
    """Generate or refresh a whole-book summary for long-context awareness.

    Reads all chapters, generates a structured summary (plot arc, character
    development, key events, unresolved threads), and stores it in the book's
    metadata. This summary is injected into system_prompt for long novels
    where full chapter history doesn't fit in context.
    """
    chapters = json_store.load_chapters(book_id)
    if not chapters:
        return "当前书籍没有章节，无法生成摘要。"

    # Build a condensed view of all chapters
    chapter_summaries = []
    total_words = 0
    for i, ch in enumerate(chapters):
        view = json_store._chapter_view(ch)
        content = view.get("content", "")
        title = view.get("title", f"第{i+1}章")
        words = len(content)
        total_words += words
        # Take first 300 chars as a rough preview for the summarizer
        preview = content[:300].replace("\n", " ")
        chapter_summaries.append(f"#{i+1} {title} ({words}字): {preview}...")

    book = json_store.get_book(book_id) or {}
    book_title = book.get("title", "未命名")

    system = """你是小说分析师。根据给定的章节概要，生成一份结构化的全书摘要。
输出 JSON 格式：
{
  "premise": "故事核心设定（1-2句）",
  "plot_arc": "主线剧情发展（200字内）",
  "characters": [{"name": "角色名", "role": "主角/配角/反派", "status": "当前状态"}],
  "key_events": ["关键事件1", "关键事件2", "..."],
  "unresolved": ["未解决的伏笔1", "未解决的伏笔2", "..."],
  "themes": ["主题1", "主题2"]
}"""

    prompt = f"""# 书名: {book_title}
# 章节数: {len(chapters)}
# 总字数: {total_words}

## 各章概要:
{chr(10).join(chapter_summaries[:50])}

请生成全书摘要（JSON格式）。"""

    if queue := args.get("_queue"):
        await queue.put({"_progress": "正在生成全书摘要..."})

    result_str = await loop.run_in_executor(
        ai_executor, llm_chat, prompt, system, 0.3, "analysis"
    )

    from core.utils import safe_json_parse
    summary = safe_json_parse(result_str)
    if not isinstance(summary, dict):
        summary = {"raw": result_str[:2000]}

    summary["_generated_at"] = datetime.now().isoformat()
    summary["_chapter_count"] = len(chapters)
    summary["_total_words"] = total_words

    # Persist to book metadata
    json_store.update_book(book_id, {"book_summary": summary})

    char_list = ", ".join(
        f"{c.get('name','?')}({c.get('role','?')})"
        for c in summary.get("characters", [])[:5]
    )
    return (
        f"全书摘要已生成并保存。\n"
        f"  书名: {book_title}\n"
        f"  章节: {len(chapters)} | 字数: {total_words}\n"
        f"  核心设定: {summary.get('premise', '?')[:60]}\n"
        f"  主要角色: {char_list}\n"
        f"  未解伏笔: {len(summary.get('unresolved', []))} 条"
    )


async def find_replace_book(loop, args: dict, book_id: str) -> str:
    """Literal find-and-replace across all (or scoped) chapters.

    Creates a new version for each modified chapter (reversible via revert).
    Supports regex mode.
    """
    pattern = args.get("pattern", "")
    replacement = args.get("replacement", "")
    scope = args.get("scope", "all")
    use_regex = bool(args.get("regex", False))
    dry_run = bool(args.get("dry_run", False))
    commit_msg = args.get("message", f"查找替换: {pattern} → {replacement}")

    if not pattern:
        return "错误: 需要 pattern 参数"

    chapters = json_store.load_chapters(book_id)
    if not chapters:
        return "当前书籍没有章节。"

    target_indices = _parse_chapter_range(scope, len(chapters))
    if not target_indices:
        return f"无法解析章节范围: {scope}"

    total_matches = 0
    chapter_results = []
    modified_count = 0

    for idx in target_indices:
        ch = chapters[idx]
        view = json_store._chapter_view(ch)
        content = view.get("content", "")
        title = view.get("title", f"第{idx+1}章")

        if use_regex:
            # ReDoS protection: validate regex complexity
            if len(pattern) > 500:
                return "正则表达式过长（>500字符），请简化"
            if _is_dangerous_regex(pattern):
                return "正则表达式包含潜在的危险模式（嵌套量词/指数回溯），请简化"
            try:
                new_content, count = re.subn(pattern, replacement, content)
            except re.error as e:
                return f"正则表达式错误: {e}"
        else:
            count = content.count(pattern)
            new_content = content.replace(pattern, replacement) if count else content

        if count == 0:
            chapter_results.append(f"  #{idx+1} {title[:15]}: 0 处匹配")
            continue

        total_matches += count
        if dry_run:
            chapter_results.append(f"  #{idx+1} {title[:15]}: {count} 处匹配（预览未写入）")
        else:
            json_store.edit_chapter(book_id, ch["id"], new_content, message=commit_msg)
            modified_count += 1
            chapter_results.append(f"  #{idx+1} {title[:15]}: {count} 处匹配 → 已修改")

    mode_str = "（预览模式，未实际修改）" if dry_run else f"（已修改 {modified_count} 章）"
    summary = [
        f"查找替换完成{mode_str}:",
        f"  模式: {'正则' if use_regex else '字面'}",
        f"  查找: {pattern[:40]}",
        f"  替换: {replacement[:40]}",
        f"  总匹配: {total_matches} 处",
        f"  范围: {scope}（{len(target_indices)} 章）",
        "",
        "逐章结果:",
    ]
    summary.extend(chapter_results)
    return "\n".join(summary)


async def apply_directive_globally(loop, args: dict, book_id: str) -> str:
    """Apply a natural-language editing directive across all (or scoped) chapters.

    Uses LLM to interpret the directive and apply it to each chapter.
    Creates a new version per modified chapter (reversible).

    The directive can be anything: "把所有'小姐'改成'姑娘'",
    "战争场面描写更详细", "把叙事视角从第一人称改为第三人称", etc.
    """
    directive = args.get("directive", "")
    scope = args.get("scope", "all")
    execution_mode = args.get("execution_mode", "auto")
    dry_run = bool(args.get("dry_run", False))

    if not directive:
        return "错误: 需要 directive 参数（自然语言修改指令）"

    chapters = json_store.load_chapters(book_id)
    if not chapters:
        return "当前书籍没有章节。"

    target_indices = _parse_chapter_range(scope, len(chapters))
    if not target_indices:
        return f"无法解析章节范围: {scope}"

    # Determine execution mode
    serial_keywords = ["呼应", "连贯", "伏笔", "前后", "顺序", "承接", "时间线"]
    parallel_keywords = ["改名", "替换", "查找", "统一", "所有", "全部"]

    if execution_mode == "auto":
        directive.lower()
        if any(kw in directive for kw in serial_keywords):
            execution_mode = "serial"
        elif any(kw in directive for kw in parallel_keywords):
            execution_mode = "parallel"
        else:
            execution_mode = "parallel"  # default: parallel is safe for independent edits

    edit_system = f"""你是小说编辑器。对章节内容执行以下修改指令，输出修改后的完整章节正文。

修改指令: {directive}

规则:
1. 输出修改后的完整正文，不要输出说明或前缀
2. 保持原文的叙事结构和情节走向
3. 只按指令修改，不做额外改动
4. 如果指令不适用于本章（如章节中没有相关内容），原样输出不修改"""

    PER_CHAPTER_TIMEOUT = 120
    commit_msg = f"全书变换: {directive[:30]}"

    if execution_mode == "parallel":
        # Parallel execution (like batch_edit_chapters)
        CONCURRENCY = 3
        semaphore = asyncio.Semaphore(CONCURRENCY)
        results = [None] * len(target_indices)
        completed = 0
        len(target_indices)

        async def _edit_one(pos: int):
            nonlocal completed
            async with semaphore:
                idx = target_indices[pos]
                ch = chapters[idx]
                view = json_store._chapter_view(ch)
                content = view.get("content", "")
                title = view.get("title", f"第{idx+1}章")

                if not content or len(content) < 50:
                    return (pos, f"  #{idx+1} {title[:15]}: 内容过短，跳过", "skip")

                prompt = f"## 原文（{title}）\n{content}\n\n请按指令修改后输出完整正文:"
                try:
                    new_content = await asyncio.wait_for(
                        loop.run_in_executor(
                            ai_executor, _call_edit_llm, llm_chat, prompt, edit_system),
                        timeout=PER_CHAPTER_TIMEOUT)
                except TimeoutError:
                    return (pos, f"  ⏱ #{idx+1} {title[:15]}: 超时，跳过", "fail")
                except Exception as e:
                    return (pos, f"  ❌ #{idx+1} {title[:15]}: {str(e)[:50]}", "fail")

                if isinstance(new_content, dict):
                    return (pos, f"  🚫 #{idx+1} {title[:15]}: {new_content.get('blocked_reason','拦截')}", "fail")

                if new_content and len(new_content) > 100:
                    if not dry_run:
                        json_store.edit_chapter(book_id, ch["id"], new_content, message=commit_msg)
                    return (pos, f"  ✅ #{idx+1} {title[:15]}: {len(content)}→{len(new_content)}字", "ok")
                return (pos, f"  ⚠️ #{idx+1} {title[:15]}: 返回过短，跳过", "fail")

        tasks = [_edit_one(i) for i in range(len(target_indices))]
        edited = skipped = failed = 0
        for coro in asyncio.as_completed(tasks):
            pos, status, category = await coro
            completed += 1
            if category == "ok":
                edited += 1
            elif category == "skip":
                skipped += 1
            else:
                failed += 1
            results[pos] = status

    else:
        # Serial execution — each chapter's result feeds into the next as context
        edited = skipped = failed = 0
        results = []
        prev_summary = ""
        for pos, idx in enumerate(target_indices):
            ch = chapters[idx]
            view = json_store._chapter_view(ch)
            content = view.get("content", "")
            title = view.get("title", f"第{idx+1}章")

            if not content or len(content) < 50:
                results.append(f"  #{idx+1} {title[:15]}: 内容过短，跳过")
                skipped += 1
                continue

            context_hint = f"\n（前章修改摘要: {prev_summary[:100]}）" if prev_summary else ""
            prompt = f"## 原文（{title}）\n{content}{context_hint}\n\n请按指令修改后输出完整正文:"

            try:
                new_content = await asyncio.wait_for(
                    loop.run_in_executor(
                        ai_executor, _call_edit_llm, llm_chat, prompt, edit_system),
                    timeout=PER_CHAPTER_TIMEOUT)
            except TimeoutError:
                results.append(f"  ⏱ #{idx+1} {title[:15]}: 超时，跳过")
                failed += 1
                continue
            except Exception as e:
                results.append(f"  ❌ #{idx+1} {title[:15]}: {str(e)[:50]}")
                failed += 1
                continue

            if isinstance(new_content, dict):
                results.append(f"  🚫 #{idx+1} {title[:15]}: {new_content.get('blocked_reason','拦截')}")
                failed += 1
                continue

            if new_content and len(new_content) > 100:
                if not dry_run:
                    json_store.edit_chapter(book_id, ch["id"], new_content, message=commit_msg)
                results.append(f"  ✅ #{idx+1} {title[:15]}: {len(content)}→{len(new_content)}字")
                edited += 1
                prev_summary = f"第{idx+1}章已按指令修改"
            else:
                results.append(f"  ⚠️ #{idx+1} {title[:15]}: 返回过短，跳过")
                failed += 1

    mode_str = "（预览模式，未实际修改）" if dry_run else f"（已修改 {edited} 章）"
    summary = [
        f"全书变换完成{mode_str}:",
        f"  指令: {directive[:50]}",
        f"  执行模式: {execution_mode}",
        f"  范围: {scope}（{len(target_indices)} 章）",
        f"  ✅ 成功: {edited} | 🚫 跳过: {skipped} | ❌ 失败: {failed}",
        "",
        "逐章结果:",
    ]
    summary.extend(r for r in results if r)
    return "\n".join(summary)


async def transform_chapters_batch(loop, args: dict, book_id: str) -> str:
    """Batch transform selected chapters with an LLM instruction.

    Similar to apply_directive_globally but for explicitly selected chapters
    with a mode choice (patch = modify in place, rewrite = full rewrite).
    """
    chapter_ids = args.get("chapter_ids", "")
    instruction = args.get("instruction", "")
    mode = args.get("mode", "patch")  # patch | rewrite
    dry_run = bool(args.get("dry_run", False))

    if not instruction:
        return "错误: 需要 instruction 参数"

    chapters = json_store.load_chapters(book_id)
    if not chapters:
        return "当前书籍没有章节。"

    target_indices = _parse_chapter_range(chapter_ids, len(chapters))
    if not target_indices:
        return f"无法解析章节范围: {chapter_ids}"

    mode_desc = {
        "patch": "在原文基础上修改，保持大部分内容不变，只调整指令涉及的部分",
        "rewrite": "根据原文情节完全重写本章，保持故事走向但用全新的文字表达",
    }
    edit_system = f"""你是小说编辑器。

模式: {mode_desc.get(mode, mode_desc['patch'])}

修改指令: {instruction}

规则:
1. 输出修改后的完整正文
2. 保持原文的情节走向和人物关系
3. 只按指令修改，不做额外改动"""

    commit_msg = f"批量变换({mode}): {instruction[:30]}"
    edited = skipped = failed = 0
    results = []
    PER_CHAPTER_TIMEOUT = 120

    from ._common import _call_edit_llm

    for idx in target_indices:
        ch = chapters[idx]
        view = json_store._chapter_view(ch)
        content = view.get("content", "")
        title = view.get("title", f"第{idx+1}章")

        if not content or len(content) < 50:
            results.append(f"  #{idx+1} {title[:15]}: 内容过短，跳过")
            skipped += 1
            continue

        prompt = f"## 原文（{title}）\n{content}\n\n请按指令修改后输出完整正文:"

        try:
            new_content = await asyncio.wait_for(
                loop.run_in_executor(
                    ai_executor, _call_edit_llm, llm_chat, prompt, edit_system),
                timeout=PER_CHAPTER_TIMEOUT)
        except TimeoutError:
            results.append(f"  ⏱ #{idx+1} {title[:15]}: 超时，跳过")
            failed += 1
            continue
        except Exception as e:
            results.append(f"  ❌ #{idx+1} {title[:15]}: {str(e)[:50]}")
            failed += 1
            continue

        if isinstance(new_content, dict):
            results.append(f"  🚫 #{idx+1} {title[:15]}: {new_content.get('blocked_reason','拦截')}")
            failed += 1
            continue

        if new_content and len(new_content) > 100:
            if not dry_run:
                json_store.edit_chapter(book_id, ch["id"], new_content, message=commit_msg)
            results.append(f"  ✅ #{idx+1} {title[:15]}: {len(content)}→{len(new_content)}字")
            edited += 1
        else:
            results.append(f"  ⚠️ #{idx+1} {title[:15]}: 返回过短，跳过")
            failed += 1

    mode_str = "（预览模式）" if dry_run else f"（已修改 {edited} 章）"
    summary = [
        f"批量变换完成{mode_str}:",
        f"  指令: {instruction[:50]}",
        f"  模式: {mode}",
        f"  范围: {chapter_ids}（{len(target_indices)} 章）",
        f"  ✅ 成功: {edited} | 🚫 跳过: {skipped} | ❌ 失败: {failed}",
        "",
        "逐章结果:",
    ]
    summary.extend(results)
    return "\n".join(summary)


async def restyle_book(loop, args: dict, book_id: str) -> str:
    """Apply a writing style to multiple chapters.

    Uses the existing styles system (styles/default.yaml + data/styles/) to
    extract style guidelines and rewrite chapters to match.
    """
    style_id = args.get("style_id", "")
    scope = args.get("scope", "all")
    dry_run = bool(args.get("dry_run", False))

    if not style_id:
        return "错误: 需要 style_id 参数"

    # Load style definition
    from core.styles import manager as styles_manager
    style = styles_manager.get(style_id)
    if not style:
        available = [s["name"] for s in styles_manager.list_styles()]
        return f"未找到文风 '{style_id}'。可用文风: {', '.join(available)}"

    style_desc = style.description or ""
    # Build style guidelines from slots
    style_rules_parts = []
    for slot in style.slots:
        if slot.get("enabled", True):
            target = slot.get("target", "")
            content = slot.get("content", "")
            style_rules_parts.append(f"[{target}] {content}")
    style_rules = "\n".join(style_rules_parts)

    chapters = json_store.load_chapters(book_id)
    if not chapters:
        return "当前书籍没有章节。"

    target_indices = _parse_chapter_range(scope, len(chapters))
    if not target_indices:
        return f"无法解析章节范围: {scope}"

    edit_system = f"""你是小说编辑器。将章节内容改写为指定的文风。

## 目标文风: {style.name}
{style_desc}

## 文风规则:
{style_rules}

规则:
1. 输出改写后的完整正文
2. 保持原文的情节、人物、对话内容不变
3. 只调整文风（遣词造句、句式节奏、叙事语气），不改剧情
4. 不要输出说明或前缀"""

    commit_msg = f"文风调整: {style.name}"
    edited = skipped = failed = 0
    results = []
    PER_CHAPTER_TIMEOUT = 150

    for idx in target_indices:
        ch = chapters[idx]
        view = json_store._chapter_view(ch)
        content = view.get("content", "")
        title = view.get("title", f"第{idx+1}章")

        if not content or len(content) < 50:
            results.append(f"  #{idx+1} {title[:15]}: 内容过短，跳过")
            skipped += 1
            continue

        prompt = f"## 原文（{title}）\n{content}\n\n请按目标文风改写后输出完整正文:"

        try:
            new_content = await asyncio.wait_for(
                loop.run_in_executor(
                    ai_executor, _call_edit_llm, llm_chat, prompt, edit_system),
                timeout=PER_CHAPTER_TIMEOUT)
        except TimeoutError:
            results.append(f"  ⏱ #{idx+1} {title[:15]}: 超时，跳过")
            failed += 1
            continue
        except Exception as e:
            results.append(f"  ❌ #{idx+1} {title[:15]}: {str(e)[:50]}")
            failed += 1
            continue

        if isinstance(new_content, dict):
            results.append(f"  🚫 #{idx+1} {title[:15]}: {new_content.get('blocked_reason','拦截')}")
            failed += 1
            continue

        if new_content and len(new_content) > 100:
            if not dry_run:
                json_store.edit_chapter(book_id, ch["id"], new_content, message=commit_msg)
            results.append(f"  ✅ #{idx+1} {title[:15]}: {len(content)}→{len(new_content)}字")
            edited += 1
        else:
            results.append(f"  ⚠️ #{idx+1} {title[:15]}: 返回过短，跳过")
            failed += 1

    mode_str = "（预览模式）" if dry_run else f"（已修改 {edited} 章）"
    summary = [
        f"文风调整完成{mode_str}:",
        f"  文风: {style.name}",
        f"  范围: {scope}（{len(target_indices)} 章）",
        f"  ✅ 成功: {edited} | 🚫 跳过: {skipped} | ❌ 失败: {failed}",
        "",
        "逐章结果:",
    ]
    summary.extend(results)
    return "\n".join(summary)
