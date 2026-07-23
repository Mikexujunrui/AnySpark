# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Autopilot planner — intent classification and step sequence generation."""

import asyncio
import json
import logging
import re
import time

from ..task_queue import PersistentTask, TaskStep
from .config import INTENT_PATTERNS, AutopilotConfig, PlanIntent

logger = logging.getLogger(__name__)


def _classify_intent(instruction: str, book_state: dict) -> PlanIntent:
    """Classify user instruction into a structured PlanIntent.

    Uses keyword pattern matching first, falls back to LLM for ambiguous cases.
    """

    # Try rule-based classification first
    scores = {}
    for intent_type, pattern in INTENT_PATTERNS.items():
        score = 0
        for kw in pattern["keywords"]:
            # Support regex patterns (e.g., "第.*章.*改")
            if ".*" in kw:
                if re.search(kw, instruction):
                    score += 2
            elif kw in instruction:
                score += 1
        scores[intent_type] = score

    # Get the highest-scoring intent
    best_intent = max(scores, key=scores.get)
    best_score = scores[best_intent]

    # Parse chapter indices from instruction (e.g., "#3-#8", "第3-8章", "#3,#5,#7")
    chapter_indices = _parse_chapter_indices(instruction)

    # Determine scope
    scope = "all"
    if chapter_indices:
        if len(chapter_indices) == 1:
            scope = f"#{chapter_indices[0]}"
        else:
            scope = f"#{chapter_indices[0]}-#{chapter_indices[-1]}"
    elif re.search(r"第\d+-\d+章|#\d+-#\d+", instruction):
        scope = "range"
    elif "全书" in instruction or "全部" in instruction or "所有" in instruction:
        scope = "all"

    # If score is too low or ambiguous, use LLM fallback
    if best_score == 0:
        # Could not classify - mark as mixed for LLM planning
        return PlanIntent(
            intent_type="mixed",
            scope=scope,
            directive=instruction,
            chapter_indices=chapter_indices,
            requires_outline=False,
            requires_writing=False,
            requires_edit=False,
            requires_analysis=False,
            sequential_dependency=False,
            priority_notes="需要LLM规划",
        )

    # Build intent from pattern
    pattern = INTENT_PATTERNS[best_intent]
    sequential = False

    # Determine sequential dependency based on instruction semantics
    if best_intent == "batch_edit":
        # If instruction mentions coherence/continuity, make it sequential
        if any(kw in instruction for kw in ["连贯", "衔接", "一致", "前后", "呼应"]):
            sequential = True
    elif best_intent in ("write_new", "import_and_refine"):
        sequential = True  # Chapter writing/refining is always sequential

    # Parse skip indices for import_and_refine
    skip_indices = _parse_skip_indices(instruction) if best_intent == "import_and_refine" else []

    # Extract ref_book_id if mentioned (e.g. "从参考书XXX导入")
    ref_book_id = ""
    if best_intent == "import_and_refine":
        ref_match = re.search(r"参考书\s*[：:]\s*(\S+?)(?:\s|导入|中|的|$)", instruction)
        if not ref_match:
            ref_match = re.search(r"从\s*(\S+?)\s*导入", instruction)
        if ref_match:
            ref_book_id = ref_match.group(1).strip()

    return PlanIntent(
        intent_type=best_intent,
        scope=scope,
        directive=instruction,
        chapter_indices=chapter_indices,
        skip_indices=skip_indices,
        ref_book_id=ref_book_id,
        requires_outline=pattern.get("requires_outline", False),
        requires_writing=pattern.get("requires_writing", False),
        requires_edit=pattern.get("requires_edit", False),
        requires_analysis=pattern.get("requires_analysis", False),
        sequential_dependency=sequential,
        priority_notes="",
    )


def _parse_chapter_indices(instruction: str) -> list:
    """Extract chapter indices from instruction text.

    Supports formats:
    - "#3-#8" or "#3~#8" → [3,4,5,6,7,8]
    - "#3,#5,#7" → [3,5,7]
    - "第3-8章" → [3,4,5,6,7,8]
    - "第3章" → [3]
    """
    indices = []

    # Match "#N-#M" or "#N~#M" patterns
    range_match = re.search(r"#(\d+)\s*[-~]\s*#(\d+)", instruction)
    if range_match:
        start, end = int(range_match.group(1)), int(range_match.group(2))
        indices = list(range(start, end + 1))
        return indices

    # Match "第N-M章" pattern
    cn_range_match = re.search(r"第(\d+)\s*[-~到至]\s*(\d+)章", instruction)
    if cn_range_match:
        start, end = int(cn_range_match.group(1)), int(cn_range_match.group(2))
        indices = list(range(start, end + 1))
        return indices

    # Match "#N,#M,#K" patterns
    hash_matches = re.findall(r"#(\d+)", instruction)
    if hash_matches:
        indices = [int(x) for x in hash_matches]
        return sorted(set(indices))

    # Match "第N章" single chapter
    cn_single = re.search(r"第(\d+)章", instruction)
    if cn_single:
        indices = [int(cn_single.group(1))]
        return indices

    return indices


def _parse_skip_indices(instruction: str) -> list:
    """Extract chapter indices to skip from instruction text.

    Supports formats:
    - "跳过第20-25章" → [20,21,22,23,24,25]
    - "跳过#20-#25" → [20,21,22,23,24,25]
    - "已经改过20-25了" → [20,21,22,23,24,25]
    - "跳过第3章" → [3]
    """
    indices = []

    # Match "跳过第N-M章" or "跳过#N-#M"
    range_match = re.search(r"跳过\s*(?:第)?\s*#?(\d+)\s*[-~到至]\s*#?(\d+)\s*(?:章)?", instruction)
    if range_match:
        start, end = int(range_match.group(1)), int(range_match.group(2))
        indices = list(range(start, end + 1))
        return indices

    # Match "已经改过N-M" or "改过#N-#M"
    already_match = re.search(r"(?:已经|已)?改过\s*#?(\d+)\s*[-~到至]\s*#?(\d+)", instruction)
    if already_match:
        start, end = int(already_match.group(1)), int(already_match.group(2))
        indices = list(range(start, end + 1))
        return indices

    # Match individual "跳过第N章"
    skip_singles = re.findall(r"跳过\s*(?:第)?\s*#?(\d+)\s*(?:章)?", instruction)
    if skip_singles:
        indices = [int(x) for x in skip_singles]
        return sorted(set(indices))

    return indices


