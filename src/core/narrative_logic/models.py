# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Data models for the narrative logic engine.

All dataclasses are plain data containers — no business logic, no Neo4j
calls.  This keeps the storage / scoring / propagation modules decoupled
from the data shape, making them independently testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── Constraint models ───────────────────────────────────────────────

@dataclass
class Constraint:
    """A narrative constraint rule stored as a :Constraint node in Neo4j."""

    id: str
    description: str                        # natural-language rule
    constraint_type: str = "custom"            # entity_state | relation_lock | temporal_order | custom
    target_entity: str = ""                 # entity name or id the rule governs
    condition: dict = field(default_factory=dict)   # structured conditions
    violation_query: str = ""               # Cypher fragment (read-only MATCH/RETURN)
    severity: str = "hard"                  # hard | soft
    status: str = "active"                  # active | disabled
    created_at: str = ""


@dataclass
class ConstraintViolation:
    """Result of checking a single constraint against the graph."""

    constraint_id: str
    description: str
    severity: str
    violations: list[dict] = field(default_factory=list)  # [{entity, detail, ...}]


# ── Impact propagation models ───────────────────────────────────────

@dataclass
class ImpactSource:
    """The origin of a change whose impact we want to propagate."""

    source_type: str        # entity | timeline_event | foreshadow
    source_id: str
    description: str = ""


@dataclass
class ImpactReport:
    """Multi-hop weighted BFS result showing blast radius."""

    source: ImpactSource
    directly_affected: list[dict] = field(default_factory=list)
    indirectly_affected: list[dict] = field(default_factory=list)
    affected_chapters: list[dict] = field(default_factory=list)
    affected_foreshadows: list[dict] = field(default_factory=list)
    blast_radius: int = 0
    max_severity: str = "low"


# ── Confidence scoring models ───────────────────────────────────────

@dataclass
class EntityScore:
    """Confidence score for a single knowledge entity."""

    entity_id: str
    entity_name: str
    entity_type: str
    confidence: float = 0.0
    stars: int = 0
    factors: dict = field(default_factory=dict)
    chapter_mentions: int = 0
    relation_count: int = 0
    contradiction_count: int = 0
    recommendation: str = ""
