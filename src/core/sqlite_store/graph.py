"""SQLite store — graph traversal and analysis algorithms.

Part of the ``core.sqlite_store`` package.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from core.knowledge import Foreshadow

from .crud import CrudMixin

logger = logging.getLogger(__name__)


class GraphMixin(CrudMixin):
    """Graph traversal, PageRank, community detection and link prediction."""

    def _get_direct_neighbors(self, entity_id: str, rel_types: list[str] | None = None) -> list[dict]:
        """Get direct neighbors of an entity via relations table."""
        if rel_types:
            placeholders = ",".join("?" for _ in rel_types)
            rows = self._run(
                f"""
                SELECT r.to_entity AS id, r.type, e.name, e.entity_type AS type_label
                FROM relations r JOIN entities e ON r.to_entity = e.id
                WHERE r.from_entity=? AND r.project_id=?
                  AND r.type IN ({placeholders})
                UNION
                SELECT r.from_entity, r.type, e.name, e.entity_type
                FROM relations r JOIN entities e ON r.from_entity = e.id
                WHERE r.to_entity=? AND r.project_id=?
                  AND r.type IN ({placeholders})
            """,
                (entity_id, self.project_id, *rel_types, entity_id, self.project_id, *rel_types),
            )
        else:
            rows = self._run(
                """
                SELECT r.to_entity AS id, r.type, e.name, e.entity_type AS type_label
                FROM relations r JOIN entities e ON r.to_entity = e.id
                WHERE r.from_entity=? AND r.project_id=?
                UNION
                SELECT r.from_entity, r.type, e.name, e.entity_type
                FROM relations r JOIN entities e ON r.from_entity = e.id
                WHERE r.to_entity=? AND r.project_id=?
            """,
                (entity_id, self.project_id, entity_id, self.project_id),
            )
        # Deduplicate
        seen: set = set()
        result = []
        for r in rows:
            key = (r["id"], r["type"])
            if key not in seen:
                seen.add(key)
                result.append(dict(r))
        return result

    def get_neighbors(self, entity_id: str, depth: int = 1) -> list[dict]:
        """Get all neighbors up to given depth (BFS)."""
        visited: set = {entity_id}
        frontier: list[tuple[str, int]] = [(entity_id, 0)]
        neighbors: list[dict] = []
        while frontier:
            current, d = frontier.pop(0)
            if d >= depth:
                continue
            for nb in self._get_direct_neighbors(current):
                nb_id = nb["id"]
                if nb_id not in visited:
                    visited.add(nb_id)
                    entry = {
                        "id": nb_id,
                        "name": nb.get("name", ""),
                        "type": nb.get("type_label", ""),
                        "relationship": nb.get("type", ""),
                        "depth": d + 1,
                    }
                    neighbors.append(entry)
                    frontier.append((nb_id, d + 1))
        return neighbors

    def get_path(self, from_id: str, to_id: str, max_depth: int = 3) -> list[dict]:
        """BFS shortest path — replaces Cypher shortestPath()."""
        max_depth = max(1, min(int(max_depth), 10))
        if from_id == to_id:
            return []
        parent: dict[str, tuple[str | None, str | None]] = {from_id: (None, None)}
        queue: list[tuple[str, int]] = [(from_id, 0)]
        found = False
        while queue and not found:
            current, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for nb in self._get_direct_neighbors(current):
                nb_id = nb["id"]
                if nb_id not in parent:
                    parent[nb_id] = (current, nb.get("type", ""))
                    if nb_id == to_id:
                        found = True
                        break
                    queue.append((nb_id, depth + 1))
        if not found:
            return []
        # Backtrack to build path
        nodes: list[dict] = []
        node = to_id
        while node != from_id:
            p, rel = parent[node]
            nodes.insert(0, {"id": node, "via": rel})
            node = p
        nodes.insert(0, {"id": from_id, "via": None})
        return [{"nodes": nodes, "hops": len(nodes) - 1}]

    def find_relationships(self, from_id: str, to_id: str, max_depth: int = 3) -> list[dict]:
        return self.get_path(from_id, to_id, max_depth)

    def get_entity_network(self, entity_id: str, depth: int = 2) -> dict:
        """Get the subgraph around an entity up to given depth."""
        nodes_set: dict[str, dict] = {}
        edges_set: dict[str, dict] = {}
        visited: set = {entity_id}
        frontier: list[tuple[str, int]] = [(entity_id, 0)]

        # Get root entity
        root = self.get_entity(entity_id)
        if root:
            nodes_set[entity_id] = {"id": entity_id, "name": root.name, "type": root.type}

        while frontier:
            current, d = frontier.pop(0)
            if d >= depth:
                continue
            for nb in self._get_direct_neighbors(current):
                nb_id = nb["id"]
                # Add node
                if nb_id not in nodes_set:
                    nodes_set[nb_id] = {
                        "id": nb_id,
                        "name": nb.get("name", ""),
                        "type": nb.get("type_label", ""),
                    }
                # Add edge
                edge_key = f"{current}|{nb_id}|{nb.get('type', '')}"
                if edge_key not in edges_set:
                    edges_set[edge_key] = {
                        "source": current,
                        "target": nb_id,
                        "type": nb.get("type", "").lower(),
                    }
                if nb_id not in visited:
                    visited.add(nb_id)
                    frontier.append((nb_id, d + 1))

        return {
            "nodes": list(nodes_set.values()),
            "edges": list(edges_set.values()),
        }

    def _get_graph_adjacency(
        self, char_ids: list[str] | None = None, rel_types: list[str] | None = None
    ) -> dict[str, set[str]]:
        """Build in-memory adjacency dict from the relations table.

        Returns {entity_id: {neighbor_id, ...}}.
        """
        if rel_types is None:
            rel_types = [
                "KNOWS",
                "ALLY",
                "FAMILY",
                "ANTAGONIST",
                "ROMANTIC",
                "MASTER_OF",
                "MENTOR_OF",
                "KILLED",
                "SAVED",
                "LOVES",
            ]
        placeholders = ",".join("?" for _ in rel_types)

        if char_ids:
            id_placeholders = ",".join("?" for _ in char_ids)
            rows = self._run(
                f"""
                SELECT r.from_entity AS src, r.to_entity AS tgt
                FROM relations r
                WHERE r.project_id=?
                  AND r.type IN ({placeholders})
                  AND ((r.from_entity IN ({id_placeholders}) AND r.to_entity IN ({id_placeholders})))
                  AND r.from_entity <> r.to_entity
            """,
                (self.project_id, *rel_types, *char_ids, *char_ids),
            )
        else:
            rows = self._run(
                f"""
                SELECT r.from_entity AS src, r.to_entity AS tgt
                FROM relations r
                WHERE r.project_id=?
                  AND r.type IN ({placeholders})
                  AND r.from_entity <> r.to_entity
            """,
                (self.project_id, *rel_types),
            )

        adj: dict[str, set[str]] = {}
        for r in rows:
            src, tgt = r["src"], r["tgt"]
            adj.setdefault(src, set()).add(tgt)
            adj.setdefault(tgt, set()).add(src)
        return adj

    # ════════════════════════════════════════════════════════════════
    # Graph analysis algorithms
    # ════════════════════════════════════════════════════════════════

    # ── PageRank ──

    def _compute_pagerank(self, char_ids: list[str], max_iter: int = 20, damping: float = 0.85) -> dict[str, float]:
        """Compute iterative PageRank for character nodes."""
        if not char_ids:
            return {}
        id_set = set(char_ids)
        adj: dict[str, list[str]] = {cid: [] for cid in char_ids}
        rows = self._run(
            f"""
            SELECT r.from_entity AS src, r.to_entity AS tgt
            FROM relations r
            WHERE r.project_id=? AND r.from_entity IN ({",".join("?" for _ in char_ids)})
              AND r.to_entity IN ({",".join("?" for _ in char_ids)})
              AND r.from_entity <> r.to_entity
        """,
            (self.project_id, *char_ids, *char_ids),
        )
        for r in rows:
            src, tgt = r["src"], r["tgt"]
            if src in id_set and tgt in id_set:
                adj[src].append(tgt)

        n = len(char_ids)
        if n == 0:
            return {}
        pr: dict[str, float] = dict.fromkeys(char_ids, 1.0 / n)
        for _ in range(max_iter):
            new_pr: dict[str, float] = {}
            total = 0.0
            for cid in char_ids:
                incoming = 0.0
                for src_id, tgts in adj.items():
                    if cid in tgts:
                        incoming += pr[src_id] / max(len(tgts), 1)
                new_pr[cid] = (1 - damping) / n + damping * incoming
                total += new_pr[cid]
            # Normalize
            if total > 0:
                for cid in char_ids:
                    new_pr[cid] /= total
            pr = new_pr
        return pr

    def get_character_importance(self) -> list[dict]:
        """Rank characters by composite importance: degree + PageRank + appearances."""
        return self._cached("char_importance", self._compute_character_importance)

    def _compute_character_importance(self) -> list[dict]:
        chars = self.list_entities(entity_type="character")
        if not chars:
            return []
        char_ids = [c.id for c in chars]

        # Degree (from character-character relationships)
        adj = self._get_graph_adjacency(char_ids)
        degree = {cid: len(adj.get(cid, set())) for cid in char_ids}

        # PageRank
        pr = self._compute_pagerank(char_ids)

        # Appearances (from timeline INVOLVES)
        # In SQLite, we approximate by counting timeline events where character
        # appears as a related entity in foreshadow or timeline event data
        appear = dict.fromkeys(char_ids, 0)
        events = self.list_timeline_events()
        for evt in events:
            _count_entity_refs(evt, char_ids, appear)

        max_degree = max(degree.values()) if degree else 1
        max_pr = max(pr.values()) if pr else 1
        max_appear = max(appear.values()) if appear else 1

        results: list[dict[str, Any]] = []
        for cid in char_ids:
            deg_norm = (degree.get(cid, 0) / max(max_degree, 1)) * 100
            pr_norm = (pr.get(cid, 0) / max(max_pr, 1)) * 100
            appear_norm = (appear.get(cid, 0) / max(max_appear, 1)) * 100
            composite = round(deg_norm * 0.40 + pr_norm * 0.35 + appear_norm * 0.25)

            if composite >= 70:
                role = "主角"
            elif composite >= 45:
                role = "重要角色"
            elif composite >= 25:
                role = "配角"
            else:
                role = "龙套"

            char = next((c for c in chars if c.id == cid), None)
            results.append(
                {
                    "entity_id": cid,
                    "name": char.name if char else cid,
                    "composite_score": min(composite, 100),
                    "role": role,
                    "degree": degree.get(cid, 0),
                    "appearances": appear.get(cid, 0),
                    "pagerank_score": round(pr_norm),
                }
            )

        results.sort(key=lambda x: x["composite_score"], reverse=True)
        return results

    # ── Community detection ──

    def get_character_communities(self) -> list[dict]:
        return self._cached("char_communities", self._compute_character_communities)

    def _compute_character_communities(self) -> list[dict]:
        chars = self.list_entities(entity_type="character")
        if not chars:
            return []
        char_ids = [c.id for c in chars]

        adj = self._get_graph_adjacency(char_ids)

        # BFS connected components
        visited: set = set()
        communities: list[list[dict]] = []
        for cid in char_ids:
            if cid in visited:
                continue
            component: list[dict] = []
            queue = [cid]
            while queue:
                node = queue.pop(0)
                if node in visited:
                    continue
                visited.add(node)
                char = next((c for c in chars if c.id == node), None)
                component.append({"id": node, "name": char.name if char else node})
                for nb in adj.get(node, set()):
                    if nb not in visited:
                        queue.append(nb)
            if component:
                communities.append(component)

        result: list[dict] = []
        for i, comp in enumerate(communities):
            result.append(
                {
                    "community_id": f"comm_{i}",
                    "size": len(comp),
                    "members": comp,
                }
            )
        result.sort(key=lambda x: x["size"], reverse=True)
        return result

    def detect_communities(self) -> dict:
        """Label propagation community detection."""
        chars = self.list_entities(entity_type="character")
        if not chars:
            return {"community_count": 0, "communities": {}, "intra_community_missing": []}
        char_ids = [c.id for c in chars]
        adj = self._get_graph_adjacency(char_ids)

        # Initialize: each character its own community
        community: dict[str, str] = {cid: cid for cid in char_ids}

        # 3 rounds of label propagation
        for _ in range(3):
            new_community = dict(community)
            for cid in char_ids:
                neighbor_comms: dict[str, int] = {}
                for nb in adj.get(cid, set()):
                    nc = community.get(nb, nb)
                    neighbor_comms[nc] = neighbor_comms.get(nc, 0) + 1
                if neighbor_comms:
                    # Pick the most common neighbor community
                    new_comm = max(neighbor_comms, key=neighbor_comms.get)
                    new_community[cid] = new_comm
            community = new_community

        # Group by community
        comm_groups: dict[str, list[dict]] = {}
        for cid in char_ids:
            comm = community.get(cid, cid)
            char = next((c for c in chars if c.id == cid), None)
            comm_groups.setdefault(comm, []).append(
                {
                    "id": cid,
                    "name": char.name if char else cid,
                }
            )

        # Find intra-community pairs without direct edges
        intra_missing = []
        for comm_id, members in comm_groups.items():
            if len(members) < 2 or len(members) > 15:
                continue
            for i, a in enumerate(members):
                for b in members[i + 1 :]:
                    if b["id"] not in adj.get(a["id"], set()):
                        intra_missing.append(
                            {
                                "community": comm_id,
                                "char_a": a["name"],
                                "char_b": b["name"],
                                "aid": a["id"],
                                "bid": b["id"],
                            }
                        )

        return {
            "community_count": len(comm_groups),
            "communities": {k: [m["name"] for m in v] for k, v in comm_groups.items() if 2 <= len(v) <= 15},
            "intra_community_missing": intra_missing[:20],
        }

    # ── Clustering coefficient ──

    def get_clustering_coefficient(self) -> list[dict]:
        return self._cached("clustering", self._compute_clustering_coefficient)

    def _compute_clustering_coefficient(self) -> list[dict]:
        chars = self.list_entities(entity_type="character")
        if not chars:
            return []
        char_ids = [c.id for c in chars]
        adj = self._get_graph_adjacency(char_ids)

        results: list[dict[str, Any]] = []
        for cid in char_ids:
            neighbors = list(adj.get(cid, set()))
            n_count = len(neighbors)
            if n_count < 2:
                continue
            max_edges = n_count * (n_count - 1) / 2
            if max_edges == 0:
                continue

            edge_count = 0
            for i, a_id in enumerate(neighbors):
                for b_id in neighbors[i + 1 :]:
                    if b_id in adj.get(a_id, set()):
                        edge_count += 1

            cc = round(edge_count / max_edges, 3)
            char = next((c for c in chars if c.id == cid), None)
            results.append(
                {
                    "entity_id": cid,
                    "name": char.name if char else cid,
                    "clustering_coefficient": cc,
                    "neighbor_count": n_count,
                    "edges_among_neighbors": edge_count,
                }
            )

        results.sort(key=lambda x: x["clustering_coefficient"], reverse=True)
        return results

    # ── Link prediction (Adamic-Adar / Jaccard) ──

    def _compute_link_prediction(self, top_n: int = 20) -> list[dict]:
        """Predict missing character relationships via Adamic-Adar / Jaccard."""
        chars = self.list_entities(entity_type="character")
        if len(chars) < 2:
            return []
        char_ids = [c.id for c in chars]

        adj = self._get_graph_adjacency(char_ids)
        degree = {cid: len(adj.get(cid, set())) for cid in char_ids}

        predictions: list[dict[str, Any]] = []
        for i, a_id in enumerate(char_ids):
            for b_id in char_ids[i + 1 :]:
                if b_id in adj.get(a_id, set()):
                    continue  # already connected

                common = adj.get(a_id, set()) & adj.get(b_id, set())
                if not common:
                    continue

                union = adj.get(a_id, set()) | adj.get(b_id, set())
                common_count = len(common)
                jaccard = common_count / len(union) if union else 0
                adamic_adar = sum(1.0 / math.log(degree.get(cn, 0) + 2) for cn in common)

                char_a = next((c for c in chars if c.id == a_id), None)
                char_b = next((c for c in chars if c.id == b_id), None)
                predictions.append(
                    {
                        "char_a_id": a_id,
                        "char_a_name": char_a.name if char_a else a_id,
                        "char_b_id": b_id,
                        "char_b_name": char_b.name if char_b else b_id,
                        "common_neighbors": common_count,
                        "adamic_adar": round(adamic_adar, 4),
                        "jaccard": round(jaccard, 4),
                    }
                )

        predictions.sort(key=lambda x: x["adamic_adar"], reverse=True)
        return predictions[:top_n]

    def get_link_prediction(self, top_n: int = 20) -> list[dict]:
        """Predict missing character relationships via Adamic-Adar / Jaccard.

        Public wrapper around _compute_link_prediction, matching the
        API expected by routes/knowledge.py.
        """
        return self._compute_link_prediction(top_n=top_n)

    # ── Bridge / Forgotten / Missing-relation analysis ──

    def find_bridge_characters(self) -> list[dict]:
        """Find bridge characters using BFS-based betweenness approximation."""
        chars = self.list_entities(entity_type="character")
        if len(chars) < 3:
            return []
        char_ids = [c.id for c in chars]
        adj = self._get_graph_adjacency(char_ids)

        # Count how many pairs each character bridges (shortest path goes through them)
        bridge_count: dict[str, int] = {}
        bridge_pairs: dict[str, list] = {}

        for i, a_id in enumerate(char_ids):
            for b_id in char_ids[i + 1 :]:
                if a_id == b_id:
                    continue
                if b_id in adj.get(a_id, set()):
                    continue  # directly connected, no bridge needed

                # BFS shortest path
                parent: dict[str, str | None] = {a_id: None}
                queue = [a_id]
                found = False
                while queue and not found:
                    cur = queue.pop(0)
                    for nb in adj.get(cur, set()):
                        if nb not in parent:
                            parent[nb] = cur
                            if nb == b_id:
                                found = True
                                break
                            queue.append(nb)

                if found:
                    # Backtrack, exclude endpoints
                    path_nodes = []
                    node = b_id
                    while node is not None:
                        path_nodes.append(node)
                        node = parent.get(node)
                    path_nodes.reverse()
                    # Count internal nodes as bridges
                    for n in path_nodes[1:-1]:
                        if n != a_id and n != b_id:
                            bridge_count[n] = bridge_count.get(n, 0) + 1
                            if n not in bridge_pairs:
                                bridge_pairs[n] = []
                            if len(bridge_pairs[n]) < 5:
                                bridge_pairs[n].append([a_id, b_id])

        results: list[dict[str, Any]] = []
        for cid, count in sorted(bridge_count.items(), key=lambda x: x[1], reverse=True):
            char = next((c for c in chars if c.id == cid), None)
            sample = bridge_pairs.get(cid, [])
            sample_names = []
            for pair in sample[:5]:
                a = next((c.name for c in chars if c.id == pair[0]), pair[0])
                b = next((c.name for c in chars if c.id == pair[1]), pair[1])
                sample_names.append([a, b])
            results.append(
                {
                    "entity_id": cid,
                    "entity_name": char.name if char else cid,
                    "bridge_count": count,
                    "would_disconnect": sample_names,
                }
            )

        return results

    def find_forgotten_characters(self, max_order: int, threshold: int = 5) -> list[dict]:
        """Find characters who haven't appeared in recent events."""
        chars = self.list_entities(entity_type="character")
        if not chars:
            return []
        char_ids = [c.id for c in chars]

        # Count events per character
        appear = dict.fromkeys(char_ids, 0)
        events = self.list_timeline_events()
        for evt in events:
            _count_entity_refs(evt, char_ids, appear)

        # Characters with total appearances below threshold
        results: list[dict[str, Any]] = []
        for cid in char_ids:
            if appear.get(cid, 0) < threshold:
                total = appear.get(cid, 0)
                char = next((c for c in chars if c.id == cid), None)
                results.append(
                    {
                        "name": char.name if char else cid,
                        "entity_id": cid,
                        "total_appearances": total,
                        "important": total == 0,  # hasn't appeared at all
                    }
                )

        results.sort(key=lambda x: x["total_appearances"])
        return results

    def find_missing_relations(self, char_ids: list[str]) -> list[dict]:
        """Find character pairs with no path in the relationship graph."""
        if len(char_ids) < 2:
            return []
        adj = self._get_graph_adjacency(char_ids)
        missing = []
        for i, a_id in enumerate(char_ids):
            for b_id in char_ids[i + 1 :]:
                if b_id in adj.get(a_id, set()):
                    continue
                # BFS to check if path exists
                visited = {a_id}
                queue = [a_id]
                found = False
                while queue and not found:
                    cur = queue.pop(0)
                    for nb in adj.get(cur, set()):
                        if nb not in visited:
                            visited.add(nb)
                            if nb == b_id:
                                found = True
                                break
                            queue.append(nb)
                if not found:
                    missing.append({"from": a_id, "to": b_id})
        return missing

    # ════════════════════════════════════════════════════════════════
    # Timeline-entity linking (INVOLVES equivalent)
    # ════════════════════════════════════════════════════════════════


