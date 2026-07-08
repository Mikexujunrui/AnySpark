# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Narrative logic engine — constraint checking, impact propagation, confidence scoring.

This package is a **read-mostly** consumer of the existing Neo4j graph.
It does not modify Entity / Relation / Timeline / Foreshadow nodes.
The only write operations are on :Constraint nodes (an independent label).

Import paths are deliberately kept internal:
    from core.narrative_logic import ConstraintChecker, ImpactPropagator, ConfidenceScorer
"""

from .confidence_scorer import ConfidenceScorer
from .constraint_checker import ConstraintChecker
from .constraint_store import ConstraintStore
from .impact_propagator import ImpactPropagator
from .models import (
    Constraint,
    ConstraintViolation,
    EntityScore,
    ImpactReport,
    ImpactSource,
)

__all__ = [
    "Constraint",
    "ConstraintViolation",
    "EntityScore",
    "ImpactReport",
    "ImpactSource",
    "ConstraintStore",
    "ConstraintChecker",
    "ImpactPropagator",
    "ConfidenceScorer",
]
