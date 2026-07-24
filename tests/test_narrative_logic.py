# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Unit tests for the narrative logic engine.

Tests focus on:
  1. Data model correctness (pure dataclasses)
  2. Constraint checker safety logic (write-keyword rejection)
  3. Impact propagator edge-weight mapping
  4. Confidence scorer formula correctness

GraphStore-dependent methods are tested with mock objects — no Neo4j
required.  This keeps tests fast and isolated.
"""

from unittest.mock import MagicMock

import pytest

from core.narrative_logic.confidence_scorer import ConfidenceScorer
from core.narrative_logic.constraint_checker import ConstraintChecker
from core.narrative_logic.impact_propagator import (
    _DEFAULT_WEIGHT,
    _EDGE_WEIGHTS,
    ImpactPropagator,
)
from core.narrative_logic.models import (
    Constraint,
    ConstraintViolation,
    EntityScore,
    ImpactReport,
    ImpactSource,
)

# ── Model tests ──────────────────────────────────────────────────────


class TestModels:
    def test_constraint_defaults(self):
        c = Constraint(id="C001", description="test rule")
        assert c.constraint_type == "custom"
        assert c.severity == "hard"
        assert c.status == "active"
        assert c.condition == {}
        assert c.violation_query == ""

    def test_constraint_violation_defaults(self):
        v = ConstraintViolation(
            constraint_id="C001",
            description="test",
            severity="hard",
        )
        assert v.violations == []

    def test_impact_source(self):
        s = ImpactSource(source_type="entity", source_id="e1")
        assert s.description == ""

    def test_impact_report_defaults(self):
        s = ImpactSource(source_type="entity", source_id="e1")
        r = ImpactReport(source=s)
        assert r.blast_radius == 0
        assert r.max_severity == "low"
        assert r.directly_affected == []

    def test_entity_score_defaults(self):
        s = EntityScore(entity_id="e1", entity_name="test", entity_type="character")
        assert s.confidence == 0.0
        assert s.stars == 0
        assert s.recommendation == ""


# ── Constraint checker safety tests ──────────────────────────────────


class TestConstraintCheckerSafety:
    def test_safe_query_passes(self):
        assert ConstraintChecker._is_safe_query("MATCH (e:Entity) RETURN e.name") is True

    def test_empty_query_rejected(self):
        assert ConstraintChecker._is_safe_query("") is False
        assert ConstraintChecker._is_safe_query("   ") is False

    def test_create_rejected(self):
        assert ConstraintChecker._is_safe_query("CREATE (n:Test) RETURN n") is False

    def test_delete_rejected(self):
        assert ConstraintChecker._is_safe_query("MATCH (n) DELETE n") is False

    def test_set_rejected(self):
        assert ConstraintChecker._is_safe_query("MATCH (n) SET n.x = 1 RETURN n") is False

    def test_merge_rejected(self):
        assert ConstraintChecker._is_safe_query("MERGE (n:Test {id: 1}) RETURN n") is False

    def test_drop_rejected(self):
        assert ConstraintChecker._is_safe_query("DROP INDEX test") is False

    def test_case_insensitive(self):
        assert ConstraintChecker._is_safe_query("match (n) create (n) return n") is False

    def test_call_rejected(self):
        assert ConstraintChecker._is_safe_query("CALL db.labels()") is False


# ── Impact propagator weight tests ───────────────────────────────────


class TestImpactPropagatorWeights:
    def test_involves_weight(self):
        assert _EDGE_WEIGHTS["INVOLVES"] == 0.9

    def test_depends_on_weight(self):
        assert _EDGE_WEIGHTS["DEPENDS_ON"] == 0.8

    def test_killed_weight(self):
        assert _EDGE_WEIGHTS["KILLED"] == 0.8

    def test_causes_weight(self):
        assert _EDGE_WEIGHTS["CAUSES"] == 0.8

    def test_default_weight(self):
        assert _DEFAULT_WEIGHT == 0.5

    def test_unknown_edge_uses_default(self):
        assert _EDGE_WEIGHTS.get("NONEXISTENT", _DEFAULT_WEIGHT) == _DEFAULT_WEIGHT

    def test_all_weights_in_valid_range(self):
        for edge_type, weight in _EDGE_WEIGHTS.items():
            assert 0.0 < weight <= 1.0, f"{edge_type} has invalid weight {weight}"


# ── Impact propagator with mock store ────────────────────────────────


class TestImpactPropagatorMock:
    def _make_mock_store(self, neighbors_map: dict, node_details: dict):
        """Create a mock GraphStore with predefined neighbor and detail data."""
        store = MagicMock()
        store.project_id = "test_project"

        def mock_run(query, params=None):
            # Return empty for any query (overridden per-test)
            return []

        def mock_run_single(query, params=None):
            return None

        store._run = MagicMock(side_effect=mock_run)
        store._run_single = MagicMock(side_effect=mock_run_single)
        return store

    def test_propagate_no_source_node(self):
        store = MagicMock()
        store.project_id = "test"
        store._run.return_value = []  # No node found
        store._run_single.return_value = None

        propagator = ImpactPropagator(store)
        source = ImpactSource(source_type="entity", source_id="nonexistent")
        report = propagator.propagate(source)

        assert report.blast_radius == 0
        assert report.max_severity == "low"

    def test_propagate_unsupported_source_type(self):
        store = MagicMock()
        store.project_id = "test"

        propagator = ImpactPropagator(store)
        source = ImpactSource(source_type="invalid_type", source_id="x")
        report = propagator.propagate(source)

        assert report.blast_radius == 0


# ── Confidence scorer formula tests ──────────────────────────────────


class TestConfidenceScorerFormula:
    def _make_mock_store(self, mention_count=0, relation_count=0, contradictions=None, entity=None):
        store = MagicMock()
        store.project_id = "test_project"

        def mock_run(query, params=None):
            return [{"cnt": mention_count}]

        # First call is _count_timeline_mentions, second is _count_relations
        # We need to differentiate based on the query content
        def mock_run_smart(query, params=None):
            if "Timeline" in query and "INVOLVES" in query:
                return [{"cnt": mention_count}]
            elif "Entity" in query and "-[r]-" in query:
                return [{"cnt": relation_count}]
            return []

        store._run = MagicMock(side_effect=mock_run_smart)

        # check_consistency returns contradictions
        result = {"contradictions": contradictions or []}
        store.check_consistency = MagicMock(return_value=result)
        store.get_entity = MagicMock(return_value=entity)

        return store

    def test_zero_score_for_isolated_entity(self):
        store = self._make_mock_store(
            mention_count=0,
            relation_count=0,
            entity=MagicMock(name="isolated", id="e1"),
        )
        scorer = ConfidenceScorer(store)
        score = scorer.score_one("e1", "isolated", "character")

        # reference: 0, relation: 0, consistency: (1-0)*0.3 = 0.3
        assert score.confidence == pytest.approx(0.3, abs=0.01)
        assert score.stars >= 1  # min 1 star
        assert "不足" in score.recommendation or "较薄" in score.recommendation

    def test_high_score_for_well_connected_entity(self):
        store = self._make_mock_store(
            mention_count=10,
            relation_count=5,
            entity=MagicMock(name="hero", id="e1"),
        )
        scorer = ConfidenceScorer(store)
        score = scorer.score_one("e1", "hero", "character")

        # reference: min(10/10,1)*0.4 = 0.4
        # relation: min(5/5,1)*0.3 = 0.3
        # consistency: (1-0*0.2)*0.3 = 0.3
        assert score.confidence == pytest.approx(1.0, abs=0.01)
        assert score.stars == 5
        assert score.recommendation == "设定充足"

    def test_medium_score(self):
        store = self._make_mock_store(
            mention_count=5,
            relation_count=2,
            entity=MagicMock(name="mid", id="e1"),
        )
        scorer = ConfidenceScorer(store)
        score = scorer.score_one("e1", "mid", "character")

        # reference: min(5/10,1)*0.4 = 0.2
        # relation: min(2/5,1)*0.3 = 0.12
        # consistency: 0.3
        expected = round(0.2 + 0.12 + 0.3, 3)
        assert score.confidence == pytest.approx(expected, abs=0.01)

    def test_contradiction_reduces_score(self):
        contradictions = [
            {"description": "hero is in two places at once"},
        ]
        # Use a spec'd mock so .name returns the real string
        entity_mock = MagicMock()
        entity_mock.name = "hero"
        entity_mock.id = "e1"
        store = self._make_mock_store(
            mention_count=10,
            relation_count=5,
            contradictions=contradictions,
            entity=entity_mock,
        )
        scorer = ConfidenceScorer(store)
        score = scorer.score_one("e1", "hero", "character")

        # consistency: max(1-1*0.2, 0)*0.3 = 0.24
        # total: 0.4 + 0.3 + 0.24 = 0.94
        assert score.confidence == pytest.approx(0.94, abs=0.01)
        assert "矛盾" in score.recommendation

    def test_factors_dict_structure(self):
        store = self._make_mock_store(
            mention_count=3,
            relation_count=1,
            entity=MagicMock(name="test", id="e1"),
        )
        scorer = ConfidenceScorer(store)
        score = scorer.score_one("e1", "test", "character")

        assert "reference" in score.factors
        assert "relation" in score.factors
        assert "consistency" in score.factors

    def test_stars_capped_at_5(self):
        store = self._make_mock_store(
            mention_count=100,
            relation_count=100,
            entity=MagicMock(name="max", id="e1"),
        )
        scorer = ConfidenceScorer(store)
        score = scorer.score_one("e1", "max", "character")

        assert score.stars == 5

    def test_stars_min_1(self):
        store = self._make_mock_store(
            mention_count=0,
            relation_count=0,
            entity=MagicMock(name="min", id="e1"),
        )
        scorer = ConfidenceScorer(store)
        score = scorer.score_one("e1", "min", "character")

        assert score.stars >= 1
