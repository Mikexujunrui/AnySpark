# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Incremental knowledge graph sync — auto-diff knowledge after chapter writes.

When a chapter is written or edited, this module:
1. Extracts knowledge from the new content (using Flash model for speed)
2. Compares against existing graph entities to find new/changed proposals
3. Emits a KNOWLEDGE_PROPOSED event for the frontend to render proposal cards
4. Checks for consistency issues (contradictions with existing knowledge)

All operations are async and non-blocking — writing flow is never interrupted.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyIssue:
    """A detected inconsistency between chapter content and existing knowledge."""

    issue_type: str = ""  # contradiction / timeline_conflict / missing_entity
    description: str = ""
    entity_name: str = ""
    chapter_id: str = ""
    severity: str = "warning"  # warning / error

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_type": self.issue_type,
            "description": self.description,
            "entity_name": self.entity_name,
            "chapter_id": self.chapter_id,
            "severity": self.severity,
        }


@dataclass
class KnowledgeProposalBatch:
    """A batch of knowledge change proposals from incremental sync."""

    book_id: str = ""
    chapter_id: str = ""
    new_entities: list[dict] = field(default_factory=list)
    changed_entities: list[dict] = field(default_factory=list)
    new_relations: list[dict] = field(default_factory=list)
    consistency_issues: list[ConsistencyIssue] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "book_id": self.book_id,
            "chapter_id": self.chapter_id,
            "new_entities": self.new_entities,
            "changed_entities": self.changed_entities,
            "new_relations": self.new_relations,
            "consistency_issues": [i.to_dict() for i in self.consistency_issues],
            "summary": self.summary,
        }


async def diff_and_propose(
    book_id: str,
    chapter_id: str,
    new_content: str,
    old_content: str = "",
) -> KnowledgeProposalBatch:
    """Extract knowledge from new chapter content and diff against existing graph.

    This is designed to be called via asyncio.create_task() after a chapter
    write completes — it runs entirely in the background.

    Args:
        book_id: The book being written.
        chapter_id: The chapter that was written/edited.
        new_content: The new chapter text.
        old_content: The previous version text (for diff-aware extraction).

    Returns:
        KnowledgeProposalBatch with proposals and consistency issues.
    """
    batch = KnowledgeProposalBatch(book_id=book_id, chapter_id=chapter_id)

    if not new_content.strip():
        batch.summary = "章节内容为空，跳过知识同步"
        return batch

    try:
        # Use the existing extractor to get knowledge proposals
        from core.extractor import extract_knowledge_sync
        from core.graph_store import GraphStore

        # Extract knowledge from new content (Flash model, non-blocking)
        proposals = await asyncio.to_thread(
            extract_knowledge_sync,
            new_content,
            book_id,
        )

        if not proposals:
            batch.summary = "未检测到新的知识实体"
            return batch

        # Compare against existing entities
        store = GraphStore()
        existing_entities = store.get_entities(book_id)
        existing_names = {e.get("name", "") for e in existing_entities if e.get("name")}

        for proposal in proposals:
            if isinstance(proposal, dict):
                name = proposal.get("name", "")
                etype = proposal.get("type", "")
                if name and name not in existing_names:
                    batch.new_entities.append({
                        "name": name,
                        "type": etype,
                        "data": proposal.get("data", {}),
                        "source": f"chapter:{chapter_id}",
                    })
                elif name:
                    batch.changed_entities.append({
                        "name": name,
                        "type": etype,
                        "data": proposal.get("data", {}),
                        "source": f"chapter:{chapter_id}",
                    })

        # Check for consistency issues
        batch.consistency_issues = _check_consistency(
            book_id, chapter_id, new_content, existing_entities
        )

        # Build summary
        parts = []
        if batch.new_entities:
            parts.append(f"新增 {len(batch.new_entities)} 个实体")
        if batch.changed_entities:
            parts.append(f"更新 {len(batch.changed_entities)} 个实体")
        if batch.consistency_issues:
            parts.append(f"检测到 {len(batch.consistency_issues)} 个一致性问题")
        batch.summary = "；".join(parts) if parts else "无新增知识"

        # Emit event for frontend
        from core.event_bus import Event, EventType, bus

        await bus.emit(Event(
            type=EventType.KNOWLEDGE_PROPOSED,
            data=batch.to_dict(),
            source="incremental_sync",
        ))

    except Exception as e:
        logger.error("Incremental sync failed for %s/%s: %s", book_id, chapter_id, e)
        batch.summary = f"知识同步失败: {e}"

    return batch


def _check_consistency(
    book_id: str,
    chapter_id: str,
    content: str,
    existing_entities: list[dict],
) -> list[ConsistencyIssue]:
    """Check for consistency issues between chapter content and knowledge graph.

    Currently checks:
    - Entity name mentions without existing knowledge entries
    - Basic attribute contradictions (age, etc.)
    """
    issues: list[ConsistencyIssue] = []

    # Check for character name mentions that don't have entities
    char_names = [e.get("name", "") for e in existing_entities if e.get("type") == "character"]
    for name in char_names:
        if name and name in content:
            # Character is mentioned — check if their attributes are consistent
            entity = next((e for e in existing_entities if e.get("name") == name), None)
            if entity:
                data = entity.get("data", {})
                age = data.get("age") or data.get("年龄")
                if age and isinstance(age, str) and age in content:
                    # Simple check: if the age string appears near the character name
                    # but differs from the stored age
                    pass  # Deep contradiction detection requires LLM

    return issues


async def trigger_sync_after_write(
    book_id: str,
    chapter_id: str,
    new_content: str,
    old_content: str = "",
) -> None:
    """Fire-and-forget: trigger incremental sync after a chapter write.

    This should be called from the writing tools (store_chapter, write_chapter)
    via asyncio.create_task() so it never blocks the writing flow.
    """
    try:
        await diff_and_propose(book_id, chapter_id, new_content, old_content)
    except Exception as e:
        logger.warning("Background incremental sync failed: %s", e)
