"""SQLite store — narrative analytics and diagnostics.

Part of the ``core.sqlite_store`` package.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime

from .graph import GraphMixin

logger = logging.getLogger(__name__)


class AnalyticsMixin(GraphMixin):
    """Narrative analytics, consistency checks and insights."""

    def link_timeline_to_entities(self, event_id: str, entity_ids: list[str]) -> int:
        """Record that a timeline event involves certain entities.

        Stores the relationship in the event's data field as a JSON array
        of involved entity IDs.  Returns the number of links created.
        """
        if not entity_ids:
            return 0
        evt = self.get_timeline_event(event_id)
        if not evt:
            return 0
        # Update data field with involved entities
        data = {"involved_entities": entity_ids}
        now = datetime.now().isoformat()
        self._execute(
            "UPDATE timeline_events SET data=?, updated_at=? WHERE id=? AND project_id=?",
            (json.dumps(data, ensure_ascii=False), now, event_id, self.project_id),
        )
        self._invalidate_cache(self.project_id)
        return len(entity_ids)

    def get_timeline_involved_entities(self, event_id: str) -> list[str]:
        """Get entity IDs involved in a timeline event."""
        row = self._run_single(
            "SELECT data FROM timeline_events WHERE id=? AND project_id=?",
            (event_id, self.project_id),
        )
        if not row:
            return []
        data = json.loads(row["data"]) if isinstance(row["data"], str) else (row["data"] or {})
        return list(data.get("involved_entities", []))

    # ════════════════════════════════════════════════════════════════
    # Consistency check
    # ════════════════════════════════════════════════════════════════

    def check_consistency(self) -> dict:
        """Check graph consistency — returns issues and stats."""
        issues = []

        # 1. Location conflict: entity at multiple locations
        loc_rows = self._run(
            """
            SELECT e1.name AS entity, e2.name AS loc_a, e3.name AS loc_b
            FROM relations r1
            JOIN entities e1 ON r1.from_entity = e1.id
            JOIN entities e2 ON r1.to_entity = e2.id
            JOIN relations r2 ON r2.from_entity = r1.from_entity AND r2.project_id = r1.project_id
            JOIN entities e3 ON r2.to_entity = e3.id
            WHERE r1.type = 'LOCATED_AT' AND r2.type = 'LOCATED_AT'
              AND r1.to_entity <> r2.to_entity
              AND r1.project_id = ?
            LIMIT 20
        """,
            (self.project_id,),
        )
        for r in loc_rows:
            issues.append(
                {
                    "type": "location_conflict",
                    "severity": "high",
                    "description": f"实体「{r['entity']}」同时位于「{r['loc_a']}」和「{r['loc_b']}」",
                }
            )

        # 2. Temporal contradiction: A BEFORE B AND B BEFORE A
        temp_rows = self._run(
            """
            SELECT a.name AS ea, b.name AS eb
            FROM relations r1
            JOIN entities a ON r1.from_entity = a.id
            JOIN relations r2 ON r1.from_entity = r2.to_entity AND r1.to_entity = r2.from_entity
            JOIN entities b ON r1.to_entity = b.id
            WHERE r1.type = 'BEFORE' AND r2.type = 'BEFORE'
              AND r1.project_id = ? AND r2.project_id = ?
            LIMIT 10
        """,
            (self.project_id, self.project_id),
        )
        for r in temp_rows:
            issues.append(
                {
                    "type": "temporal_conflict",
                    "severity": "high",
                    "description": f"时序矛盾: 「{r['ea']}」先于「{r['eb']}」又后于「{r['eb']}」",
                }
            )

        # 3. Isolated entities (no relations)
        isolated = self._run(
            """
            SELECT e.name, e.entity_type FROM entities e
            WHERE e.project_id = ? AND e.id NOT IN (
                SELECT DISTINCT from_entity FROM relations WHERE project_id = ?
                UNION
                SELECT DISTINCT to_entity FROM relations WHERE project_id = ?
            )
        """,
            (self.project_id, self.project_id, self.project_id),
        )
        for r in isolated:
            issues.append(
                {
                    "type": "isolated_entity",
                    "severity": "medium",
                    "description": f"实体「{r['name']}」（{r['entity_type']}）无任何关系连接",
                }
            )

        stats = {
            "entity_count": len(self.list_entities()),
            "relation_count": len(self.list_relations()),
            "foreshadow_count": len(self.list_foreshadows()),
            "issues_found": len(issues),
        }
        return {"contradictions": issues, "stats": stats}

    # ════════════════════════════════════════════════════════════════
    # Graph insights & narrative diagnosis
    # ════════════════════════════════════════════════════════════════

    def get_graph_insights(self) -> dict:
        return self._cached("insights", self._compute_graph_insights)

    def _compute_graph_insights(self) -> dict:
        insights: dict = {
            "forgotten_characters": [],
            "unresolved_foreshadows": [],
            "disconnected_pairs": [],
            "bridge_characters": [],
            "underutilized_locations": [],
            "suggestions": [],
        }

        chars = self.list_entities(entity_type="character")
        locations = self.list_entities(entity_type="location")
        all_fores = self.list_foreshadows()

        # Forgotten characters
        timeline_events = self.list_timeline_events()
        if timeline_events:
            max_order = int(max(e.time_order for e in timeline_events))
            forgotten = self.find_forgotten_characters(max_order, threshold=5)
            important = [c for c in forgotten if c.get("important")]
            insights["forgotten_character_count"] = len(important)
            insights["forgotten_characters"] = important[:5]
            if important:
                names = ", ".join(c["name"] for c in important[:3])
                insights["suggestions"].append(
                    {
                        "type": "warning",
                        "priority": "high",
                        "message": f"重要角色已多章未出场：{names}。考虑在下一章让他们露面或提及。",
                    }
                )

        # Unresolved foreshadows
        open_fores = [f for f in all_fores if not f.resolved]
        insights["unresolved_foreshadow_count"] = len(open_fores)
        if open_fores:
            insights["unresolved_foreshadows"] = [
                {"id": f.id, "text": f.text[:50], "related_entities": f.related_entities} for f in open_fores[:10]
            ]
            if len(open_fores) > 3:
                insights["suggestions"].append(
                    {
                        "type": "reminder",
                        "priority": "medium",
                        "message": f"有 {len(open_fores)} 个伏笔尚未回收，注意适时推进。",
                    }
                )

        # Disconnected pairs
        if 2 < len(chars) <= 30:
            char_ids = [c.id for c in chars]
            missing = self.find_missing_relations(char_ids)
            insights["disconnected_pair_count"] = len(missing)
            # Map to frontend format: entity_a/entity_b with name and warning
            char_map = {c.id: c.name for c in chars}
            insights["disconnected_pairs"] = [
                {
                    "entity_a": {"id": p["from"], "name": char_map.get(p["from"], p["from"])},
                    "entity_b": {"id": p["to"], "name": char_map.get(p["to"], p["to"])},
                    "warning": "这两角色在关系图中无路径连接",
                }
                for p in missing[:5]
            ]
            if missing:
                insights["suggestions"].append(
                    {
                        "type": "info",
                        "priority": "low",
                        "message": f"发现 {len(missing)} 对角色之间无关系路径。",
                    }
                )

        # Bridge characters
        bridges = self.find_bridge_characters()
        insights["bridge_character_count"] = len(bridges)
        insights["bridge_characters"] = bridges[:5]
        if bridges:
            names = ", ".join(b["entity_name"] for b in bridges[:3])
            insights["suggestions"].append(
                {
                    "type": "info",
                    "priority": "medium",
                    "message": f"关键枢纽角色：{names}。这些角色连接多个关系链，修改时需谨慎。",
                }
            )

        # Unused locations
        if locations:
            char_locations = set()
            for loc in locations:
                rows = self._run(
                    "SELECT from_entity FROM relations WHERE to_entity=? AND type='LOCATED_AT' AND project_id=?",
                    (loc.id, self.project_id),
                )
                if rows:
                    char_locations.add(loc.id)
            unused = [loc for loc in locations if loc.id not in char_locations]
            insights["unused_location_count"] = len(unused)
            insights["underutilized_locations"] = [{"id": loc.id, "name": loc.name} for loc in unused[:5]]

        return insights

    def get_narrative_diagnosis(self) -> dict:
        return self._cached("diagnosis", self._compute_narrative_diagnosis)

    def _compute_narrative_diagnosis(self) -> dict:
        raw = self.get_graph_insights()
        forgotten = raw.get("forgotten_characters", [])
        forgotten_count = raw.get("forgotten_character_count", len(forgotten))
        unresolved_fs_count = raw.get("unresolved_foreshadow_count", 0)
        disconnected_count = raw.get("disconnected_pair_count", 0)
        bridges = raw.get("bridge_characters", [])

        total_chars = len(self.list_entities(entity_type="character"))
        total_fores = len(self.list_foreshadows())

        dims = []
        # Character continuity
        if forgotten_count > 0:
            important = sum(1 for c in forgotten if c.get("important"))
            weighted = important * 2 + (forgotten_count - important)
            rate = weighted / max(total_chars, 1) / 2
            char_score = round(100 * (1 - rate**0.4))
        else:
            char_score = 100
        dims.append(
            {
                "name": "角色连贯性",
                "score": char_score,
                "finding": f"{forgotten_count} 个角色多章未出场" if forgotten_count else "所有角色出场连贯",
                "weight": 0.20,
            }
        )

        # Foreshadow management
        if unresolved_fs_count > 0:
            rate = unresolved_fs_count / max(total_fores, 1)
            fore_score = round(100 * (1 / (1 + math.log(1 + rate * 8))))
        else:
            fore_score = 100
        dims.append(
            {
                "name": "伏笔管理",
                "score": fore_score,
                "finding": f"{unresolved_fs_count} 个伏笔待回收" if unresolved_fs_count else "所有伏笔已回收",
                "weight": 0.15,
            }
        )

        # Relationship network
        if total_chars > 2:
            max_pairs = total_chars * (total_chars - 1) / 2
            disc_rate = min(disconnected_count / max(max_pairs, 1), 1.0)
            rel_score = round(100 * (1 - disc_rate * 0.7))
        else:
            rel_score = 100
        dims.append(
            {
                "name": "关系网络",
                "score": rel_score,
                "finding": f"{disconnected_count} 对角色无关联" if disconnected_count else "关系网络良好",
                "weight": 0.15,
            }
        )

        # Overall health
        overall = round(sum(d["score"] * d["weight"] for d in dims))
        if overall >= 90:
            summary = "叙事结构健康，各维度表现均衡。"
        elif overall >= 70:
            weak = [d for d in dims if d["score"] < 70]
            summary = f"整体良好，但 {len(weak)} 个维度需要关注：{'、'.join(d['name'] for d in weak[:2])}。"
        else:
            summary = "叙事结构存在较多问题，建议系统性地修复。"

        return {
            "health_score": overall,
            "summary": summary,
            "dimensions": dims,
            "action_items": [],
            "raw_data": {
                "forgotten_count": forgotten_count,
                "foreshadow_count": unresolved_fs_count,
                "disconnected_count": disconnected_count,
                "bridge_count": len(bridges),
            },
        }

    # ════════════════════════════════════════════════════════════════
    # Worldbuilding metrics
    # ════════════════════════════════════════════════════════════════

    def get_worldbuilding_metrics(self) -> dict:
        """Get comprehensive worldbuilding statistics.

        Returns flat structure matching frontend MetricsData interface:
        entity_count, relation_count, density, isolated_entities, isolated_count,
        largest_component_size, fragmentation_ratio, health_assessment, health_score.
        """
        chars = self.list_entities(entity_type="character")
        locations = self.list_entities(entity_type="location")
        orgs = self.list_entities(entity_type="organization")
        items = self.list_entities(entity_type="item")
        skills = self.list_entities(entity_type="skill")
        concepts = self.list_entities(entity_type="concept")
        events_e = self.list_entities(entity_type="event")

        relations = self.list_relations()

        total_entities = (
            len(chars) + len(locations) + len(orgs) + len(items) + len(skills) + len(concepts) + len(events_e)
        )
        relation_count = len(relations)
        max_pairs = total_entities * (total_entities - 1) / 2 if total_entities > 1 else 1
        density_val = round(relation_count / max_pairs, 4) if max_pairs > 0 else 0

        # Isolated entities (no relations)
        isolated_entities = []
        for e in self.list_entities():
            has_rel = self._run_single(
                "SELECT 1 FROM relations WHERE (from_entity=? OR to_entity=?) AND project_id=? LIMIT 1",
                (e.id, e.id, self.project_id),
            )
            if not has_rel:
                isolated_entities.append({"name": e.name, "type": e.type})

        # Connected components (via entity graph)
        all_entity_ids = [e.id for e in self.list_entities()]
        adj = self._get_graph_adjacency(all_entity_ids)
        visited: set = set()
        component_sizes: list[int] = []
        for eid in all_entity_ids:
            if eid in visited:
                continue
            size = 0
            stack = [eid]
            while stack:
                cur = stack.pop()
                if cur in visited:
                    continue
                visited.add(cur)
                size += 1
                for nb in adj.get(cur, set()):
                    if nb not in visited:
                        stack.append(nb)
            if size > 0:
                component_sizes.append(size)

        largest_component = max(component_sizes) if component_sizes else 0
        fragmentation_ratio = 1 - (largest_component / max(total_entities, 1)) if total_entities > 0 else 0

        # Health assessment
        if density_val >= 0.1 and fragmentation_ratio <= 0.2 and relation_count >= total_entities:
            health = "良好"
            score = 85 + min(15, int(density_val * 100))
        elif density_val >= 0.03 or fragmentation_ratio <= 0.5:
            health = "一般"
            score = 50 + min(35, int(density_val * 200))
        else:
            health = "稀疏"
            score = max(5, min(50, int(density_val * 300)))

        return {
            "entity_count": total_entities,
            "relation_count": relation_count,
            "density": density_val,
            "isolated_entities": isolated_entities,
            "isolated_count": len(isolated_entities),
            "largest_component_size": largest_component,
            "fragmentation_ratio": round(fragmentation_ratio, 4),
            "health_assessment": health,
            "health_score": score,
        }

    def get_location_importance(self) -> list[dict]:
        """Rank locations by composite importance score."""
        locations = self.list_entities(entity_type="location")
        if not locations:
            return []

        results = []
        for loc in locations:
            # Count degree (relations involving this location)
            degree_rows = self._run(
                "SELECT COUNT(*) AS cnt FROM relations WHERE (from_entity=? OR to_entity=?) AND project_id=?",
                (loc.id, loc.id, self.project_id),
            )
            degree = degree_rows[0]["cnt"] if degree_rows else 0

            # Count timeline events at this location
            event_count = 0
            for evt in self.list_timeline_events():
                if evt.location_ref == loc.id or loc.id in evt.location_ref:
                    event_count += 1

            # Count character visits
            visit_rows = self._run(
                "SELECT COUNT(DISTINCT from_entity) AS cnt FROM relations WHERE to_entity=? AND type IN ('LOCATED_AT','BELONGS_TO') AND project_id=?",
                (loc.id, self.project_id),
            )
            visits = visit_rows[0]["cnt"] if visit_rows else 0

            composite = round(degree * 0.30 + event_count * 0.40 + visits * 0.30)

            if composite >= 70:
                role = "核心地点"
            elif composite >= 45:
                role = "重要地点"
            elif composite >= 25:
                role = "次要地点"
            else:
                role = "边缘地点"

            results.append(
                {
                    "entity_id": loc.id,
                    "name": loc.name,
                    "composite_score": min(composite, 100),
                    "role": role,
                    "degree": degree,
                    "event_count": event_count,
                    "character_visits": visits,
                }
            )

        results.sort(key=lambda x: x["composite_score"], reverse=True)
        return results

    def get_organization_importance(self) -> list[dict]:
        """Rank organizations by composite importance."""
        orgs = self.list_entities(entity_type="organization")
        if not orgs:
            return []

        results = []
        for org in orgs:
            degree_rows = self._run(
                "SELECT COUNT(*) AS cnt FROM relations WHERE (from_entity=? OR to_entity=?) AND project_id=?",
                (org.id, org.id, self.project_id),
            )
            degree = degree_rows[0]["cnt"] if degree_rows else 0

            member_rows = self._run(
                "SELECT COUNT(DISTINCT from_entity) AS cnt FROM relations WHERE to_entity=? AND type IN ('BELONGS_TO','OWNS','MASTER_OF') AND project_id=?",
                (org.id, self.project_id),
            )
            members = member_rows[0]["cnt"] if member_rows else 0

            event_count = 0
            for evt in self.list_timeline_events():
                if org.id in evt.location_ref or org.id == evt.location_ref:
                    event_count += 1

            composite = round(degree * 0.25 + members * 0.45 + event_count * 0.30)

            if composite >= 70:
                role = "核心势力"
            elif composite >= 45:
                role = "重要势力"
            elif composite >= 25:
                role = "次要势力"
            else:
                role = "边缘势力"

            results.append(
                {
                    "entity_id": org.id,
                    "name": org.name,
                    "composite_score": min(composite, 100),
                    "role": role,
                    "degree": degree,
                    "member_count": members,
                    "event_count": event_count,
                }
            )

        results.sort(key=lambda x: x["composite_score"], reverse=True)
        return results

    # ════════════════════════════════════════════════════════════════
    # Event causal chain
    # ════════════════════════════════════════════════════════════════

    def get_event_causal_chain(self) -> dict:
        """Build event DAG from timeline, find critical path."""
        events = self.list_timeline_events()
        if not events:
            return {"critical_path": [], "branches": 0}

        sorted_events = sorted(events, key=lambda e: e.time_order)
        critical_path = []
        for i, evt in enumerate(sorted_events):
            entry = {"id": evt.id, "label": evt.label, "order": evt.time_order}
            if i > 0:
                entry["depends_on"] = sorted_events[i - 1].id
            critical_path.append(entry)

        tracks = {e.track_id for e in events}

        return {
            "critical_path": critical_path,
            "branches": len(tracks),
            "total_events": len(events),
        }

    # ════════════════════════════════════════════════════════════════
    # Knowledge summary & search
    # ════════════════════════════════════════════════════════════════

    def get_knowledge_summary(self) -> str:
        """Return a text summary of all knowledge in the store."""
        entities = self.list_entities()
        relations = self.list_relations()
        foreshadows = self.list_foreshadows()
        timeline = self.list_timeline_events()

        lines = [f"项目 {self.project_id} 知识库摘要", "=" * 40, ""]
        lines.append(f"实体总数: {len(entities)}")
        for etype in ["character", "location", "organization", "item", "skill", "concept", "event"]:
            count = len([e for e in entities if e.type == etype])
            if count:
                lines.append(f"  {etype}: {count}")
        lines.append(f"关系总数: {len(relations)}")
        lines.append(f"伏笔总数: {len(foreshadows)}")
        lines.append(f"  未回收: {sum(1 for f in foreshadows if not f.resolved)}")
        lines.append(f"时间线事件: {len(timeline)}")
        return "\n".join(lines)
