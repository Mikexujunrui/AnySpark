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
    def __init__(self, project_id: str = "default", budget: ContextBudget = None):
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

        # Append pre-calculated structural sections (already budget-reserved)
        sections.extend(structural_sections)

        return "\n".join(sections) if sections else "（知识范围为空，无可用的设定）"

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
    ) -> str:
        """Build context for writing or analysis.

        Args:
            instruction: The writing task description
            relevant_entity_names: Explicitly specified entity names
            mode: "write" (focused context) or "analyze" (full context)
        """
        all_entities = self.store.list_entities()
        if not all_entities:
            return "（知识库为空，无可参考的设定）"

        sections = []
        added_ids = set()
        remaining_budget = self.budget.lore_budget
        shown_relation_pairs = set()

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
            unresolved = [f for f in foreshadows if not f.resolved]
            if unresolved:
                fs_lines = [f"\n## 待回收伏笔 ({len(unresolved)}个)"]
                for f in unresolved[:8]:
                    fs_lines.append(f"- ⏳ {f.text[:40]}")
                    if f.hint:
                        fs_lines.append(f"  暗示: {f.hint[:40]}")
                fs_block = "\n".join(fs_lines)
                if estimate_tokens(fs_block) <= min(remaining_budget, 1000):
                    sections.append(fs_block)

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

        return "\n".join(lines)
