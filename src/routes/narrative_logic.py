# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""REST API for narrative logic features.

Endpoints:
  POST   /books/{bid}/narrative/constraints        — create constraint
  GET    /books/{bid}/narrative/constraints        — list constraints
  DELETE /books/{bid}/narrative/constraints/{cid}  — delete constraint
  POST   /books/{bid}/narrative/constraints/check  — check all constraints
  POST   /books/{bid}/narrative/impact             — impact propagation
  GET    /books/{bid}/narrative/confidence          — confidence scores
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.graph_store import get_store
from core.narrative_logic import (
    ConfidenceScorer,
    ConstraintChecker,
    ConstraintStore,
    ImpactPropagator,
    ImpactSource,
)

router = APIRouter(tags=["narrative-logic"])


# ── Request models ──


class CreateConstraintRequest(BaseModel):
    description: str
    constraint_type: str = "custom"
    target_entity: str = ""
    condition: dict = {}
    violation_query: str = ""
    severity: str = "hard"


class CheckConstraintsRequest(BaseModel):
    chapter_id: str = ""


class ImpactRequest(BaseModel):
    source_type: str = "entity"
    source_id: str = ""
    change_description: str = ""


# ── Constraint endpoints ──


@router.post("/books/{book_id}/narrative/constraints")
def create_constraint(book_id: str, req: CreateConstraintRequest):
    kb = get_store(book_id)
    store = ConstraintStore(kb)
    c = store.add(
        description=req.description,
        constraint_type=req.constraint_type,
        target_entity=req.target_entity,
        condition=req.condition,
        violation_query=req.violation_query,
        severity=req.severity,
    )
    return asdict(c)


@router.get("/books/{book_id}/narrative/constraints")
def list_constraints(book_id: str, active_only: bool = True):
    kb = get_store(book_id)
    store = ConstraintStore(kb)
    return [asdict(c) for c in store.list(active_only=active_only)]


@router.delete("/books/{book_id}/narrative/constraints/{constraint_id}")
def delete_constraint(book_id: str, constraint_id: str):
    kb = get_store(book_id)
    store = ConstraintStore(kb)
    existing = store.get(constraint_id)
    if not existing:
        raise HTTPException(404, f"约束 {constraint_id} 不存在")
    store.delete(constraint_id)
    return {"ok": True, "deleted": constraint_id}


@router.post("/books/{book_id}/narrative/constraints/check")
def check_constraints(book_id: str, req: CheckConstraintsRequest | None = None):
    kb = get_store(book_id)
    checker = ConstraintChecker(kb)
    violations = checker.check_all()
    return {
        "total_checked": len(ConstraintStore(kb).list(active_only=True)),
        "violations_found": len(violations),
        "violations": [asdict(v) for v in violations],
    }


# ── Impact propagation endpoint ──


@router.post("/books/{book_id}/narrative/impact")
def analyze_impact(book_id: str, req: ImpactRequest):
    kb = get_store(book_id)
    propagator = ImpactPropagator(kb)
    source = ImpactSource(
        source_type=req.source_type,
        source_id=req.source_id,
        description=req.change_description,
    )
    report = propagator.propagate(source)
    return asdict(report)


# ── Confidence scoring endpoint ──


@router.get("/books/{book_id}/narrative/confidence")
def get_confidence_scores(book_id: str, entity_id: str = ""):
    kb = get_store(book_id)
    scorer = ConfidenceScorer(kb)
    if entity_id:
        score = scorer.score_one(entity_id)
        return asdict(score)
    scores = scorer.score_all()
    return [asdict(s) for s in scores]


# ── Foreshadow matching endpoint ──


@router.get("/books/{book_id}/foreshadow-matches")
def foreshadow_matches(book_id: str):
    """Return auto-matched foreshadow-payoff pairs and dangling foreshadows."""
    from core.foreshadow_matcher import foreshadow_summary

    return foreshadow_summary(book_id)


@router.post("/books/{book_id}/foreshadow-matches/refresh")
def refresh_foreshadow_matches(book_id: str):
    """Force recompute foreshadow matches."""
    from core.foreshadow_matcher import foreshadow_summary

    return foreshadow_summary(book_id)


# ── Chapter dependency graph endpoint ──


@router.get("/books/{book_id}/chapter-dependencies")
def chapter_dependencies(book_id: str):
    """Return chapter dependency graph data."""
    from core.chapter_dependency import build_and_visualize

    return build_and_visualize(book_id)


@router.post("/books/{book_id}/chapter-dependencies/impact")
def chapter_dependency_impact(book_id: str, req: ImpactRequest):
    """Return impact propagation for a modified chapter."""
    from core.chapter_dependency import propagate_impact_by_id

    affected = propagate_impact_by_id(book_id, req.source_id)
    return {
        "book_id": book_id,
        "modified_chapter": req.source_id,
        "affected_chapters": affected,
        "total_affected": len(affected),
    }
