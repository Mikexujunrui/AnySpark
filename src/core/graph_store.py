"""Neo4j Graph Store — replaces SQLite KnowledgeStore with graph-native operations."""

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase

from .graph_schema import CONSTRAINTS, INDEXES, entity_label
from .knowledge import CharacterSnapshot, Entity, EntityType, Foreshadow, Relation, RelationType, TimelineEvent

logger = logging.getLogger(__name__)


env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

# ── Shared Neo4j driver singleton (avoid creating a new driver per GraphStore) ──
_shared_driver: Driver | None = None
_last_connect_attempt: float = 0.0  # timestamp of last connection attempt
RECONNECT_INTERVAL: float = 60.0    # seconds between reconnection retries


def _get_driver() -> Driver | None:
    global _shared_driver, _last_connect_attempt
    if _shared_driver is None:
        # Reconnection guard: don't hammer Neo4j if it's down
        import time
        now = time.time()
        if _last_connect_attempt > 0 and (now - _last_connect_attempt) < RECONNECT_INTERVAL:
            return None
        _last_connect_attempt = now

        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "novel_agent_2024!")
        try:
            _shared_driver = GraphDatabase.driver(uri, auth=(user, password))
            _shared_driver.verify_connectivity()
            logger.info("Neo4j connected successfully")
        except Exception as e:
            logger.warning(f"Neo4j unavailable, graph features degraded: {e}")
            _shared_driver = None
    return _shared_driver


def close_shared_driver():
    """Close the shared driver on application shutdown."""
    global _shared_driver
    if _shared_driver is not None:
        try:
            _shared_driver.close()
        except (OSError, RuntimeError):
            pass
        _shared_driver = None


