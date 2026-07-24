"""Plot tool implementations — suggest directions, generate volume outlines.

Extracted from executor.py to keep module sizes manageable.
"""

import asyncio
import json
import logging
import re as _re
from datetime import datetime
from pathlib import Path

from core.config import config
from core.knowledge import Entity, EntityType
from core.llm_client import chat as llm_chat
from core.thread_pools import llm_pool as _ai_executor
from data.json_store import json_store
from tools.impl.writing import _format_chapter_result

PLOT_DIRECTIONS_SYSTEM = """你是小说剧情设计师。根据当前故事状态，生成多个不同方向的剧情走向选项。

每个选项必须是截然不同的方向（不是同一方向的微调），让作者有真正的选择空间。

输出严格JSON（不要加```标记）：
{
  "context_summary": "当前剧情状态的一句话总结",
  "cards": [
    {
      "id": "a",
      "title": "方向名称（6字以内）",
      "description": "这个方向会发生什么（50-100字）",
      "key_events": ["关键事件1", "关键事件2", "关键事件3"],
      "tone": "基调标签（如：热血/虐心/悬疑/治愈/反转）",
      "impact": "对后续剧情的影响（一句话）",
      "risk": "这个方向的创作风险或难点（一句话）"
    }
  ]
}

规则：
1. 每个方向的tone应尽量不同，给作者多样化选择
2. description要具体到能让作者判断好不好写
3. key_events是这个方向下会发生的核心事件，3-5个
4. impact说明选了这个方向后剧情大走向会怎样
5. risk帮助作者评估每个方向的难度"""


async def _suggest_plot_directions(loop, args: dict, kb, book_id: str) -> dict:

    instruction = args.get("instruction", "")
    chapter_ref = args.get("chapter_ref", "")
    num_options = min(int(args.get("num_options", 3)), 5)

    source_parts = []

    if kb:
        try:
            summary = kb.get_knowledge_summary()[:2000]
            if summary:
                source_parts.append(f"## 知识库摘要\n{summary}")
        except Exception:
            pass

    outline = json_store.get_outline(book_id)
    if outline.get("summary"):
        source_parts.append(f"## 全书总纲\n{outline['summary'][:300]}")
    if outline.get("chapters"):
        ch_lines = []
        for i, c in enumerate(outline["chapters"]):
            if c and c.get("synopsis"):
                ch_lines.append(f"第{i + 1}章 {c.get('title', '')}: {c['synopsis'][:60]}")
        if ch_lines:
            source_parts.append("## 大纲\n" + "\n".join(ch_lines[-10:]))

    if chapter_ref:
        try:
            ch = json_store.get_chapter(book_id, chapter_ref)
            content = ch.get("content", "")[:2000]
            if content:
                source_parts.append(f"## 当前章节内容\n{content}")
        except Exception:
            pass
    else:
        chapters = json_store.load_chapters(book_id)
        if chapters:
            last = json_store._chapter_view(chapters[-1])
            content = last.get("content", "")[:1500]
            title = last.get("title", "")
            if content:
                source_parts.append(f"## 最新章节: {title}\n{content}")

    if not source_parts:
        return "没有可参考的内容。请先导入章节或创建大纲。"

    source = "\n\n".join(source_parts)
    user_need = instruction or "接下来的剧情怎么发展？"
    prompt = f"{source}\n\n## 用户需求\n{user_need}\n\n请生成 {num_options} 个不同的剧情走向选项，输出JSON:"

    try:
        response = await asyncio.wait_for(
            loop.run_in_executor(_ai_executor, llm_chat, prompt, PLOT_DIRECTIONS_SYSTEM, 0.8, "writing"),
            timeout=120,
        )
    except TimeoutError:
        return "剧情生成超时，请重试。"
    except Exception as e:
        return f"剧情生成失败: {str(e)[:80]}"

    j = response.strip()
    if j.startswith("```json"):
        j = j[7:]
    if j.startswith("```"):
        j = j[3:]
    if j.endswith("```"):
        j = j[:-3]

    try:
        data = json.loads(j.strip())
    except json.JSONDecodeError:
        return f"解析失败。原始响应:\n{response[:500]}"

    cards = data.get("cards", [])
    if not cards:
        return "未能生成有效的剧情选项。"

    return {
        "type": "plot_cards",
        "context_summary": data.get("context_summary", ""),
        "instruction": instruction,
        "cards": cards,
    }


