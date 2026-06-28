"""Knowledge tool implementations — extraction, validation, batch editing."""
import asyncio
import json

from core.config import config
from core.llm_client import chat as llm_chat
from core.thread_pools import llm_pool as _ai_executor
from data.json_store import json_store
from tools._common import (
    PROGRESSIVE_EXTRACT_SYSTEM,
    SKIP_CHECK_SYSTEM,
    VALIDATION_SYSTEM,
    _apply_progressive_result_batch,
    _build_existing_cards,
    _EntityCache,
    _local_skip_check,
    _parse_chapter_range,
    _parse_progressive_result,
)


async def _should_skip_chapter(
        loop, content: str, existing_cards: str, title: str) -> bool:
    from core.llm_client import MODELS, get_client

    cards_brief = existing_cards[:3000]
    text_brief = content[:4000]

    prompt = f"## 已有角色卡（摘要）\n{cards_brief}\n\n## 本章内容: {title}\n{text_brief}\n\n本章是否有需要更新卡片的新信息？只回答 YES 或 NO:"

    def _call():
        client = get_client()
        r = client.chat.completions.create(
            model=MODELS["flash"],
            messages=[
                {"role": "system", "content": SKIP_CHECK_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=5,
        )
        return r.choices[0].message.content or ""

    response = await loop.run_in_executor(_ai_executor, _call)
    answer = response.strip().upper()
    return "NO" in answer and "YES" not in answer

async def _validate_consistency(loop, kb, book_id: str) -> str:
    # Phase 1: Cypher deterministic checks
    cypher_result = kb.check_consistency()
    lines = []
    contradictions = cypher_result.get("contradictions", [])

    if contradictions:
        lines.append(f"🔍 图规则检测到 {len(contradictions)} 个确定性矛盾:")
        for c in contradictions:
            sev = {
                "high": "🔴",
                "medium": "🟡",
                "low": "🟢"}.get(
                c.get(
                    "severity",
                    "low"),
                "⚪")
            lines.append(f"  {sev} [{c['type']}] {c['description']}")
    else:
        lines.append("✅ 图规则检查未发现矛盾。")

    # Phase 2: LLM semantic check (only for unresolved issues)
    cards = _build_existing_cards(kb)
    if cards and len(cards) >= 100:
        llm_prompt = (
            f"## 全部角色/设定卡片\n{cards[:config.storage.max_extraction_chars]}\n\n"
            f"## 图规则已检测到 {len(contradictions)} 个矛盾（已列出，忽略即可）\n"
            f"请额外审核卡片之间的语义矛盾，如性格与行为不一致、设定逻辑漏洞等。输出JSON:"
        )
        try:
            response = await loop.run_in_executor(
                _ai_executor, llm_chat, llm_prompt, VALIDATION_SYSTEM, 0.1, "extraction"
            )
            j = response.strip()
            if j.startswith("```json"):
                j = j[7:]
            if j.startswith("```"):
                j = j[3:]
            if j.endswith("```"):
                j = j[:-3]
            data = json.loads(j.strip())
            semantic_issues = data.get("issues", [])
            semantic_summary = data.get("summary", "")
            if semantic_issues:
                lines.append(f"\n🔎 LLM语义检查发现 {len(semantic_issues)} 个问题:")
                for iss in semantic_issues[:8]:
                    lines.append(
                        f"  ⚠ [{iss.get('entity', '')}] {iss.get('type', '')}: {iss.get('description', '')}")
                    if iss.get("suggestion"):
                        lines.append(f"    → {iss['suggestion']}")
            if semantic_summary:
                lines.append(f"\n总评: {semantic_summary}")
        except Exception as e:
            lines.append(f"\n（LLM语义检查跳过: {str(e)[:40]}）")

    return "\n".join(lines)

def _call_edit_llm(llm_chat, prompt, system):
    from openai import APIError
    try:
        result = llm_chat(
            prompt,
            system=system,
            temperature=0.3,
            task="writing")
    except APIError as e:
        body = str(e.body or "").lower()
        if "content" in body or "filter" in body or "sensitive" in body or "policy" in body:
            return {
                "blocked_reason": f"API审查: {str(e.body)[:60]}", "content": ""}
        raise
    except Exception as e:
        err = str(e).lower()
        if "content" in err and ("filter" in err or "policy" in err):
            return {"blocked_reason": f"审查拦截: {str(e)[:60]}", "content": ""}
        raise

    if not result:
        return {"blocked_reason": "空响应", "content": ""}

    refusal_patterns = ["我无法", "我不能", "抱歉，我无法", "作为AI", "违反", "不适合"]
    first_line = result.strip()[:50]
    if any(p in first_line for p in refusal_patterns):
        return {"blocked_reason": f"模型拒绝: {first_line[:40]}", "content": ""}

    return result

async def _extract_all_chapters(
        loop, args: dict, kb, book_id: str, msg: str = "", queue=None) -> str:

    args.get("focus", "")
    chapters = json_store.load_chapters(book_id)
    if not chapters:
        return "当前书籍没有章节。请先导入章节。"

    total_new = 0
    total_updated = 0
    total_relations = 0
    total_foreshadows = 0
    chapter_logs = []

    PER_CHAPTER_TIMEOUT = 200
    BATCH_CONCURRENCY = 3
    failed = 0

    entity_cache = _EntityCache(kb)

    prepared = []
    for idx, ch in enumerate(chapters):
        view = json_store._chapter_view(ch) if "versions" in ch else ch
        content = view.get("content", "")
        title = view.get("title", "")
        prepared.append((idx, title, content))

    async def _process_one(idx: int, title: str,
                           content: str, cards_snapshot: str):
        tag = f"第{idx + 1}/{len(chapters)}章 {title[:15]}"

        if not content or len(content) < 50:
            return ("skip_empty", tag, None)

        if queue:
            await queue.put({"_progress": f"提取 {tag} ({len(content)}字)..."})

        prompt = f"## 已有角色/实体卡片\n{cards_snapshot}\n\n" if cards_snapshot else ""
        prompt += f"## 当前章节: {title}\n{content[:config.storage.max_extraction_chars]}\n\n请输出JSON:"

        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    _ai_executor,
                    llm_chat,
                    prompt,
                    PROGRESSIVE_EXTRACT_SYSTEM,
                    0.1,
                    "extraction"),
                timeout=PER_CHAPTER_TIMEOUT
            )
        except TimeoutError:
            return ("timeout", tag, None)
        except Exception as e:
            err = str(e)[:60]
            if any(k in err.lower()
                   for k in ["content", "filter", "sensitive", "policy"]):
                return ("censored", tag, err[:40])
            return ("error", tag, err[:40])

        if not response or len(response.strip()) < 10:
            return ("empty", tag, None)

        try:
            chapter_result = _parse_progressive_result(response)
        except Exception as e:
            return ("parse_error", tag, str(e)[:40])

        return ("ok", tag, chapter_result)

    for batch_start in range(0, len(prepared), BATCH_CONCURRENCY):
        from core.session_state import run_state
        handle = run_state.get_handle(
            f"sub_{book_id}") or run_state.get_handle(book_id)
        if handle and handle.cancelled:
            chapter_logs.append("  ⏹ 用户中止，后续章节跳过")
            break

        batch = prepared[batch_start:batch_start + BATCH_CONCURRENCY]

        to_process = []
        for idx, title, content in batch:
            tag = f"第{idx + 1}/{len(chapters)}章 {title[:15]}"
            if not content or len(content) < 50:
                chapter_logs.append(f"  ⚠️ {tag}: 跳过（无内容）")
                continue

            if entity_cache.get_cards():
                if _local_skip_check(content, entity_cache.get_known_names()):
                    try:
                        skip = await asyncio.wait_for(
                            _should_skip_chapter(
                                loop, content, entity_cache.get_cards(), title),
                            timeout=30
                        )
                    except Exception:
                        skip = False
                    if skip:
                        status = f"  ⏭ {tag} ({len(content)}字): 无新变化，跳过"
                        chapter_logs.append(status)
                        if queue:
                            await queue.put({"_progress": status.strip()})
                        continue

            to_process.append((idx, title, content))

        if not to_process:
            continue

        if queue:
            tags = [f"第{idx + 1}章" for idx, _, _ in to_process]
            await queue.put({"_progress": f"并行提取: {', '.join(tags)}..."})

        cards_snapshot = entity_cache.get_cards()

        sem = asyncio.Semaphore(BATCH_CONCURRENCY)

        async def _sem_process(idx, title, content):
            async with sem:
                return await _process_one(idx, title, content, cards_snapshot)

        tasks = [_sem_process(idx, title, content)
                 for idx, title, content in to_process]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        batch_new = 0
        batch_updated = 0
        batch_rels = 0
        batch_fs = 0

        for res in results:
            if isinstance(res, Exception):
                failed += 1
                chapter_logs.append(f"  ❌ 异常: {str(res)[:40]}")
                continue

            status_type, tag, data = res

            if status_type == "skip_empty":
                chapter_logs.append(f"  ⚠️ {tag}: 跳过（无内容）")
            elif status_type == "timeout":
                failed += 1
                status = f"  ⏱ {tag}: 超时（>{PER_CHAPTER_TIMEOUT}s），跳过"
                chapter_logs.append(status)
                if queue:
                    await queue.put({"_progress": status.strip()})
            elif status_type == "censored":
                failed += 1
                status = f"  🚫 {tag}: 审查拦截 — {data}"
                chapter_logs.append(status)
                if queue:
                    await queue.put({"_progress": status.strip()})
            elif status_type == "error":
                failed += 1
                status = f"  ❌ {tag}: 错误 — {data}"
                chapter_logs.append(status)
                if queue:
                    await queue.put({"_progress": status.strip()})
            elif status_type == "empty":
                failed += 1
                status = f"  🚫 {tag}: 空响应，疑似审查"
                chapter_logs.append(status)
                if queue:
                    await queue.put({"_progress": status.strip()})
            elif status_type == "parse_error":
                failed += 1
                status = f"  ❌ {tag}: 解析失败 — {data}"
                chapter_logs.append(status)
                if queue:
                    await queue.put({"_progress": status.strip()})
            elif status_type == "ok":
                chapter_result = data
                try:
                    new_count, update_count, rel_count, fs_count = _apply_progressive_result_batch(
                        chapter_result, kb, book_id
                    )
                    batch_new += new_count
                    batch_updated += update_count
                    batch_rels += rel_count
                    batch_fs += fs_count
                    status = (f"  ✅ {tag}: "
                              f"+{new_count}新 ↑{update_count}更新 +{rel_count}关系 +{fs_count}伏笔")
                    chapter_logs.append(status)
                    if queue:
                        await queue.put({"_progress": status.strip()})
                except Exception as e:
                    failed += 1
                    status = f"  ❌ {tag}: 入库失败 — {str(e)[:40]}"
                    chapter_logs.append(status)
                    if queue:
                        await queue.put({"_progress": status.strip()})

        total_new += batch_new
        total_updated += batch_updated
        total_relations += batch_rels
        total_foreshadows += batch_fs

        entity_cache.refresh()

    entities = kb.list_entities()
    json_store.update_book_stats(book_id, entity_count=len(entities))

    validation_result = ""
    if entities:
        if queue:
            await queue.put({"_progress": "全部章节提取完毕，正在通读验证一致性..."})
        try:
            validation_result = await asyncio.wait_for(
                _validate_consistency(loop, kb, book_id), timeout=PER_CHAPTER_TIMEOUT
            )
        except Exception as e:
            validation_result = f"（验证步骤出错: {str(e)[:50]}）"

    summary_parts = [
        f"逐章提取完成（{len(chapters)} 章）:",
        f"  ✅ 新增实体: {total_new}",
        f"  ↑ 更新实体: {total_updated}",
        f"  🔗 新增关系: {total_relations}",
        f"  📌 新增伏笔: {total_foreshadows}",
        f"  ❌ 失败/跳过: {failed}",
        f"  📊 知识库总实体: {len(entities)}",
    ]
    if chapter_logs:
        summary_parts.append("\n逐章详情:")
        summary_parts.extend(chapter_logs)
    if validation_result:
        summary_parts.append(f"\n一致性审核:\n{validation_result}")

    return "\n".join(summary_parts)

