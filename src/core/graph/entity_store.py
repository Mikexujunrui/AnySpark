"""Entity CRUD mixin — extracted from ``graph_store.py``."""

from __future__ import annotations

import json
from datetime import datetime

from ..knowledge import Entity


class EntityMixin:
    """Mixin providing entity CRUD operations.

    Depends on ``self._run()``, ``self._run_single()``, ``self.project_id``,
    ``self._invalidate_cache()`` and ``self._row_to_entity()`` from the host
    ``GraphStore`` class.
    """

    def add_entity(self, entity: Entity) -> Entity:
        from ..graph_schema import entity_label
        label = entity_label(entity.type)
        self._run(f"""
            MERGE (e:Entity:{label} {{id: $id}})
            SET e.entity_type = $type, e.name = $name, e.aliases = $aliases,
                e.data = $data, e.project_id = $pid, e.updated_at = $now,
                e.created_at = coalesce(e.created_at, $now)
            MERGE (p:Project {{id: $pid}})
            MERGE (e)-[:BELONGS_TO_PROJECT]->(p)
        """, {
            "id": entity.id, "type": entity.type, "name": entity.name,
            "aliases": entity.aliases,
            "data": json.dumps(entity.data, ensure_ascii=False),
            "pid": self.project_id, "now": datetime.now().isoformat(),
        })
        self._invalidate_cache(self.project_id)
        return entity

    def get_entity(self, entity_id: str) -> Entity | None:
        r = self._run_single(
            "MATCH (e:Entity {id: $id, project_id: $pid}) RETURN e",
            {"id": entity_id, "pid": self.project_id}
        )
        if not r:
            return None
        return self._row_to_entity(r["e"])

    def get_entity_by_name(self, name: str) -> Entity | None:
        r = self._run_single("""
            MATCH (e:Entity {project_id: $pid}) WHERE e.name = $name
            RETURN e LIMIT 1
        """, {"name": name, "pid": self.project_id})
        if r:
            return self._row_to_entity(r["e"])
        r2 = self._run_single("""
            MATCH (e:Entity {project_id: $pid}) WHERE $name IN e.aliases
            RETURN e LIMIT 1
        """, {"name": name, "pid": self.project_id})
        if r2:
            return self._row_to_entity(r2["e"])
        r3 = self._run_single("""
            MATCH (e:Entity {project_id: $pid}) WHERE toLower(e.name) = toLower($name)
            RETURN e LIMIT 1
        """, {"name": name, "pid": self.project_id})
        if r3:
            return self._row_to_entity(r3["e"])
        return None

    def list_entities(self, entity_type: str | None = None) -> list[Entity]:
        from ..graph_schema import entity_label
        if entity_type:
            label = entity_label(entity_type)
            rows = self._run(
                f"MATCH (e:{label} {{project_id: $pid}}) RETURN e ORDER BY e.name",
                {"pid": self.project_id}
            )
        else:
            rows = self._run(
                "MATCH (e:Entity {project_id: $pid}) RETURN e ORDER BY e.entity_type, e.name",
                {"pid": self.project_id}
            )
        return [self._row_to_entity(r["e"]) for r in rows]

    def update_entity(self, entity_id: str, data: dict,
                      name: str | None = None,
                      aliases: list[str] | None = None) -> bool:
        set_clauses = ["e.data = $data", "e.updated_at = $now"]
        params = {
            "id": entity_id, "pid": self.project_id,
            "data": json.dumps(data, ensure_ascii=False),
            "now": datetime.now().isoformat(),
        }
        if name is not None:
            set_clauses.append("e.name = $name")
            params["name"] = name
        if aliases is not None:
            set_clauses.append("e.aliases = $aliases")
            params["aliases"] = aliases
        result = self._run(f"""
            MATCH (e:Entity {{id: $id, project_id: $pid}})
            SET {", ".join(set_clauses)}
            RETURN count(e) as cnt
        """, params)
        self._invalidate_cache(self.project_id)
        return result[0]["cnt"] > 0 if result else False

    def delete_entity(self, entity_id: str) -> bool:
        self._run("MATCH (e:Entity {id: $id, project_id: $pid}) DETACH DELETE e",
                  {"id": entity_id, "pid": self.project_id})
        self._invalidate_cache(self.project_id)
        return True
