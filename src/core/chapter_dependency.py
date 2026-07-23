# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Chapter dependency graph — track content-level dependencies between chapters.

Builds a directed graph where an edge A→B means "chapter B references content
first introduced in chapter A". This is complementary to the narrative_logic
impact_propagator (which tracks constraint-level impacts at the Neo4j layer).

Dependency types:
- entity_reference: entity X first appears in A, referenced again in B
- event_continuation: event E from A is continued/resolved in B
- foreshadow_setup: foreshadow from A is paid off in B

When a chapter is modified, BFS traversal of this graph reveals all chapters
that may need review.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from data.json_store import json_store

logger = logging.getLogger(__name__)


@dataclass
class DependencyEdge:
    """A single dependency edge between two chapters."""

    source_chapter_id: str = ""
    target_chapter_id: str = ""
    dependency_type: str = ""  # entity_reference / event_continuation / foreshadow_setup
    shared_entities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source_chapter_id,
            "target": self.target_chapter_id,
            "type": self.dependency_type,
            "shared_entities": self.shared_entities,
        }


@dataclass
class DependencyGraph:
    """Full chapter dependency graph for a book."""

    book_id: str = ""
    nodes: list[dict] = field(default_factory=list)  # [{id, title, index}]
    edges: list[DependencyEdge] = field(default_factory=list)
    adjacency: dict[str, list[str]] = field(default_factory=dict)  # forward deps
    reverse_adjacency: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "book_id": self.book_id,
            "nodes": self.nodes,
            "edges": [e.to_dict() for e in self.edges],
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
        }


def _get_entity_names(book_id: str) -> dict[str, str]:
    """Get entity name → entity_id mapping from graph store."""
    try:
        from core.graph_store import GraphStore

        store = GraphStore()
        entities = store.list_entities()
        return {e.name: e.id for e in entities if e.name}
    except Exception as e:
        logger.warning("Failed to load entity names: %s", e)
        return {}


def build_dependency_graph(book_id: str) -> DependencyGraph:
    """Build the chapter dependency graph for a book.

    Scans each chapter for mentions of entity names. If entity X first appears
    in chapter A and is mentioned again in chapter B (B > A), then A→B edge.
    """
    chapters = json_store.load_chapters(book_id)
    regular = [ch for ch in chapters if not ch.get("is_extra")]
    entity_names = _get_entity_names(book_id)

    if not entity_names:
        # Fallback: use character names from character mentions
        mentions = json_store.get_character_mentions(book_id)
        if mentions and mentions.get("matrix"):
            entity_names = {name: name for name in mentions.get("characters", [])}

    graph = DependencyGraph(book_id=book_id)

    # Track which entities first appear in which chapter
    entity_first_chapter: dict[str, str] = {}  # entity_name → chapter_id
    # Track which entities appear in each chapter
    chapter_entities: dict[str, set[str]] = {}  # chapter_id → set of entity names

    for idx, ch in enumerate(regular):
        cur = json_store._get_current_version(ch)
        content = cur.get("content", "")
        ch_id = ch.get("id", "")
        ch_title = cur.get("title", ch.get("title", ""))

        graph.nodes.append({
            "id": ch_id,
            "title": ch_title,
            "index": idx + 1,
        })

        # Find which entities are mentioned in this chapter
        mentioned: set[str] = set()
        for name in entity_names:
            if name and name in content:
                mentioned.add(name)

        chapter_entities[ch_id] = mentioned

        # Record first appearance
        for name in mentioned:
            if name not in entity_first_chapter:
                entity_first_chapter[name] = ch_id

    # Build edges: if entity X first in A, appears in B (B > A) → A→B
    edge_map: dict[tuple[str, str], list[str]] = defaultdict(list)

    for ch in regular:
        ch_id = ch.get("id", "")
        mentioned = chapter_entities.get(ch_id, set())
        for name in mentioned:
            first_ch = entity_first_chapter.get(name)
            if first_ch and first_ch != ch_id:
                edge_key = (first_ch, ch_id)
                edge_map[edge_key].append(name)

    # Create edge objects
    for (source, target), shared in edge_map.items():
        graph.edges.append(DependencyEdge(
            source_chapter_id=source,
            target_chapter_id=target,
            dependency_type="entity_reference",
            shared_entities=shared,
        ))

    # Build adjacency lists
    for edge in graph.edges:
        graph.adjacency.setdefault(edge.source_chapter_id, []).append(edge.target_chapter_id)
        graph.reverse_adjacency.setdefault(edge.target_chapter_id, []).append(edge.source_chapter_id)

    # Ensure all nodes have adjacency entries
    for node in graph.nodes:
        nid = node["id"]
        graph.adjacency.setdefault(nid, [])
        graph.reverse_adjacency.setdefault(nid, [])

    return graph


def propagate_impact(graph: DependencyGraph, modified_chapter_id: str) -> list[dict]:
    """BFS traversal to find all chapters affected by modifying a given chapter.

    Returns a list of {chapter_id, depth, path} dicts, sorted by depth.
    Direct dependencies (depth=1) are listed first.
    """
    if modified_chapter_id not in graph.adjacency:
        return []

    visited: set[str] = {modified_chapter_id}
    queue: deque[tuple[str, int]] = deque([(modified_chapter_id, 0)])
    affected: list[dict] = []

    while queue:
        current, depth = queue.popleft()
        if depth > 0:
            affected.append({
                "chapter_id": current,
                "depth": depth,
            })

        for neighbor in graph.adjacency.get(current, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, depth + 1))

    return affected


def propagate_impact_by_id(book_id: str, chapter_id: str) -> list[dict]:
    """Convenience: build graph and propagate impact for a single chapter."""
    graph = build_dependency_graph(book_id)
    return propagate_impact(graph, chapter_id)


def build_and_visualize(book_id: str) -> dict[str, Any]:
    """Build dependency graph and return D3-force-graph-compatible data."""
    graph = build_dependency_graph(book_id)

    # D3 force layout format: {nodes: [...], links: [...]}
    d3_links = []
    for edge in graph.edges:
        d3_links.append({
            "source": edge.source_chapter_id,
            "target": edge.target_chapter_id,
            "type": edge.dependency_type,
            "shared_count": len(edge.shared_entities),
            "shared_entities": edge.shared_entities[:5],  # limit for display
        })

    return {
        **graph.to_dict(),
        "d3_format": {
            "nodes": [
                {"id": n["id"], "title": n["title"], "index": n["index"]}
                for n in graph.nodes
            ],
            "links": d3_links,
        },
    }