# ── Module-level helpers ──


    def clear_all_timeline_events(self, project_id: str | None = None) -> int:
        """Delete all timeline events and their INVOLVES edges."""
        pid = project_id or self.project_id
        # Timeline nodes are relation sources (INVOLVES / OCCURRED_AT edges).
        self._run(
            "DELETE FROM relations WHERE from_entity IN "
            "(SELECT id FROM timeline_events WHERE project_id=?) AND project_id=?",
            (pid, pid),
        )
        rows = self._run("SELECT COUNT(*) c FROM timeline_events WHERE project_id=?", (pid,))
        self._run("DELETE FROM timeline_events WHERE project_id=?", (pid,))
        return rows[0]["c"] if rows else 0


    # ── Missing-method debt (Neo4j→SQLite migration) ──

    def schedule_foreshadow(self, foreshadow_id: str, chapter: str) -> None:
        """Plan a foreshadow to resolve at a chapter (scheduled_chapter)."""
        self._run(
            "UPDATE foreshadows SET scheduled_chapter=?, status='planned', planned_resolve_arc=? WHERE id=?",
            (chapter, chapter, foreshadow_id),
        )

    def postpone_foreshadow(self, foreshadow_id: str) -> None:
        """Move a 'due' foreshadow back to 'planned' (keep planned arc)."""
        self._run(
            "UPDATE foreshadows SET status='planned' WHERE id=?",
            (foreshadow_id,),
        )

    def list_scheduled_foreshadows(self, chapter: str) -> list[Foreshadow]:
        """Foreshadows scheduled to resolve at this chapter."""
        rows = self._run(
            "SELECT * FROM foreshadows WHERE scheduled_chapter=?",
            (chapter,),
        )
        return [self._row_to_foreshadow(r) for r in rows]

    def update_snapshot(self, snapshot_id: str, payload: dict) -> None:
        """Update snapshot fields (whitelisted keys only)."""
        allowed = {"label", "phase", "phase_key", "data", "description", "is_current", "time_point"}
        sets = []
        params = []
        for k, v in payload.items():
            if k in allowed:
                sets.append(f"{k}=?")
                params.append(v)
        if sets:
            params.append(snapshot_id)
            self._run(f"UPDATE snapshots SET {', '.join(sets)} WHERE id=?", tuple(params))

    def add_temporal_relation(self, from_id: str, to_id: str, rel_type: str, since_chapter: str) -> None:
        """Time-annotated relationship edge (data.since_chapter)."""
        import uuid as _uuid

        from core.knowledge import Relation, RelationType

        try:
            typed = RelationType(rel_type)
        except ValueError:
            typed = rel_type  # type: ignore[assignment]  # non-enum edge type (e.g. DEPENDS_ON)
        self.add_relation(
            Relation(
                id=str(_uuid.uuid4())[:8],
                from_entity=from_id,
                to_entity=to_id,
                type=typed,
                data={"since_chapter": since_chapter},
            )
        )

    def add_foreshadow_dependency(self, from_id: str, to_id: str) -> None:
        """DEPENDS_ON edge between foreshadows (stored in relations)."""
        import uuid as _uuid

        from core.knowledge import Relation

        self.add_relation(
            Relation(
                id=str(_uuid.uuid4())[:8],
                from_entity=from_id,
                to_entity=to_id,
                type="DEPENDS_ON",  # type: ignore[arg-type]  # non-enum edge type
                data={},
            )
        )

    def get_entity_state_at_time(self, entity_id: str, time_order: int, track_id: str = "") -> dict | None:
        """Best snapshot state at or before time_order."""
        rows = self._run(
            "SELECT * FROM snapshots WHERE character_id=? AND time_order<=? "
            "ORDER BY time_order DESC LIMIT 1",
            (entity_id, time_order),
        )
        return dict(rows[0]) if rows else None

    # ── Legacy analysis endpoints: minimal SQLite implementation ──

    def get_pov_subgraph(self, character_id: str) -> dict:
        """Relations involving a character (pov subgraph)."""
        rels = self._run(
            "SELECT * FROM relations WHERE (from_entity=? OR to_entity=?) AND project_id=?",
            (character_id, character_id, self.project_id),
        )
        return {"character_id": character_id, "relations": [dict(r) for r in rels], "nodes": []}

    def get_character_knowledge(self, character_id: str, at_chapter: str | int = "") -> dict:
        """What this character is linked to (entities + snapshots)."""
        rels = self._run(
            "SELECT * FROM relations WHERE (from_entity=? OR to_entity=?) AND project_id=?",
            (character_id, character_id, self.project_id),
        )
        snaps = self._run(
            "SELECT * FROM snapshots WHERE character_id=? AND project_id=? ORDER BY time_order DESC LIMIT 5",
            (character_id, self.project_id),
        )
        return {"relations": [dict(r) for r in rels], "snapshots": [dict(s) for s in snaps]}

    def detect_foreshadow_cycles(self) -> list[dict]:
        """Detect cycles in DEPENDS_ON relations (2-node self-cycles only)."""
        rows = self._run(
            """
            SELECT r1.from_entity AS a, r1.to_entity AS b
            FROM relations r1 JOIN relations r2
              ON r1.from_entity = r2.to_entity AND r1.to_entity = r2.from_entity
            WHERE r1.type='DEPENDS_ON' AND r2.type='DEPENDS_ON'
              AND r1.from_entity < r1.to_entity AND r1.project_id=?
            """,
            (self.project_id,),
        )
        return [{"from": r["a"], "to": r["b"], "cycle": True} for r in rows]

    def get_foreshadow_resolution_order(self) -> list[dict]:
        """Foreshadows ordered by scheduled resolution chapter."""
        rows = self._run(
            "SELECT id, text, status, scheduled_chapter FROM foreshadows "
            "WHERE project_id=? AND scheduled_chapter IS NOT NULL AND scheduled_chapter != '' "
            "ORDER BY scheduled_chapter",
            (self.project_id,),
        )
        return [dict(r) for r in rows]


    # ── Legacy analysis endpoints: SQLite implementations ──

    def get_full_graph(self, at_time_order: int | None = None, include_simulations: bool = False) -> dict:
        """Full knowledge graph: nodes (entities) + links (relations)."""
        nodes = self._run(
            "SELECT id, entity_type, name, data FROM entities WHERE project_id=?", (self.project_id,)
        )
        rels = self._run(
            "SELECT from_entity, to_entity, type FROM relations WHERE project_id=?", (self.project_id,)
        )
        return {
            "nodes": [dict(r) for r in nodes],
            "links": [dict(r) for r in rels],
        }

    def get_map_at_time(self, time_order: int) -> dict:
        """Locations and relations at a point in time."""
        locs = self._run(
            "SELECT id, entity_type, name, data FROM entities "
            "WHERE project_id=? AND entity_type='location'",
            (self.project_id,),
        )
        rels = self._run(
            "SELECT * FROM relations WHERE project_id=?", (self.project_id,)
        )
        return {"locations": [dict(r) for r in locs], "relations": [dict(r) for r in rels], "time_order": time_order}

    def find_downstream_impact(self, event_id: str) -> dict:
        """Entities/events downstream of a timeline event (via INVOLVES + one hop)."""
        involved = self._run(
            "SELECT to_entity AS eid FROM relations WHERE from_entity=? AND type='INVOLVES' AND project_id=?",
            (event_id, self.project_id),
        )
        eids = [r["eid"] for r in involved]
        entities = []
        relations = []
        if eids:
            placeholders = ",".join("?" * len(eids))
            entities = self._run(
                f"SELECT id, entity_type, name FROM entities WHERE id IN ({placeholders}) AND project_id=?",
                tuple(eids + [self.project_id]),
            )
            relations = self._run(
                f"SELECT * FROM relations WHERE (from_entity IN ({placeholders}) OR to_entity IN ({placeholders})) AND project_id=?",
                tuple(eids + eids + [self.project_id]),
            )
        return {"event_id": event_id, "entities": [dict(r) for r in entities], "relations": [dict(r) for r in relations]}

    def get_network_evolution(self) -> list[dict]:
        """Node/edge counts bucketed by time_order (from relations.created_at is not
        reliable, so bucket by distinct entity creation order — approximate)."""
        points = self._run(
            "SELECT COUNT(*) AS c FROM entities WHERE project_id=?", (self.project_id,)
        )
        edge_count = self._run(
            "SELECT COUNT(*) AS c FROM relations WHERE project_id=?", (self.project_id,)
        )
        return [{"time_order": 0, "node_count": points[0]["c"] if points else 0,
                 "edge_count": edge_count[0]["c"] if edge_count else 0}]

    def get_character_heatmap(self) -> list[dict]:
        """Characters with chapter-mention counts (approximate via relations)."""
        rows = self._run(
            """
            SELECT e.name AS name, COUNT(r.id) AS mention_count
            FROM entities e
            LEFT JOIN relations r ON (r.from_entity = e.id OR r.to_entity = e.id) AND r.project_id = e.project_id
            WHERE e.entity_type='character' AND e.project_id=?
            GROUP BY e.id ORDER BY mention_count DESC
            """,
            (self.project_id,),
        )
        return [dict(r) for r in rows]

    def get_foreshadow_dependency_analysis(self) -> dict:
        """Foreshadow status + DEPENDS_ON edges."""
        foreshadows = self._run(
            "SELECT id, text, status, resolve_chapter FROM foreshadows WHERE project_id=?",
            (self.project_id,),
        )
        deps = self._run(
            "SELECT from_entity, to_entity FROM relations WHERE type='DEPENDS_ON' AND project_id=?",
            (self.project_id,),
        )
        return {"foreshadows": [dict(r) for r in foreshadows], "dependencies": [dict(r) for r in deps]}

    def aggregate_narrative_arcs(self) -> list[dict]:
        """Timeline events grouped by track (arc)."""
        rows = self._run(
            "SELECT track_id, track_name, COUNT(*) AS event_count, MIN(time_order) AS start_order, MAX(time_order) AS end_order "
            "FROM timeline_events WHERE project_id=? GROUP BY track_id, track_name",
            (self.project_id,),
        )
        return [dict(r) for r in rows]

    def get_pacing_analysis(self) -> dict:
        """Basic pacing stats from timeline density."""
        rows = self._run(
            "SELECT COUNT(*) AS event_count, AVG(time_order) AS avg_order FROM timeline_events WHERE project_id=?",
            (self.project_id,),
        )
        return {"timeline_events": rows[0]["event_count"] if rows else 0,
                "avg_time_order": rows[0]["avg_order"] if rows else 0}

    def match_foreshadow_resolutions(self, chapters: list[dict], llm_chat=None) -> list[dict]:
        """Keyword-based foreshadow resolution matching (deterministic; no LLM)."""
        foreshadows = self._run(
            "SELECT id, text, hint, resolve_keywords FROM foreshadows "
            "WHERE project_id=? AND (resolved = 0 OR resolved IS NULL)",
            (self.project_id,),
        )
        matches = []
        for f in foreshadows:
            keywords = (f.get("resolve_keywords") or "").lower().split()
            hit_chapter = ""
            for ch in chapters:
                body = (ch.get("content") or "").lower()
                if any(kw and kw in body for kw in keywords):
                    hit_chapter = ch.get("id", "")
                    break
            matches.append({"foreshadow_id": f["id"], "text": f.get("text", ""), "match_chapter": hit_chapter})
        return matches


def _count_entity_refs(event, entity_ids: list[str], counter: dict[str, int]) -> None:
    """Count how many timeline events reference each entity ID."""
    for eid in entity_ids:
        if event.chapter_ref and eid in event.chapter_ref:
            counter[eid] = counter.get(eid, 0) + 1
            continue
        if event.location_ref and eid in event.location_ref:
            counter[eid] = counter.get(eid, 0) + 1


# ════════════════════════════════════════════════════════════════
# Constraint operations
# ════════════════════════════════════════════════════════════════