async def _batch_edit_chapters(
        loop, args: dict, kb, book_id: str, msg: str = "", queue=None) -> str:
    from core.session_state import run_state

    instruction = args.get("instruction", "")
    chapters_range = args.get("chapters", "all").strip()
    commit_msg = args.get("message", instruction[:30])

    if not instruction:
        return "错误: 需要 instruction 参数（修改指令）"

    all_chapters = json_store.load_chapters(book_id)
    if not all_chapters:
        return "当前书籍没有章节。"

    target_indices = _parse_chapter_range(chapters_range, len(all_chapters))
    if not target_indices:
        return f"无法解析章节范围: {chapters_range}"

    edit_system = f"""你是小说编辑器。对章节内容执行以下修改指令，输出修改后的完整章节正文。

修改指令: {instruction}

规则:
1. 输出修改后的完整正文，不要输出说明或前缀
2. 保持原文的叙事结构和情节走向
3. 只按指令修改，不做额外改动
4. 如果指令不适用于本章（如章节中没有相关内容），原样输出不修改"""

    PER_CHAPTER_TIMEOUT = 120
    CONCURRENCY = 3
    HEARTBEAT = 15
    semaphore = asyncio.Semaphore(CONCURRENCY)
    results = [None] * len(target_indices)
    completed = 0
    total = len(target_indices)

    async def _edit_one(ch_idx: int, pos: int):
        nonlocal completed
        async with semaphore:
            idx = target_indices[ch_idx]
            ch = all_chapters[idx]
            view = json_store._chapter_view(ch)
            content = view.get("content", "")
            title = view.get("title", "")

            if not content or len(content) < 50:
                return (ch_idx, None, "skip_empty")

            if queue:
                await queue.put({"_progress": f"修改第{idx + 1}/{len(all_chapters)}章: {title[:15]}..."})

            prompt = f"## 原文（{title}）\n{content}\n\n请按指令修改后输出完整正文:"

            heartbeat_event = asyncio.Event()

            async def _heartbeat():
                while not heartbeat_event.is_set():
                    try:
                        await asyncio.wait_for(heartbeat_event.wait(), timeout=HEARTBEAT)
                    except TimeoutError:
                        if queue:
                            await queue.put({"_progress": f"  第{idx + 1}章 仍在处理中..."})

            heartbeat_task = asyncio.ensure_future(_heartbeat())

            try:
                new_content = await asyncio.wait_for(
                    loop.run_in_executor(
                        _ai_executor,
                        _call_edit_llm,
                        llm_chat,
                        prompt,
                        edit_system),
                    timeout=PER_CHAPTER_TIMEOUT
                )
            except TimeoutError:
                heartbeat_event.set()
                return (ch_idx, None, f"⏱ #{idx + 1} {title[:15]}: 超时（>{PER_CHAPTER_TIMEOUT}s），跳过")
            except Exception as e:
                heartbeat_event.set()
                err_msg = str(e)[:80]
                if "content" in err_msg.lower() and ("filter" in err_msg.lower() or "policy" in err_msg.lower()):
                    return (ch_idx, None, f"🚫 #{idx + 1} {title[:15]}: 内容审查拒绝，跳过")
                if "rate" in err_msg.lower() or "429" in err_msg:
                    return (ch_idx, None, f"⚠️ #{idx + 1} {title[:15]}: 速率限制")
                return (ch_idx, None, f"❌ #{idx + 1} {title[:15]}: 错误 — {err_msg[:50]}")
            finally:
                heartbeat_event.set()
                await heartbeat_task

            if isinstance(new_content, dict):
                reason = new_content.get("blocked_reason", "")
                if reason:
                    return (ch_idx, None, f"🚫 #{idx + 1} {title[:15]}: 模型审查拦截 — {reason}")
                new_content = new_content.get("content", "")

            if new_content and len(new_content) > 100:
                json_store.edit_chapter(book_id, ch["id"], new_content, message=commit_msg)
                status = f"✅ #{idx + 1} {title[:15]}: {len(content)}→{len(new_content)}字"
                return (ch_idx, status, "edited")
            elif new_content is not None and len(new_content or "") < 100:
                return (ch_idx, None, f"🚫 #{idx + 1} {title[:15]}: 返回过短({len(new_content or '')}字)")
            else:
                return (ch_idx, None, f"⚠️ #{idx + 1} {title[:15]}: 空响应，跳过")

    tasks = [_edit_one(i, target_indices[i]) for i in range(len(target_indices))]
    edited = skipped = failed = 0

    for coro in asyncio.as_completed(tasks):
        session_id = f"sub_{book_id}"
        handle = run_state.get_handle(session_id) or run_state.get_handle(book_id)
        if handle and handle.cancelled:
            for t in tasks:
                t.cancel()
            break

        ch_idx, status, category = await coro
        completed += 1
        if category == "edited":
            edited += 1
        elif category == "skip_empty":
            skipped += 1
        else:
            failed += 1

        display = status or ""
        results[ch_idx] = display
        if queue and display:
            await queue.put({"_progress": f"[{completed}/{total}] {display}"})

    summary = [
        f"批量修改完成 ({len(target_indices)} 章):",
        f"  ✅ 成功: {edited}",
        f"  🚫 审查/跳过: {skipped}",
        f"  ❌ 失败/超时: {failed}",
        f"  指令: {instruction[:50]}",
        "",
        "逐章状态:",
    ]
    summary.extend(r for r in results if r)
    return "\n".join(summary)