def _generate_volume_outlines(book_id: str) -> str:
    """Auto-generate volume structure with story_line based on book outline."""
    import json as _json

    from core.llm_client import chat

    outline = json_store.load_outline(book_id) or {}
    chapters = json_store.load_chapters(book_id) or []
    existing_volumes = json_store.load_volumes(book_id) or []

    existing_with_story = [v for v in existing_volumes if v.get("storyLine", "").strip()]
    total_chapters = len(chapters)
    outline_chapters = outline.get("chapters", [])
    outline_summary = outline.get("summary", "")

    if not outline_chapters and not outline_summary:
        return "❌ 当前书籍没有大纲。请先用 generate_outline 生成全书大纲，再根据大纲自动分卷。"

    outline_text = f"全书总纲: {outline_summary[:500]}\n\n" if outline_summary else ""
    outline_text += f"共 {total_chapters} 章\n"
    for i, ch in enumerate(outline_chapters[:30]):
        outline_text += f"第{i + 1}章: {ch.get('title', ch.get('name', ''))} - {ch.get('synopsis', '')[:80]}\n"
    if len(outline_chapters) > 30:
        outline_text += f"... (还有 {len(outline_chapters) - 30} 章)\n"

    existing_vol_text = ""
    if existing_with_story:
        existing_vol_text = "\n已有分卷（保留）:\n"
        for v in existing_with_story:
            existing_vol_text += f"- {v['title']}: {v['storyLine'][:100]}\n"

    planner_prompt = f"""根据以下大纲，将整部小说划分为合理的分卷（卷/部/篇）。

{outline_text}
{existing_vol_text}
总章节数: {total_chapters}

请输出分卷计划 JSON：
{{
  "volumes": [
    {{
      "title": "第一卷 启程",
      "storyLine": "本卷故事主线（100-300字）",
      "chapter_range": "第1-15章"
    }}
  ]
}}

原则：每卷8-25章，有独立叙事弧；storyLine描述本卷而非全书；已有分卷跳过。只输出JSON。"""

    try:
        response = asyncio.get_event_loop().run_until_complete(
            asyncio.to_thread(
                chat, planner_prompt, system="你是小说结构规划师。输出 JSON。", temperature=0.2, task="general"
            )
        )
    except RuntimeError:
        response = chat(planner_prompt, system="你是小说结构规划师。输出 JSON。", temperature=0.2, task="general")

    json_str = response.strip()
    if json_str.startswith("```"):
        json_str = _re.sub(r"^```(?:json)?\s*", "", json_str)
        json_str = _re.sub(r"\s*```$", "", json_str)

    try:
        plan = _json.loads(json_str)
    except _json.JSONDecodeError:
        return f"❌ 解析分卷计划失败。返回: {response[:300]}"

    volumes_data = plan.get("volumes", [])
    if not volumes_data:
        return "❌ 未生成有效分卷计划。"

    created, updated = [], []
    for vd in volumes_data:
        title = vd.get("title", "")
        story_line = vd.get("storyLine", "")
        if not title:
            continue
        existing = next((v for v in existing_volumes if v.get("title") == title), None)
        if existing:
            if not existing.get("storyLine", "").strip() and story_line:
                json_store.update_volume(book_id, existing["id"], {"storyLine": story_line})
                updated.append(title)
        else:
            json_store.add_volume(book_id, title, story_line)
            created.append(title)

    lines = ["## 分卷计划完成\n"]
    if created:
        lines.append(f"✅ 新建 {len(created)} 卷: {', '.join(created)}")
    if updated:
        lines.append(f"📝 补充 {len(updated)} 卷的 storyLine: {', '.join(updated)}")
    if not created and not updated:
        lines.append("所有分卷已存在且均有故事主线，无需修改。")
    return "\n".join(lines)


logger = logging.getLogger(__name__)


async def _compare_versions(loop, args: dict, kb, msg: str) -> str:
    text = args.get("text", msg)
    kb_text = kb.get_knowledge_summary()[:2000]
    return await loop.run_in_executor(
        _ai_executor,
        llm_chat,
        f"对比知识库与新文本:\nKB:{kb_text}\n\nNew:{text[:2000]}\n列出冲突和新增",
        "",
        0.1,
        "extraction",
    )


