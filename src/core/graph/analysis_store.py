"""Graph analysis & insight mixin — extracted from ``graph_store.py``."""

from __future__ import annotations

import math as _math


class AnalysisMixin:
    """Mixin providing graph analysis, insight, and diagnostic methods.

    Depends on ``self._run()``, ``self._run_single()``, ``self.project_id``,
    ``self._invalidate_cache()``, ``self._cached()`` and entity/relation CRUD
    mixin methods via MRO.
    """

    # ── Consistency check (original full implementation) ──

    def check_consistency(self) -> dict:
        issues = []

        # 1. Location conflict
        rows = self._run("""
            MATCH (e:Entity {project_id: $pid})-[r1:LOCATED_AT]->(loc1:Entity {project_id: $pid})
            MATCH (e)-[r2:LOCATED_AT]->(loc2:Entity {project_id: $pid})
            WHERE loc1.id <> loc2.id
            RETURN e.name as entity, loc1.name as loc_a, loc2.name as loc_b
        """, {"pid": self.project_id})
        for r in rows:
            issues.append({"type": "location_conflict", "severity": "high",
                           "description": f"实体「{r['entity']}」同时位于「{r['loc_a']}」和「{r['loc_b']}」"})

        # 2. Temporal contradiction
        rows = self._run("""
            MATCH (a:Entity {project_id: $pid})-[r1:BEFORE]->(b:Entity {project_id: $pid})
            MATCH (b)-[r2:BEFORE]->(a) WHERE a.id <> b.id
            RETURN a.name as ea, b.name as eb
        """, {"pid": self.project_id})
        for r in rows:
            issues.append({"type": "temporal_conflict", "severity": "high",
                           "description": f"时序矛盾: 「{r['ea']}」先于「{r['eb']}」又后于「{r['eb']}」"})

        # 3. Relationship contradiction
        rows = self._run("""
            MATCH (a:Entity {project_id: $pid})-[r]-(b:Entity {project_id: $pid})
            WITH a, b, collect(type(r)) as types WHERE size(types) > 1 AND
                  (('ANTAGONIST' IN types AND 'ALLY' IN types) OR
                   ('ANTAGONIST' IN types AND 'FAMILY' IN types))
            RETURN a.name as ea, b.name as eb, types
        """, {"pid": self.project_id})
        for r in rows:
            issues.append({"type": "relationship_conflict", "severity": "medium",
                           "description": f"关系矛盾: 「{r['ea']}」↔「{r['eb']}」同时具有关系 {', '.join(r['types'])}"})

        # 4. Spatial cycle
        cycle = self._run("""
            MATCH (a:Entity:Location {project_id: $pid})-[:LOCATED_IN]->(b:Entity:Location {project_id: $pid})-[:LOCATED_IN]->(a)
            RETURN a.name as name_a, b.name as name_b
        """, {"pid": self.project_id})
        for r in cycle:
            issues.append({"type": "spatial_cycle", "severity": "high",
                           "description": f"空间包含循环: 「{r['name_a']}」↔「{r['name_b']}」"})

        # 5. Isolated entities
        isolated = self._run("""
            MATCH (e:Entity {project_id: $pid}) WHERE NOT (e)-[]-()
            RETURN e.name as name, e.entity_type as type
        """, {"pid": self.project_id})
        for r in isolated:
            issues.append({"type": "isolated_entity", "severity": "medium",
                           "description": f"实体「{r['name']}」（{r.get('type','?')}）无任何关系连接"})

        # 6. Disconnected character pairs
        disconnected = self._run("""
            MATCH (a:Entity:Character {project_id: $pid}), (b:Entity:Character {project_id: $pid})
            WHERE a.id < b.id AND NOT EXISTS {
                MATCH path = shortestPath(
                    (a)-[:KNOWS|ALLY|FAMILY|ANTAGONIST|ROMANTIC|MASTER_OF|MENTOR_OF|KILLED|SAVED|LOVES*1..3]-(b)
                )
            }
            RETURN a.name as name_a, b.name as name_b LIMIT 10
        """, {"pid": self.project_id})
        for r in disconnected:
            issues.append({"type": "disconnected_characters", "severity": "low",
                           "description": f"角色「{r['name_a']}」与「{r['name_b']}」在关系图中无路径连接"})

        stats = {
            "entity_count": len(self.list_entities()),
            "relation_count": len(self.list_relations()),
            "foreshadow_count": len(self.list_foreshadows()),
            "issues_found": len(issues),
        }
        return {"contradictions": issues, "stats": stats}

    # ── Graph insights ──

    def get_graph_insights(self) -> dict:
        return self._cached("insights", self._compute_graph_insights)

    def _compute_graph_insights(self) -> dict:
        insights = {"forgotten_characters": [], "unresolved_foreshadows": [],
                    "disconnected_pairs": [], "bridge_characters": [],
                    "underutilized_locations": [], "suggestions": []}

        timeline_events = self.list_timeline_events()
        if timeline_events:
            max_order = max(e.time_order for e in timeline_events)
            forgotten = self.find_forgotten_characters(max_order, threshold=5)
            important = [c for c in forgotten if c.get("important")]
            insights["forgotten_character_count"] = len(important)
            insights["forgotten_characters"] = important[:5]
            if important:
                names = ", ".join(c["name"] for c in important[:3])
                insights["suggestions"].append(
                    {"type": "warning", "priority": "high",
                     "message": f"重要角色已多章未出场：{names}。考虑在下一章让他们露面或提及。"})

        all_fores = self.list_foreshadows()
        open_fores = [f for f in all_fores if not f.resolved]
        insights["unresolved_foreshadow_count"] = len(open_fores)
        if open_fores:
            insights["unresolved_foreshadows"] = [
                {"id": f.id, "text": f.text[:50], "related_entities": f.related_entities}
                for f in open_fores[:10]]
            if len(open_fores) > 3:
                insights["suggestions"].append(
                    {"type": "reminder", "priority": "medium",
                     "message": f"有 {len(open_fores)} 个伏笔尚未回收，注意适时推进。"})

        chars = self.list_entities(entity_type="character")
        if 2 < len(chars) <= 30:
            missing = self.find_missing_relations([c.id for c in chars])
            insights["disconnected_pair_count"] = len(missing)
            insights["disconnected_pairs"] = missing[:5]
            if missing:
                insights["suggestions"].append(
                    {"type": "info", "priority": "low",
                     "message": f"发现 {len(missing)} 对角色之间无关系路径。"})

        bridges = self.find_bridge_characters()
        insights["bridge_character_count"] = len(bridges)
        insights["bridge_characters"] = bridges[:5]
        if bridges:
            names = ", ".join(b["entity_name"] for b in bridges[:3])
            insights["suggestions"].append(
                {"type": "info", "priority": "medium",
                 "message": f"关键枢纽角色：{names}。这些角色连接多个关系链，修改时需谨慎。"})

        # Confidence scores
        from ..narrative_logic import ConfidenceScorer
        scorer = ConfidenceScorer(self)
        all_scores = scorer.score_all()
        insights["confidence_scores"] = [
            {"entity_id": s.entity_id, "entity_name": s.entity_name,
             "entity_type": s.entity_type, "confidence": s.confidence,
             "stars": s.stars, "recommendation": s.recommendation}
            for s in all_scores[:20]]
        weak = [s for s in all_scores if s.confidence < 0.3]
        if weak:
            insights["suggestions"].append(
                {"type": "warning", "priority": "medium",
                 "message": f"设定薄弱实体：{', '.join(s.entity_name for s in weak[:3])}。"})

        # Constraint violations
        from ..narrative_logic import ConstraintChecker, ConstraintStore
        constraints = ConstraintStore(self).list(active_only=True)
        if constraints:
            violations = ConstraintChecker(self).check_all()
            insights["constraint_violations"] = [
                {"constraint_id": v.constraint_id, "description": v.description,
                 "severity": v.severity, "violations": v.violations[:5]}
                for v in violations]
            if violations:
                hard_count = sum(1 for v in violations if v.severity == "hard")
                insights["suggestions"].append(
                    {"type": "warning", "priority": "high",
                     "message": f"{len(violations)} 条约束被违反（{hard_count}条硬约束）。"})
        return insights

    # ── Narrative diagnosis ──

    def get_narrative_diagnosis(self) -> dict:
        return self._cached("diagnosis", self._compute_narrative_diagnosis)

    def _compute_narrative_diagnosis(self) -> dict:
        raw = self.get_graph_insights()
        forgotten = raw.get("forgotten_characters", [])
        forgotten_count = raw.get("forgotten_character_count", len(forgotten))
        unresolved_fs_count = raw.get("unresolved_foreshadow_count", 0)
        disconnected_count = raw.get("disconnected_pair_count", 0)
        unused_loc_count = raw.get("unused_location_count", 0)
        constraints = raw.get("constraint_violations", [])
        confidence = raw.get("confidence_scores", [])

        total_chars = len(self.list_entities(entity_type="character"))
        total_locs = len(self.list_entities(entity_type="location"))
        total_fores = len(self.list_foreshadows())

        # Dimension 1: Character continuity
        if forgotten_count > 0:
            important = sum(1 for c in forgotten if c.get("important"))
            weighted = important * 2 + (forgotten_count - important)
            rate = weighted / max(total_chars, 1) / 2
            char_score = round(100 * (1 - rate ** 0.4))
        else:
            char_score = 100
        char_finding = (f"{forgotten_count} 个重要角色多章未出场" if forgotten_count > 0
                        else "所有角色出场连贯")

        # Dimension 2: Foreshadow management
        if unresolved_fs_count > 0:
            rate = unresolved_fs_count / max(total_fores, 1)
            fore_score = round(100 * (1 / (1 + _math.log(1 + rate * 8))))
        else:
            fore_score = 100
        fore_finding = (f"{unresolved_fs_count} 个伏笔待回收" if unresolved_fs_count > 0
                        else "所有伏笔已回收")

        # Dimension 3: Relationship network
        if total_chars > 2:
            max_pairs = total_chars * (total_chars - 1) / 2
            disc_rate = min(disconnected_count / max(max_pairs, 1), 1.0)
            rel_score = round(100 * (1 - disc_rate * 0.7))
        else:
            rel_score = 100
        rel_finding = (f"{disconnected_count} 对角色之间无关联路径" if disconnected_count > 0
                       else "角色关系网络连接良好")

        # Dimension 4: Location utilization
        if unused_loc_count > 0 and total_locs > 0:
            loc_score = round(100 * (1 - (unused_loc_count / total_locs) ** 0.6))
        else:
            loc_score = 100
        loc_finding = (f"{unused_loc_count} 个地点从未使用" if unused_loc_count > 0
                       else "所有地点使用率合理")

        # Dimension 5: Confidence
        if confidence:
            avg_conf = sum(c["confidence"] for c in confidence) / len(confidence)
            low_conf = len([c for c in confidence if c["confidence"] < 0.3])
            conf_score = round(max(0, min(100, avg_conf * 100 - (low_conf / max(len(confidence), 1)) ** 0.5 * 30)))
        else:
            conf_score = 100
        conf_finding = f"{len([c for c in confidence if c['confidence'] < 0.3])} 个实体设定可信度偏低" if confidence else "暂无设定可信度数据"

        # Dimension 6: Constraint compliance
        hard = [c for c in constraints if c.get("severity") == "hard"]
        const_score = round(max(0, 100 * (1 - (len(hard) * 35 + (len(constraints) - len(hard)) * 12) / 100))) if constraints else 100
        const_finding = f"{len(constraints)} 条约束违反（{len(hard)}条硬约束）" if constraints else "所有约束已满足"

        dims = [
            {"name": "角色连贯性", "score": char_score, "finding": char_finding, "weight": 0.20},
            {"name": "伏笔管理", "score": fore_score, "finding": fore_finding, "weight": 0.15},
            {"name": "关系网络", "score": rel_score, "finding": rel_finding, "weight": 0.15},
            {"name": "地点利用", "score": loc_score, "finding": loc_finding, "weight": 0.10},
            {"name": "设定可信度", "score": conf_score, "finding": conf_finding, "weight": 0.15},
            {"name": "约束合规", "score": const_score, "finding": const_finding, "weight": 0.25},
        ]
        overall = round(sum(d["score"] * d["weight"] for d in dims))

        # ── Summary ──
        if overall >= 90:
            summary = "叙事结构健康，各维度表现均衡。"
        elif overall >= 70:
            weak = [d for d in dims if d["score"] < 70]
            summary = f"整体良好，但 {len(weak)} 个维度需要关注：{'、'.join(d['name'] for d in weak[:2])}。"
        elif overall >= 50:
            summary = f"需关注 {len([d for d in dims if d['score'] < 60])} 个维度。"
        else:
            summary = "叙事结构存在较多问题，建议系统性地修复。"

        # ── Action items ──
        action_items = []
        hard_violations = [c for c in constraints if c.get("severity") == "hard"]
        for v in constraints[:5]:
            action_items.append({
                "priority": "high" if v.get("severity") == "hard" else "medium",
                "action": f"修复约束违反: {v.get('description', '')[:100]}",
                "category": "约束合规",
            })
        if forgotten:
            action_items.append({
                "priority": "high" if len(forgotten) > 3 else "medium",
                "action": f"安排 {forgotten[0]['name']} 出场",
                "category": "角色连贯性",
            })
        bridges = raw.get("bridge_characters", [])
        if bridges and disconnected_count > 0:
            action_items.append({
                "priority": "medium",
                "action": f"通过枢纽角色 {bridges[0]['entity_name']} 连接断裂关系",
                "category": "关系网络",
            })
        if confidence:
            low_conf = [c for c in confidence if c["confidence"] < 0.3]
            if low_conf:
                action_items.append({
                    "priority": "low",
                    "action": f"丰富 {low_conf[0]['entity_name']} 的设定细节",
                    "category": "设定可信度",
                })

        # Transform flat suggestions into structured causal chains
        causal_chains = []
        for s in raw.get("suggestions", []):
            chain = {
                "cause": s.get("message", ""),
                "effect": "",
                "link": "",
                "suggestion": "",
                "severity": s.get("priority", "medium"),
            }
            # Derive suggestion from message type
            if s.get("type") == "warning":
                chain["suggestion"] = "建议优先处理上述问题"
            elif s.get("type") == "reminder":
                chain["suggestion"] = "请在后续章节中适时推进"
            elif s.get("type") == "info":
                chain["suggestion"] = "可作为改进参考"
            causal_chains.append(chain)

        return {
            "health_score": overall,
            "summary": summary,
            "dimensions": dims,
            "causal_chains": causal_chains,
            "action_items": action_items,
            "raw_data": {
                "forgotten_count": forgotten_count,
                "foreshadow_count": unresolved_fs_count,
                "disconnected_count": disconnected_count,
                "bridge_count": len(bridges),
                "unused_location_count": unused_loc_count,
                "constraint_count": len(constraints),
                "hard_constraint_count": len(hard_violations),
            },
        }
