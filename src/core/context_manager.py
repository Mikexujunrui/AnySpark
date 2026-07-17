# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Context Manager — fine-grained budget allocation and tiered knowledge loading.

Budget allocation per context source:
  - lore (entities): 30%
  - tool results: 20%
  - conversation history: 20%
  - system instructions: 10%
  - reserve: 20%

Tiered loading:
  - Tier 0 (resident): entities explicitly referenced by name, full detail
  - Tier 1 (index): all entities listed as compact index (name + type + 1-line brief)
  - Tier 2 (on-demand): entities fetched only when agent explicitly asks
"""

import logging
from collections import defaultdict
from dataclasses import dataclass

from .graph_store import GraphStore
from .knowledge import EntityType
from .utils import estimate_tokens

logger = logging.getLogger(__name__)


def _chapter_ref_to_number(chapter_ref: str) -> int | None:
    """Parse a ``#N`` chapter reference into an integer chapter number.

    Returns ``None`` for empty strings, unparseable formats, or extras like
    ``#番外2`` which have no arc ordering anyway. Only leading ``#`` is
    stripped; the remainder must parse as a positive integer.
    """
    if not chapter_ref:
        return None
    s = chapter_ref.strip()
    if s.startswith("#"):
        s = s[1:]
    if not s:
        return None
    # "番外1", "E1", etc. — extras don't participate in arc ordering.
    if not s.isdigit():
        return None
    try:
        n = int(s)
    except ValueError:
        return None
    return n if n > 0 else None


@dataclass
class ContextBudget:
    total_tokens: int = 32000
    lore_ratio: float = 0.30
    tool_results_ratio: float = 0.20
    history_ratio: float = 0.20
    system_ratio: float = 0.10
    reserve_ratio: float = 0.20

    @property
    def lore_budget(self) -> int:
        return int(self.total_tokens * self.lore_ratio)

    @property
    def tool_budget(self) -> int:
        return int(self.total_tokens * self.tool_results_ratio)

    @property
    def history_budget(self) -> int:
        return int(self.total_tokens * self.history_ratio)

    @property
    def system_budget(self) -> int:
        return int(self.total_tokens * self.system_ratio)

    @property
    def reserve_budget(self) -> int:
        return int(self.total_tokens * self.reserve_ratio)



class ContextManager:
    def __init__(self, project_id: str = "default", budget: ContextBudget | None = None):
        self.store = GraphStore(project_id)
        self.store.init_schema()
        self.project_id = project_id
        self.budget = budget or ContextBudget(total_tokens=120000)

    def build_scoped_context(self, scope) -> str:
        """基于 WritingKnowledgeScope 构建精选上下文——仅包含白名单内的实体。"""
        from .knowledge_scope import ExposureLevel, WritingKnowledgeScope

        if not isinstance(scope, WritingKnowledgeScope):
            return self.build_writing_context()

        # Derive current chapter number from scope.chapter_ref so we can
        # pick character arc phases automatically. ``#5`` → 5, ``#番外2`` →
        # ignored (extras have no arc ordering). Safe to ignore: if we can't
        # determine the number we just fall back to entity.data.
        _chapter_ref_to_number(scope.chapter_ref)

        all_entities = self.store.list_entities()
        name_to_entity = {}
        for e in all_entities:
            name_to_entity[e.name] = e
            for a in e.aliases:
                name_to_entity[a] = e

        # ── Pre-calculate budget for structural constraints (outline, rules, etc.) ──
        structural_sections = []
        if scope.chapter_outline:
            structural_sections.append(f"\n## 本章大纲\n{scope.chapter_outline}")
        if scope.prev_chapter_summary:
            structural_sections.append(f"\n## 前情提要\n{scope.prev_chapter_summary}")
        if scope.prev_chapter_issues:
            issues_text = "\n".join(f"- {i}" for i in scope.prev_chapter_issues[:5])
            structural_sections.append(f"\n## 上一章发现的问题（本章请避免）\n{issues_text}")
        if scope.writing_rules:
            structural_sections.append(f"\n## 写作规则\n{scope.writing_rules}")
        if scope.forbidden_characters:
            structural_sections.append("\n## 禁止出场\n" + ", ".join(f"✕{c}" for c in scope.forbidden_characters))
        if scope.forbidden_revelations:
            structural_sections.append("\n## 禁止揭露\n" + ", ".join(scope.forbidden_revelations))
        if scope.style_requirements:
            structural_sections.append(f"\n## 风格要求\n{scope.style_requirements}")
        if scope.target_word_count:
            structural_sections.append(f"\n目标字数: {scope.target_word_count} 字")
        # Inject analysis-layer constraints (from reference_analyzer)
        if scope.style_fingerprint:
            try:
                from .reference_analyzer import StyleFingerprint
                fp = StyleFingerprint(**scope.style_fingerprint)
                fragment = fp.to_prompt_fragment()
                if fragment:
                    structural_sections.append(fragment)
            except Exception:
                pass  # best-effort injection
        if scope.structure_report:
            try:
                from .reference_analyzer import StructureReport
                sr = StructureReport(**scope.structure_report)
                fragment = sr.to_prompt_fragment()
                if fragment:
                    structural_sections.append(f"\n## 原著结构参考\n{fragment}")
            except Exception:
                pass  # best-effort injection
        # Inject deep style constraints (from reference_analyzer deep analysis)
        if scope.sentence_rhythm:
            try:
                from .reference_analyzer import SentenceRhythm
                sr = SentenceRhythm(**scope.sentence_rhythm)
                fragment = sr.to_prompt_fragment()
                if fragment:
                    structural_sections.append(fragment)
            except Exception:
                pass
        if scope.rhetoric_density:
            try:
                from .reference_analyzer import RhetoricDensity
                rd = RhetoricDensity(**scope.rhetoric_density)
                fragment = rd.to_prompt_fragment()
                if fragment:
                    structural_sections.append(fragment)
            except Exception:
                pass
        if scope.prophecy_signature:
            try:
                from .reference_analyzer import ProphecySignature
                ps = ProphecySignature(**scope.prophecy_signature)
                fragment = ps.to_prompt_fragment()
                if fragment:
                    structural_sections.append(fragment)
            except Exception:
                pass
        if scope.narrative_pov:
            try:
                from .reference_analyzer import NarrativePOVSignature
                np = NarrativePOVSignature(**scope.narrative_pov)
                fragment = np.to_prompt_fragment()
                if fragment:
                    structural_sections.append(fragment)
            except Exception:
                pass
        if scope.emotional_curve:
            try:
                from .emotion_analyzer import EmotionalCurve
                ec = EmotionalCurve(**scope.emotional_curve)
                fragment = ec.to_prompt_fragment()
                if fragment:
                    structural_sections.append(fragment)
            except Exception:
                pass

        structural_budget = estimate_tokens("\n".join(structural_sections))
        total_lore_budget = self.budget.lore_budget
        entity_budget = max(total_lore_budget - structural_budget, int(total_lore_budget * 0.5))

        sections = []
        remaining_budget = entity_budget
        shown_relation_pairs = set()

        type_groups = [
            ("character", "人物", scope.characters),
            ("location", "地点", scope.locations),
            ("concept", "世界观设定", scope.concepts),
            ("item", "物品/法宝", scope.items),
        ]

        for _, label, exposures in type_groups:
            if not exposures:
                continue
            section_lines = [f"\n## {label}"]
            for exp in exposures:
                entity = name_to_entity.get(exp.entity_name)
                if not entity:
                    section_lines.append(f"- ⚠️ {exp.entity_name}（知识库中未找到）")
                    continue

                if exp.level == ExposureLevel.FULL:
                    phase_override, phase_label = (
                        self._resolve_phase_for_entity(entity)
                    )
                    block = self._format_entity_detail(
                        entity, all_entities, self.store,
                        shown_relation_pairs,
                        data_override=phase_override,
                        phase_label=phase_label,
                    )
                elif exp.level == ExposureLevel.SUMMARY:
                    phase_override, phase_label = (
                        self._resolve_phase_for_entity(entity)
                    )
                    block = self._format_entity_summary(
                        entity, data_override=phase_override, phase_label=phase_label,
                    )
                elif exp.level == ExposureLevel.NAME_ONLY:
                    block = f"- {entity.name}（仅提及）"
                else:
                    continue

                if estimate_tokens("\n".join(section_lines + [block])) <= remaining_budget:
                    section_lines.append(block)
                    remaining_budget -= estimate_tokens(block)
                else:
                    section_lines.append(f"- ...（预算不足，省略 {exp.entity_name}）")
                    continue

            sections.extend(section_lines)

        # ── Graph-aware: relationship topology between scope entities ──
        scope_entity_ids = []
        for exp_list in [scope.characters, scope.locations, scope.concepts, scope.items]:
            for exp in exp_list:
                entity = name_to_entity.get(exp.entity_name)
                if entity:
                    scope_entity_ids.append(entity.id)

        if len(scope_entity_ids) >= 2:
            try:
                shared_conns = self.store.find_share_connections(scope_entity_ids)
                if shared_conns:
                    entity_by_id = {e.id: e for e in all_entities}
                    rel_lines = ["\n## 角色关系网"]
                    for conn in shared_conns:
                        from_e = entity_by_id.get(conn["from"])
                        to_e = entity_by_id.get(conn["to"])
                        if from_e and to_e:
                            rel_lines.append(
                                f"- {from_e.name} --[{conn['type']}]--> {to_e.name}"
                            )
                    rel_block = "\n".join(rel_lines)
                    rel_tokens = estimate_tokens(rel_block)
                    if rel_tokens <= min(remaining_budget, 800):
                        sections.append(rel_block)
                        remaining_budget -= rel_tokens
            except Exception:
                logger.debug("Scope relationship topology query failed", exc_info=True)

        # ── Graph-aware: scheduled foreshadows (active resolution tasks) ──
        # These are foreshadows the user has explicitly confirmed for this chapter.
        # They are injected as ACTIVE tasks, not passive reminders.
        chapter_ref = scope.chapter_ref or ""
        if remaining_budget > 300 and scope_entity_ids:
            try:
                scheduled = self.store.list_scheduled_foreshadows(chapter=chapter_ref)
                scope_scheduled = []
                for f in scheduled:
                    related = set(f.related_entities)
                    if related & set(scope_entity_ids):
                        scope_scheduled.append(f)
                if scope_scheduled:
                    fs_lines = [f"\n## ⚠️ 本章需回收的伏笔 ({len(scope_scheduled)}个) — 必须在本章回收"]
                    for f in scope_scheduled[:6]:
                        plant_info = f" (埋设于{f.plant_chapter})" if f.plant_chapter else ""
                        fs_lines.append(f"- 🔴 回收: {f.text[:60]}{plant_info}")
                        if f.expected_resolution:
                            fs_lines.append(f"  预期回收方式: {f.expected_resolution[:60]}")
                        if f.hint:
                            fs_lines.append(f"  暗示: {f.hint[:40]}")
                    fs_block = "\n".join(fs_lines)
                    fs_tokens = estimate_tokens(fs_block)
                    if fs_tokens <= min(remaining_budget, 800):
                        sections.append(fs_block)
                        remaining_budget -= fs_tokens
            except Exception:
                logger.debug("Scheduled foreshadow query failed", exc_info=True)

        # ── Graph-aware: open foreshadows (passive reminders) ──
        # These are foreshadows without a resolution plan. They are injected as
        # reminders — the LLM should NOT actively resolve them without user approval.
        if remaining_budget > 300 and scope_entity_ids:
            try:
                foreshadows = self.store.list_foreshadows(status="open")
                scope_fores = []
                for f in foreshadows:
                    related = set(f.related_entities)
                    if related & set(scope_entity_ids):
                        scope_fores.append(f)
                if scope_fores:
                    fs_lines = [f"\n## 本章需注意的伏笔 ({len(scope_fores)}个) — 仅供参考，请勿主动回收"]
                    for f in scope_fores[:6]:
                        plant_info = f" (埋设于{f.plant_chapter})" if f.plant_chapter else ""
                        fs_lines.append(f"- [待规划] {f.text[:60]}{plant_info}")
                        if f.hint:
                            fs_lines.append(f"  暗示: {f.hint[:40]}")
                    fs_block = "\n".join(fs_lines)
                    fs_tokens = estimate_tokens(fs_block)
                    if fs_tokens <= min(remaining_budget, 600):
                        sections.append(fs_block)
                        remaining_budget -= fs_tokens
            except Exception:
                logger.debug("Scope foreshadow query failed", exc_info=True)

        # ── Graph-aware: active narrative constraints for scope entities ──
        if remaining_budget > 200 and scope_entity_ids:
            try:
                from .narrative_logic import ConstraintStore
                constraint_store = ConstraintStore(self.store)
                constraints = constraint_store.list(active_only=True)
                if constraints:
                    scope_names = {exp.entity_name
                                   for exp_list in [scope.characters, scope.locations,
                                                    scope.concepts, scope.items]
                                   for exp in exp_list}
                    relevant = [c for c in constraints
                                if not c.target_entity
                                or c.target_entity in scope_names
                                or any(name in c.description for name in scope_names)]
                    if relevant:
                        cs_lines = [f"\n## 叙事约束 ({len(relevant)}条)"]
                        for c in relevant[:8]:
                            sev = "🔴" if c.severity == "hard" else "🟡"
                            cs_lines.append(f"- {sev} [{c.severity}] {c.description}")
                        cs_block = "\n".join(cs_lines)
                        cs_tokens = estimate_tokens(cs_block)
                        if cs_tokens <= min(remaining_budget, 500):
                            sections.append(cs_block)
                            remaining_budget -= cs_tokens
            except Exception:
                logger.debug("Scope constraint query failed", exc_info=True)

        # Append pre-calculated structural sections (already budget-reserved)
        sections.extend(structural_sections)

        # ── Character voice injection (only if scope.inject_voice_constraints) ──
        if scope.inject_voice_constraints and scope.characters and remaining_budget > 400:
            try:
                from .voice_fingerprint import build_voice_prompt, get_character_voice
                voice_lines = ["\n## 角色对话风格约束"]
                for exp in scope.characters[:5]:
                    if exp.level.value == "full":
                        fp = get_character_voice(self.project_id, exp.entity_name)
                        if fp and fp.dialogue_count >= 3:
                            prompt = build_voice_prompt(fp)
                            if prompt:
                                voice_lines.append(f"\n{prompt}")
                if len(voice_lines) > 1:
                    voice_block = "\n".join(voice_lines)
                    voice_tokens = estimate_tokens(voice_block)
                    if voice_tokens <= min(remaining_budget, 800):
                        sections.append(voice_block)
                        remaining_budget -= voice_tokens
            except Exception:
                logger.debug("Voice fingerprint injection failed", exc_info=True)

        # ── Annotation constraint injection (only if scope.inject_annotation_constraints) ──
        if scope.inject_annotation_constraints and remaining_budget > 300:
            try:
                from .annotation_engine import build_annotation_constraints
                chapter_num = _chapter_ref_to_number(scope.chapter_ref)
                ann_text = build_annotation_constraints(self.project_id, chapter_num)
                if ann_text:
                    ann_tokens = estimate_tokens(ann_text)
                    if ann_tokens <= min(remaining_budget, 600):
                        sections.append(f"\n{ann_text}")
                        remaining_budget -= ann_tokens
            except Exception:
                logger.debug("Annotation constraint injection failed", exc_info=True)

        # ── Memory system: Tier 2 auto-promotion ──
        # When the writing scope contains keywords matching user preferences,
        # inject relevant preference entries for the writer's reference.
        if remaining_budget > 200:
            try:
                from core.memory import get_memory_manager
                mm = get_memory_manager()
                if mm:
                    keywords = mm.triggers.extract_keywords_from_scope(scope)
                    if keywords:
                        pref_text = mm.inject_tier2(keywords)
                        if pref_text:
                            pref_tokens = estimate_tokens(pref_text)
                            if pref_tokens <= min(remaining_budget, 600):
                                sections.append(f"\n{pref_text}")
                                remaining_budget -= pref_tokens
            except Exception:
                logger.debug("Memory Tier 2 injection failed", exc_info=True)

        return "\n".join(sections) if sections else "（知识范围为空，无可用的设定）"

    def get_pending_foreshadows(self, scope) -> list:
        """Return foreshadows that need user attention before writing.

        Returns a list of dicts with keys: id, text, hint, plant_chapter,
        planned_resolve_arc, status. These are foreshadows in 'planned' or
        'due' status that involve scope entities.

        The writing flow should call this before writing and prompt the user
        to confirm/reschedule/postpone.
        """
        from .knowledge_scope import WritingKnowledgeScope

        if not isinstance(scope, WritingKnowledgeScope):
            return []

        scope_entity_ids = []
        all_entities = self.store.list_entities()
        name_to_entity = {e.name: e for e in all_entities}
        for a in all_entities:
            for alias in a.aliases:
                name_to_entity[alias] = a

        for exp_list in [scope.characters, scope.locations, scope.concepts, scope.items]:
            for exp in exp_list:
                entity = name_to_entity.get(exp.entity_name)
                if entity:
                    scope_entity_ids.append(entity.id)

        if not scope_entity_ids:
            return []

        result = []
        try:
            # Check 'planned' — user set an arc but not yet due
            planned = self.store.list_foreshadows(status="planned")
            for f in planned:
                related = set(f.related_entities)
                if related & set(scope_entity_ids):
                    result.append({
                        "id": f.id, "text": f.text, "hint": f.hint,
                        "plant_chapter": f.plant_chapter,
                        "planned_resolve_arc": f.planned_resolve_arc,
                        "status": "planned",
                        "expected_resolution": f.expected_resolution,
                    })

            # Check 'due' — arc is active, waiting for user confirmation
            due = self.store.list_foreshadows(status="due")
            for f in due:
                related = set(f.related_entities)
                if related & set(scope_entity_ids):
                    result.append({
                        "id": f.id, "text": f.text, "hint": f.hint,
                        "plant_chapter": f.plant_chapter,
                        "planned_resolve_arc": f.planned_resolve_arc,
                        "status": "due",
                        "expected_resolution": f.expected_resolution,
                    })
        except Exception:
            logger.debug("get_pending_foreshadows query failed", exc_info=True)

        return result

    def _resolve_phase_for_entity(self, entity) -> tuple[dict | None, str]:
        """Return (phase_data, phase_label) for a character entity.

        Phase selection is **order-based and decoupled from chapters**: the
        current phase (``is_current``) is used, falling back to the most recent
        phase by ``time_order``. Returns ``(None, "")`` for non-character
        entities or characters with no phase snapshots — callers then fall back
        to ``entity.data``.
        """
        if entity.type != EntityType.CHARACTER:
            return None, ""
        phase = self.store.get_current_phase(entity.id)
        if phase is None:
            return None, ""
        data = dict(phase.data) if phase.data else {}
        label = phase.phase or phase.label or ""
        return data, label

    def _format_entity_summary(self, entity, data_override: dict | None = None,
                                phase_label: str = "") -> str:
        """紧凑摘要：名字 + 3-5 个关键字段。如果提供 data_override，用它替代 entity.data。"""
        parts = [f"\n### {entity.name}"]
        if phase_label:
            parts[0] += f"  [阶段: {phase_label}]"
        if entity.aliases:
            parts[0] += f"（{', '.join(entity.aliases[:2])}）"
        data = data_override if data_override is not None else entity.data
        key_fields = ["personality", "role", "abilities", "appearance", "background",
                      "description", "location", "function", "effect", "rules",
                      "motivation", "relationships", "growth_note"]
        shown = 0
        for key in key_fields:
            val = data.get(key, "")
            if val and shown < 5:
                parts.append(f"- **{key}**: {str(val)[:80]}")
                shown += 1
        if shown == 0:
            for k, v in data.items():
                if v and isinstance(v, str):
                    parts.append(f"- **{k}**: {v[:80]}")
                    shown += 1
                    if shown >= 5:
                        break
        return "\n".join(parts)

    def build_writing_context(
        self,
        instruction: str = "",
        relevant_entity_names: list[str] | None = None,
        mode: str = "write",
        chapter_number: int | None = None,
        pov_character_id: str | None = None,
    ) -> str:
        """Build context for writing or analysis.

        Args:
            instruction: The writing task description
            relevant_entity_names: Explicitly specified entity names
            mode: "write" (focused context) or "analyze" (full context)
            chapter_number: Current chapter for phase selection
            pov_character_id: P2-15 — filter context to POV character's visible world.
                When combined with chapter_number, also applies P2-6 knowledge horizon.
        """
        all_entities = self.store.list_entities()
        if not all_entities:
            return "（知识库为空，无可参考的设定）"

        sections = []
        added_ids = set()
        remaining_budget = self.budget.lore_budget
        shown_relation_pairs = set()

        # ── P2-15: POV perspective filtering ──
        # Only include entities visible from the POV character's perspective:
        # direct relationships + entities from shared timeline events.
        # P2-6: When chapter_number is also provided, further filter by what
        # the character knows at that chapter (knowledge horizon).
        if pov_character_id:
            try:
                pov = self.store.get_pov_subgraph(pov_character_id)
                visible_ids = {e["id"] for e in pov["visible_entities"]}
                visible_ids.add(pov_character_id)
                if chapter_number is not None:
                    knowledge = self.store.get_character_knowledge(
                        pov_character_id, chapter_number
                    )
                    known_ids = {e["id"] for e in knowledge["known_entities"]}
                    known_ids.add(pov_character_id)
                    visible_ids = visible_ids & known_ids
                all_entities = [e for e in all_entities if e.id in visible_ids]
                sections.append(
                    f"\n## 视角限制\n当前以角色视角过滤上下文，"
                    f"仅注入该角色可感知的 {len(all_entities)} 个实体。"
                )
            except Exception:
                logger.debug("POV/knowledge horizon filtering failed", exc_info=True)

        # ── Tier 0: Resident entities explicitly referenced ──
        if relevant_entity_names:
            name_idx = {e.name: e for e in all_entities}
            alias_idx: dict[str, list] = defaultdict(list)
            for e in all_entities:
                for a in e.aliases:
                    alias_idx[a].append(e)

            resident = []
            for name in relevant_entity_names:
                if name in name_idx:
                    resident.append(name_idx[name])
                elif name in alias_idx:
                    resident.extend(alias_idx[name])

            for e in resident:
                if e.id not in added_ids:
                    phase_override, phase_label = self._resolve_phase_for_entity(
                        e,
                    )
                    block = self._format_entity_detail(
                        e, all_entities, self.store,
                        shown_relation_pairs,
                        data_override=phase_override,
                        phase_label=phase_label,
                    )
                    if remaining_budget - estimate_tokens(block) > 0:
                        sections.append(block)
                        added_ids.add(e.id)
                        remaining_budget -= estimate_tokens(block)

            # ── P0-4: Scene configuration — mutual relationships between co-occurring entities ──
            # Activates the previously dormant find_share_connections() method.
            # When multiple entities appear in the same chapter, inject their
            # mutual relationship matrix so the LLM understands scene dynamics.
            resident_added = [e for e in resident if e.id in added_ids]
            if len(resident_added) >= 2:
                try:
                    shared_conns = self.store.find_share_connections(
                        [e.id for e in resident_added]
                    )
                    if shared_conns:
                        entity_by_id = {e.id: e for e in all_entities}
                        scene_lines = ["\n## 同场实体关系矩阵"]
                        for conn in shared_conns:
                            from_e = entity_by_id.get(conn["from"])
                            to_e = entity_by_id.get(conn["to"])
                            if from_e and to_e:
                                scene_lines.append(
                                    f"- {from_e.name} ↔[{conn['type']}]↔ {to_e.name}"
                                )
                        scene_block = "\n".join(scene_lines)
                        if estimate_tokens(scene_block) <= min(remaining_budget, 500):
                            sections.append(scene_block)
                            remaining_budget -= estimate_tokens(scene_block)
                except Exception:
                    logger.debug("Scene configuration query failed", exc_info=True)

        # ── Tier 1: Index of entities (compact brief) ──
        remaining = [e for e in all_entities if e.id not in added_ids]

        # In "write" mode, filter to entities mentioned in instruction
        if mode == "write" and instruction:
            instr_lower = instruction.lower()
            remaining = [e for e in remaining
                         if e.name.lower() in instr_lower
                         or any(a.lower() in instr_lower for a in e.aliases)]

        if remaining and remaining_budget > 200:
            index_lines = []
            for etype in EntityType.BUILTIN:
                type_entities = [e for e in remaining if e.type == etype]
                if not type_entities:
                    continue
                label = {
                    EntityType.CHARACTER: "人物",
                    EntityType.LOCATION: "地点",
                    EntityType.ORGANIZATION: "组织/势力",
                    EntityType.CONCEPT: "世界观设定",
                    EntityType.ITEM: "物品/法宝",
                    EntityType.EVENT: "关键事件",
                }.get(etype, etype.title())

                index_lines.append(f"\n  [{label}]")
                for e in type_entities:
                    brief = self._entity_brief(e)
                    line = f"    - {e.name}{brief}"
                    if estimate_tokens("\n".join(index_lines + [line])) > remaining_budget:
                        index_lines.append(f"    ... ({len(type_entities)}个中的剩余未显示)")
                        break
                    index_lines.append(line)
                    added_ids.add(e.id)

            if index_lines:
                sections.append("\n" + "\n".join(index_lines))

        # ── Foreshadow summary (if budget remains) ──
        if remaining_budget > 500:
            foreshadows = self.store.list_foreshadows(resolved=None)
            open_fs = [f for f in foreshadows if f.status == "open"]
            dangling_fs = [f for f in foreshadows if f.status == "dangling"]
            cross_vol_fs = [f for f in foreshadows if f.status == "cross_volume"]
            if open_fs:
                fs_lines = [f"\n## 待回收伏笔 ({len(open_fs)}个)"]
                for f in open_fs[:8]:
                    overdue = ""
                    if f.source == "planted" and f.planned_resolve_arc:
                        overdue = f" [计划回收弧: {f.planned_resolve_arc}]"
                    plant_info = f" (埋设于{f.plant_chapter})" if f.plant_chapter else ""
                    fs_lines.append(f"- ⏳ {f.text[:40]}{plant_info}{overdue}")
                    if f.hint:
                        fs_lines.append(f"  暗示: {f.hint[:40]}")
                fs_block = "\n".join(fs_lines)
                if estimate_tokens(fs_block) <= min(remaining_budget, 1000):
                    sections.append(fs_block)
                    remaining_budget -= estimate_tokens(fs_block)
            if cross_vol_fs and remaining_budget > 200:
                cv_lines = [f"\n## 跨卷伏笔 ({len(cross_vol_fs)}个)"]
                for f in cross_vol_fs[:3]:
                    vol_info = f" [{f.volume_ref}]" if f.volume_ref else ""
                    cv_lines.append(f"- 📖 {f.text[:40]}{vol_info}")
                cv_block = "\n".join(cv_lines)
                if estimate_tokens(cv_block) <= min(remaining_budget, 300):
                    sections.append(cv_block)
                    remaining_budget -= estimate_tokens(cv_block)
            if dangling_fs and remaining_budget > 200:
                dg_lines = [f"\n## 悬置线索 ({len(dangling_fs)}个)"]
                for f in dangling_fs[:3]:
                    conf = f" [置信度: {f.confidence}]" if f.confidence != "high" else ""
                    dg_lines.append(f"- ❓ {f.text[:40]}{conf}")
                dg_block = "\n".join(dg_lines)
                if estimate_tokens(dg_block) <= min(remaining_budget, 300):
                    sections.append(dg_block)

        return "\n".join(sections)

    def _entity_brief(self, entity) -> str:
        parts = []
        if entity.aliases:
            parts.append(f"（{', '.join(entity.aliases[:2])}）")
        for k, v in entity.data.items():
            if isinstance(v, str) and v:
                parts.append(f"{k}={v[:20]}")
                break
        return " " + "; ".join(parts[:2]) if parts else ""

    def _format_entity_detail(self, entity, all_entities: list, store,
                              shown_relation_pairs: set | None = None,
                              data_override: dict | None = None,
                              phase_label: str = "") -> str:
        label = {
            EntityType.CHARACTER: "## 人物",
            EntityType.LOCATION: "## 地点",
            EntityType.ORGANIZATION: "## 组织/势力",
            EntityType.CONCEPT: "## 世界观设定",
            EntityType.ITEM: "## 物品/法宝",
            EntityType.EVENT: "## 关键事件",
        }.get(entity.type, f"## {entity.type}")

        title_line = f"### {entity.name}"
        if phase_label:
            title_line += f"  [阶段: {phase_label}]"
        aliases = f"（{', '.join(entity.aliases)}）" if entity.aliases else ""
        lines = [f"\n{label}", f"{title_line} {aliases}"]
        data = data_override if data_override is not None else entity.data
        for key, value in data.items():
            if value:
                lines.append(f"- **{key}**: {value}")

        entity_by_id = {e.id: e for e in all_entities}
        relations = store.list_relations(entity.id)
        if relations:
            shown_count = 0
            for r in relations:
                if shown_count >= 6:
                    break
                other_id = r.to_entity if r.from_entity == entity.id else r.from_entity
                # Deduplicate: skip if this pair was already shown for another entity
                pair_key = tuple(sorted([entity.id, other_id]))
                if shown_relation_pairs is not None and pair_key in shown_relation_pairs:
                    continue
                other = entity_by_id.get(other_id)
                if other:
                    direction = "→" if r.from_entity == entity.id else "←"
                    lines.append(f"- {direction} [{r.type}] {other.name}")
                    if shown_relation_pairs is not None:
                        shown_relation_pairs.add(pair_key)
                    shown_count += 1

        # ── P0-5: Multi-hop indirect relationships (activates get_neighbors) ──
        # Discover entities reachable in 2 hops that aren't already direct
        # relations. This surfaces indirect connections like "A knows B, B knows C"
        # so the LLM doesn't write "A has never heard of C" when they share
        # a mutual acquaintance.
        direct_ids = {
            r.to_entity if r.from_entity == entity.id else r.from_entity
            for r in relations
        } if relations else set()
        try:
            neighbors = store.get_neighbors(entity.id, depth=2)
            indirect = [
                n for n in neighbors
                if n["entity"].id != entity.id
                and n["entity"].id not in direct_ids
            ]
            if indirect:
                lines.append(f"- 🔄 间接关联 ({len(indirect)}个):")
                for n in indirect[:4]:
                    path_desc = " → ".join(n["path"])
                    lines.append(f"  通过 [{path_desc}] → {n['entity'].name}")
        except Exception:
            logger.debug("Multi-hop neighbor query failed", exc_info=True)

        return "\n".join(lines)