async def _decompose_chapter(loop, args: dict, msg: str, book_id: str) -> str:
    # Get chapter text from chapter_id or direct text
    chapter_id = args.get("chapter_id", "")
    chapter_title = args.get("chapter_title", "")
    ref_book_id = args.get("ref_book_id", "")

    if chapter_id:
        # Determine target book (current or reference)
        target_book_id = book_id
        if ref_book_id:
            ref_ids = json_store.get_reference_books(book_id)
            if not ref_ids or not any(r == ref_book_id or r.startswith(ref_book_id) for r in ref_ids):
                return f"❌ {ref_book_id} 不是当前项目的参考书。先用 set_reference_books 设置。"
            target_book_id = ref_book_id

        try:
            ch = json_store.get_chapter(target_book_id, chapter_id)
            chapter = ch.get("content", "")
            if not chapter_title:
                chapter_title = ch.get("title", "")
        except Exception as e:
            return f"❌ 无法读取章节 {chapter_id}: {str(e)[:100]}"
    else:
        chapter = args.get("chapter_text", msg)

    if not chapter or len(chapter.strip()) < 50:
        return "❌ 章节内容过短，无法拆解"

    system = """你是小说结构分析师。将一章小说拆解为结构化剧情链。
对每个场景节点提取:
- scene_name: 场景名
- location: 地点
- characters: 出场人物列表
- plot_beats: 3-5个情节节拍
- dialogues: 关键对话摘要
- key_event: 关键事件
- emotional_arc: 情感弧线（如“从猜疑到信任”）
- importance: 重要性(1-5)
- transition_to_next: 到下一场景的过渡

- source_text: 原文中的关键段落和对话（直接摘录，越完整越好，用于保真复写）

- edit_mode: 改写模式，可选值:
  - "keep": 原样保留，不做任何修改（直接输出原文）
  - "tweak": 微调，保留大部分原文，只改特定处
  - "rewrite": 大幅改写，只保留结构框架
  默认为"rewrite"，除非用户明确要求保真

- edit_instructions: 具体修改指令（仅 tweak/rewrite 模式需要，keep 模式为 null）
  例如: "把A角色的反应从愤怒改为隐忍" 或 null

输出JSON数组: [{"scene_name":"场景名","location":"地点","characters":["角色"],"plot_beats":["节拍1","节拍2"],"dialogues":["摘要"],"key_event":"关键事件","emotional_arc":"情感变化","importance":5,"transition_to_next":"过渡描述","source_text":"原文关键段落摘录（尽量完整）","edit_mode":"rewrite","edit_instructions":null}]
只提取原文明确出现的信息。"""

    result = await loop.run_in_executor(
        _ai_executor,
        llm_chat,
        f"章节标题: {chapter_title}\n\n原文:\n{chapter[: config.storage.max_extraction_chars]}",
        system,
        0.2,
        "extraction",
    )

    # Try to parse and store the chain
    save = args.get("save", True)
    nodes = None
    try:
        # Try to extract JSON from response
        import re

        json_match = re.search(r"\[.*\]", result, re.DOTALL)
        if json_match:
            nodes = json.loads(json_match.group())
    except (json.JSONDecodeError, Exception):
        pass

    chain_id = None
    if nodes and save:
        try:
            chain_data = {
                "chapter_id": chapter_id,
                "chapter_title": chapter_title,
                "nodes": [
                    {
                        "index": i,
                        "scene_name": n.get("scene_name", f"场景{i + 1}"),
                        "location": n.get("location", ""),
                        "characters": n.get("characters", []),
                        "plot_beats": n.get("plot_beats", []),
                        "dialogues": n.get("dialogues", []),
                        "key_event": n.get("key_event", ""),
                        "emotional_arc": n.get("emotional_arc", ""),
                        "importance": n.get("importance", 3),
                        "transition_to_next": n.get("transition_to_next", ""),
                        "source_text": n.get("source_text", ""),
                        "edit_mode": n.get("edit_mode", "rewrite"),
                        "edit_instructions": n.get("edit_instructions", None),
                    }
                    for i, n in enumerate(nodes)
                ],
                "summary": f"共{len(nodes)}个场景",
                "total_nodes": len(nodes),
            }
            saved_chain = json_store.save_plot_chain(book_id, chain_data)
            chain_id = saved_chain["id"]
        except Exception as e:
            logger.warning(f"Failed to save plot chain: {e}")

    # Format summary output
    if nodes:
        lines = [f"# 剧情链拆解完成\n共 {len(nodes)} 个场景节点"]
        if chain_id:
            lines.append(f"链ID: {chain_id}\n")
        for i, n in enumerate(nodes):
            lines.append(f"\n## 节点{i}: {n.get('scene_name', '?')}")
            lines.append(f"地点: {n.get('location', '?')} | 人物: {', '.join(n.get('characters', []))}")
            lines.append(f"情感: {n.get('emotional_arc', '-')}")
            beats = n.get("plot_beats", [])
            if beats:
                lines.append("节拍: " + " → ".join(beats[:4]))
            source = n.get("source_text", "")
            if source:
                lines.append(f"原文锚点: {len(source)}字")
            edit_mode = n.get("edit_mode", "rewrite")
            mode_label = {"keep": "原样保留", "tweak": "微调", "rewrite": "改写"}.get(edit_mode, edit_mode)
            lines.append(f"改写模式: {mode_label}")
            if n.get("edit_instructions"):
                lines.append(f"修改指令: {n['edit_instructions'][:60]}...")
        lines.append("\n💡 使用 annotate_chain 可修改各节点的改写模式(keep/tweak/rewrite)")
        lines.append("💡 使用 rewrite_by_chain 可按此链逐节点复写")
        return "\n".join(lines)

    # Fallback: return raw result
    return result