class GraphStore:
    def __init__(self, project_id: str = "default"):
        self.project_id = project_id
        self._driver: Driver | None = _get_driver()

    def _run(self, query: str, params: dict = None):
        if self._driver is None:
            logger.debug("Neo4j unavailable, returning empty result")
            return []
        try:
            with self._driver.session() as session:
                return list(session.run(query, params or {}))
        except Exception as e:
            logger.warning("Neo4j query failed: %s", e)
            return []

    def _run_single(self, query: str, params: dict = None):
        r = self._run(query, params)
        return r[0] if r else None

    def init_schema(self):
        try:
            self._run("MERGE (p:Project {id: $pid}) SET p.name = 'default'", {"pid": self.project_id})
        except Exception:
            pass
        for c in CONSTRAINTS + INDEXES:
            try:
                self._run(c)
            except Exception as e:
                logger.debug("Schema constraint/index failed: %s", e)

    def close(self):
        # No-op: shared driver is managed globally via close_shared_driver()
        pass


    # ── Batch Operations ──

    def batch_write(self, operations: list[dict]):
        if self._driver is None:
            logger.warning("batch_write skipped: Neo4j unavailable")
            return
        with self._driver.session() as session:
            with session.begin_transaction() as tx:
                for op in operations:
                    try:
                        if op["type"] == "add_entity":
                            self._tx_add_entity(tx, op["entity"])
                        elif op["type"] == "update_entity":
                            self._tx_update_entity(tx, op["id"], op["data"])
                        elif op["type"] == "add_relation":
                            self._tx_add_relation(tx, op["relation"])
                        elif op["type"] == "add_foreshadow":
                            self._tx_add_foreshadow(tx, op["foreshadow"])
                    except Exception as e:
                        logger.warning(f"batch_write operation failed ({op.get('type', '?')}): {e}")
                tx.commit()

    def batch_add_entities(self, entities: list[Entity]):
        if not entities:
            return
        params = []
        for e in entities:
            params.append({
                "id": e.id, "type": e.type, "name": e.name,
                "aliases": e.aliases,
                "data": json.dumps(e.data, ensure_ascii=False),
            })
        with self._driver.session() as session:
            session.run("""
                UNWIND $batch AS item
                MERGE (e:Entity {id: item.id, project_id: $pid})
                SET e.entity_type = item.type, e.name = item.name,
                    e.aliases = item.aliases, e.data = item.data,
                    e.updated_at = $now, e.created_at = coalesce(e.created_at, $now)
                WITH e
                MERGE (p:Project {id: $pid})
                MERGE (e)-[:BELONGS_TO_PROJECT]->(p)
            """, {"batch": params, "pid": self.project_id, "now": datetime.now().isoformat()})

    def batch_add_relations(self, relations: list["Relation"]):
        if not relations:
            return
        from collections import defaultdict
        by_type = defaultdict(list)
        for rel in relations:
            by_type[rel.type.upper()].append(rel)
        with self._driver.session() as session:
            now = datetime.now().isoformat()
            pid = self.project_id
            for rel_type, rels in by_type.items():
                params = []
                for rel in rels:
                    params.append({
                        "from_id": rel.from_entity, "to_id": rel.to_entity,
                        "rid": rel.id,
                        "data": json.dumps(rel.data, ensure_ascii=False),
                    })
                try:
                    session.run("""
                        UNWIND $batch AS item
                        MATCH (a:Entity {id: item.from_id, project_id: $pid})
                        MATCH (b:Entity {id: item.to_id, project_id: $pid})
                        MERGE (a)-[r:""" + rel_type + """]->(b)
                        SET r.id = item.rid, r.data = item.data,
                            r.project_id = $pid, r.updated_at = $now,
                            r.created_at = coalesce(r.created_at, $now)
                    """, {"batch": params, "pid": pid, "now": now})
                except Exception as e:
                    logger.warning("batch_add_relations failed for type %s: %s", rel_type, e)

    def batch_add_foreshadows(self, foreshadows: list["Foreshadow"]):
        if not foreshadows:
            return
        params = []
        for fs in foreshadows:
            params.append({
                "id": fs.id, "text": fs.text, "hint": fs.hint,
                "er": fs.expected_resolution, "r": fs.resolved, "rt": fs.resolution_text,
                "data": json.dumps({"text": fs.text, "hint": fs.hint,
                                    "expected_resolution": fs.expected_resolution,
                                    "resolved": fs.resolved, "resolution_text": fs.resolution_text,
                                    "related_entities": fs.related_entities,
                                    "related_events": fs.related_events}, ensure_ascii=False),
            })
        with self._driver.session() as session:
            session.run("""
                UNWIND $batch AS item
                CREATE (s:Snapshot:Fore {
                    id: item.id, character_id: '', time_point: '',
                    time_order: 0, label: 'foreshadow', data: item.data,
                    description: '', project_id: $pid,
                    text: item.text, hint: item.hint,
                    expected_resolution: item.er, resolved: item.r,
                    resolution_text: item.rt
                })
            """, {"batch": params, "pid": self.project_id})

    def _tx_add_entity(self, tx, entity: Entity):
        label = entity_label(entity.type)
        tx.run(f"""
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

    def _tx_update_entity(self, tx, entity_id: str, data: dict):
        tx.run("""
            MATCH (e:Entity {id: $id, project_id: $pid})
            SET e.data = $data, e.updated_at = $now
        """, {"id": entity_id, "pid": self.project_id,
              "data": json.dumps(data, ensure_ascii=False),
              "now": datetime.now().isoformat()})

    def _tx_add_relation(self, tx, relation: "Relation"):
        rel_type = relation.type.upper()
        tx.run(f"""
            MATCH (a:Entity {{id: $from_id, project_id: $pid}})
            MATCH (b:Entity {{id: $to_id, project_id: $pid}})
            MERGE (a)-[r:{rel_type}]->(b)
            SET r.id = $rid, r.data = $data, r.project_id = $pid
        """, {
            "from_id": relation.from_entity, "to_id": relation.to_entity,
            "rid": relation.id, "pid": self.project_id,
            "data": json.dumps(relation.data, ensure_ascii=False),
        })

    def _tx_add_foreshadow(self, tx, fs: "Foreshadow"):
        tx.run("""
            CREATE (s:Snapshot:Fore {
                id: $id, character_id: '', time_point: '',
                time_order: 0, label: 'foreshadow',
                data: $data, description: '', project_id: $pid,
                text: $text, hint: $hint, expected_resolution: $er,
                resolved: $r, resolution_text: $rt
            })
        """, {
            "id": fs.id, "text": fs.text, "hint": fs.hint,
            "er": fs.expected_resolution, "r": fs.resolved, "rt": fs.resolution_text,
            "data": json.dumps({"text": fs.text, "hint": fs.hint}, ensure_ascii=False),
            "pid": self.project_id,
        })

    # ── Entity CRUD ──

    def add_entity(self, entity: Entity) -> Entity:
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
        # Alias lookup: limit 1 to stay deterministic even if aliases are dirty
        # (multiple entities sharing one alias shouldn't crash callers).
        r2 = self._run_single("""
            MATCH (e:Entity {project_id: $pid}) WHERE $name IN e.aliases
            RETURN e LIMIT 1
        """, {"name": name, "pid": self.project_id})
        if r2:
            return self._row_to_entity(r2["e"])
        # Last-resort: case-insensitive name match (LLMs frequently drift on casing)
        r3 = self._run_single("""
            MATCH (e:Entity {project_id: $pid}) WHERE toLower(e.name) = toLower($name)
            RETURN e LIMIT 1
        """, {"name": name, "pid": self.project_id})
        if r3:
            return self._row_to_entity(r3["e"])
        return None

    def list_entities(self, entity_type: str | None = None) -> list[Entity]:
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
        """Update an entity's data, and optionally its name and/or aliases.

        - ``data`` is always replaced with the provided dict (merge is the
          caller's responsibility).
        - ``name``/``aliases`` are only touched when explicitly non-None.
        """
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
        return result[0]["cnt"] > 0 if result else False

    def delete_entity(self, entity_id: str) -> bool:
        self._run("MATCH (e:Entity {id: $id, project_id: $pid}) DETACH DELETE e",
                  {"id": entity_id, "pid": self.project_id})
        return True

    # ── Relation CRUD ──

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
            rels.append(Relation(
                id=r.get("id", str(uuid.uuid4())[:8]),
                from_entity=a["id"],
                to_entity=b["id"],
                type=RelationType(r.type.lower()),
                data=json.loads(r.get("data", "{}")) if r.get("data") else {},
            ))
        return rels

    def get_neighbors(self, entity_id: str, depth: int = 1) -> list[dict]:
        depth = max(1, min(int(depth), 10))  # clamp to [1, 10] to prevent Cypher injection
        rows = self._run(f"""
            MATCH (a:Entity {{id: $eid, project_id: $pid}})-[r*1..{depth}]-(b:Entity {{project_id: $pid}})
            RETURN DISTINCT b, [rel in r | type(rel)] as path_types
        """, {"eid": entity_id, "pid": self.project_id})
        return [{"entity": self._row_to_entity(r["b"]), "path": list(r["path_types"])} for r in rows]

    def get_path(self, from_id: str, to_id: str, max_depth: int = 3) -> list[dict]:
        max_depth = max(1, min(int(max_depth), 10))  # clamp to [1, 10]
        rows = self._run(f"""
            MATCH path = shortestPath(
                (a:Entity {{id: $from_id, project_id: $pid}})-[*1..{max_depth}]-(b:Entity {{id: $to_id, project_id: $pid}})
            )
            WHERE all(node IN nodes(path) WHERE NOT node:Project)
            RETURN nodes(path) as nodes, relationships(path) as rels, length(path) as hops
        """, {"from_id": from_id, "to_id": to_id, "pid": self.project_id})
        if not rows:
            return []
        result = []
        for row in rows:
            nodes = [{"id": n["id"], "name": n.get("name", ""), "type": n.get("entity_type", "")} for n in row["nodes"]]
            edges = [{"type": r.type, "from": r.start_node["id"], "to": r.end_node["id"]} for r in row["rels"]]
            result.append({"nodes": nodes, "edges": edges, "hops": row["hops"]})
        return result

    # ── Graph-specific queries ──

    def find_relationships(self, from_id: str, to_id: str, max_depth: int = 3) -> list[dict]:
        return self.get_path(from_id, to_id, max_depth)

    def get_entity_network(self, entity_id: str, depth: int = 2) -> dict:
        nodes_set = {}
        edges_set = {}

        rows = self._run(f"""
            MATCH (a:Entity {{id: $eid, project_id: $pid}})-[r*1..{depth}]-(b:Entity {{project_id: $pid}})
            WHERE NOT b:Project
            UNWIND r as rel
            RETURN DISTINCT startNode(rel) as sn, rel, endNode(rel) as en
        """, {"eid": entity_id, "pid": self.project_id})

        for row in rows:
            sn, r, en = row["sn"], row["rel"], row["en"]
            for n in [sn, en]:
                if n["id"] not in nodes_set:
                    nodes_set[n["id"]] = {"id": n["id"], "name": n.get("name", ""), "type": n.get("entity_type", ""),
                                          "data": json.loads(n.get("data", "{}")) if n.get("data") else {}}
            ekey = f"{sn['id']}|{en['id']}|{r.type}"
            if ekey not in edges_set:
                edges_set[ekey] = {"from": sn["id"], "to": en["id"], "type": r.type}

        return {"nodes": list(nodes_set.values()), "edges": list(edges_set.values())}

    def find_share_connections(self, entity_ids: list[str]) -> list[dict]:
        rows = self._run("""
            MATCH (a:Entity {project_id: $pid})-[r]-(b:Entity {project_id: $pid})
            WHERE a.id IN $ids AND b.id IN $ids
            RETURN a.id as from_id, b.id as to_id, type(r) as rel_type
        """, {"ids": entity_ids, "pid": self.project_id})
        return [{"from": r["from_id"], "to": r["to_id"], "type": r["rel_type"]} for r in rows]

    # ── Foreshadows ──

    def add_foreshadow(self, fs: Foreshadow) -> Foreshadow:
        self._run("""
            CREATE (s:Snapshot:Fore {
                id: $id, character_id: $cid, time_point: $tp,
                time_order: $to, label: $label, data: $data,
                description: $desc, project_id: $pid,
                text: $text, hint: $hint, expected_resolution: $er,
                resolved: $r, resolution_text: $rt
            })
        """, {
            "id": fs.id, "cid": "", "tp": "", "to": 0, "label": "foreshadow",
            "data": json.dumps({"text": fs.text, "hint": fs.hint, "expected_resolution": fs.expected_resolution,
                                "resolved": fs.resolved, "resolution_text": fs.resolution_text,
                                "related_entities": fs.related_entities, "related_events": fs.related_events},
                               ensure_ascii=False),
            "desc": "", "pid": self.project_id,
            "text": fs.text, "hint": fs.hint, "er": fs.expected_resolution,
            "r": fs.resolved, "rt": fs.resolution_text,
        })
        return fs

    def list_foreshadows(self, resolved: bool | None = None) -> list[Foreshadow]:
        if resolved is not None:
            rows = self._run(
                "MATCH (f:Fore {project_id: $pid}) WHERE f.resolved = $r RETURN f ORDER BY f.created_at",
                {"pid": self.project_id, "r": resolved}
            )
        else:
            rows = self._run(
                "MATCH (f:Fore {project_id: $pid}) RETURN f ORDER BY f.created_at",
                {"pid": self.project_id}
            )
        result = []
        for row in rows:
            n = row["f"]
            result.append(Foreshadow(
                id=n["id"], text=n.get("text", ""), hint=n.get("hint", ""),
                expected_resolution=n.get("expected_resolution", ""),
                resolved=n.get("resolved", False),
                resolution_text=n.get("resolution_text", ""),
                related_entities=json.loads(n.get("data", "{}")).get("related_entities", []) if n.get("data") else [],
                related_events=json.loads(n.get("data", "{}")).get("related_events", []) if n.get("data") else [],
            ))
        return result

    def resolve_foreshadow(self, fs_id: str, resolution_text: str) -> bool:
        self._run(
            "MATCH (f:Fore {id: $id, project_id: $pid}) SET f.resolved = true, f.resolution_text = $rt",
            {"id": fs_id, "pid": self.project_id, "rt": resolution_text}
        )
        return True

    # ── Snapshots ──

    def add_snapshot(self, snapshot: CharacterSnapshot) -> CharacterSnapshot:
        self._run("""
            CREATE (s:Snapshot {
                id: $sid, character_id: $cid, time_point: $tp,
                time_order: $to, label: $label,
                data: $data, description: $desc, project_id: $pid,
                phase: $phase, phase_key: $phase_key,
                is_current: $is_current
            })
        """, {
            "sid": snapshot.id, "cid": snapshot.character_entity_id,
            "tp": snapshot.time_point, "to": snapshot.time_order,
            "label": snapshot.label,
            "data": json.dumps(snapshot.data, ensure_ascii=False),
            "desc": snapshot.description, "pid": self.project_id,
            "phase": snapshot.phase or "",
            "phase_key": snapshot.phase_key or "",
            "is_current": bool(snapshot.is_current),
        })
        # Only one phase can be "current" per character at a time.
        if snapshot.is_current:
            self._run("""
                MATCH (s:Snapshot {character_id: $cid, project_id: $pid})
                WHERE s.id <> $sid AND s.is_current = true
                SET s.is_current = false
            """, {"cid": snapshot.character_entity_id,
                  "sid": snapshot.id, "pid": self.project_id})
        self._run("""
            MATCH (e:Entity {id: $cid, project_id: $pid})
            MATCH (s:Snapshot {id: $sid, project_id: $pid})
            MERGE (e)-[:HAS_SNAPSHOT]->(s)
        """, {"cid": snapshot.character_entity_id, "sid": snapshot.id, "pid": self.project_id})
        return snapshot

    def update_snapshot(self, snapshot_id: str, updates: dict) -> bool:
        """Partial update of a Snapshot node. Only provided keys are touched.

        ``data`` must be a full dict (will be JSON-serialized). Other keys
        (phase, phase_key, is_current, label, description, time_point,
        time_order) are primitive and set as-is.

        When ``is_current`` is flipped to true, all other snapshots of the
        same character are cleared of that flag.
        """
        if not updates:
            return False
        primitive_keys = [
            "phase", "phase_key",
            "label", "description", "time_point",
        ]
        set_clauses: list[str] = []
        params: dict = {"sid": snapshot_id, "pid": self.project_id}
        for k in primitive_keys:
            if k in updates:
                set_clauses.append(f"s.{k} = ${k}")
                params[k] = updates[k] if updates[k] is not None else ""
        if "time_order" in updates and updates["time_order"] is not None:
            set_clauses.append("s.time_order = $time_order")
            params["time_order"] = int(updates["time_order"])
        if "data" in updates and isinstance(updates["data"], dict):
            set_clauses.append("s.data = $data")
            params["data"] = json.dumps(updates["data"], ensure_ascii=False)
        if "is_current" in updates and updates["is_current"] is not None:
            set_clauses.append("s.is_current = $is_current")
            params["is_current"] = bool(updates["is_current"])
        if not set_clauses:
            return False
        self._run(f"MATCH (s:Snapshot {{id: $sid, project_id: $pid}}) SET {', '.join(set_clauses)}", params)
        if params.get("is_current"):
            # Find this snapshot's character_id, then clear is_current on siblings.
            rows = self._run(
                "MATCH (s:Snapshot {id: $sid, project_id: $pid}) RETURN s.character_id AS cid",
                {"sid": snapshot_id, "pid": self.project_id},
            )
            if rows and rows[0].get("cid"):
                self._run("""
                    MATCH (o:Snapshot {character_id: $cid, project_id: $pid})
                    WHERE o.id <> $sid AND o.is_current = true
                    SET o.is_current = false
                """, {"cid": rows[0]["cid"], "sid": snapshot_id, "pid": self.project_id})
        return True

    def list_snapshots(self, character_entity_id: str | None = None,
                       time_point: str | None = None) -> list[CharacterSnapshot]:
        if character_entity_id:
            rows = self._run(
                "MATCH (s:Snapshot {character_id: $cid, project_id: $pid}) RETURN s ORDER BY s.time_order",
                {"cid": character_entity_id, "pid": self.project_id}
            )
        elif time_point:
            rows = self._run(
                "MATCH (s:Snapshot {time_point: $tp, project_id: $pid}) RETURN s ORDER BY s.time_order",
                {"tp": time_point, "pid": self.project_id}
            )
        else:
            rows = self._run(
                "MATCH (s:Snapshot {project_id: $pid}) RETURN s ORDER BY s.time_order",
                {"pid": self.project_id}
            )
        return [self._row_to_snapshot(r["s"]) for r in rows]

    def _row_to_snapshot(self, n) -> CharacterSnapshot:
        phase = n.get("phase")
        # Lazy backfill: snapshots created with the legacy schema have no
        # phase field at all. Distinguish from an explicitly-empty phase so
        # the frontend can label them "未分阶段".
        if phase is None:
            phase = "未分阶段"
        return CharacterSnapshot(
            id=n["id"], character_entity_id=n.get("character_id", ""),
            time_point=n.get("time_point", ""),
            time_order=n.get("time_order", 0),
            label=n.get("label", ""),
            data=json.loads(n.get("data", "{}") or "{}"),
            description=n.get("description", ""),
            phase=phase,
            phase_key=n.get("phase_key", "") or "",
            is_current=bool(n.get("is_current", False)),
        )

    def get_current_phase(self, character_entity_id: str) -> CharacterSnapshot | None:
        """Return the current phase card for a character, or None.

        Phase selection is **order-based and decoupled from chapters**:
        1. If any snapshot has ``is_current=True``, return it (the latest one
           if multiple, defensively).
        2. Otherwise fall back to the snapshot with the highest ``time_order``
           (the most recent phase in the arc timeline).
        3. Returns None when the character has no phase snapshots at all.
        """
        snaps = self.list_snapshots(character_entity_id=character_entity_id)
        if not snaps:
            return None
        current = [s for s in snaps if s.is_current]
        if current:
            current.sort(key=lambda s: s.time_order, reverse=True)
            return current[0]
        snaps.sort(key=lambda s: s.time_order, reverse=True)
        return snaps[0]

    def delete_snapshot(self, snapshot_id: str) -> bool:
        self._run("MATCH (s:Snapshot {id: $id, project_id: $pid}) DETACH DELETE s",
                  {"id": snapshot_id, "pid": self.project_id})
        return True

    # ── Timeline ──

    def add_timeline_event(self, event: TimelineEvent) -> TimelineEvent:
        self._run("""
            CREATE (t:Timeline {
                id: $id, time_point: $tp, label: $label,
                time_order: $to, description: $desc,
                chapter_ref: $cr, event_entity_id: $eid,
                project_id: $pid
            })
        """, {
            "id": event.id, "tp": event.time_point, "label": event.label,
            "to": event.time_order, "desc": event.description,
            "cr": event.chapter_ref, "eid": event.event_entity_id,
            "pid": self.project_id,
        })
        return event

    def list_timeline_events(self) -> list[TimelineEvent]:
        rows = self._run(
            "MATCH (t:Timeline {project_id: $pid}) RETURN t ORDER BY t.time_order",
            {"pid": self.project_id}
        )
        return [TimelineEvent(
            id=r["t"]["id"], time_point=r["t"].get("time_point", ""),
            label=r["t"].get("label", ""),
            time_order=r["t"].get("time_order", 0),
            description=r["t"].get("description", ""),
            chapter_ref=r["t"].get("chapter_ref", ""),
            event_entity_id=r["t"].get("event_entity_id", ""),
        ) for r in rows]

    def delete_timeline_event(self, event_id: str) -> bool:
        self._run("MATCH (t:Timeline {id: $id, project_id: $pid}) DELETE t",
                  {"id": event_id, "pid": self.project_id})
        return True

    def get_all_time_points(self) -> list[dict]:
        rows = self._run(
            "MATCH (t:Timeline {project_id: $pid}) RETURN t.label as label, t.time_point as tp, t.time_order as to ORDER BY to",
            {"pid": self.project_id}
        )
        return [{"time_point": r["tp"], "label": r["label"]} for r in rows]

    # ── Consistency Check ──

    def check_consistency(self) -> dict:
        """Run deterministic Cypher queries to find factual contradictions.

        Returns:
            dict with:
              - contradictions: list of deterministic conflicts found
              - stats: entity/relation/foreshadow counts for LLM semantic check
        """
        issues = []

        # 1. Location conflict: same entity located_at two different places
        rows = self._run("""
            MATCH (e:Entity {project_id: $pid})-[r1:LOCATED_AT]->(loc1:Entity {project_id: $pid})
            MATCH (e)-[r2:LOCATED_AT]->(loc2:Entity {project_id: $pid})
            WHERE loc1.id <> loc2.id
            RETURN e.name as entity, loc1.name as loc_a, loc2.name as loc_b
        """, {"pid": self.project_id})
        for r in rows:
            issues.append({
                "type": "location_conflict",
                "severity": "high",
                "description": f"实体「{r['entity']}」同时位于「{r['loc_a']}」和「{r['loc_b']}」",
            })

        # 2. Temporal contradiction: A before B and A after B
        rows = self._run("""
            MATCH (a:Entity {project_id: $pid})-[r1:BEFORE]->(b:Entity {project_id: $pid})
            MATCH (b)-[r2:BEFORE]->(a)
            WHERE a.id <> b.id
            RETURN a.name as ea, b.name as eb
        """, {"pid": self.project_id})
        for r in rows:
            issues.append({
                "type": "temporal_conflict",
                "severity": "high",
                "description": f"时序矛盾: 「{r['ea']}」先于「{r['eb']}」又后于「{r['eb']}」",
            })

        # 3. Relationship contradiction: antagonist AND ally for same pair
        rows = self._run("""
            MATCH (a:Entity {project_id: $pid})-[r]-(b:Entity {project_id: $pid})
            WITH a, b, collect(type(r)) as types
            WHERE size(types) > 1 AND
                  (('ANTAGONIST' IN types AND 'ALLY' IN types) OR
                   ('ANTAGONIST' IN types AND 'FAMILY' IN types))
            RETURN a.name as ea, b.name as eb, types
        """, {"pid": self.project_id})
        for r in rows:
            types_str = ", ".join(r["types"])
            issues.append({
                "type": "relationship_conflict",
                "severity": "medium",
                "description": f"关系矛盾: 「{r['ea']}」↔「{r['eb']}」同时具有关系 {types_str}",
            })

        # 4. Owner without owned entity (orphan OWNS)
        rows = self._run("""
            MATCH (o:Entity {project_id: $pid})-[r:OWNS]->(i:Entity {project_id: $pid})
            WHERE i.entity_type = 'item' AND i.name = ''
            RETURN o.name as owner, i.id as orphan_id
        """, {"pid": self.project_id})
        for r in rows:
            issues.append({
                "type": "orphan_relation",
                "severity": "low",
                "description": f"「{r['owner']}」拥有一个未命名的物品({r['orphan_id'][:8]})",
            })

        stats = {
            "entity_count": len(self.list_entities()),
            "relation_count": len(self.list_relations()),
            "foreshadow_count": len(self.list_foreshadows()),
            "issues_found": len(issues),
        }

        return {"contradictions": issues, "stats": stats}

    # ── Summary ──

    def get_knowledge_summary(self) -> str:
        entities = self.list_entities()
        relations = self.list_relations()
        self.list_foreshadows()

        lines = ["## 知识库总览\n"]
        for etype in EntityType.BUILTIN:
            type_entities = [e for e in entities if e.type == etype]
            if type_entities:
                lines.append(f"### {etype}（{len(type_entities)}个）")
                for e in type_entities:
                    aliases = f" (别名: {', '.join(e.aliases)})" if e.aliases else ""
                    lines.append(f"- **{e.name}**{aliases}")
                    for k, v in list(e.data.items())[:5]:
                        lines.append(f"  - {k}: {v}")
                lines.append("")
        if relations:
            lines.append(f"### 关系（{len(relations)}条）")
            for r in relations:
                fe = next((e.name for e in entities if e.id == r.from_entity), r.from_entity)
                te = next((e.name for e in entities if e.id == r.to_entity), r.to_entity)
                lines.append(f"- {fe} --[{r.type}]--> {te}")
        return "\n".join(lines)

    @staticmethod
    def _row_to_entity(node) -> Entity:
        etype = EntityType(node.get("entity_type", "character"))
        aliases = node.get("aliases")
        if isinstance(aliases, str):
            aliases = json.loads(aliases)
        elif aliases is None:
            aliases = []
        data = node.get("data")
        if isinstance(data, str):
            data = json.loads(data)
        elif data is None:
            data = {}
        return Entity(
            id=node["id"],
            type=etype,
            name=node.get("name", ""),
            aliases=aliases,
            data=data,
        )


def get_store(book_id: str) -> GraphStore:
    store = GraphStore(book_id)
    store.init_schema()
    return store
