# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

from data.json_store import json_store

from .config import config
from .context_manager import ContextManager
from .knowledge_scope import WritingKnowledgeScope
from .llm_client import chat, chat_stream
from .plugin_loader import plugin_manager

WRITER_STRICT_SYSTEM = """你是一位严格遵循设定的小说续写助手。

# 核心规则
1. **只使用下方提供的知识库内容**——不要自行编造新角色、新地点。
2. 知识库中没有出现的角色绝对不能出场。如需要某个角色出场但知识库没提供，请在文中标记【需要补充：角色名】。
3. **严格遵守写作规则和禁止项**——禁止出场的角色绝对不能出现，禁止揭露的伏笔绝对不能暗示。
4. **可以发挥的部分**：描写（环境、心理、动作细节）、对话、文风、过渡衔接。
5. **保持一致性**：人物的性格、能力、关系必须与知识库完全一致。

# 输出要求
- 直接输出小说正文，不要加解释、说明、前缀
- 按照大纲和风格要求写作"""

WRITER_SUGGEST_SYSTEM = """你是一位小说续写助手。

# 规则
1. **优先使用知识库**：知识库中有明确设定的内容必须严格遵循。
2. **可以合理补充**：知识库中没有但情景必要的细节可以补充，但必须在文末以【新增设定】标注。
3. **需要确认时**：关键的新设定用【需确认：描述】标记。
4. 知识库中没有出现的角色不能出场，除非你确认需要且标记为【新增设定】。

# 输出要求
- 直接输出小说正文
- 若有新增设定，在文末列出"""


def _build_reference_context(book_id: str, ref_chapters: list[str] | None = None) -> str:
    """Build context from reference books: entities + optional full chapters."""
    ref_ids = json_store.get_reference_books(book_id)
    if not ref_ids:
        return ""

    sections = []
    from .graph_store import GraphStore

    for ref_id in ref_ids:
        try:
            ref_book = json_store.get_book(ref_id)
            book_title = ref_book.get("title", ref_id)
            ref_sections = [f"## 参考书: {book_title}"]

            # Load entities from reference book
            ref_kb = GraphStore(ref_id)
            ref_kb.init_schema()
            entities = ref_kb.list_entities()
            if entities:
                char_lines = []
                loc_lines = []
                for e in entities[:30]:  # Limit to avoid context overflow
                    brief = ", ".join(f"{k}: {str(v)[:40]}" for k, v in
                                      list(e.data.items())[:3] if v)
                    line = f"- **{e.name}** [{e.type}]"
                    if brief:
                        line += f" — {brief}"
                    if e.type == "character":
                        char_lines.append(line)
                    elif e.type == "location":
                        loc_lines.append(line)

                if char_lines:
                    ref_sections.append("\n### 原著角色")
                    ref_sections.extend(char_lines)
                if loc_lines:
                    ref_sections.append("\n### 原著地点")
                    ref_sections.extend(loc_lines)
            ref_kb.close()

            # Load specific chapters if requested
            if ref_chapters:
                ref_chs = json_store.load_chapters(ref_id)
                for ch_ref in ref_chapters:
                    # Parse chapter reference: "ref_book_id:#3" or "#3"
                    if ":" in ch_ref:
                        parts = ch_ref.split(":", 1)
                        if parts[0] != ref_id:
                            continue
                        ch_id = parts[1]
                    else:
                        ch_id = ch_ref

                    # Find matching chapter using _find_chapter (handles #N format)
                    found = json_store._find_chapter(ref_chs, ch_id)
                    if found:
                        view = json_store._chapter_view(found)
                        ref_sections.append(f"\n### 原著章节: {view.get('title', '?')}")
                        content = view.get("content", "")
                        limit = config.storage.max_ref_chapter_chars
                        if len(content) > limit:
                            content = content[:limit] + f"...（内容过长，已截断至{limit}字）"
                        ref_sections.append(content)

            # Inject structural analysis report (if cached)
            try:
                from .reference_analyzer import load_analysis
                structure_data = load_analysis("structure", ref_id)
                if structure_data:
                    ref_sections.append(_format_structure_constraints(structure_data))

                # Inject style fingerprint (if cached)
                style_data = load_analysis("style_fingerprint", ref_id)
                if style_data:
                    ref_sections.append(_format_style_constraints(style_data))
            except Exception:
                pass  # analysis injection is best-effort

            sections.extend(ref_sections)
        except Exception as e:
            sections.append(f"## 参考书 {ref_id} (加载失败: {str(e)[:50]})")

    return "\n".join(sections) if sections else ""


