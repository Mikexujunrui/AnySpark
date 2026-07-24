# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Confidence scorer — rates each entity on a 0–1 scale.

Three dimensions (simplified, no probability theory):
  1. Reference density  (0–0.4): how many timeline events mention this entity
  2. Relation richness  (0–0.3): how many relationships the entity has
  3. Consistency        (0–0.3): penalised by contradictions from check_consistency

A low score flags underdeveloped or potentially contradictory settings.
"""

from __future__ import annotations

import logging

from core.graph_store import GraphStore

from .models import EntityScore

logger = logging.getLogger(__name__)


class ConfidenceScorer:
    """Read-only graph-topology-based confidence scoring."""

    def __init__(self, store: GraphStore):
        self._store = store

    # ── Public API ──

    def score_all(self) -> list[EntityScore]:
        """Score every entity in the project, sorted high → low."""
        entities = self._store.list_entities()
        scores = [self.score_one(e.id, e.name, e.type) for e in entities]
        scores.sort(key=lambda s: s.confidence, reverse=True)
        return scores

    def score_one(self, entity_id: str, name: str = "", entity_type: str = "") -> EntityScore:
        """Compute a confidence score for a single entity."""
        if not name or not entity_type:
            ent = self._store.get_entity(entity_id)
            if ent:
                name = ent.name
                entity_type = ent.type
            else:
                name = name or entity_id
                entity_type = entity_type or "unknown"

        # Dimension 1: reference density (0–0.4)
        mention_count = self._count_timeline_mentions(entity_id)
        reference_score = min(mention_count / 10.0, 1.0) * 0.4

        # Dimension 2: relation richness (0–0.3)
        relation_count = self._count_relations(entity_id)
        relation_score = min(relation_count / 5.0, 1.0) * 0.3

        # Dimension 3: consistency (0–0.3)
        contradiction_count = self._count_contradictions(entity_id)
        consistency_score = max(1.0 - contradiction_count * 0.2, 0.0) * 0.3

        total = round(reference_score + relation_score + consistency_score, 3)
        stars = max(1, min(5, round(total * 5)))

        # Recommendation
        if contradiction_count > 0:
            recommendation = "存在矛盾，需检查"
        elif total < 0.3:
            recommendation = "设定不足，建议补充关联和引用"
        elif total < 0.5:
            recommendation = "设定较薄，建议增加出场或关系"
        else:
            recommendation = "设定充足"

        return EntityScore(
            entity_id=entity_id,
            entity_name=name,
            entity_type=entity_type,
            confidence=total,
            stars=stars,
            factors={
                "reference": round(reference_score, 3),
                "relation": round(relation_score, 3),
                "consistency": round(consistency_score, 3),
            },
            chapter_mentions=mention_count,
            relation_count=relation_count,
            contradiction_count=contradiction_count,
            recommendation=recommendation,
        )

    # ── Dimension helpers ──

    def _count_timeline_mentions(self, entity_id: str) -> int:
        """Count timeline events that INVOLVE this entity."""
        rows = self._store._run(
            """
            MATCH (t:Timeline {project_id: $pid})-[:INVOLVES]->(e:Entity {id: $eid})
            RETURN count(DISTINCT t) as cnt
        """,
            {"pid": self._store.project_id, "eid": entity_id},
        )
        return rows[0]["cnt"] if rows else 0

    def _count_relations(self, entity_id: str) -> int:
        """Count all relationships (incoming + outgoing) for this entity."""
        rows = self._store._run(
            """
            MATCH (e:Entity {id: $eid, project_id: $pid})-[r]-(other:Entity {project_id: $pid})
            RETURN count(DISTINCT r) as cnt
        """,
            {"pid": self._store.project_id, "eid": entity_id},
        )
        return rows[0]["cnt"] if rows else 0

    def _count_contradictions(self, entity_id: str) -> int:
        """Count consistency issues involving this entity.

        Delegates to the existing GraphStore.check_consistency() and
        filters results that mention the entity's id or name.
        """
        try:
            result = self._store.check_consistency()
            contradictions = result.get("contradictions", [])
            ent = self._store.get_entity(entity_id)
            if not ent:
                return 0
            # Check if entity name appears in any contradiction description
            count = 0
            for c in contradictions:
                desc = c.get("description", "")
                if ent.name in desc or entity_id in desc:
                    count += 1
            return count
        except Exception as e:
            logger.debug("check_consistency failed during scoring: %s", e)
            return 0
