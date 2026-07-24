# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Tests for chapter dependency graph — BFS impact propagation."""

from core.chapter_dependency import (
    DependencyEdge,
    DependencyGraph,
    propagate_impact,
)


class TestPropagateImpact:
    """Test BFS impact propagation on a dependency graph."""

    def test_single_node_no_deps(self):
        """A single node with no dependencies should produce no affected chapters."""
        graph = DependencyGraph()
        graph.nodes = [{"id": "ch1", "title": "第一章", "index": 1}]
        graph.adjacency = {"ch1": []}
        graph.reverse_adjacency = {"ch1": []}

        affected = propagate_impact(graph, "ch1")
        assert len(affected) == 0

    def test_linear_chain(self):
        """A→B→C chain: modifying A should affect B and C."""
        graph = DependencyGraph()
        graph.nodes = [
            {"id": "ch1", "title": "一", "index": 1},
            {"id": "ch2", "title": "二", "index": 2},
            {"id": "ch3", "title": "三", "index": 3},
        ]
        graph.adjacency = {"ch1": ["ch2"], "ch2": ["ch3"], "ch3": []}
        graph.reverse_adjacency = {"ch1": [], "ch2": ["ch1"], "ch3": ["ch2"]}

        affected = propagate_impact(graph, "ch1")
        assert len(affected) == 2
        # ch2 is depth 1 (direct), ch3 is depth 2 (indirect)
        depths = {a["chapter_id"]: a["depth"] for a in affected}
        assert depths["ch2"] == 1
        assert depths["ch3"] == 2

    def test_branching_graph(self):
        """A→B, A→C: modifying A should affect both B and C at depth 1."""
        graph = DependencyGraph()
        graph.nodes = [
            {"id": "ch1", "title": "一", "index": 1},
            {"id": "ch2", "title": "二", "index": 2},
            {"id": "ch3", "title": "三", "index": 3},
        ]
        graph.adjacency = {"ch1": ["ch2", "ch3"], "ch2": [], "ch3": []}
        graph.reverse_adjacency = {"ch1": [], "ch2": ["ch1"], "ch3": ["ch1"]}

        affected = propagate_impact(graph, "ch1")
        assert len(affected) == 2
        for a in affected:
            assert a["depth"] == 1

    def test_no_cycles(self):
        """BFS should not revisit nodes (handles potential cycles)."""
        graph = DependencyGraph()
        graph.nodes = [
            {"id": "ch1", "title": "一", "index": 1},
            {"id": "ch2", "title": "二", "index": 2},
        ]
        # Simulate a cycle: ch1→ch2→ch1
        graph.adjacency = {"ch1": ["ch2"], "ch2": ["ch1"]}
        graph.reverse_adjacency = {"ch1": ["ch2"], "ch2": ["ch1"]}

        affected = propagate_impact(graph, "ch1")
        # Should only report ch2 once, not infinitely loop
        assert len(affected) == 1
        assert affected[0]["chapter_id"] == "ch2"

    def test_nonexistent_chapter(self):
        """Modifying a chapter not in the graph should return empty."""
        graph = DependencyGraph()
        graph.adjacency = {"ch1": []}
        affected = propagate_impact(graph, "nonexistent")
        assert len(affected) == 0


class TestDependencyEdgeDataclass:
    """Test DependencyEdge serialization."""

    def test_to_dict(self):
        edge = DependencyEdge(
            source_chapter_id="ch1",
            target_chapter_id="ch2",
            dependency_type="entity_reference",
            shared_entities=["张三", "酒馆"],
        )
        d = edge.to_dict()
        assert d["source"] == "ch1"
        assert d["target"] == "ch2"
        assert d["type"] == "entity_reference"
        assert "张三" in d["shared_entities"]


class TestDependencyGraphDataclass:
    """Test DependencyGraph serialization."""

    def test_to_dict(self):
        graph = DependencyGraph(
            book_id="book1",
            nodes=[{"id": "ch1", "title": "一", "index": 1}],
            edges=[DependencyEdge(source_chapter_id="ch1", target_chapter_id="ch2")],
        )
        d = graph.to_dict()
        assert d["book_id"] == "book1"
        assert d["total_nodes"] == 1
        assert d["total_edges"] == 1