class AutopilotPlanner:
    """Intelligent planner that classifies intent and generates customized step sequences."""

    async def plan(self, config: AutopilotConfig) -> dict:
        """Generate an execution plan based on intent classification.

        Returns:
            {
                "plan_summary": str,
                "chapters": [{"index": int, "title": str}],
                "steps": [TaskStep],
                "estimated_chapters": int,
                "intent_type": str,
            }
        """
        book_state = await self._read_book_state(config.book_id)

        # Classify intent
        intent = _classify_intent(config.instruction, book_state)

        # Dispatch to appropriate step builder based on intent
        prefix = f"ap_{int(time.time() * 1000)}"

        if intent.intent_type == "write_new":
            return self._plan_write_new(prefix, config, book_state, intent)
        elif intent.intent_type == "batch_edit":
            return self._plan_batch_edit(prefix, config, book_state, intent)
        elif intent.intent_type == "global_replace":
            return self._plan_global_replace(prefix, config, book_state, intent)
        elif intent.intent_type == "style_change":
            return self._plan_style_change(prefix, config, book_state, intent)
        elif intent.intent_type == "targeted_edit":
            return self._plan_targeted_edit(prefix, config, book_state, intent)
        elif intent.intent_type == "analysis":
            return self._plan_analysis(prefix, config, book_state, intent)
        elif intent.intent_type == "insert_content":
            return self._plan_insert_content(prefix, config, book_state, intent)
        elif intent.intent_type == "import_and_refine":
            return await self._plan_import_and_refine(prefix, config, book_state, intent)
        else:  # mixed or unknown
            return await self._plan_with_llm(prefix, config, book_state, intent)

    # ── Book State Reading ──

    async def _read_book_state(self, book_id: str) -> dict:
        """Read current book state: outline, chapters, knowledge."""
        from data.json_store import json_store

        chapters = json_store.load_chapters(book_id) or []
        outline = json_store.load_outline(book_id) or {}
        detailed_outline = json_store.load_detailed_outline(book_id) or {}

        # Determine which chapters exist
        existing_indices = set()
        for ch in chapters:
            idx = ch.get("index", ch.get("chapter_index"))
            if idx is not None:
                existing_indices.add(int(idx))
                continue
            # fallback: 从句柄名称推断 (如 "第十一章 荒野追杀" → 11)
            title = ch.get("title", "")
            if title:
                import re
                ch_num_map = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10,"百":100}
                # 尝试匹配 "第X章" 格式
                m = re.match(r'第([一二三四五六七八九十百千\d]+)章', title)
                if m:
                    num_str = m.group(1)
                    if num_str.isdigit():
                        existing_indices.add(int(num_str))
                    else:
                        # 中文数字转换
                        val = 0
                        unit = 1
                        for c in reversed(num_str):
                            if c in ch_num_map:
                                n = ch_num_map[c]
                                if n >= 10:
                                    unit = n if val == 0 else unit * n
                                    val = max(val, 1) * unit if val == 0 else val
                                else:
                                    val += n * unit
                            elif c == '零':
                                pass
                        if val > 0:
                            existing_indices.add(val)

        # Get outline chapter list
        outline_chapters = []
        if outline and isinstance(outline, dict):
            outline_chapters = outline.get("chapters", [])
        if detailed_outline and isinstance(detailed_outline, dict):
            detailed_chs = detailed_outline.get("chapters", [])
            if detailed_chs and not outline_chapters:
                outline_chapters = detailed_chs

        # Volume state — check how many volumes exist and have story_line filled
        volumes = json_store.load_volumes(book_id) or []
        volumes_count = len(volumes)
        volumes_with_story = len([v for v in volumes if v.get("storyLine", "").strip()])

        return {
            "existing_indices": existing_indices,
            "existing_count": len(chapters),
            "total_words": sum(len(ch.get("content", "")) for ch in chapters),
            "outline_chapters": outline_chapters,
            "has_outline": bool(outline_chapters),
            "has_summary": bool(outline.get("summary", "").strip()) if isinstance(outline, dict) else False,
            "detailed_outline_count": len(detailed_chs) if detailed_outline and isinstance(detailed_outline, dict) else 0,
            "volumes_count": volumes_count,
            "volumes_with_story": volumes_with_story,
            "chapter_titles": {
                int(ch.get("index", ch.get("chapter_index", 0))):
                    ch.get("title", f"第{ch.get('index', ch.get('chapter_index', '?'))}章")
                for ch in chapters
                if ch.get("index") or ch.get("chapter_index")
            },
        }

    # ── Write New Plan ──

    def _plan_write_new(self, prefix: str, config: AutopilotConfig,
                        book_state: dict, intent: PlanIntent) -> dict:
        """Plan for sequential chapter writing."""
        chapters_to_write = self._determine_chapters(book_state, config)

        steps = []
        step_counter = 0

        # ── Auto-generate outline if none exists ──
        # Without an outline, chapters have no titles/synopsis and the Agent
        # has no structural guidance, causing plot drift over long sequences.
        has_outline = book_state.get("has_outline", False)
        has_summary = book_state.get("has_summary", False)  # 总纲
        has_detailed = bool(book_state.get("detailed_outline_count", 0))
        total_chs = book_state["existing_count"] + len(chapters_to_write)

        # For substantial books (5+ chapters), the 总纲 (summary) is mandatory.
        # Missing 总纲 = treat as "no outline" even if per-chapter synopses exist.
        needs_outline_for_summary = (total_chs >= 5) and not has_summary

        if (not has_outline and not has_detailed) or needs_outline_for_summary:
            # Step 0a: Generate book-level outline (and detailed if missing)
            steps.append(TaskStep(
                id=f"{prefix}_gen_outline",
                type="agent_loop",
                label="自动生成全书大纲",
                config={
                    "prompt": "使用 generate_outline 工具自动生成全书大纲。"
                              "读取所有已有章节，逐章概括情节要点，最后生成全书总纲。",
                    "agent_type": "write",
                    "mode": "write",
                    "temperature": 0.2,
                    "max_rounds": 30,
                    "step_category": "generate",
                },
            ))
            step_counter += 1
            if not has_detailed:
                steps.append(TaskStep(
                id=f"{prefix}_gen_detailed",
                type="agent_loop",
                label="自动生成细纲",
                config={
                    "prompt": "使用 generate_detailed_outline 工具自动生成细纲（纯剧情骨架）。"
                              "逐章提取纯剧情事件链，去掉描写和对话。",
                    "agent_type": "write",
                    "mode": "write",
                    "temperature": 0.1,
                    "max_rounds": 40,
                    "step_category": "generate",
                    "depends_on": [f"{prefix}_gen_outline"],
                },
            ))
            step_counter += 1
        elif not has_outline:
            # Has detailed outline but no book-level outline
            steps.append(TaskStep(
                id=f"{prefix}_gen_outline",
                type="agent_loop",
                label="自动生成全书大纲",
                config={
                    "prompt": "使用 generate_outline 工具自动生成全书大纲。"
                              "读取所有已有章节，逐章概括情节要点，最后生成全书总纲。",
                    "agent_type": "write",
                    "mode": "write",
                    "temperature": 0.2,
                    "max_rounds": 30,
                    "step_category": "generate",
                },
            ))
            step_counter += 1
        elif not has_detailed:
            # Has outline but no detailed outline
            steps.append(TaskStep(
                id=f"{prefix}_gen_detailed",
                type="agent_loop",
                label="自动生成细纲",
                config={
                    "prompt": "使用 generate_detailed_outline 工具自动生成细纲（纯剧情骨架）。"
                              "逐章提取纯剧情事件链，去掉描写和对话。",
                    "agent_type": "write",
                    "mode": "write",
                    "temperature": 0.1,
                    "max_rounds": 40,
                    "step_category": "generate",
                },
            ))
            step_counter += 1

        # ── Auto-generate volume outlines ──
        # If we have/will-have an outline but volumes are missing or lack story_line,
        # let the Agent auto-generate the volume structure.
        volumes_count = book_state.get("volumes_count", 0)
        volumes_with_story = book_state.get("volumes_with_story", 0)
        # Total chapter count (existing + to-be-written) tells us if volumes are needed
        total_chs = book_state["existing_count"] + len(chapters_to_write)
        if total_chs >= 20:  # Only suggest volumes for 20+ chapter books
            needs_volumes = (volumes_count == 0) or (volumes_with_story < volumes_count)
            if needs_volumes:
                dep_ids = []
                if not has_outline:
                    dep_ids.append(f"{prefix}_gen_outline")
                if not has_detailed:
                    dep_ids.append(f"{prefix}_gen_detailed")
                steps.append(TaskStep(
                    id=f"{prefix}_gen_volumes",
                    type="agent_loop",
                    label="自动生成分卷结构",
                    config={
                        "prompt": "使用 generate_volume_outlines 工具根据大纲自动划分分卷。"
                                  "然后使用 move_chapter_to_volume 将已有章节归入对应分卷。"
                                  "分卷应有独立叙事弧和 storyLine，每卷8-25章。",
                        "agent_type": "write",
                        "mode": "write",
                        "temperature": 0.2,
                        "max_rounds": 25,
                        "step_category": "generate",
                        "depends_on": dep_ids if dep_ids else None,
                    },
                ))
                step_counter += 1

        for ch_info in chapters_to_write:
            ch_idx = ch_info["index"]
            ch_title = ch_info.get("title", f"第{ch_idx}章")
            ch_steps = self._build_chapter_steps(
                prefix, ch_idx, ch_title, config, step_counter
            )
            steps.extend(ch_steps)
            step_counter += len(ch_steps)

        outline_note = ""
        if not has_outline and not has_detailed:
            outline_note = "（⚠️ 无大纲，将先生成全书大纲+细纲）"
        elif not has_outline:
            outline_note = "（无全书大纲，将先生成）"
        elif not has_detailed:
            outline_note = "（无细纲，将先生成）"

        # Volume note
        total_chs = book_state["existing_count"] + len(chapters_to_write)
        vol_note = ""
        if total_chs >= 20:
            if volumes_count == 0:
                vol_note = " + 自动划分分卷"
            elif volumes_with_story < volumes_count:
                vol_note = " + 补全卷纲"

        plan_summary = (
            f"📝 续写模式：计划写 {len(chapters_to_write)} 章"
            f"（第{chapters_to_write[0]['index']}章 ~ "
            f"第{chapters_to_write[-1]['index']}章）"
            f"{outline_note}{vol_note}，"
            f"共 {len(steps)} 个步骤。"
        )

        return {
            "plan_summary": plan_summary,
            "chapters": chapters_to_write,
            "steps": steps,
            "estimated_chapters": len(chapters_to_write),
            "total_steps": len(steps),
            "intent_type": "write_new",
        }

    def _determine_chapters(self, book_state: dict, config: AutopilotConfig) -> list[dict]:
        """Figure out which chapters need to be written."""
        existing = book_state["existing_indices"]
        outline_chs = book_state["outline_chapters"]

        chapters = []

        if outline_chs:
            for i, ch in enumerate(outline_chs):
                idx = i + 1
                if idx not in existing:
                    title = ch.get("title", ch.get("name", f"第{idx}章"))
                    chapters.append({"index": idx, "title": title})
        else:
            start = max(existing) + 1 if existing else 1
            count = min(config.max_chapters_per_run, 5)
            for idx in range(start, start + count):
                chapters.append({"index": idx, "title": f"第{idx}章"})

        chapters = chapters[:config.max_chapters_per_run]
        return chapters

    def _build_chapter_steps(self, prefix: str, ch_idx: int, ch_title: str,
                              config: AutopilotConfig, offset: int) -> list[TaskStep]:
        """Build step sequence for writing one new chapter."""
        steps = []

        def sid(n: int) -> str:
            return f"{prefix}_ch{ch_idx}_s{offset + n}"

        # 1. Plan chapter
        steps.append(TaskStep(
            id=sid(0),
            type="agent_loop",
            label=f"规划{ch_title}",
            config={
                "prompt": f"为{ch_title}规划本章内容。"
                          f"阅读大纲和前文，决定本章的主要场景、人物、情节发展。"
                          f"输出一份简要的章节写作计划。",
                "agent_type": "plan",
                "mode": "plan",
                "temperature": 0.3,
                "step_category": "plan",
            },
        ))

        # 2. User confirm (hard mode)
        if config.audit_mode == "hard":
            steps.append(TaskStep(
                id=sid(1),
                type="user_confirm",
                label=f"确认开始{ch_title}",
                config={
                    "message": f"即将开始写{ch_title}，确认继续？",
                    "header": "章节确认",
                    "options": [
                        {"label": "确认写作", "description": "按规划开始写本章"},
                        {"label": "跳过本章", "description": "跳过这一章"},
                        {"label": "暂停任务", "description": "暂停autopilot"},
                    ],
                },
            ))

        # 3. Write chapter
        ref_instruction = (
            f"请调用 write_chapter 工具写{ch_title}（章节索引: chapter_index={ch_idx}）。\n"
            f"必须传入参数: chapter_title='{ch_title}', chapter_index={ch_idx}。\n"
            f"如果不传 chapter_index，会导致章节编号混乱和重复。"
        )
        if ch_idx > 1:
            ref_instruction += "前情提要和大纲已包含在写作知识范围中，请基于这些信息保持剧情连贯，无需读取前文全文。"

        steps.append(TaskStep(
            id=sid(2),
            type="agent_loop",
            label=f"写作{ch_title}",
            config={
                "prompt": ref_instruction,
                "agent_type": "write",
                "mode": "write",
                "temperature": 0.3,
                "max_rounds": 50,
                "step_category": "write",
                "chapter_index": ch_idx,
                "depends_on": [sid(0)],  # Depends on plan step
            },
        ))

        # 4. Checkpoint
        steps.append(TaskStep(
            id=sid(3),
            type="checkpoint",
            label=f"保存{ch_title}进度",
            config={"chapter_index": ch_idx, "chapter_title": ch_title},
        ))

        # 5. Extract knowledge
        if config.auto_extract:
            steps.append(TaskStep(
                id=sid(4),
                type="agent_loop",
                label=f"提取{ch_title}知识",
                config={
                    "prompt": f"从刚写完的{ch_title}中提取关键设定：新出场人物、"
                              f"地点、道具、伏笔、时间线事件。使用 extract_knowledge 工具。",
                    "agent_type": "extract",
                    "mode": "write",
                    "temperature": 0.1,
                    "max_rounds": 20,
                    "step_category": "extract",
                    "chapter_index": ch_idx,
                },
            ))

        # 6. Quality review
        if config.auto_review:
            steps.append(TaskStep(
                id=sid(5),
                type="agent_loop",
                label=f"评审{ch_title}",
                config={
                    "prompt": f"对{ch_title}进行质量评审。检查：\n"
                              f"1. 与大纲是否一致\n"
                              f"2. 人物行为是否合理\n"
                              f"3. 叙事节奏是否流畅\n"
                              f"4. 有无前后矛盾\n"
                              f"输出评分(1-10)和简要评语。",
                    "agent_type": "reviewer",
                    "mode": "plan",
                    "temperature": 0.3,
                    "max_rounds": 15,
                    "quality_gate": config.quality_gate,
                    "chapter_ref": f"#{ch_idx}",
                    "step_category": "review",
                },
            ))

        # 7. Final checkpoint
        final_id = 6 if config.auto_extract else (5 if config.auto_review else 4)
        steps.append(TaskStep(
            id=sid(final_id),
            type="checkpoint",
            label=f"{ch_title}完成",
            config={
                "chapter_index": ch_idx,
                "chapter_title": ch_title,
                "final": True,
            },
        ))

        return steps

    # ── Batch Edit Plan ──

    def _plan_batch_edit(self, prefix: str, config: AutopilotConfig,
                          book_state: dict, intent: PlanIntent) -> dict:
        """Plan for batch editing existing chapters."""
        # Determine target chapters
        target_indices = intent.chapter_indices
        if not target_indices:
            # Use all existing chapters if no specific range
            target_indices = sorted(book_state["existing_indices"])
        target_indices = target_indices[:config.max_chapters_per_run]

        chapter_titles = book_state.get("chapter_titles", {})

        steps = []
        step_counter = 0

        if intent.sequential_dependency:
            # Sequential: chapters depend on each other (coherence adjustments)
            for ch_idx in target_indices:
                ch_title = chapter_titles.get(ch_idx, f"第{ch_idx}章")
                ch_steps = self._build_edit_steps(
                    prefix, ch_idx, ch_title, config, intent.directive, step_counter
                )
                steps.extend(ch_steps)
                step_counter += len(ch_steps)
        else:
            # Parallel: each chapter can be edited independently
            # Use apply_directive_globally for efficiency
            steps.append(TaskStep(
                id=f"{prefix}_global_s0",
                type="agent_loop",
                label=f"批量改写: {intent.directive[:30]}...",
                config={
                    "prompt": f"使用 apply_directive_globally 工具执行以下指令：\n"
                              f"「{intent.directive}」\n\n"
                              f"目标章节范围: {intent.scope}\n"
                              f"请先用 dry_run=true 预览效果，确认无误后再执行。",
                    "agent_type": "edit",
                    "mode": "write",
                    "temperature": 0.3,
                    "max_rounds": 80,
                    "step_category": "edit",
                },
            ))
            steps.append(TaskStep(
                id=f"{prefix}_global_s1",
                type="checkpoint",
                label="批量改写完成",
                config={"final": True},
            ))

        plan_summary = (
            f"✏️ 批量改写模式：对 {len(target_indices)} 个章节执行「{intent.directive[:30]}」，"
            f"{'串行' if intent.sequential_dependency else '并行'}执行，共 {len(steps)} 个步骤。"
        )

        return {
            "plan_summary": plan_summary,
            "chapters": [{"index": idx, "title": chapter_titles.get(idx, f"第{idx}章")}
                          for idx in target_indices],
            "steps": steps,
            "estimated_chapters": len(target_indices),
            "total_steps": len(steps),
            "intent_type": "batch_edit",
        }

    def _build_edit_steps(self, prefix: str, ch_idx: int, ch_title: str,
                           config: AutopilotConfig, directive: str,
                           offset: int) -> list[TaskStep]:
        """Build step sequence for editing one existing chapter."""
        steps = []
        def sid(n):
            return f"{prefix}_edit{ch_idx}_s{offset + n}"

        # 1. Read chapter
        steps.append(TaskStep(
            id=sid(0),
            type="agent_loop",
            label=f"读取{ch_title}",
            config={
                "prompt": f"读取第{ch_idx}章的内容，使用 read_chapter 工具。简要概述本章内容。",
                "agent_type": "plan",
                "mode": "plan",
                "temperature": 0.1,
                "max_rounds": 10,
                "step_category": "read",
                "chapter_index": ch_idx,
            },
        ))

        # 2. Edit chapter
        steps.append(TaskStep(
            id=sid(1),
            type="agent_loop",
            label=f"改写{ch_title}",
            config={
                "prompt": f"对{ch_title}执行以下修改：\n「{directive}」\n\n"
                          f"使用 patch_chapter 工具进行精确修改，不要重写全章。"
                          f"修改完成后简要说明改了什么。",
                "agent_type": "edit",
                "mode": "write",
                "temperature": 0.3,
                "max_rounds": 30,
                "step_category": "edit",
                "chapter_index": ch_idx,
                "depends_on": [sid(0)],
            },
        ))

        # 3. Checkpoint
        steps.append(TaskStep(
            id=sid(2),
            type="checkpoint",
            label=f"{ch_title}改写完成",
            config={"chapter_index": ch_idx, "chapter_title": ch_title, "final": True},
        ))

        return steps

    # ── Global Replace Plan ──

    def _plan_global_replace(self, prefix: str, config: AutopilotConfig,
                              book_state: dict, intent: PlanIntent) -> dict:
        """Plan for whole-book find/replace operations."""
        steps = [
            TaskStep(
                id=f"{prefix}_replace_s0",
                type="agent_loop",
                label=f"全书替换: {intent.directive[:40]}",
                config={
                    "prompt": f"执行全书查找替换操作：\n「{intent.directive}」\n\n"
                              f"使用 find_replace_book 工具。"
                              f"先执行 dry_run 预览所有命中位置，确认无误后再实际应用。"
                              f"完成后报告：命中章节数、替换次数。",
                    "agent_type": "edit",
                    "mode": "write",
                    "temperature": 0.1,
                    "max_rounds": 40,
                    "step_category": "edit",
                },
            ),
            TaskStep(
                id=f"{prefix}_replace_s1",
                type="checkpoint",
                label="全书替换完成",
                config={"final": True},
            ),
        ]

        plan_summary = f"🔍 全书替换模式：执行「{intent.directive[:40]}」，共 {len(steps)} 个步骤。"

        return {
            "plan_summary": plan_summary,
            "chapters": [],
            "steps": steps,
            "estimated_chapters": book_state["existing_count"],
            "total_steps": len(steps),
            "intent_type": "global_replace",
        }

    # ── Style Change Plan ──

    def _plan_style_change(self, prefix: str, config: AutopilotConfig,
                            book_state: dict, intent: PlanIntent) -> dict:
        """Plan for whole-book style adjustment."""
        steps = [
            TaskStep(
                id=f"{prefix}_style_s0",
                type="agent_loop",
                label=f"全书风格调整: {intent.directive[:30]}",
                config={
                    "prompt": f"执行全书文风调整：\n「{intent.directive}」\n\n"
                              f"使用 restyle_book 工具。先查看可用风格列表（list_styles），"
                              f"选择合适的风格执行。保持情节不变，只调整遣词造句。"
                              f"完成后报告调整了哪些章节。",
                    "agent_type": "edit",
                    "mode": "write",
                    "temperature": 0.3,
                    "max_rounds": 50,
                    "step_category": "edit",
                },
            ),
            TaskStep(
                id=f"{prefix}_style_s1",
                type="checkpoint",
                label="风格调整完成",
                config={"final": True},
            ),
        ]

        plan_summary = f"🎨 风格调整模式：执行「{intent.directive[:30]}」，共 {len(steps)} 个步骤。"

        return {
            "plan_summary": plan_summary,
            "chapters": [],
            "steps": steps,
            "estimated_chapters": book_state["existing_count"],
            "total_steps": len(steps),
            "intent_type": "style_change",
        }

    # ── Targeted Edit Plan ──

    def _plan_targeted_edit(self, prefix: str, config: AutopilotConfig,
                             book_state: dict, intent: PlanIntent) -> dict:
        """Plan for focused refinement of specific chapters.

        Auto-detects chapters that don't exist yet and writes them fresh
        instead of trying to patch_empty.  This prevents the agent from
        falling into the expensive rewrite_by_chain workflow.
        """
        target_indices = intent.chapter_indices
        if not target_indices:
            # Try to extract from instruction
            target_indices = _parse_chapter_indices(intent.directive)
        if not target_indices:
            # Fallback: use first existing chapter
            existing = sorted(book_state["existing_indices"])
            target_indices = existing[:1] if existing else [1]

        chapter_titles = book_state.get("chapter_titles", {})
        existing_indices = book_state.get("existing_indices", set())

        steps = []
        step_counter = 0
        refine_count = 0
        write_count = 0

        for ch_idx in target_indices:
            ch_title = chapter_titles.get(ch_idx, f"第{ch_idx}章")
            ch_exists = ch_idx in existing_indices

            # Analysis step (always do this regardless of existence)
            steps.append(TaskStep(
                id=f"{prefix}_target{ch_idx}_s{step_counter}",
                type="agent_loop",
                label=f"分析{ch_title}",
                config={
                    "prompt": f"分析{ch_title}的当前内容。使用 read_chapter 读取，"
                              f"然后分析：主要情节、角色表现、存在的问题、改进方向。"
                              f"输出一份简要分析报告。",
                    "agent_type": "plan",
                    "mode": "plan",
                    "temperature": 0.2,
                    "max_rounds": 15,
                    "step_category": "analyze",
                    "chapter_index": ch_idx,
                },
            ))
            step_counter += 1

            if ch_exists:
                # 精修: existing chapter -> patch_chapter
                refine_count += 1
                steps.append(TaskStep(
                    id=f"{prefix}_target{ch_idx}_s{step_counter}",
                    type="agent_loop",
                    label=f"精修{ch_title}",
                    config={
                        "prompt": (
                            f"对第{ch_idx}章执行以下修改：\n"
                            f"「{intent.directive}」\n\n"
                            f"使用 patch_chapter 工具进行精确修改，不要重写全章。\n"
                            f"禁止使用 decompose_chapter、annotate_chain、rewrite_by_chain，"
                            f"这些工具在这种情况下效率极低，只能使用 patch_chapter。\n"
                            f"参考前一步的分析结果，重点关注改进方向。"
                        ),
                        "agent_type": "edit",
                        "mode": "write",
                        "temperature": 0.3,
                        "max_rounds": 30,
                        "step_category": "edit",
                        "chapter_index": ch_idx,
                        "depends_on": [f"{prefix}_target{ch_idx}_s{step_counter - 1}"],
                    },
                ))
            else:
                # 写作: non-existing chapter -> write_chapter with reference context
                write_count += 1
                steps.append(TaskStep(
                    id=f"{prefix}_target{ch_idx}_s{step_counter}",
                    type="agent_loop",
                    label=f"写作{ch_title}",
                    config={
                        "prompt": (
                            f"第{ch_idx}章尚不存在，需要新建。\n"
                            f"指令：\n「{intent.directive}」\n\n"
                            f"使用 write_chapter 或 delegate_writing 工具直接写作完整章节。\n"
                            f"如果有参考书，使用 ref_chapters 参数注入原著章节内容作为写作基础。\n"
                            f"禁止使用 decompose_chapter、annotate_chain、rewrite_by_chain，"
                            f"这些工具在这种情况下效率极低。\n"
                            f"写作完成后简要说明本章内容。"
                        ),
                        "agent_type": "edit",
                        "mode": "write",
                        "temperature": 0.3,
                        "max_rounds": 30,
                        "step_category": "edit",
                        "chapter_index": ch_idx,
                        "depends_on": [f"{prefix}_target{ch_idx}_s{step_counter - 1}"],
                    },
                ))
            step_counter += 1

            # Checkpoint
            steps.append(TaskStep(
                id=f"{prefix}_target{ch_idx}_s{step_counter}",
                type="checkpoint",
                label=f"{ch_title}完成",
                config={"chapter_index": ch_idx, "chapter_title": ch_title, "final": True},
            ))
            step_counter += 1

        # Build plan summary
        parts = []
        if refine_count:
            parts.append(f"精修 {refine_count} 章")
        if write_count:
            parts.append(f"写作 {write_count} 章")
        plan_summary = (
            f"🎯 针对性精修模式：{' + '.join(parts)}「{intent.directive[:30]}」，"
            f"共 {len(steps)} 个步骤。"
        )
        if write_count:
            plan_summary += "\n⚠️ 其中有章节尚不存在，会先写作再精修风格。"

        return {
            "plan_summary": plan_summary,
            "chapters": [{"index": idx, "title": chapter_titles.get(idx, f"第{idx}章")}
                          for idx in target_indices],
            "steps": steps,
            "estimated_chapters": len(target_indices),
            "total_steps": len(steps),
            "intent_type": "targeted_edit",
        }

    # ── Analysis Plan ──

    def _plan_analysis(self, prefix: str, config: AutopilotConfig,
                        book_state: dict, intent: PlanIntent) -> dict:
        """Plan for full-book analysis and potential fixes."""
        steps = [
            # Phase 1: Analysis
            TaskStep(
                id=f"{prefix}_analyze_s0",
                type="agent_loop",
                label=f"全书分析: {intent.directive[:30]}",
                config={
                    "prompt": f"执行全书分析：\n「{intent.directive}」\n\n"
                              f"1. 使用 search_knowledge 检索相关设定\n"
                              f"2. 使用 read_chapter 逐章阅读（或抽样阅读）\n"
                              f"3. 检查一致性、矛盾、遗漏\n"
                              f"4. 输出结构化分析报告：\n"
                              f"   - 发现的问题列表（标注严重程度）\n"
                              f"   - 建议的修复方案\n"
                              f"   - 需要修改的章节列表",
                    "agent_type": "consistency",
                    "mode": "plan",
                    "temperature": 0.1,
                    "max_rounds": 60,
                    "step_category": "analyze",
                    "replan_on_fail": "full_replan",  # If analysis fails, replan
                },
            ),
            # Phase 2: Generate fix plan based on analysis (replan trigger)
            TaskStep(
                id=f"{prefix}_analyze_s1",
                type="checkpoint",
                label="分析完成，等待修复规划",
                config={
                    "final": False,
                    "trigger_replan": True,  # Signal to replan based on analysis results
                },
            ),
        ]

        plan_summary = (
            f"🔬 全书分析模式：执行「{intent.directive[:30]}」，"
            f"先分析后根据结果动态规划修复步骤。"
        )

        return {
            "plan_summary": plan_summary,
            "chapters": [],
            "steps": steps,
            "estimated_chapters": 0,
            "total_steps": len(steps),
            "intent_type": "analysis",
        }

    # ── Insert Content Plan ──

    def _plan_insert_content(self, prefix: str, config: AutopilotConfig,
                              book_state: dict, intent: PlanIntent) -> dict:
        """Plan for inserting content across chapters."""
        steps = [
            TaskStep(
                id=f"{prefix}_insert_s0",
                type="agent_loop",
                label=f"全书内容插入: {intent.directive[:30]}",
                config={
                    "prompt": f"在所有章节中合适的位置插入内容：\n「{intent.directive}」\n\n"
                              f"使用 apply_directive_globally 工具执行。"
                              f"指令：在每章合适的位置自然地加入相关内容，"
                              f"不要生硬插入，要与上下文融合。"
                              f"先用 dry_run=true 预览效果。",
                    "agent_type": "edit",
                    "mode": "write",
                    "temperature": 0.3,
                    "max_rounds": 80,
                    "step_category": "edit",
                },
            ),
            TaskStep(
                id=f"{prefix}_insert_s1",
                type="checkpoint",
                label="内容插入完成",
                config={"final": True},
            ),
        ]

        plan_summary = f"📝 内容插入模式：执行「{intent.directive[:30]}」，共 {len(steps)} 个步骤。"

        return {
            "plan_summary": plan_summary,
            "chapters": [],
            "steps": steps,
            "estimated_chapters": book_state["existing_count"],
            "total_steps": len(steps),
            "intent_type": "insert_content",
        }

    # ── Import & Refine Plan ──

    async def _plan_import_and_refine(self, prefix: str, config: AutopilotConfig,
                                       book_state: dict, intent: PlanIntent) -> dict:
        """Plan for importing reference chapters and then refining them.

        Three phases:
        1. Discover: read reference book chapters, compare with existing
        2. Import: batch import chapters that don't already exist (skip duplicates + user-skipped)
        3. Refine: for each imported chapter → read → patch_edit → checkpoint

        Auto-skips chapters that already exist in the current book (by title match).
        Respects user-specified skip ranges (e.g. "跳过第20-25章").
        """
        from data.json_store import json_store

        # ── Get reference books ──
        ref_ids = json_store.get_reference_books(config.book_id)
        if not ref_ids:
            return {
                "plan_summary": "⚠️ 当前书籍未设置参考书。请先在「参考书」面板中添加参考书，然后重试。",
                "chapters": [],
                "steps": [],
                "estimated_chapters": 0,
                "total_steps": 0,
                "intent_type": "import_and_refine",
            }

        # If user specified a particular ref_book_id, filter to that one
        if intent.ref_book_id:
            matched = [rid for rid in ref_ids if intent.ref_book_id in rid or rid in intent.ref_book_id]
            if matched:
                ref_ids = matched[:1]

        # ── Collect all reference chapters ──
        all_ref_chapters = []  # [{ref_book_id, chapter_id, title, index, chars}, ...]
        for ref_id in ref_ids:
            try:
                ref_book = json_store.get_book(ref_id)
                ref_book_title = ref_book.get("title", ref_id)
                ref_chs = json_store.load_chapters(ref_id)
                for i, ch in enumerate(ref_chs):
                    view = json_store._chapter_view(ch)
                    all_ref_chapters.append({
                        "ref_book_id": ref_id,
                        "ref_book_title": ref_book_title,
                        "chapter_id": view["id"],
                        "title": view.get("title", f"第{i + 1}章"),
                        "index": i + 1,
                        "chars": len(view.get("content", "")),
                    })
            except Exception as e:
                logger.warning("Failed to read reference book %s: %s", ref_id, e)
                continue

        if not all_ref_chapters:
            return {
                "plan_summary": "⚠️ 参考书中未找到任何章节。",
                "chapters": [],
                "steps": [],
                "estimated_chapters": 0,
                "total_steps": 0,
                "intent_type": "import_and_refine",
            }

        # ── Apply filters: target range + skip range + existing ──
        target_indices = intent.chapter_indices
        skip_indices = intent.skip_indices

        # Filter by user's target chapter range (e.g. "导入第1-50章")
        if target_indices:
            all_ref_chapters = [ch for ch in all_ref_chapters if ch["index"] in target_indices]

        # Filter out user-skipped chapters (e.g. "跳过第20-25章")
        skipped_by_user = []
        if skip_indices:
            skipped_by_user = [ch for ch in all_ref_chapters if ch["index"] in skip_indices]
            all_ref_chapters = [ch for ch in all_ref_chapters if ch["index"] not in skip_indices]

        # Check which chapters already exist in current book (by title match)
        existing_titles = set()
        for _idx, title in book_state.get("chapter_titles", {}).items():
            existing_titles.add(title.strip())

        to_import = []
        to_skip_existing = []
        for ch in all_ref_chapters:
            if ch["title"].strip() in existing_titles:
                to_skip_existing.append(ch)
            else:
                to_import.append(ch)

        # ── Limit to max_chapters_per_run ──
        to_import = to_import[:config.max_chapters_per_run]

        # ── Build steps ──
        steps = []
        step_counter = 0
        def sid(n):
            return f"{prefix}_ir_s{n}"

        if not to_import:
            # All chapters already exist or were skipped
            already_msg = f"已有 {len(to_skip_existing)} 章" if to_skip_existing else ""
            skip_msg = f"用户跳过 {len(skipped_by_user)} 章" if skipped_by_user else ""
            parts = [p for p in [already_msg, skip_msg] if p]
            return {
                "plan_summary": f"✅ 所有目标章节已存在或已跳过（{'，'.join(parts)}），无需导入。",
                "chapters": [],
                "steps": [],
                "estimated_chapters": 0,
                "total_steps": 0,
                "intent_type": "import_and_refine",
            }

        # Phase 1: Import — batch import all needed chapters in one step
        import_ids = [ch["chapter_id"] for ch in to_import]
        ref_book_id_for_import = to_import[0]["ref_book_id"]
        ref_book_title_for_import = to_import[0].get("ref_book_title", ref_book_id_for_import)

        steps.append(TaskStep(
            id=sid(0),
            type="agent_loop",
            label=f"从《{ref_book_title_for_import}》导入 {len(to_import)} 章",
            config={
                "prompt": (
                    f"使用 import_reference_chapters 工具批量导入章节：\n"
                    f"- ref_book_id: \"{ref_book_id_for_import}\"\n"
                    f"- 共 {len(to_import)} 章，ID 列表：\n"
                    f"  {json.dumps(import_ids, ensure_ascii=False)}\n\n"
                    f"导入后报告成功数量。如果某些章节已存在会自动跳过。"
                ),
                "agent_type": "plan",
                "mode": "plan",
                "temperature": 0.1,
                "max_rounds": 20,
                "step_category": "import",
            },
        ))
        step_counter = 1

        # Phase 2: Per-chapter refine (read → edit → checkpoint)
        for ch in to_import:
            ch_title = ch["title"]
            ch_index = ch["index"]

            # Read step
            read_sid = sid(step_counter)
            steps.append(TaskStep(
                id=read_sid,
                type="agent_loop",
                label=f"读取《{ref_book_title_for_import}》{ch_title}",
                config={
                    "prompt": (
                        f"使用 read_chapter 读取刚导入的章节（标题：「{ch_title}」）。"
                        f"阅读后简要概括：主要情节、出场角色、关键事件。"
                    ),
                    "agent_type": "plan",
                    "mode": "plan",
                    "temperature": 0.2,
                    "max_rounds": 10,
                    "step_category": "read",
                    "chapter_index": ch_index,
                },
            ))
            step_counter += 1

            # Edit step
            edit_sid = sid(step_counter)
            steps.append(TaskStep(
                id=edit_sid,
                type="agent_loop",
                label=f"精修{ch_title}",
                config={
                    "prompt": (
                        f"对{ch_title}进行精修。\n\n"
                        f"用户指令：「{intent.directive}」\n\n"
                        f"要求：\n"
                        f"1. 使用 patch_chapter 工具进行精准修改\n"
                        f"2. 保持原有情节结构，只调整文笔和表达\n"
                        f"3. 修改完成后简要说明改动内容"
                    ),
                    "agent_type": "edit",
                    "mode": "write",
                    "temperature": 0.3,
                    "max_rounds": 35,
                    "step_category": "edit",
                    "chapter_index": ch_index,
                    "depends_on": [read_sid],
                },
            ))
            step_counter += 1

            # Checkpoint
            steps.append(TaskStep(
                id=sid(step_counter),
                type="checkpoint",
                label=f"{ch_title}精修完成",
                config={
                    "chapter_index": ch_index,
                    "chapter_title": ch_title,
                    "final": False,
                },
            ))
            step_counter += 1

        # Final checkpoint
        steps.append(TaskStep(
            id=sid(step_counter),
            type="checkpoint",
            label=f"全部导入与精修完成（{len(to_import)} 章）",
            config={"final": True},
        ))

        # ── Build summary ──
        skip_parts = []
        if to_skip_existing:
            skip_parts.append(f"已有 {len(to_skip_existing)} 章自动跳过")
        if skipped_by_user:
            skip_parts.append(f"用户跳过 {len(skipped_by_user)} 章")
        skip_note = "（" + "，".join(skip_parts) + "）" if skip_parts else ""

        plan_summary = (
            f"📥 导入精修模式：从《{ref_book_title_for_import}》导入 {len(to_import)} 章"
            f"{skip_note}，逐章精修，共 {len(steps)} 个步骤。"
        )

        return {
            "plan_summary": plan_summary,
            "chapters": [{"index": ch["index"], "title": ch["title"]}
                          for ch in to_import],
            "steps": steps,
            "estimated_chapters": len(to_import),
            "total_steps": len(steps),
            "intent_type": "import_and_refine",
        }

    # ── LLM-Based Planning (for mixed/complex intents) ──

    async def _plan_with_llm(self, prefix: str, config: AutopilotConfig,
                              book_state: dict, intent: PlanIntent) -> dict:
        """Use LLM to generate a custom plan for complex/mixed intents."""
        if not config.use_smart_planner:
            # Fallback to write_new if smart planner disabled
            return self._plan_write_new(prefix, config, book_state, intent)

        # Build book state summary for LLM
        book_summary = self._build_book_state_summary(book_state)

        planner_prompt = f"""书籍状态：
{book_summary}

用户指令：「{config.instruction}」

约束条件：
- 最多处理 {config.max_chapters_per_run} 个章节
- 审核模式: {config.audit_mode}
- 自动评审: {config.auto_review}
- 自动提取: {config.auto_extract}
- 质量门控: {config.quality_gate}

请根据以上信息，输出一个执行计划 JSON。格式：
{{
  "plan_summary": "一句话概述",
  "steps": [
    {{
      "category": "plan|write|edit|extract|review|analyze|checkpoint",
      "label": "步骤标签",
      "prompt": "给agent的详细指令",
      "agent_type": "write|plan|extract|edit|reviewer|consistency",
      "mode": "write|plan",
      "max_rounds": 30,
      "chapter_index": null
    }}
  ]
}}

注意：
- prompt 要具体，告诉 agent 使用什么工具
- 可用工具：delegate_writing, patch_chapter, read_chapter, extract_knowledge,
  find_replace_book, apply_directive_globally, batch_edit_chapters,
  restyle_book, transform_chapters_batch, search_knowledge,
  import_reference_chapters, list_reference_chapters, list_reference_books
- 只输出 JSON，不要加其他内容"""

        try:
            from ..llm_client import chat
            response = await asyncio.to_thread(
                chat, planner_prompt,
                system="你是 Autopilot 任务规划器。输出结构化 JSON 执行计划。",
                temperature=0.2,
                task="general",
            )

            # Parse JSON response
            json_str = response.strip()
            if json_str.startswith("```"):
                json_str = re.sub(r"^```(?:json)?\s*", "", json_str)
                json_str = re.sub(r"\s*```$", "", json_str)

            plan_data = json.loads(json_str)
            steps = self._parse_llm_plan_steps(prefix, plan_data)

            return {
                "plan_summary": plan_data.get("plan_summary", f"智能规划：{config.instruction[:30]}"),
                "chapters": [],
                "steps": steps,
                "estimated_chapters": len([s for s in steps if s.config.get("chapter_index")]),
                "total_steps": len(steps),
                "intent_type": "mixed",
            }

        except (json.JSONDecodeError, Exception) as e:
            logger.warning("LLM planner failed: %s, falling back to write_new", e)
            return self._plan_write_new(prefix, config, book_state, intent)

    def _build_book_state_summary(self, book_state: dict) -> str:
        """Build a concise summary of book state for LLM consumption."""
        lines = [
            f"已有章节数: {book_state['existing_count']}",
            f"总字数: {book_state['total_words']}",
            f"有大纲: {'是' if book_state['has_outline'] else '否'}",
        ]

        if book_state.get("outline_chapters"):
            ch_titles = [ch.get("title", f"第{i+1}章")
                         for i, ch in enumerate(book_state["outline_chapters"][:20])]
            lines.append(f"大纲章节: {', '.join(ch_titles)}")

        existing = sorted(book_state["existing_indices"])
        if existing:
            lines.append(f"已有章节索引: {existing[:20]}{'...' if len(existing) > 20 else ''}")

        return "\n".join(lines)

    def _parse_llm_plan_steps(self, prefix: str, plan_data: dict) -> list[TaskStep]:
        """Parse LLM-generated plan JSON into TaskStep objects."""
        steps = []
        for i, step_data in enumerate(plan_data.get("steps", [])):
            category = step_data.get("category", "write")
            step_type = "checkpoint" if category == "checkpoint" else "agent_loop"

            step = TaskStep(
                id=f"{prefix}_llm_s{i}",
                type=step_type,
                label=step_data.get("label", f"步骤 {i + 1}"),
                config={
                    "prompt": step_data.get("prompt", ""),
                    "agent_type": step_data.get("agent_type", "write"),
                    "mode": step_data.get("mode", "write"),
                    "temperature": step_data.get("temperature", 0.3),
                    "max_rounds": step_data.get("max_rounds", 30),
                    "step_category": category,
                    "chapter_index": step_data.get("chapter_index"),
                },
            )
            steps.append(step)

        # Ensure at least one checkpoint at the end
        if not any(s.type == "checkpoint" for s in steps):
            steps.append(TaskStep(
                id=f"{prefix}_llm_final",
                type="checkpoint",
                label="任务完成",
                config={"final": True},
            ))

        return steps

    # ── Dynamic Replan ──

    async def replan(self, task: "PersistentTask", trigger_reason: str,
                     accumulator=None) -> list[TaskStep]:
        """Replan remaining steps based on execution feedback.

        Called by TaskRunner when a replan trigger fires (step failure,
        quality below threshold, etc). Uses LLM to generate adjusted
        remaining steps.
        """
        prefix = f"replan_{int(time.time() * 1000)}"
        completed_steps = list(task.steps[:task.current_step_index])
        remaining_steps = task.steps[task.current_step_index:]

        # Build replan prompt
        completed_summary = self._summarize_completed(completed_steps, accumulator)
        remaining_summary = self._summarize_remaining(remaining_steps)
        instruction = (task.metadata or {}).get('instruction', '')

        replan_prompt = f"""原始指令: 「{instruction}」
触发原因: {trigger_reason}
已完成步骤: {len(completed_steps)} 个
当前进度: {task.current_step_index}/{len(task.steps)}

已完成的步骤摘要:
{completed_summary}

原计划剩余步骤:
{remaining_summary}

请根据当前情况，输出调整后的剩余步骤序列。
可以: 增加步骤、删除步骤、修改步骤的 prompt、调整步骤顺序。
格式同初始规划（JSON 数组，每个元素包含 category/label/prompt/agent_type/mode/max_rounds）。
如果当前状态已经足够好，可以输出空数组 [] 表示直接完成。
只输出 JSON 数组。"""

        try:
            from ..llm_client import chat
            response = await asyncio.to_thread(
                chat, replan_prompt,
                system="你是 Autopilot 任务规划器。根据执行情况调整后续计划。输出 JSON 数组。",
                temperature=0.2,
                task="general",
            )

            json_str = response.strip()
            if json_str.startswith("```"):
                json_str = re.sub(r"^```(?:json)?\s*", "", json_str)
                json_str = re.sub(r"\s*```$", "", json_str)

            steps_data = json.loads(json_str)
            if not isinstance(steps_data, list):
                steps_data = steps_data.get("steps", [])

            new_steps = []
            for i, step_data in enumerate(steps_data):
                category = step_data.get("category", "write")
                step_type = "checkpoint" if category == "checkpoint" else "agent_loop"
                new_steps.append(TaskStep(
                    id=f"{prefix}_rp_s{i}",
                    type=step_type,
                    label=step_data.get("label", f"调整步骤 {i + 1}"),
                    config={
                        "prompt": step_data.get("prompt", ""),
                        "agent_type": step_data.get("agent_type", "write"),
                        "mode": step_data.get("mode", "write"),
                        "max_rounds": step_data.get("max_rounds", 30),
                        "step_category": category,
                        "chapter_index": step_data.get("chapter_index"),
                    },
                ))

            # Ensure at least a final checkpoint
            if not any(s.type == "checkpoint" for s in new_steps):
                new_steps.append(TaskStep(
                    id=f"{prefix}_rp_final",
                    type="checkpoint",
                    label="调整后任务完成",
                    config={"final": True},
                ))

            return new_steps

        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Replan LLM call failed: %s, skipping replan", e)
            return []  # Empty = don't replan, continue with original plan

    def _summarize_completed(self, steps: list, accumulator=None) -> str:
        """Build a summary of completed steps for the replan prompt."""
        if not steps:
            return "(无)"
        lines = []
        for s in steps:
            status_icon = "✅" if s.status == "completed" else "❌"
            result_text = ""
            if accumulator and s.id in accumulator._results:
                result = accumulator._results[s.id]
                text = result.get('text', '')
                result_text = f" → {text[:100]}..." if len(text) > 100 else f" → {text}"
            elif s.result:
                text = s.result.get('text', '')
                result_text = f" → {text[:100]}..." if len(text) > 100 else f" → {text}"
            lines.append(f"  {status_icon} [{s.label}]{result_text}")
        return "\n".join(lines)

    def _summarize_remaining(self, steps: list) -> str:
        """Build a summary of remaining steps for the replan prompt."""
        if not steps:
            return "(无)"
        lines = []
        for s in steps:
            lines.append(f"  ⬜ [{s.label}] ({s.type})")
        return "\n".join(lines)