def _format_structure_constraints(structure: dict) -> str:
    """Format a structure report dict as a writing-constraint text block."""
    lines = ["\n### 原著结构约束"]
    ch_count = structure.get("chapter_count", 0)
    total = structure.get("total_words", 0)
    avg = structure.get("avg_chapter_length", 0)
    if ch_count:
        lines.append(
            f"原著共 {ch_count} 章，{total} 字，平均每章 {avg:.0f} 字。"
        )
    avg_dr = structure.get("avg_dialogue_ratio", 0)
    if avg_dr:
        lines.append(f"平均对话占比 {avg_dr:.1%}。")
    para = structure.get("paragraph_stats", {})
    if para.get("avg_per_chapter"):
        lines.append(
            f"平均每章 {para['avg_per_chapter']:.0f} 段，每段约 {para['avg_length']:.0f} 字。"
        )
    sent = structure.get("sentence_stats", {})
    if sent.get("avg_per_chapter"):
        lines.append(
            f"平均每章 {sent['avg_per_chapter']:.0f} 句，每句约 {sent['avg_length']:.0f} 字。"
        )
    lines.append("续写时应保持相近的章节篇幅和对话密度。")
    return "\n".join(lines)


def _format_style_constraints(fingerprint: dict) -> str:
    """Format a style fingerprint dict as a writing-constraint text block."""
    lines = ["\n### 文风量化约束"]
    dist = fingerprint.get("sentence_length_distribution", {})
    if dist:
        lines.append("句长分布:")
        for bucket in ["<10", "10-20", "20-40", ">40"]:
            val = dist.get(bucket, 0)
            if val:
                lines.append(f"  {bucket}字: {val:.1%}")
    ttr = fingerprint.get("vocabulary_richness_ttr", 0)
    if ttr:
        lines.append(f"词汇丰富度(TTR): {ttr:.3f}")
    idiom = fingerprint.get("four_char_idiom_density", 0)
    if idiom:
        lines.append(f"四字成语密度: {idiom:.4f}")
    para = fingerprint.get("paragraph_length_stats", {})
    if para.get("mean"):
        lines.append(
            f"段落长度: 均值{para['mean']:.0f}字, 中位数{para.get('median', 0):.0f}字"
        )
    dd = fingerprint.get("dialogue_density", 0)
    if dd:
        lines.append(f"对话密度: {dd:.1%}")
    lines.append("续写时应尽量匹配以上文风量化指标。")
    return "\n".join(lines)


def _build_write_prompt(task_instruction: str, mode: str, project_id: str,
                        relevant_entities: list[str] | None = None,
                        scope: WritingKnowledgeScope | None = None,
                        ref_chapters: list[str] | None = None,
                        chapter_number: int | None = None) -> tuple[str, str]:
    plugin_manager.call_hook("on_write_before", instruction=task_instruction, mode=mode, project_id=project_id)
    cm = ContextManager(project_id)
    # If caller gave a chapter_ref but no derived number, derive it now so
    # character arc phases can be auto-injected.
    if chapter_number is None and scope and scope.chapter_ref:
        from .context_manager import _chapter_ref_to_number
        chapter_number = _chapter_ref_to_number(scope.chapter_ref)
    if scope:
        knowledge_text = cm.build_scoped_context(scope)
    else:
        knowledge_text = cm.build_writing_context(
            task_instruction, relevant_entities,
            chapter_number=chapter_number,
        )
    system = WRITER_STRICT_SYSTEM if mode == "strict" else WRITER_SUGGEST_SYSTEM
    system = plugin_manager.call_hook_chain("modify_system_prompt", system, context="writing")
    # Build reference book context if available
    ref_context = _build_reference_context(project_id, ref_chapters)
    ref_section = ''
    if ref_context:
        ref_section = '---\n\n以下是参考书（原著）的设定和章节，写作时请参考：\n\n' + ref_context
    knowledge_hint = ''
    if '（知识库为空' in knowledge_text:
        knowledge_hint = '（注意：知识库目前为空或极小，请用 suggest 模式写作）'

    prompt = f"""以下是已有的知识库设定：

{knowledge_text}

{ref_section}

---

请根据以上设定，完成以下写作任务：

{task_instruction}

{knowledge_hint}"""
    return prompt, system


def write(task_instruction: str, mode: str = "strict",
          relevant_entities: list[str] | None = None,
          project_id: str = "default",
          scope: WritingKnowledgeScope | None = None,
          ref_chapters: list[str] | None = None,
          chapter_number: int | None = None) -> str:
    prompt, system = _build_write_prompt(
        task_instruction, mode, project_id, relevant_entities,
        scope, ref_chapters, chapter_number,
    )
    result = chat(prompt, system=system, temperature=0.7, task="writing")
    plugin_manager.call_hook("on_write_after", instruction=task_instruction, result=result, project_id=project_id)
    return result


def write_stream(task_instruction: str, mode: str = "strict",
                 relevant_entities: list[str] | None = None,
                 project_id: str = "default",
                 scope: WritingKnowledgeScope | None = None,
                 ref_chapters: list[str] | None = None,
                 chapter_number: int | None = None):
    prompt, system = _build_write_prompt(
        task_instruction, mode, project_id, relevant_entities,
        scope, ref_chapters, chapter_number,
    )
    yield from chat_stream(prompt, system=system, temperature=0.7, task="writing")
