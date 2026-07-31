# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Impact propagator — weighted multi-hop BFS over the knowledge graph.

When a user modifies an entity, timeline event, or foreshadow, this
module traces the blast radius: which other elements are affected and
how strongly.

Edge weights (simplified, not full belief propagation):
  INVOLVES (Timeline→Entity)     : 0.9
  Entity-Entity relationships    : 0.7
  DEPENDS_ON (Foreshadow→Fores.) : 0.8
  HAS_PHASE (Entity→Snapshot)    : 0.6
  All other edges                : 0.5

Propagation stops when weight drops below MIN_WEIGHT (0.3) or after
MAX_HOPS (3) hops.
"""

from __future__ import annotations

import logging
from typing import cast

from core.graph_store import GraphStore

from .models import ImpactReport, ImpactSource

logger = logging.getLogger(__name__)

MAX_HOPS = 3
MIN_WEIGHT = 0.3

# Edge type → weight mapping.  Undirected edges use the same weight
# regardless of traversal direction.
_EDGE_WEIGHTS: dict[str, float] = {
    "INVOLVES": 0.9,
    "DEPENDS_ON": 0.8,
    "ALLY": 0.7,
    "ANTAGONIST": 0.7,
    "FAMILY": 0.7,
    "ROMANTIC": 0.7,
    "KNOWS": 0.6,
    "MENTOR_OF": 0.7,
    "MASTER_OF": 0.7,
    "KILLED": 0.8,
    "SAVED": 0.7,
    "LOVES": 0.7,
    "OWNS": 0.7,
    "LOCATED_AT": 0.6,
    "HAS_PHASE": 0.6,
    "BEFORE": 0.5,
    "AFTER": 0.5,
    "FORESHADOWS": 0.7,
    "RESOLVES": 0.7,
    "CAUSES": 0.8,
    "GOVERNS": 0.3,
}
_DEFAULT_WEIGHT = 0.5


class ImpactPropagator:
    """Read-only multi-hop weighted BFS.  Never writes to the graph."""

    def __init__(self, store: GraphStore):
        self._store = store

    # ── Public API ──

    def propagate(self, source: ImpactSource) -> ImpactReport:
        """Trace the impact of modifying *source* through the graph."""

        # Resolve source node id to a graph-store internal id for traversal
        source_node_id = self._resolve_source_node(source)
        if not source_node_id:
            return ImpactReport(
                source=source,
                blast_radius=0,
                max_severity="low",
            )

        # Weighted BFS
        visited: dict[str, float] = {source_node_id: 1.0}
        # Track hop level for each node
        hop_levels: dict[str, int] = {source_node_id: 0}
        # Track path info
        path_info: dict[str, list[str]] = {source_node_id: [source_node_id]}
        frontier = [source_node_id]

        for hop in range(MAX_HOPS):
            next_frontier: list[str] = []
            for node_id in frontier:
                current_weight = visited[node_id]
                neighbors = self._get_neighbors(node_id)
                for nid, edge_type, edge_weight in neighbors:
                    propagated = current_weight * edge_weight
                    if propagated < MIN_WEIGHT:
                        continue
                    # Keep the higher weight if already visited
                    if nid not in visited or propagated > visited[nid]:
                        visited[nid] = propagated
                        hop_levels[nid] = hop + 1
                        path_info[nid] = path_info.get(node_id, [node_id]) + [nid]
                        if nid not in next_frontier:
                            next_frontier.append(nid)
            frontier = next_frontier

        # Build report
        return self._build_report(source, visited, hop_levels, path_info, source_node_id)

    # ── Internal helpers ──

    def _resolve_source_node(self, source: ImpactSource) -> str | None:
        """Resolve the source element to a graph-store element id for traversal."""
        pid = self._store.project_id
        if source.source_type == "entity":
            rows = self._store._run(
                "SELECT id FROM entities WHERE id=? AND project_id=?",
                (source.source_id, pid),
            )
        elif source.source_type == "timeline_event":
            rows = self._store._run(
                "SELECT id FROM timeline_events WHERE id=? AND project_id=?",
                (source.source_id, pid),
            )
        elif source.source_type == "foreshadow":
            rows = self._store._run(
                "SELECT id FROM foreshadows WHERE id=? AND project_id=?",
                (source.source_id, pid),
            )
        else:
            return None

        return cast(str | None, rows[0]["id"] if rows else None)

    def _get_neighbors(self, node_id: str) -> list[tuple[str, str, float]]:
        """Get (neighbor_id, edge_type, weight) for all edges of node_id."""
        rows = self._store._run(
            """
            SELECT to_entity AS mid, type AS rtype FROM relations
            WHERE from_entity=? AND project_id=?
            UNION
            SELECT from_entity AS mid, type AS rtype FROM relations
            WHERE to_entity=? AND project_id=?
            """,
            (node_id, self._store.project_id, node_id, self._store.project_id),
        )
        result = []
        for r in rows:
            mid = r["mid"]
            rtype = r["rtype"]
            weight = _EDGE_WEIGHTS.get(rtype, _DEFAULT_WEIGHT)
            result.append((mid, rtype, weight))
        return result

    def _build_report(
        self,
        source: ImpactSource,
        visited: dict[str, float],
        hop_levels: dict[str, int],
        path_info: dict[str, list[str]],
        source_node_id: str,
    ) -> ImpactReport:
        """Convert raw BFS results into a structured ImpactReport."""

        # Separate by hop level
        [nid for nid, h in hop_levels.items() if h == 1]
        [nid for nid, h in hop_levels.items() if h >= 2]

        # Fetch node details
        all_ids = [nid for nid in visited if nid != source_node_id]
        node_details = self._fetch_node_details(all_ids)

        directly_affected = []
        indirectly_affected = []
        affected_chapters = []
        affected_foreshadows = []

        for nid in all_ids:
            detail = node_details.get(nid, {})
            info = {
                "node_id": nid,
                "name": detail.get("name", "?"),
                "type": detail.get("type", "unknown"),
                "weight": round(visited[nid], 3),
                "hop": hop_levels.get(nid, 0),
                "edge_types": detail.get("edge_types", []),
            }
            if hop_levels.get(nid, 0) == 1:
                directly_affected.append(info)
            else:
                info["path_length"] = hop_levels.get(nid, 0)
                indirectly_affected.append(info)

            # Categorize special types
            if detail.get("type") == "foreshadow":
                affected_foreshadows.append(
                    {
                        "id": detail.get("id", ""),
                        "text": detail.get("name", ""),
                        "resolved": detail.get("resolved", False),
                    }
                )
            if detail.get("type") == "timeline":
                affected_chapters.append(
                    {
                        "id": detail.get("id", ""),
                        "label": detail.get("name", ""),
                        "chapter_ref": detail.get("chapter_ref", ""),
                    }
                )

        # Sort by weight descending
        directly_affected.sort(key=lambda x: x["weight"], reverse=True)
        indirectly_affected.sort(key=lambda x: x["weight"], reverse=True)

        blast_radius = len(all_ids)
        max_severity = (
            "high" if any(v > 0.7 for v in visited.values() if v < 1.0) else "medium" if blast_radius > 5 else "low"
        )

        return ImpactReport(
            source=source,
            directly_affected=directly_affected,
            indirectly_affected=indirectly_affected,
            affected_chapters=affected_chapters,
            affected_foreshadows=affected_foreshadows,
            blast_radius=blast_radius,
            max_severity=max_severity,
        )

    def _fetch_node_details(self, node_ids: list[str]) -> dict[str, dict]:
        """Batch-fetch name/type/id for a list of graph-store element ids."""
        if not node_ids:
            return {}
        pid = self._store.project_id
        placeholders = ",".join("?" for _ in node_ids)
        params = node_ids + [pid]
        # Union across the node tables; source_type column emulates Neo4j labels.
        query = f"""
            SELECT id, name, entity_type AS ntype, 'Entity' AS src_type, NULL AS resolved, NULL AS cr
              FROM entities WHERE id IN ({placeholders}) AND project_id=?
            UNION ALL
            SELECT id, label AS name, NULL AS ntype, 'Timeline' AS src_type, NULL AS resolved, chapter_ref AS cr
              FROM timeline_events WHERE id IN ({placeholders}) AND project_id=?
            UNION ALL
            SELECT id, text AS name, NULL AS ntype, 'Fore' AS src_type, resolved, NULL AS cr
              FROM foreshadows WHERE id IN ({placeholders}) AND project_id=?
            UNION ALL
            SELECT id, label AS name, NULL AS ntype, 'Snapshot' AS src_type, NULL AS resolved, NULL AS cr
              FROM snapshots WHERE id IN ({placeholders}) AND project_id=?
        """
        rows = self._store._run(query, tuple(params * 4))
        details: dict[str, dict] = {}
        for r in rows:
            src = r.get("src_type", "")
            if src == "Entity":
                ntype = r.get("ntype") or "unknown"
            elif src == "Timeline":
                ntype = "timeline"
            elif src == "Fore":
                ntype = "foreshadow"
            elif src == "Snapshot":
                ntype = "snapshot"
            else:
                ntype = "unknown"
            details[r["id"]] = {
                "id": r.get("id", ""),
                "name": r.get("name") or r.get("id", "?"),
                "type": ntype,
                "resolved": r.get("resolved", False),
                "chapter_ref": r.get("cr", ""),
            }
        return details
