"""Deterministic evidence checks for LLM-extracted novel knowledge.

The extractor may propose facts, but a new entity or relation should not
become canon unless the source chapter contains its named endpoints. These
checks intentionally prefer missing a pronoun-only update over polluting the
knowledge base with an unsupported invention.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from .knowledge import KnowledgeProposal


@dataclass
class GroundingStats:
    dropped_entities: int = 0
    dropped_relations: int = 0
    dropped_updates: int = 0

    @property
    def dropped_total(self) -> int:
        return self.dropped_entities + self.dropped_relations + self.dropped_updates


def _evidence_excerpt(text: str, names: list[str], radius: int = 80) -> tuple[str, str]:
    for raw_name in names:
        name = str(raw_name or "").strip()
        if len(name) < 2:
            continue
        index = text.find(name)
        if index >= 0:
            start = max(0, index - radius)
            end = min(len(text), index + len(name) + radius)
            return name, text[start:end].strip()
    return "", ""


def _source_record(chapter_id: str, chapter_title: str, matched_name: str, excerpt: str) -> dict:
    return {
        "chapter_id": chapter_id,
        "chapter_title": chapter_title,
        "matched_name": matched_name,
        "excerpt": excerpt,
    }


def _append_source(data: dict, source: dict) -> None:
    existing = data.get("_sources", [])
    if not isinstance(existing, list):
        existing = []
    signature = (source["chapter_id"], source["matched_name"], source["excerpt"])
    if not any(
        isinstance(item, dict)
        and (item.get("chapter_id"), item.get("matched_name"), item.get("excerpt")) == signature
        for item in existing
    ):
        existing.append(source)
    data["_sources"] = existing[-12:]


def ground_proposal(
    proposal: KnowledgeProposal,
    source_text: str,
    chapter_id: str,
    chapter_title: str,
) -> tuple[KnowledgeProposal, GroundingStats]:
    """Filter unsupported entities/relations and attach source excerpts."""
    grounded = copy.deepcopy(proposal)
    stats = GroundingStats()
    grounded_entities = []

    for entity in grounded.entities:
        matched_name, excerpt = _evidence_excerpt(source_text, [entity.name, *entity.aliases])
        if not matched_name:
            stats.dropped_entities += 1
            continue
        _append_source(
            entity.data,
            _source_record(chapter_id, chapter_title, matched_name, excerpt),
        )
        grounded_entities.append(entity)
    grounded.entities = grounded_entities

    grounded_relations = []
    for relation in grounded.relations:
        from_match, _ = _evidence_excerpt(source_text, [relation.from_entity])
        to_match, _ = _evidence_excerpt(source_text, [relation.to_entity])
        if not from_match or not to_match:
            stats.dropped_relations += 1
            continue
        relation.data = dict(relation.data or {})
        relation.data["_source_chapter"] = chapter_id
        grounded_relations.append(relation)
    grounded.relations = grounded_relations
    return grounded, stats


def ground_progressive_result(
    result: dict,
    source_text: str,
    chapter_id: str,
    chapter_title: str,
) -> tuple[dict, GroundingStats]:
    """Ground the dictionary schema used by progressive whole-book extraction."""
    grounded = copy.deepcopy(result)
    stats = GroundingStats()

    new_entities = []
    for entity in grounded.get("new_entities", []):
        names = [entity.get("name", ""), *(entity.get("aliases", []) or [])]
        matched_name, excerpt = _evidence_excerpt(source_text, names)
        if not matched_name:
            stats.dropped_entities += 1
            continue
        data = entity.get("data")
        if not isinstance(data, dict):
            data = {}
            entity["data"] = data
        _append_source(data, _source_record(chapter_id, chapter_title, matched_name, excerpt))
        new_entities.append(entity)
    grounded["new_entities"] = new_entities

    updates = []
    for update in grounded.get("updates", []):
        matched_name, excerpt = _evidence_excerpt(source_text, [update.get("name", "")])
        if not matched_name:
            stats.dropped_updates += 1
            continue
        add_data = update.get("add")
        if not isinstance(add_data, dict):
            add_data = {}
            update["add"] = add_data
        _append_source(add_data, _source_record(chapter_id, chapter_title, matched_name, excerpt))
        updates.append(update)
    grounded["updates"] = updates

    for key in ("relations", "spatial_relations"):
        supported = []
        for relation in grounded.get(key, []):
            from_match, _ = _evidence_excerpt(source_text, [relation.get("from", "")])
            to_match, _ = _evidence_excerpt(source_text, [relation.get("to", "")])
            if not from_match or not to_match:
                stats.dropped_relations += 1
                continue
            relation["_source_chapter"] = chapter_id
            supported.append(relation)
        grounded[key] = supported

    return grounded, stats
