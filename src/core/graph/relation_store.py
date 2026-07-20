"""Relation CRUD mixin — extracted from ``graph_store.py``."""

from __future__ import annotations

import json
import uuid

from ..knowledge import Relation, RelationType


class RelationMixin:
    """Mixin providing relation CRUD operations.

    Depends on ``self._run()``, ``self._run_single()``, ``self.project_id``,
    ``self._invalidate_cache()``, ``self._row_to_entity()`` and ``self.get_entity()``
    from the host ``GraphStore`` class.
    """

    def add_relation(self, relation: Relation) -> Relation:
        rel_type = relation.type.upper()
        self._run(f"""
            MATCH (a:Entity {{id: $from_id, project_id: $pid}})
            MATCH (b:Entity {{id: $to_id, project_id: $pid}})
            MERGE (a)-[r:{rel_type}]->(b)
            SET r.id = $rid, r.data = $data, r.project_id = $pid
        """, {
            "from_id": relation.from_entity, "to_id": relation.to_entity,
            "rid": relation.id, "pid": self.project_id,
            "data": json.dumps(relation.data, ensure_ascii=False),
        })
        self._invalidate_cache(self.project_id)
        return relation

    def list_relations(self, entity_id: str | None = None) -> list[Relation]:
        if entity_id:
            rows = self._run("""
                MATCH (a:Entity {id: $eid, project_id: $pid})-[r]-(b:Entity {project_id: $pid})
                RETURN a, r, b
            """, {"eid": entity_id, "pid": self.project_id})
        else:
            rows = self._run("""
                MATCH (a:Entity {project_id: $pid})-[r]-(b:Entity {project_id: $pid})
                RETURN a, r, b
            """, {"pid": self.project_id})

        rels = []
        for row in rows:
            a, r, b = row["a"], row["r"], row["b"]
            raw_type = r.type.lower()
            try:
                rel_type = RelationType(raw_type)
            except ValueError:
                rel_type = raw_type  # type: ignore[assignment]
            rels.append(Relation(
                id=r.get("id", str(uuid.uuid4())[:8]),
                from_entity=a["id"],
                to_entity=b["id"],
                type=rel_type,
                data=json.loads(r.get("data", "{}")) if r.get("data") else {},
            ))
        return rels

    def find_share_connections(self, entity_ids: list[str]) -> list[dict]:
        """Find direct relationships among a list of entity IDs."""
        if len(entity_ids) < 2:
            return []
        rows = self._run("""
            MATCH (a:Entity {project_id: $pid})-[r]-(b:Entity {project_id: $pid})
            WHERE a.id IN $ids AND b.id IN $ids AND a.id <> b.id
            RETURN a.id as from, type(r) as type, b.id as to
        """, {"ids": entity_ids, "pid": self.project_id})
        return [{"from": r["from"], "type": r["type"].lower(), "to": r["to"]} for r in rows]