def _annotate_chain(args: dict, book_id: str) -> str:
    """Update edit_mode and edit_instructions for nodes in a plot chain.
    Supports preview=true to show source_text excerpts without modifying."""
    chain_id = args.get("chain_id", "")
    try:
        if chain_id:
            chain = json_store.get_plot_chain(book_id, chain_id)
        else:
            chain = json_store.get_latest_plot_chain(book_id)
            if not chain:
                return "❌ 没有找到剧情链。请先使用 decompose_chapter 拆解章节。"
    except Exception as e:
        return f"❌ 无法获取剧情链: {str(e)[:100]}"

    nodes = chain.get("nodes", [])
    preview = args.get("preview", False)
    annotations = args.get("annotations", [])

    # PREVIEW mode: show chain summary with source_text excerpts
    if preview:
        lines = [f"📝 剧情链预览: {chain.get('chapter_title', '?')} (共{len(nodes)}个节点)\n"]
        for i, n in enumerate(nodes):
            scene = n.get("scene_name", "?")
            mode = n.get("edit_mode", "rewrite")
            mode_label = {"keep": "原样保留", "tweak": "微调", "rewrite": "改写"}.get(mode, mode)
            source = n.get("source_text", "")
            source_preview = source[:120].replace("\n", " ") + ("..." if len(source) > 120 else "")
            inst = n.get("edit_instructions", "")

            lines.append(f"【节点{i}】{scene}  [{mode_label}]")
            if source_preview:
                lines.append(f"  原文: {source_preview}")
            if inst:
                lines.append(f"  修改指令: {inst[:80]}{'...' if len(str(inst)) > 80 else ''}")
            lines.append("")

        lines.append("ℹ️ 这是预览模式，未修改剧情链。")
        lines.append("ℹ️ 可用 annotate_chain(annotations=[...]) 修改标注，或用 ask_user 向用户展示选择后确认。")
        return "\n".join(lines)

    if not annotations:
        # Show current state
        lines = [f"剧情链: {chain.get('chapter_title', '?')} (共{len(nodes)}个节点)\n"]
        for i, n in enumerate(nodes):
            mode = n.get("edit_mode", "rewrite")
            mode_label = {"keep": "原样保留", "tweak": "微调", "rewrite": "改写"}.get(mode, mode)
            inst = n.get("edit_instructions", "") or "无"
            if len(str(inst)) > 50:
                inst = str(inst)[:50] + "..."
            lines.append(f"  节点{i}: {n.get('scene_name', '?')} | {mode_label} | {inst}")
        lines.append(
            "\n用法: annotate_chain(annotations=[{index:0, edit_mode:'tweak', edit_instructions:'把A改为B'}, ...])"
        )
        return "\n".join(lines)

    # Apply annotations
    updated = 0
    for ann in annotations:
        idx = ann.get("index")
        if idx is not None and 0 <= idx < len(nodes):
            if "edit_mode" in ann:
                if ann["edit_mode"] in ("keep", "tweak", "rewrite"):
                    nodes[idx]["edit_mode"] = ann["edit_mode"]
                    updated += 1
                else:
                    return f"❌ 节点{idx}的edit_mode无效，可选: keep/tweak/rewrite"
            if "edit_instructions" in ann:
                nodes[idx]["edit_instructions"] = ann["edit_instructions"]
                updated += 1

    # Save updated chain
    chain["nodes"] = nodes
    json_store.save_plot_chain(book_id, chain)

    # Show result
    lines = [f"已更新 {updated} 处标注\n"]
    for i, n in enumerate(nodes):
        mode = n.get("edit_mode", "rewrite")
        mode_label = {"keep": "原样保留", "tweak": "微调", "rewrite": "改写"}.get(mode, mode)
        inst = n.get("edit_instructions", "") or "无"
        if len(str(inst)) > 50:
            inst = str(inst)[:50] + "..."
        lines.append(f"  节点{i}: {n.get('scene_name', '?')} | {mode_label} | {inst}")

    return "\n".join(lines)


async def _extract_style(loop, args: dict, kb, book_id: str, msg: str) -> str:
    from core.utils import extract_json_from_response

    sample = args.get("sample_text", msg)
    if not sample or not sample.strip():
        return "错误: 未提供样本文本，无法分析文风。请提供至少一段文本内容。"
    system = """你是小说文风分析师。分析样本文本的写作风格。
输出JSON: {"avg_sentence_length":"","description_density":"high/medium/low","dialogue_ratio":"","pace":"fast/medium/slow","tone":"","vocabulary_features":[],"distinctive_patterns":[],"narrative_pov":"","paragraph_structure":""}"""
    result = await loop.run_in_executor(
        _ai_executor,
        llm_chat,
        f"样本文本:\n{sample[: config.storage.max_style_sample_chars]}",
        system,
        0.2,
        "extraction",
    )
    # 解析 JSON，防止存入无效内容
    try:
        cleaned = extract_json_from_response(result)
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return f"文风分析失败: LLM 返回的内容不是有效 JSON。原始响应前 200 字:\n{result[:200]}"
    style_id = str(int(datetime.now().timestamp() * 1000))
    entity = Entity(
        id=style_id,
        type=EntityType.CONCEPT,
        name=f"StyleProfile_{book_id[:8]}",
        data={"type": "style_profile", "analysis": json.dumps(parsed, ensure_ascii=False)},
    )
    kb.add_entity(entity)
    return json.dumps(parsed, ensure_ascii=False, indent=2)


async def _reconstruct_chapter(loop, args: dict, kb, book_id: str) -> str:
    outline = args.get("plot_outline", "")
    style = args.get("style_profile", "")
    target = int(args.get("target_words", 2000))
    title = args.get("chapter_title", "")
    summary = kb.get_knowledge_summary()[: config.storage.max_knowledge_summary_chars]
    system = f"""你是小说复写专家。根据情节大纲和知识库，复写一个章节。
目标字数: {target} 字
{style and f"文风约束: {style[:2000]}" or ""}

规则:
1. 保留所有情节节拍，不遗漏、不改变主线事件
2. 可以用不同的词语和句式，但事件走向必须一致
3. 知识库中的角色设定必须严格遵守
4. 直接输出复写的章节正文，不要加说明前缀"""
    prompt = f"""知识库:\n{summary}\n\n情节大纲:\n{outline}\n\n{"章节标题: " + title if title else ""}\n请复写本章（{
        target
    }字）:"""
    result = await loop.run_in_executor(
        _ai_executor, llm_chat, prompt, system, config.agent.creative_temperature, "writing"
    )
    ch_title = title or "复写章节"
    chapter = json_store.add_chapter(book_id, ch_title, result)
    return _format_chapter_result(book_id, chapter["id"], ch_title, result)


async def _compare_plot(loop, args: dict) -> str:
    orig = args.get("original_outline", "")
    new = args.get("new_outline", "")
    system = """你是小说情节对比分析器。
对比原文和复写版的情节大纲，输出:
1. 遗漏事件列表
2. 新增事件列表
3. 忠实度评分 (0-100)
4. 结构变化说明
输出JSON格式。"""
    return await loop.run_in_executor(
        _ai_executor,
        llm_chat,
        f"原文大纲:\n{orig[:3000]}\n\n复写大纲:\n{new[:3000]}\n\n对比分析:",
        system,
        0.1,
        "extraction",
    )


def _read_document(args: dict, session_id: str, book_id: str) -> str:
    doc_id = args.get("doc_id", "")
    sid = session_id or book_id
    if not doc_id:
        docs = json_store.load_docs(sid)
        doc_list = ", ".join(f"ID={d['id']}: {d['filename']} ({d['chars']}字)" for d in docs)
        return f"已有文档: {doc_list}"
    try:
        doc = json_store.get_doc(sid, doc_id)
    except Exception:
        docs = json_store.load_docs(sid)
        return "文档不存在。可用ID: " + ", ".join(d["id"] for d in docs)
    path = Path(doc["path"])
    if not path.exists():
        return "文件已丢失"
    from core.document_parser import parse_document

    text = parse_document(path)
    offset = int(args.get("offset", 0))
    limit = int(args.get("limit", config.storage.max_context_chars))
    return text[offset : offset + limit]
