"""Neo4j Graph Store — replaces SQLite KnowledgeStore with graph-native operations."""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase

from .graph.analysis_store import AnalysisMixin
from .graph.entity_store import EntityMixin
from .graph.relation_store import RelationMixin
from .graph_schema import CONSTRAINTS, INDEXES, entity_label
from .knowledge import CharacterSnapshot, Entity, EntityType, Foreshadow, Relation, TimelineEvent

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


class GraphStore(EntityMixin, RelationMixin, AnalysisMixin):
    # ── Class-level cache for expensive computed insights ──
    _insights_cache: dict = {}       # {book_id: (version, data)}
    _cache_version: dict = {}        # {book_id: version}

    def __init__(self, project_id: str = "default"):
        self.project_id = project_id
        self._driver: Driver | None = _get_driver()

    @classmethod
    def _invalidate_cache(cls, project_id: str) -> None:
        """Clear all cached computed data for a project after writes."""
        cls._insights_cache.pop(project_id, None)
        cls._cache_version[project_id] = cls._cache_version.get(project_id, 0) + 1

    def _cached(self, cache_key: str, compute_fn) -> dict:
        """Return cached result if version matches, otherwise recompute."""
        pid = self.project_id
        version = self._cache_version.get(pid, 0)
        entry = self._insights_cache.get(pid, {})
        if cache_key in entry and entry[cache_key][0] == version:
            return entry[cache_key][1]
        result = compute_fn()
        if pid not in self._insights_cache:
            self._insights_cache[pid] = {}
        self._insights_cache[pid][cache_key] = (version, result)
        return result

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
        if self._driver is None:
            logger.warning("batch_add_entities skipped: Neo4j unavailable")
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
        if self._driver is None:
            logger.warning("batch_add_relations skipped: Neo4j unavailable")
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
        if self._driver is None:
            logger.warning("batch_add_foreshadows skipped: Neo4j unavailable")
            return
        params = []
        for fs in foreshadows:
            params.append({
                "id": fs.id, "text": fs.text, "hint": fs.hint,
                "er": fs.expected_resolution, "r": fs.resolved, "rt": fs.resolution_text,
                "source": fs.source, "status": fs.status,
                "pc": fs.plant_chapter, "rc": fs.resolve_chapter,
                "vr": fs.volume_ref, "pra": fs.planned_resolve_arc,
                "sc": fs.scheduled_chapter,
                "conf": fs.confidence,
                "rk": json.dumps(fs.resolve_keywords, ensure_ascii=False) if fs.resolve_keywords else "[]",
                "data": json.dumps({"text": fs.text, "hint": fs.hint,
                                    "expected_resolution": fs.expected_resolution,
                                    "resolved": fs.resolved, "resolution_text": fs.resolution_text,
                                    "related_entities": fs.related_entities,
                                    "related_events": fs.related_events,
                                    "source": fs.source, "status": fs.status,
                                    "plant_chapter": fs.plant_chapter,
                                    "resolve_chapter": fs.resolve_chapter,
                                    "volume_ref": fs.volume_ref,
                                    "planned_resolve_arc": fs.planned_resolve_arc,
                                    "scheduled_chapter": fs.scheduled_chapter,
                                    "confidence": fs.confidence,
                                    "resolve_keywords": fs.resolve_keywords}, ensure_ascii=False),
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
                    resolution_text: item.rt,
                    source: item.source, status: item.status,
                    plant_chapter: item.pc, resolve_chapter: item.rc,
                    volume_ref: item.vr, planned_resolve_arc: item.pra,
                    scheduled_chapter: item.sc,
                    confidence: item.conf, resolve_keywords: item.rk
                })
            """, {"batch": params, "pid": self.project_id})
            # P0-1: Create INVOLVES edges for batch foreshadows
            for fs in foreshadows:
                for eid in fs.related_entities:
                    if eid:
                        session.run("""
                            MATCH (f:Fore {id: $fid, project_id: $pid})
                            MATCH (e:Entity {id: $eid, project_id: $pid})
                            MERGE (f)-[:INVOLVES]->(e)
                        """, {"fid": fs.id, "eid": eid, "pid": self.project_id})

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
                resolved: $r, resolution_text: $rt,
                source: $source, status: $status,
                plant_chapter: $pc, resolve_chapter: $rc,
                volume_ref: $vr, planned_resolve_arc: $pra,
                scheduled_chapter: $sc,
                confidence: $conf, resolve_keywords: $rk
            })
        """, {
            "id": fs.id, "text": fs.text, "hint": fs.hint,
            "er": fs.expected_resolution, "r": fs.resolved, "rt": fs.resolution_text,
            "source": fs.source, "status": fs.status,
            "pc": fs.plant_chapter, "rc": fs.resolve_chapter,
            "vr": fs.volume_ref, "pra": fs.planned_resolve_arc,
            "sc": fs.scheduled_chapter,
            "conf": fs.confidence,
            "rk": json.dumps(fs.resolve_keywords, ensure_ascii=False) if fs.resolve_keywords else "[]",
            "data": json.dumps({"text": fs.text, "hint": fs.hint,
                               "source": fs.source, "status": fs.status,
                               "plant_chapter": fs.plant_chapter,
                               "scheduled_chapter": fs.scheduled_chapter,
                               "confidence": fs.confidence,
                               "resolve_keywords": fs.resolve_keywords}, ensure_ascii=False),
            "pid": self.project_id,
        })
        # P0-1: Create INVOLVES edges within transaction
        for eid in fs.related_entities:
            if eid:
                tx.run("""
                    MATCH (f:Fore {id: $fid, project_id: $pid})
                    MATCH (e:Entity {id: $eid, project_id: $pid})
                    MERGE (f)-[:INVOLVES]->(e)
                """, {"fid": fs.id, "eid": eid, "pid": self.project_id})

    # ── Entity & Relation CRUD (inherited from EntityMixin / RelationMixin) ──
    # add_entity, get_entity, get_entity_by_name, list_entities,
    # update_entity, delete_entity, add_relation, list_relations,
    # find_share_connections are now defined in graph/entity_store.py and
    # graph/relation_store.py

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

    # ── Foreshadows ──

    def add_foreshadow(self, fs: Foreshadow) -> Foreshadow:
        self._run("""
            CREATE (s:Snapshot:Fore {
                id: $id, character_id: $cid, time_point: $tp,
                time_order: $to, label: $label, data: $data,
                description: $desc, project_id: $pid,
                text: $text, hint: $hint, expected_resolution: $er,
                resolved: $r, resolution_text: $rt,
                source: $source, status: $status,
                plant_chapter: $pc, resolve_chapter: $rc,
                volume_ref: $vr, planned_resolve_arc: $pra,
                confidence: $conf, resolve_keywords: $rk
            })
        """, {
            "id": fs.id, "cid": "", "tp": "", "to": 0, "label": "foreshadow",
            "data": json.dumps({"text": fs.text, "hint": fs.hint, "expected_resolution": fs.expected_resolution,
                                "resolved": fs.resolved, "resolution_text": fs.resolution_text,
                                "related_entities": fs.related_entities, "related_events": fs.related_events,
                                "source": fs.source, "status": fs.status,
                                "plant_chapter": fs.plant_chapter, "resolve_chapter": fs.resolve_chapter,
                                "volume_ref": fs.volume_ref, "planned_resolve_arc": fs.planned_resolve_arc,
                                "confidence": fs.confidence, "resolve_keywords": fs.resolve_keywords},
                               ensure_ascii=False),
            "desc": "", "pid": self.project_id,
            "text": fs.text, "hint": fs.hint, "er": fs.expected_resolution,
            "r": fs.resolved, "rt": fs.resolution_text,
            "source": fs.source, "status": fs.status,
            "pc": fs.plant_chapter, "rc": fs.resolve_chapter,
            "vr": fs.volume_ref, "pra": fs.planned_resolve_arc,
            "conf": fs.confidence,
            "rk": json.dumps(fs.resolve_keywords, ensure_ascii=False) if fs.resolve_keywords else "[]",
        })
        # P0-1: Create INVOLVES edges from foreshadow to related entities
        for eid in fs.related_entities:
            if eid:
                self._run("""
                    MATCH (f:Fore {id: $fid, project_id: $pid})
                    MATCH (e:Entity {id: $eid, project_id: $pid})
                    MERGE (f)-[:INVOLVES]->(e)
                """, {"fid": fs.id, "eid": eid, "pid": self.project_id})
        self._invalidate_cache(self.project_id)
        return fs

    def list_foreshadows(self, resolved: bool | None = None, status: str | None = None) -> list[Foreshadow]:
        """List foreshadows, optionally filtered by resolved flag or status.

        Args:
            resolved: If True, only resolved; if False, only unresolved; if None, all.
            status: Filter by status field (open/resolved/cross_volume/dangling).
                   If provided, takes precedence over resolved flag.
        """
        if status:
            rows = self._run(
                "MATCH (f:Fore {project_id: $pid}) WHERE f.status = $s RETURN f ORDER BY f.created_at",
                {"pid": self.project_id, "s": status}
            )
        elif resolved is not None:
            rows = self._run(
                "MATCH (f:Fore {project_id: $pid}) WHERE coalesce(f.resolved, false) = $r RETURN f ORDER BY f.created_at",
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
            data_dict = json.loads(n.get("data", "{}")) if n.get("data") else {}
            resolve_kw = n.get("resolve_keywords", "[]")
            if isinstance(resolve_kw, str):
                try:
                    resolve_kw = json.loads(resolve_kw)
                except (json.JSONDecodeError, ValueError):
                    resolve_kw = []
            result.append(Foreshadow(
                id=n["id"], text=n.get("text", ""), hint=n.get("hint", ""),
                expected_resolution=n.get("expected_resolution", ""),
                resolved=n.get("resolved", False),
                resolution_text=n.get("resolution_text", ""),
                related_entities=data_dict.get("related_entities", []),
                related_events=data_dict.get("related_events", []),
                source=n.get("source", "extracted"),
                status=n.get("status", "open" if not n.get("resolved", False) else "resolved"),
                plant_chapter=n.get("plant_chapter", ""),
                resolve_chapter=n.get("resolve_chapter", ""),
                volume_ref=n.get("volume_ref", ""),
                planned_resolve_arc=n.get("planned_resolve_arc", ""),
                scheduled_chapter=n.get("scheduled_chapter", ""),
                confidence=n.get("confidence", "high"),
                resolve_keywords=resolve_kw if isinstance(resolve_kw, list) else [],
            ))
        return result

    def resolve_foreshadow(self, fs_id: str, resolution_text: str, resolve_chapter: str = "") -> bool:
        """Mark a foreshadow as resolved.

        Args:
            fs_id: Foreshadow ID.
            resolution_text: How the foreshadow was resolved.
            resolve_chapter: Chapter where resolution occurred (e.g. "#15").
        """
        self._run(
            """MATCH (f:Fore {id: $id, project_id: $pid})
               SET f.resolved = true,
                   f.resolution_text = $rt,
                   f.status = 'resolved',
                   f.resolve_chapter = CASE WHEN $rc <> '' THEN $rc ELSE f.resolve_chapter END""",
            {"id": fs_id, "pid": self.project_id, "rt": resolution_text, "rc": resolve_chapter}
        )
        self._invalidate_cache(self.project_id)
        return True

    # ── Foreshadow lifecycle scheduling ──

    def set_foreshadow_planned(self, fs_id: str, planned_arc: str) -> bool:
        """Mark a foreshadow as 'planned' with a target narrative arc.

        This is the first user-driven step: the user decides which arc
        should resolve this foreshadow. The system will later detect when
        writing enters that arc and prompt for confirmation.
        """
        self._run(
            """MATCH (f:Fore {id: $id, project_id: $pid})
               SET f.status = 'planned',
                   f.planned_resolve_arc = $arc""",
            {"id": fs_id, "pid": self.project_id, "arc": planned_arc}
        )
        self._invalidate_cache(self.project_id)
        return True

    def mark_foreshadow_due(self, fs_id: str) -> bool:
        """Mark a 'planned' foreshadow as 'due' — the planned arc is now active.

        Called when the system detects that the current chapter belongs to
        the foreshadow's planned_resolve_arc. This triggers a user
        confirmation prompt before writing.
        """
        self._run(
            """MATCH (f:Fore {id: $id, project_id: $pid})
               WHERE f.status = 'planned'
               SET f.status = 'due'""",
            {"id": fs_id, "pid": self.project_id}
        )
        self._invalidate_cache(self.project_id)
        return True

    def schedule_foreshadow(self, fs_id: str, chapter: str) -> bool:
        """User confirms: schedule this foreshadow for resolution in a specific chapter.

        After this, the ContextManager will inject it as an active
        resolution task for that chapter.
        """
        self._run(
            """MATCH (f:Fore {id: $id, project_id: $pid})
               SET f.status = 'scheduled',
                   f.scheduled_chapter = $ch""",
            {"id": fs_id, "pid": self.project_id, "ch": chapter}
        )
        self._invalidate_cache(self.project_id)
        return True

    def postpone_foreshadow(self, fs_id: str) -> bool:
        """User defers: move a 'due' foreshadow back to 'planned'.

        The foreshadow keeps its planned_resolve_arc but will not prompt
        again until the next time that arc is detected.
        """
        self._run(
            """MATCH (f:Fore {id: $id, project_id: $pid})
               WHERE f.status = 'due'
               SET f.status = 'planned'""",
            {"id": fs_id, "pid": self.project_id}
        )
        self._invalidate_cache(self.project_id)
        return True

    def list_due_foreshadows(self) -> list[Foreshadow]:
        """List all foreshadows with status='due' — awaiting user confirmation."""
        return self.list_foreshadows(status="due")

    def list_scheduled_foreshadows(self, chapter: str = "") -> list[Foreshadow]:
        """List foreshadows scheduled for resolution.

        If chapter is provided, filter to those scheduled for that chapter.
        """
        if chapter:
            rows = self._run(
                """MATCH (f:Fore {project_id: $pid})
                   WHERE f.status = 'scheduled' AND f.scheduled_chapter = $ch
                   RETURN f ORDER BY f.created_at""",
                {"pid": self.project_id, "ch": chapter}
            )
            return self._rows_to_foreshadows(rows)
        return self.list_foreshadows(status="scheduled")

    def list_foreshadows_by_arc(self, arc: str) -> list[Foreshadow]:
        """List foreshadows whose planned_resolve_arc matches the given arc."""
        rows = self._run(
            """MATCH (f:Fore {project_id: $pid})
               WHERE f.planned_resolve_arc = $arc
               RETURN f ORDER BY f.created_at""",
            {"pid": self.project_id, "arc": arc}
        )
        return self._rows_to_foreshadows(rows)

    def _rows_to_foreshadows(self, rows) -> list[Foreshadow]:
        """Convert Cypher result rows to Foreshadow objects."""
        result = []
        for row in rows:
            n = row["f"]
            data_dict = json.loads(n.get("data", "{}")) if n.get("data") else {}
            resolve_kw = n.get("resolve_keywords", "[]")
            if isinstance(resolve_kw, str):
                try:
                    resolve_kw = json.loads(resolve_kw)
                except (json.JSONDecodeError, ValueError):
                    resolve_kw = []
            result.append(Foreshadow(
                id=n["id"], text=n.get("text", ""), hint=n.get("hint", ""),
                expected_resolution=n.get("expected_resolution", ""),
                resolved=n.get("resolved", False),
                resolution_text=n.get("resolution_text", ""),
                related_entities=data_dict.get("related_entities", []),
                related_events=data_dict.get("related_events", []),
                source=n.get("source", "extracted"),
                status=n.get("status", "open" if not n.get("resolved", False) else "resolved"),
                plant_chapter=n.get("plant_chapter", ""),
                resolve_chapter=n.get("resolve_chapter", ""),
                volume_ref=n.get("volume_ref", ""),
                planned_resolve_arc=n.get("planned_resolve_arc", ""),
                scheduled_chapter=n.get("scheduled_chapter", ""),
                confidence=n.get("confidence", "high"),
                resolve_keywords=resolve_kw if isinstance(resolve_kw, list) else [],
            ))
        return result

    def match_foreshadow_resolutions(self, chapters: list[dict], llm_chat=None) -> dict:
        """Pass 2: Match unresolved foreshadows to their resolutions in later chapters.

        For each foreshadow with status='open':
        1. Use resolve_keywords to find candidate passages in later chapters
        2. Use LLM to confirm if a passage constitutes a resolution
        3. Update foreshadow status to resolved/cross_volume/dangling

        Args:
            chapters: List of chapter dicts with 'title' and 'content'.
            llm_chat: Optional LLM chat function (from core.llm_client.chat).
                      If None, uses keyword-only matching without LLM confirmation.

        Returns stats about matching results.
        """
        open_fores = self.list_foreshadows(status="open")
        if not open_fores:
            return {"matched": 0, "unmatched": 0, "total": 0}

        stats = {"matched": 0, "unmatched": 0, "cross_volume": 0, "dangling": 0, "total": len(open_fores)}

        for fs in open_fores:
            # Determine which chapters to scan (after plant_chapter)
            plant_ch = fs.plant_chapter or ""
            plant_num = 0
            if plant_ch:
                try:
                    plant_num = int(plant_ch.replace("#", "").split(".")[0])
                except ValueError:
                    pass

            # Scan later chapters for resolve_keywords
            candidates = []
            for i, ch in enumerate(chapters):
                ch_num = i + 1
                if plant_num and ch_num <= plant_num:
                    continue  # Skip chapters before/at planting
                # Handle versioned chapters: content is inside the latest version
                if "versions" in ch:
                    versions = ch.get("versions", [])
                    view = versions[-1] if versions else {}
                else:
                    view = ch
                content = view.get("content", "")
                title = view.get("title", "")
                if not content:
                    continue

                # Keyword matching: check if any resolve_keywords appear in this chapter
                if fs.resolve_keywords:
                    kw_hits = sum(1 for kw in fs.resolve_keywords if kw in content)
                    if kw_hits == 0:
                        continue
                    candidates.append({
                        "chapter": f"#{ch_num}",
                        "title": title,
                        "content_snippet": content[:500],
                        "keyword_hits": kw_hits,
                    })
                else:
                    # No keywords — use text substring matching as fallback
                    if fs.text[:20] in content or fs.hint[:20] in content:
                        candidates.append({
                            "chapter": f"#{ch_num}",
                            "title": title,
                            "content_snippet": content[:500],
                            "keyword_hits": 1,
                        })

            if not candidates:
                # No candidate found in any later chapter
                if fs.confidence == "low":
                    self._set_foreshadow_status(fs.id, "dangling")
                    stats["dangling"] += 1
                else:
                    # Could be cross-volume or genuinely dangling
                    self._set_foreshadow_status(fs.id, "dangling")
                    stats["dangling"] += 1
                stats["unmatched"] += 1
                continue

            # If LLM available, confirm best candidate
            best_match = None
            if llm_chat and len(candidates) > 0:
                best_match = self._llm_confirm_resolution(fs, candidates, llm_chat)

            if best_match:
                self.resolve_foreshadow(
                    fs.id,
                    best_match.get("resolution_text", fs.expected_resolution),
                    best_match.get("resolve_chapter", "")
                )
                stats["matched"] += 1
            else:
                # LLM not available or didn't confirm — use highest keyword hit candidate
                best_cand = max(candidates, key=lambda c: c["keyword_hits"])
                if best_cand["keyword_hits"] >= 2:
                    self.resolve_foreshadow(
                        fs.id,
                        f"疑似回收于{best_cand['chapter']} {best_cand['title']}",
                        best_cand["chapter"]
                    )
                    stats["matched"] += 1
                else:
                    self._set_foreshadow_status(fs.id, "dangling")
                    stats["dangling"] += 1
                    stats["unmatched"] += 1

        self._invalidate_cache(self.project_id)
        return stats

    def _set_foreshadow_status(self, fs_id: str, status: str):
        """Update foreshadow status field."""
        self._run(
            "MATCH (f:Fore {id: $id, project_id: $pid}) SET f.status = $s",
            {"id": fs_id, "pid": self.project_id, "s": status}
        )

    def _llm_confirm_resolution(self, fs, candidates: list[dict], llm_chat) -> dict | None:
        """Use LLM to confirm which candidate passage resolves the foreshadow.

        Returns dict with resolve_chapter and resolution_text, or None if no match.
        """
        cand_lines = []
        for i, c in enumerate(candidates[:5]):
            cand_lines.append(f"{i+1}. 第{c['chapter']}章 {c['title']}:\n{c['content_snippet'][:300]}")

        prompt = f"""伏笔：{fs.text}
暗示：{fs.hint}
预期回收：{fs.expected_resolution}

以下是可能回收该伏笔的后续章节段落：
{chr(10).join(cand_lines)}

请判断哪个段落真正回收了这个伏笔。输出JSON:
{{"found": true/false, "candidate_index": 1, "resolve_chapter": "#15", "resolution_text": "回收说明"}}
如果没有任何段落回收了该伏笔，输出 {{"found": false}}"""

        try:
            from .utils import extract_json_from_response
            response = llm_chat(prompt, system="你是小说伏笔分析专家。只输出JSON。", temperature=0.1, task="extraction")
            if not response:
                return None
            j = extract_json_from_response(response)
            import json as _json
            data = _json.loads(j.strip())
            if data.get("found") and data.get("candidate_index"):
                idx = int(data["candidate_index"]) - 1
                if 0 <= idx < len(candidates):
                    return {
                        "resolve_chapter": data.get("resolve_chapter", candidates[idx]["chapter"]),
                        "resolution_text": data.get("resolution_text", ""),
                    }
        except Exception:
            pass
        return None

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
        # P0-3: Create HAS_PHASE edge from entity to snapshot
        if snapshot.character_entity_id:
            self._run("""
                MATCH (e:Entity {id: $cid, project_id: $pid})
                MATCH (s:Snapshot {id: $sid, project_id: $pid})
                MERGE (e)-[:HAS_PHASE]->(s)
            """, {"cid": snapshot.character_entity_id, "sid": snapshot.id, "pid": self.project_id})
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
        self._invalidate_cache(self.project_id)
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
            self._invalidate_cache(self.project_id)
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
        self._invalidate_cache(self.project_id)
        return True

    # ── Timeline ──

    def link_timeline_to_entities(self, event_id: str, entity_ids: list[str]) -> int:
        """Create INVOLVES edges from a timeline event to multiple entities.

        Returns the number of edges created.
        """
        if not entity_ids:
            return 0
        count = 0
        for eid in entity_ids:
            rows = self._run("""
                MATCH (t:Timeline {id: $tid, project_id: $pid})
                MATCH (e:Entity {id: $eid, project_id: $pid})
                MERGE (t)-[:INVOLVES]->(e)
                RETURN count(*) as cnt
            """, {"tid": event_id, "eid": eid, "pid": self.project_id})
            if rows and rows[0]["cnt"] > 0:
                count += 1
        if count > 0:
            self._invalidate_cache(self.project_id)
        return count

    def add_timeline_event(self, event: TimelineEvent) -> TimelineEvent:
        self._run("""
            CREATE (t:Timeline {
                id: $id, time_point: $tp, label: $label,
                time_order: $to, description: $desc,
                chapter_ref: $cr, event_entity_id: $eid,
                track_id: $tid, track_name: $tn, track_color: $tc,
                time_label: $tl, project_id: $pid,
                location_ref: $lref, arc_id: $arc, narrative_time: $ntime
            })
        """, {
            "id": event.id, "tp": event.time_point, "label": event.label,
            "to": event.time_order, "desc": event.description,
            "cr": event.chapter_ref, "eid": event.event_entity_id,
            "tid": event.track_id, "tn": event.track_name,
            "tc": event.track_color, "tl": event.time_label,
            "pid": self.project_id,
            "lref": event.location_ref, "arc": event.arc_id,
            "ntime": event.narrative_time,
        })
        # P0-2: Create INVOLVES edge from timeline event to entity
        if event.event_entity_id:
            self._run("""
                MATCH (t:Timeline {id: $tid, project_id: $pid})
                MATCH (e:Entity {id: $eid, project_id: $pid})
                MERGE (t)-[:INVOLVES]->(e)
            """, {"tid": event.id, "eid": event.event_entity_id, "pid": self.project_id})
        self._invalidate_cache(self.project_id)
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
            track_id=r["t"].get("track_id", ""),
            track_name=r["t"].get("track_name", ""),
            track_color=r["t"].get("track_color", ""),
            time_label=r["t"].get("time_label", ""),
        ) for r in rows]

    def delete_timeline_event(self, event_id: str) -> bool:
        self._run("MATCH (t:Timeline {id: $id, project_id: $pid}) DETACH DELETE t",
                  {"id": event_id, "pid": self.project_id})
        self._invalidate_cache(self.project_id)
        return True

    def clear_all_timeline_events(self) -> int:
        """Delete all timeline events for this project. Returns count deleted."""
        rows = self._run(
            "MATCH (t:Timeline {project_id: $pid}) WITH t, count(t) as cnt DETACH DELETE t RETURN cnt",
            {"pid": self.project_id}
        )
        deleted = rows[0]["cnt"] if rows else 0
        if deleted:
            self._invalidate_cache(self.project_id)
        return deleted

    def get_timeline_for_view(self) -> dict:
        """Return timeline data in the format TimelineView expects:
        {tracks: [{id, name, color}], events: [{id, track_id, label, time_label, description, chapter_ref, order, characters}]}
        """
        events = self.list_timeline_events()
        # Build tracks from unique track_id values
        track_map: dict[str, dict] = {}
        for ev in events:
            if ev.track_id and ev.track_id not in track_map:
                track_map[ev.track_id] = {
                    "id": ev.track_id,
                    "name": ev.track_name or ev.track_id,
                    "color": ev.track_color or "#22d3ee",
                }
        # If no tracks defined, create a default one
        if not track_map:
            track_map["main"] = {"id": "main", "name": "主线", "color": "#22d3ee"}
        # Get characters for each event via INVOLVES edges
        event_list = []
        for ev in events:
            chars = self._run("""
                MATCH (t:Timeline {id: $tid, project_id: $pid})-[:INVOLVES]->(e:Entity:Character)
                RETURN e.name as name
            """, {"tid": ev.id, "pid": self.project_id})
            char_names = [r["name"] for r in chars]
            event_list.append({
                "id": ev.id,
                "track_id": ev.track_id or "main",
                "label": ev.label,
                "time_label": ev.time_label or ev.time_point,
                "description": ev.description,
                "chapter_ref": ev.chapter_ref,
                "order": ev.time_order,
                "characters": char_names,
            })
        event_list.sort(key=lambda e: e["order"])
        return {"tracks": list(track_map.values()), "events": event_list}

    def get_all_time_points(self) -> list[dict]:
        rows = self._run(
            "MATCH (t:Timeline {project_id: $pid}) RETURN t.label as label, t.time_point as tp, t.time_order as to ORDER BY to",
            {"pid": self.project_id}
        )
        return [{"time_point": r["tp"], "label": r["label"]} for r in rows]

    def get_location_map_for_view(self) -> dict:
        """Return location map data in the format WorldMap expects.

        Returns nodes, connections, plus character_positions and event_anchors
        for the 4D map (location + character + event triangulation).
        """
        locs = self.list_entities(entity_type="location")
        nodes = []
        for loc in locs:
            node = {
                "id": loc.id,
                "name": loc.name,
                "type": loc.data.get("location_type", loc.data.get("type", "other")),
                "description": loc.data.get("description", ""),
                "parent": loc.data.get("parent_location", ""),
            }
            nodes.append(node)

        # Get relationships between location entities (including LOCATED_IN, ADJACENT_TO, BELONGS_TO)
        loc_ids = {loc.id for loc in locs}
        connections = []
        if loc_ids:
            rels = self._run("""
                MATCH (a:Entity:Location {project_id: $pid})-[r]->(b:Entity:Location {project_id: $pid})
                RETURN a.name as from_name, b.name as to_name, type(r) as rel_type
            """, {"pid": self.project_id})
            for r in rels:
                connections.append({
                    "from": r["from_name"],
                    "to": r["to_name"],
                    "type": r["rel_type"].lower(),
                    "label": r["rel_type"],
                })

        # ── Character positions: which characters are LOCATED_AT each location ──
        character_positions = []
        char_loc_rows = self._run("""
            MATCH (c:Entity:Character {project_id: $pid})-[r:LOCATED_AT]->(loc:Entity:Location {project_id: $pid})
            RETURN c.id as cid, c.name as cname, loc.id as lid, loc.name as lname
        """, {"pid": self.project_id})
        for r in char_loc_rows:
            character_positions.append({
                "character_id": r["cid"],
                "character_name": r["cname"],
                "location_id": r["lid"],
                "location_name": r["lname"],
            })

        # ── Event anchors: which timeline events OCCURRED_AT each location ──
        event_anchors = []
        evt_loc_rows = self._run("""
            MATCH (t:Timeline {project_id: $pid})-[:OCCURRED_AT]->(loc:Entity:Location {project_id: $pid})
            RETURN t.id as tid, t.label as tlabel, t.time_order as torder,
                   loc.id as lid, loc.name as lname
            ORDER BY t.time_order
        """, {"pid": self.project_id})
        for r in evt_loc_rows:
            event_anchors.append({
                "event_id": r["tid"],
                "event_label": r["tlabel"],
                "time_order": r["torder"],
                "location_id": r["lid"],
                "location_name": r["lname"],
            })

        return {
            "nodes": nodes,
            "connections": connections,
            "character_positions": character_positions,
            "event_anchors": event_anchors,
        }

    # ── Consistency Check (inherited from AnalysisMixin) ──

    # ── P1-3: Bridge character discovery (activates get_neighbors + path analysis) ──

    def find_bridge_characters(self) -> list[dict]:
        """Find bridge characters using approximate betweenness centrality.

        Detects characters that appear as intermediaries in shortest paths
        between otherwise-disconnected character pairs. Paths up to length 3
        are examined to capture multi-hop bridge roles.
        A character appearing in more paths has higher centrality.
        """
        rows = self._run("""
            MATCH (a:Entity:Character {project_id: $pid}),
                  (b:Entity:Character {project_id: $pid})
            WHERE a.id < b.id
            AND NOT (a)-[:KNOWS|ALLY|FAMILY|ANTAGONIST|ROMANTIC|MASTER_OF|MENTOR_OF|KILLED|SAVED|LOVES]-(b)
            MATCH path = shortestPath(
                (a)-[:KNOWS|ALLY|FAMILY|ANTAGONIST|ROMANTIC|MASTER_OF|MENTOR_OF|KILLED|SAVED|LOVES*1..3]-(b)
            )
            WHERE length(path) >= 2
            WITH nodes(path) AS ns, path
            UNWIND ns[1..-1] AS bridge
            RETURN bridge.id AS entity_id,
                   bridge.name AS entity_name,
                   count(*) AS bridge_count,
                   collect(DISTINCT [ns[0].name, ns[-1].name])[0..5] AS sample_pairs
            ORDER BY bridge_count DESC
        """, {"pid": self.project_id})
        result = []
        for r in rows:
            result.append({
                "entity_id": r["entity_id"],
                "entity_name": r.get("entity_name", ""),
                "bridge_count": r["bridge_count"],
                "would_disconnect": r.get("sample_pairs", [])[:5],
            })
        return result

    # ── P1-4: Causal chain rewrite protection (activates graph reachability) ──

    def find_downstream_impact(self, event_id: str) -> dict:
        """Find all downstream elements affected by modifying a timeline event.

        Traverses the graph from the given event to find:
        - Later timeline events involving the same entities
        - Unresolved foreshadows involving the same entities
        """
        result = {"affected_events": [], "affected_foreshadows": [], "affected_entities": []}
        event = self._run_single(
            "MATCH (t:Timeline {id: $tid, project_id: $pid}) RETURN t",
            {"tid": event_id, "pid": self.project_id}
        )
        if not event:
            return result
        time_order = event["t"].get("time_order", 0)
        # Find entities involved in this event (via P0-2 INVOLVES edges)
        rows = self._run("""
            MATCH (t:Timeline {id: $tid, project_id: $pid})-[:INVOLVES]->(e:Entity)
            RETURN e.id as eid, e.name as ename
        """, {"tid": event_id, "pid": self.project_id})
        entity_ids = [r["eid"] for r in rows]
        entity_names = [r["ename"] for r in rows]
        if not entity_ids:
            return result
        # Find later timeline events involving the same entities
        later = self._run("""
            MATCH (t2:Timeline {project_id: $pid})-[:INVOLVES]->(e:Entity)
            WHERE e.id IN $eids AND t2.time_order > $to
            RETURN DISTINCT t2.id as tid, t2.label as label,
                   t2.chapter_ref as cr, t2.time_order as to2
            ORDER BY t2.time_order
        """, {"eids": entity_ids, "to": time_order, "pid": self.project_id})
        result["affected_events"] = [
            {"id": r["tid"], "label": r["label"], "chapter_ref": r["cr"]}
            for r in later
        ]
        # Find unresolved foreshadows involving the same entities (via P0-1 INVOLVES)
        fores = self._run("""
            MATCH (f:Fore {project_id: $pid, resolved: false})-[:INVOLVES]->(e:Entity)
            WHERE e.id IN $eids
            RETURN DISTINCT f.id as fid, f.text as text
        """, {"eids": entity_ids, "pid": self.project_id})
        result["affected_foreshadows"] = [
            {"id": r["fid"], "text": r["text"]} for r in fores
        ]
        result["affected_entities"] = entity_names
        return result

    # ── P1-5: Chapter entity coverage analysis (forgotten character tracking) ──

    def find_forgotten_characters(self, current_time_order: int = 0,
                                  threshold: int = 5) -> list[dict]:
        """Find characters who haven't appeared in recent timeline events.

        Args:
            current_time_order: The current timeline position.
            threshold: Steps without appearance to be considered "forgotten".
        """
        rows = self._run("""
            MATCH (e:Entity:Character {project_id: $pid})
            OPTIONAL MATCH (t:Timeline)-[:INVOLVES]->(e)
            WITH e, max(t.time_order) as last_appearance
            WHERE last_appearance IS NULL
               OR last_appearance < $current - $threshold
            RETURN e.id as eid, e.name as name,
                   coalesce(last_appearance, -1) as last_seen,
                   e.data as data
            ORDER BY last_seen ASC
        """, {"pid": self.project_id, "current": current_time_order,
               "threshold": threshold})
        result = []
        for r in rows:
            data = r.get("data", "{}")
            if isinstance(data, str):
                data = json.loads(data) if data else {}
            elif data is None:
                data = {}
            result.append({
                "entity_id": r["eid"],
                "name": r["name"],
                "last_seen_time_order": r["last_seen"],
                "important": bool(data.get("important") or data.get("role")),
                "steps_absent": (current_time_order - r["last_seen"]
                                 if r["last_seen"] >= 0 else None),
            })
        return result

    # ── P2-11: Foreshadow dependency graph (DEPENDS_ON edges + cycle detection) ──

    def add_foreshadow_dependency(self, from_id: str, to_id: str) -> bool:
        """Create a DEPENDS_ON edge: foreshadow `from_id` depends on `to_id`.

        `to_id` must be resolved before `from_id` makes sense narratively.
        """
        self._run("""
            MATCH (f1:Fore {id: $fid, project_id: $pid})
            MATCH (f2:Fore {id: $tid, project_id: $pid})
            MERGE (f1)-[:DEPENDS_ON]->(f2)
        """, {"fid": from_id, "tid": to_id, "pid": self.project_id})
        self._invalidate_cache(self.project_id)
        return True

    def detect_foreshadow_cycles(self) -> list[dict]:
        """Detect circular dependencies in the foreshadow dependency graph."""
        rows = self._run("""
            MATCH path = (f:Fore {project_id: $pid})-[:DEPENDS_ON*1..10]->(f)
            RETURN f.id as fid, f.text as text,
                   [n in nodes(path) | n.id] as cycle_ids
        """, {"pid": self.project_id})
        return [
            {"id": r["fid"], "text": r["text"], "cycle": r["cycle_ids"]}
            for r in rows
        ]

    def get_foreshadow_resolution_order(self) -> list[dict]:
        """Generate topological sort of foreshadow resolution order.

        Foreshadows with no unresolved dependencies come first.
        Detects cycles and flags remaining foreshadows as cyclic.
        """
        fores = self.list_foreshadows(resolved=False)
        if not fores:
            return []
        dep_rows = self._run("""
            MATCH (f:Fore {project_id: $pid, resolved: false})-[:DEPENDS_ON]->(dep:Fore {resolved: false})
            RETURN f.id as fid, dep.id as depid
        """, {"pid": self.project_id})
        deps = {f.id: set() for f in fores}
        for r in dep_rows:
            deps[r["fid"]].add(r["depid"])
        # Kahn's algorithm for topological sort
        result = []
        fs_by_id = {f.id: f for f in fores}
        resolved_set = set()
        while len(resolved_set) < len(fores):
            ready = [
                fid for fid in deps
                if fid not in resolved_set
                and deps[fid].issubset(resolved_set)
            ]
            if not ready:
                cyclic = [fid for fid in deps if fid not in resolved_set]
                for fid in cyclic:
                    f = fs_by_id.get(fid)
                    result.append({
                        "id": fid, "text": f.text if f else "",
                        "warning": "存在循环依赖，无法确定回收顺序",
                    })
                break
            for fid in ready:
                f = fs_by_id.get(fid)
                result.append({
                    "id": fid, "text": f.text if f else "",
                    "dependencies": list(deps[fid]),
                })
                resolved_set.add(fid)
        return result

    # ── P2-13: Missing relationship detection (activates get_path) ──

    def find_missing_relations(self, entity_ids: list[str]) -> list[dict]:
        """Detect pairs of entities with no relationship path between them.

        Useful for checking if characters in the same scene have some
        connection (even indirect) in the relationship graph.
        """
        from itertools import combinations
        result = []
        for a, b in combinations(entity_ids, 2):
            path = self.get_path(a, b, max_depth=3)
            if not path:
                ea = self.get_entity(a)
                eb = self.get_entity(b)
                result.append({
                    "entity_a": {"id": a, "name": ea.name if ea else a},
                    "entity_b": {"id": b, "name": eb.name if eb else b},
                    "warning": f"「{ea.name if ea else a}」与「{eb.name if eb else b}」之间无任何关系路径",
                })
        return result

    # ── P2-14: Worldbuilding completeness metrics ──

    def get_worldbuilding_metrics(self) -> dict:
        """Compute graph topology metrics for worldbuilding health assessment."""
        return self._cached("metrics", self._compute_worldbuilding_metrics)

    def _compute_worldbuilding_metrics(self) -> dict:
        """Compute graph topology metrics with non-linear composite health score."""
        entity_count = len(self.list_entities())
        relation_count = len(self.list_relations())
        max_edges = entity_count * (entity_count - 1) / 2 if entity_count > 1 else 1
        density = relation_count / max_edges if max_edges > 0 else 0
        isolated = self._run("""
            MATCH (e:Entity {project_id: $pid})
            WHERE NOT (e)-[]-()
            RETURN e.name as name, e.entity_type as type
        """, {"pid": self.project_id})
        components = self._run("""
            MATCH (e:Entity {project_id: $pid})
            OPTIONAL MATCH (e)-[*1..3]-(connected:Entity {project_id: $pid})
            WITH e, collect(DISTINCT connected.id) as component
            RETURN e.id as eid, e.name as name, size(component) as comp_size
            ORDER BY comp_size DESC
        """, {"pid": self.project_id})
        largest = max((int(r["comp_size"]) for r in components), default=0)
        frag_ratio = round(1 - (largest / entity_count), 3) if entity_count > 0 else 0

        # Non-linear composite health score
        density_norm = min(density / 0.15, 1.0)
        density_score = 100 * (1 - 1 / (1 + 5 * density_norm))
        iso_rate = len(isolated) / max(entity_count, 1)
        iso_score = 100 * (1 - iso_rate ** 0.4)
        conn_score = 100 * (1 - frag_ratio ** 0.5)
        composite = round(density_score * 0.35 + iso_score * 0.35 + conn_score * 0.30)
        health = "良好" if composite >= 70 else "一般" if composite >= 40 else "稀疏"

        return {
            "entity_count": entity_count,
            "relation_count": relation_count,
            "density": round(density, 3),
            "isolated_entities": [
                {"name": r["name"], "type": r.get("type", "")} for r in isolated
            ],
            "isolated_count": len(isolated),
            "largest_component_size": largest,
            "fragmentation_ratio": frag_ratio,
            "health_assessment": health,
            "health_score": composite,
        }

    # ── P2-15: Character perspective subgraph (POV-aware) ──

    def get_pov_subgraph(self, character_id: str) -> dict:
        """Return the subgraph visible from a character's perspective.

        Includes direct relationships, entities from shared timeline events,
        and foreshadows involving this character.
        """
        direct = self._run("""
            MATCH (c:Entity {id: $cid, project_id: $pid})-[r]-(other:Entity {project_id: $pid})
            RETURN DISTINCT other.id as oid, other.name as name,
                   other.entity_type as type, type(r) as rel_type
        """, {"cid": character_id, "pid": self.project_id})
        event_entities = self._run("""
            MATCH (t:Timeline {project_id: $pid})-[:INVOLVES]->(c:Entity {id: $cid})
            MATCH (t)-[:INVOLVES]->(other:Entity)
            WHERE other.id <> $cid
            RETURN DISTINCT other.id as oid, other.name as name,
                   other.entity_type as type
        """, {"cid": character_id, "pid": self.project_id})
        char_fores = self._run("""
            MATCH (f:Fore {project_id: $pid})-[:INVOLVES]->(c:Entity {id: $cid})
            RETURN f.id as fid, f.text as text, f.resolved as resolved
        """, {"cid": character_id, "pid": self.project_id})
        nodes = {}
        for r in direct:
            nodes[r["oid"]] = {
                "id": r["oid"], "name": r["name"],
                "type": r.get("type", ""), "connection": "direct",
            }
        for r in event_entities:
            if r["oid"] not in nodes:
                nodes[r["oid"]] = {
                    "id": r["oid"], "name": r["name"],
                    "type": r.get("type", ""), "connection": "event",
                }
        return {
            "pov_character_id": character_id,
            "visible_entities": list(nodes.values()),
            "visible_foreshadows": [
                {"id": r["fid"], "text": r["text"], "resolved": r["resolved"]}
                for r in char_fores
            ],
            "visibility_scope": len(nodes),
        }

    # ── P2-6: Character knowledge horizon (time-annotated edges) ──

    def add_temporal_relation(self, from_id: str, to_id: str, rel_type: str,
                              since_chapter: int) -> bool:
        """Create a time-annotated relationship edge.

        The since_chapter property records when this relationship was
        established, enabling time-aware context filtering.
        """
        rel_upper = rel_type.upper()
        self._run(f"""
            MATCH (a:Entity {{id: $from_id, project_id: $pid}})
            MATCH (b:Entity {{id: $to_id, project_id: $pid}})
            MERGE (a)-[r:{rel_upper}]->(b)
            SET r.since_chapter = $chapter, r.project_id = $pid
        """, {"from_id": from_id, "to_id": to_id,
              "chapter": since_chapter, "pid": self.project_id})
        self._invalidate_cache(self.project_id)
        return True

    def get_character_knowledge(self, character_id: str, at_chapter: int) -> dict:
        """Query what a character knows at a given chapter.

        Returns relationships and entities the character was aware of
        up to and including the given chapter number.
        """
        rels = self._run("""
            MATCH (c:Entity {id: $cid, project_id: $pid})-[r]-(other:Entity {project_id: $pid})
            WHERE r.since_chapter IS NULL OR r.since_chapter <= $chapter
            RETURN other.id as oid, other.name as name,
                   other.entity_type as type, type(r) as rel_type,
                   r.since_chapter as since
        """, {"cid": character_id, "chapter": at_chapter, "pid": self.project_id})
        known_entities = [
            {"id": r["oid"], "name": r["name"],
             "type": r.get("type", ""),
             "relationship": r["rel_type"],
             "known_since_chapter": r.get("since")}
            for r in rels
        ]
        events = self._run("""
            MATCH (t:Timeline {project_id: $pid})-[:INVOLVES]->(c:Entity {id: $cid})
            WHERE t.chapter_ref IS NOT NULL
            AND t.chapter_ref =~ '#[0-9]+'
            AND toInteger(replace(t.chapter_ref, '#', '')) <= $chapter
            RETURN t.id as tid, t.label as label, t.chapter_ref as cr
            ORDER BY t.time_order
        """, {"cid": character_id, "chapter": at_chapter, "pid": self.project_id})
        known_events = [
            {"id": r["tid"], "label": r["label"], "chapter": r["cr"]}
            for r in events
        ]
        return {
            "character_id": character_id,
            "at_chapter": at_chapter,
            "known_entities": known_entities,
            "known_events": known_events,
        }

    # ── 4D Map: Time-aware entity state query ──

    def get_entity_state_at_time(self, entity_id: str, time_order: int, track_id: str | None = None) -> dict:
        """Get an entity's complete state at a specific timeline position.

        Returns phase, relationships, location, events, and active foreshadows
        filtered to the given time_order.

        When ``track_id`` is provided, only events from that track are included.
        When ``track_id`` is None, events from ALL tracks are returned grouped
        by track, supporting multi-track narrative (e.g. A/B storylines).
        """
        entity = self.get_entity(entity_id)
        if not entity:
            return {"error": "Entity not found"}
        result = {
            "entity_id": entity_id, "entity_name": entity.name,
            "entity_type": entity.type, "at_time_order": time_order,
        }
        if track_id:
            result["track_id"] = track_id
        # Phase: snapshot with largest time_order <= T
        if entity.type == EntityType.CHARACTER:
            phase_row = self._run_single("""
                MATCH (e:Entity {id: $eid, project_id: $pid})-[:HAS_PHASE]->(s:Snapshot)
                WHERE s.time_order <= $to
                RETURN s ORDER BY s.time_order DESC LIMIT 1
            """, {"eid": entity_id, "to": time_order, "pid": self.project_id})
            if phase_row:
                snap = self._row_to_snapshot(phase_row["s"])
                result["phase"] = {
                    "phase": snap.phase, "label": snap.label,
                    "data": snap.data, "description": snap.description,
                }
        # Relationships established by this time
        rels = self._run("""
            MATCH (e:Entity {id: $eid, project_id: $pid})-[r]-(other:Entity {project_id: $pid})
            WHERE r.since_chapter IS NULL OR r.since_chapter <= $to
            RETURN other.id as oid, other.name as oname, other.entity_type as otype,
                   type(r) as rel_type, r.since_chapter as since
        """, {"eid": entity_id, "to": time_order, "pid": self.project_id})
        result["relationships"] = [
            {"entity_id": r["oid"], "name": r["oname"], "type": r.get("otype", ""),
             "relationship": r["rel_type"], "since_chapter": r.get("since")}
            for r in rels
        ]
        # Location at this time
        loc_row = self._run_single("""
            MATCH (e:Entity {id: $eid, project_id: $pid})-[r:LOCATED_AT]->(loc:Entity {project_id: $pid})
            RETURN loc.id as lid, loc.name as lname
        """, {"eid": entity_id, "pid": self.project_id})
        if loc_row:
            result["location"] = {"id": loc_row["lid"], "name": loc_row["lname"]}
        # Timeline events up to this time — per-track when track_id given
        if track_id:
            events = self._run("""
                MATCH (t:Timeline {project_id: $pid, track_id: $tid})-[:INVOLVES]->(e:Entity {id: $eid})
                WHERE t.time_order <= $to
                RETURN t.id as tid, t.label as label, t.time_order as to2,
                       t.track_id as track_id, t.track_name as track_name,
                       t.chapter_ref as cr, t.description as desc
                ORDER BY t.time_order
            """, {"eid": entity_id, "to": time_order, "tid": track_id, "pid": self.project_id})
            result["events"] = [
                {"id": r["tid"], "label": r["label"], "time_order": r["to2"],
                 "track_id": r.get("track_id", ""), "track_name": r.get("track_name", ""),
                 "chapter_ref": r["cr"], "description": r.get("desc", "")}
                for r in events
            ]
        else:
            # Multi-track: return events grouped by track
            events = self._run("""
                MATCH (t:Timeline {project_id: $pid})-[:INVOLVES]->(e:Entity {id: $eid})
                WHERE t.time_order <= $to
                RETURN t.id as tid, t.label as label, t.time_order as to2,
                       t.track_id as track_id, t.track_name as track_name,
                       t.chapter_ref as cr, t.description as desc
                ORDER BY t.track_id, t.time_order
            """, {"eid": entity_id, "to": time_order, "pid": self.project_id})
            tracks: dict[str, dict] = {}
            for r in events:
                tid = r.get("track_id", "main")
                if tid not in tracks:
                    tracks[tid] = {
                        "track_id": tid,
                        "track_name": r.get("track_name", tid),
                        "events": [],
                    }
                tracks[tid]["events"].append({
                    "id": r["tid"], "label": r["label"], "time_order": r["to2"],
                    "chapter_ref": r["cr"], "description": r.get("desc", ""),
                })
            result["tracks"] = list(tracks.values())
        # Active foreshadows at this time
        fores = self._run("""
            MATCH (f:Fore {project_id: $pid, resolved: false})-[:INVOLVES]->(e:Entity {id: $eid})
            RETURN f.id as fid, f.text as text
        """, {"eid": entity_id, "pid": self.project_id})
        result["active_foreshadows"] = [
            {"id": r["fid"], "text": r["text"]} for r in fores
        ]
        return result

    def get_map_at_time(self, time_order: int) -> dict:
        """Get the location map with character positions at a specific timeline position.

        Returns locations, which characters are at each location, and all
        timeline events at this time.
        """
        # All location entities
        locs = self._run("""
            MATCH (loc:Entity:Location {project_id: $pid})
            RETURN loc.id as lid, loc.name as lname, loc.data as data
        """, {"pid": self.project_id})
        locations = []
        for r in locs:
            data = r.get("data", "{}")
            if isinstance(data, str):
                data = json.loads(data) if data else {}
            locations.append({
                "id": r["lid"], "name": r["lname"],
                "type": data.get("locationType", data.get("type", "other")),
                "data": data,
            })
        # Characters at each location at this time
        char_locs = self._run("""
            MATCH (t:Timeline {project_id: $pid, time_order: $to})
            MATCH (t)-[:INVOLVES]->(e:Entity:Character {project_id: $pid})
            OPTIONAL MATCH (e)-[:LOCATED_AT]->(loc:Entity {project_id: $pid})
            RETURN e.id as cid, e.name as cname,
                   loc.id as lid, loc.name as lname
        """, {"to": time_order, "pid": self.project_id})
        characters_at_locations = {}
        for r in char_locs:
            lid = r.get("lid") or "unknown"
            if lid not in characters_at_locations:
                characters_at_locations[lid] = {
                    "location_name": r.get("lname") or "未知",
                    "characters": [],
                }
            characters_at_locations[lid]["characters"].append({
                "id": r["cid"], "name": r["cname"],
            })
        # Events at this time
        events_at = self._run("""
            MATCH (t:Timeline {project_id: $pid, time_order: $to})
            RETURN t.id as tid, t.label as label, t.chapter_ref as cr,
                   t.description as desc
        """, {"to": time_order, "pid": self.project_id})
        return {
            "at_time_order": time_order,
            "locations": locations,
            "characters_at_locations": characters_at_locations,
            "events_at_time": [
                {"id": r["tid"], "label": r["label"],
                 "chapter_ref": r["cr"], "description": r.get("desc", "")}
                for r in events_at
            ],
        }

    # ── Full graph: Complete book visualization ──

    def get_full_graph(self, at_time_order: int | None = None, include_simulations: bool = False) -> dict:
        """Return the complete graph — all nodes and edges for full-book visualization.

        Includes Entity nodes, Timeline nodes, Foreshadow nodes, and all edges
        between them (relationships, INVOLVES, HAS_PHASE).

        When ``at_time_order`` is set, only timeline nodes with time_order <= T
        are included, and edges are filtered to those established by that time.

        When ``include_simulations`` is True, also includes SimulationSession,
        SimEvent, SimChoice, and SimCharacterResponse nodes (推演层) with
        their SIM_* edges to Entity:Character nodes. Frontend can style these
        with dashed/translucent visuals to distinguish hypothetical data.
        """
        node_set = {}
        edges = []
        time_filter = at_time_order is not None
        params: dict = {"pid": self.project_id}
        if time_filter:
            params["to"] = at_time_order
        # All entities (always included — they exist across time)
        entity_rows = self._run("""
            MATCH (e:Entity {project_id: $pid})
            RETURN e.id as id, e.name as name, e.entity_type as type, e.data as data
        """, {"pid": self.project_id})
        for r in entity_rows:
            data = r.get("data", "{}")
            if isinstance(data, str):
                data = json.loads(data) if data else {}
            node_set[r["id"]] = {
                "id": r["id"], "name": r["name"],
                "type": r.get("type", "unknown"), "data": data,
            }
        # All entity-entity relationships (filter by timeline if time_filter)
        if time_filter:
            # Only include edges whose since_chapter corresponds to a timeline
            # event with time_order <= at_time_order, or edges with no since_chapter
            rel_rows = self._run("""
                MATCH (a:Entity {project_id: $pid})-[r]->(b:Entity {project_id: $pid})
                WHERE r.since_chapter IS NULL
                   OR r.since_chapter <= $to
                RETURN a.id as from_id, b.id as to_id, type(r) as rel_type,
                       r.since_chapter as since
            """, params)
        else:
            rel_rows = self._run("""
                MATCH (a:Entity {project_id: $pid})-[r]->(b:Entity {project_id: $pid})
                RETURN a.id as from_id, b.id as to_id, type(r) as rel_type,
                       r.since_chapter as since
            """, {"pid": self.project_id})
        for r in rel_rows:
            edges.append({
                "from": r["from_id"], "to": r["to_id"],
                "type": r["rel_type"], "since": r.get("since"),
            })
        # Timeline nodes + INVOLVES edges
        if time_filter:
            tl_rows = self._run("""
                MATCH (t:Timeline {project_id: $pid})
                WHERE t.time_order <= $to
                OPTIONAL MATCH (t)-[:INVOLVES]->(e:Entity {project_id: $pid})
                RETURN t.id as tid, t.label as label, t.chapter_ref as cr,
                       t.time_order as to2, t.description as desc,
                       collect(e.id) as eids
                ORDER BY t.time_order
            """, params)
        else:
            tl_rows = self._run("""
                MATCH (t:Timeline {project_id: $pid})
                OPTIONAL MATCH (t)-[:INVOLVES]->(e:Entity {project_id: $pid})
                RETURN t.id as tid, t.label as label, t.chapter_ref as cr,
                       t.time_order as to2, t.description as desc,
                       collect(e.id) as eids
                ORDER BY t.time_order
            """, {"pid": self.project_id})
        for r in tl_rows:
            node_set[r["tid"]] = {
                "id": r["tid"], "name": r["label"] or r["cr"] or "事件",
                "type": "timeline",
                "data": {
                    "chapter_ref": r["cr"], "time_order": r["to2"],
                    "description": r.get("desc", ""),
                },
            }
            for eid in r["eids"]:
                if eid:
                    edges.append({"from": r["tid"], "to": eid, "type": "TIMELINE_INVOLVES"})
        # Foreshadow nodes + INVOLVES edges (always include all)
        fs_rows = self._run("""
            MATCH (f:Fore {project_id: $pid})
            OPTIONAL MATCH (f)-[:INVOLVES]->(e:Entity {project_id: $pid})
            RETURN f.id as fid, f.text as text, f.resolved as resolved,
                   collect(e.id) as eids
        """, {"pid": self.project_id})
        for r in fs_rows:
            node_set[r["fid"]] = {
                "id": r["fid"], "name": (r["text"] or "伏笔")[:20],
                "type": "foreshadow",
                "data": {"resolved": r["resolved"]},
            }
            for eid in r["eids"]:
                if eid:
                    edges.append({"from": r["fid"], "to": eid, "type": "FORESHADOW_INVOLVES"})
        # HAS_PHASE edges (Entity → Snapshot) — filter by time_order
        if time_filter:
            phase_rows = self._run("""
                MATCH (e:Entity {project_id: $pid})-[:HAS_PHASE]->(s:Snapshot {project_id: $pid})
                WHERE s.time_order <= $to
                RETURN e.id as eid, s.id as sid, s.phase as phase, s.time_order as sto
            """, params)
        else:
            phase_rows = self._run("""
                MATCH (e:Entity {project_id: $pid})-[:HAS_PHASE]->(s:Snapshot {project_id: $pid})
                RETURN e.id as eid, s.id as sid, s.phase as phase, s.time_order as sto
            """, {"pid": self.project_id})
        for r in phase_rows:
            node_set[r["sid"]] = {
                "id": r["sid"], "name": r["phase"] or "阶段",
                "type": "snapshot", "data": {"time_order": r.get("sto", 0)},
            }
            edges.append({"from": r["eid"], "to": r["sid"], "type": "HAS_PHASE"})
        # ── Simulation layer (推演层) — optional ──
        if include_simulations:
            sim_rows = self._run("""
                MATCH (s:SimulationSession {project_id: $pid})
                OPTIONAL MATCH (s)-[:SIM_HAS_EVENT]->(e:SimEvent)
                OPTIONAL MATCH (s)-[:SIM_INVOLVES]->(c:Entity {project_id: $pid})
                RETURN s.id as sid, s.mode as mode, s.status as status,
                       s.setting as setting, s.created_at as created,
                       collect(DISTINCT e.id) as event_ids,
                       collect(DISTINCT c.id) as char_ids
            """, {"pid": self.project_id})
            for r in sim_rows:
                node_set[r["sid"]] = {
                    "id": r["sid"], "name": f"推演:{(r.get('setting') or '')[:15]}",
                    "type": "sim_session",
                    "data": {"mode": r.get("mode"), "status": r.get("status")},
                }
                for cid in r["char_ids"]:
                    if cid:
                        edges.append({"from": r["sid"], "to": cid, "type": "SIM_INVOLVES"})
            # SimEvent nodes
            sim_event_rows = self._run("""
                MATCH (e:SimEvent)-[:SIM_RESPONSE_TO|SIM_HAS_EVENT*0..1]-(s:SimulationSession {project_id: $pid})
                MATCH (e)-[r:SIM_RESPONDS_AS]->(c:Entity {project_id: $pid})
                RETURN e.id as eid, e.content as content, e.turn_number as turn,
                       e.event_type as etype, c.id as cid, r.role as role
            """, {"pid": self.project_id})
            for r in sim_event_rows:
                node_set[r["eid"]] = {
                    "id": r["eid"], "name": f"Sim[{r.get('turn', 0)}]",
                    "type": "sim_event",
                    "data": {"content": (r.get("content") or "")[:80], "event_type": r.get("etype")},
                }
                edges.append({
                    "from": r["eid"], "to": r["cid"], "type": "SIM_RESPONDS_AS",
                    "role": r.get("role", ""),
                })

        return {
            "nodes": list(node_set.values()),
            "edges": edges,
            "stats": {
                "node_count": len(node_set),
                "edge_count": len(edges),
            },
        }

    # ── Summary ──

    def get_knowledge_summary(self) -> str:
        return self.to_llm_context()

    def to_llm_context(self, max_entities_per_type: int = 30) -> str:
        """Format the full knowledge graph as compact, LLM-friendly text.

        Compared to the old JSON-based summary, this format:
        - Groups entities by type with inline relationship hints
        - Lists unresolved foreshadows separately
        - Reduces token consumption by ~30-40% vs JSON
        - Makes inter-entity relationships explicit for LLM comprehension

        Args:
            max_entities_per_type: Max entities per type category (default 30).
        """
        entities = self.list_entities()
        relations = self.list_relations()
        foreshadows = self.list_foreshadows()

        if not entities:
            return "（知识库为空）"

        # Build entity lookup: id → name
        id_to_name: dict[str, str] = {e.id: e.name for e in entities}

        # Build reverse index: entity name → list of (relation_type, target_name)
        entity_rels: dict[str, list[tuple[str, str]]] = {}
        for e in entities:
            entity_rels[e.name] = []
        for r in relations:
            from_name = id_to_name.get(r.from_entity, r.from_entity)
            to_name = id_to_name.get(r.to_entity, r.to_entity)
            entity_rels.setdefault(from_name, []).append((r.type.upper(), to_name))

        lines = ["## 知识图谱\n"]

        # Group entities by type
        by_type: dict[str, list] = {}
        for e in entities:
            by_type.setdefault(e.type, []).append(e)

        type_names = {
            "character": "角色", "location": "地点", "item": "物品",
            "skill": "技能/功法", "organization": "组织", "race": "种族",
            "concept": "概念", "event": "事件",
        }

        for etype in sorted(by_type.keys()):
            elist = by_type[etype][:max_entities_per_type]
            label = type_names.get(etype, etype)
            lines.append(f"\n### {label}（{len(elist)}个）")
            for e in elist:
                aliases = f"（别名: {', '.join(e.aliases)}）" if e.aliases else ""
                # Key data fields (first 3, skip empty)
                key_data = []
                for k, v in list(e.data.items())[:3]:
                    if v:
                        key_data.append(f"{k}: {v}")
                data_str = " | ".join(key_data) if key_data else ""
                # Inline relationships
                rels = entity_rels.get(e.name, [])
                rel_str = ""
                if rels:
                    rel_parts = [f"{rt}→{tn}" for rt, tn in rels[:5]]
                    rel_str = f" [关联: {', '.join(rel_parts)}]"
                line = f"- {e.name}{aliases}"
                if data_str:
                    line += f" ({data_str})"
                if rel_str:
                    line += rel_str
                lines.append(line)

        # Relations summary (compact)
        if relations:
            lines.append(f"\n### 关系（{len(relations)}条）")
            for r in relations[:50]:
                fn = id_to_name.get(r.from_entity, r.from_entity)
                tn = id_to_name.get(r.to_entity, r.to_entity)
                lines.append(f"- {fn} --[{r.type.upper()}]--> {tn}")
            if len(relations) > 50:
                lines.append(f"  ... 还有 {len(relations) - 50} 条关系")

        # Foreshadows
        if foreshadows:
            unresolved = [f for f in foreshadows if not f.resolved]
            resolved = [f for f in foreshadows if f.resolved]
            if unresolved:
                lines.append(f"\n### 未回收伏笔（{len(unresolved)}个）")
                for f in unresolved[:10]:
                    lines.append(f"- [未回收] {f.text[:60]}")
            if resolved:
                lines.append(f"\n### 已回收伏笔（{len(resolved)}个）")
                for f in resolved[:5]:
                    lines.append(f"- [已回收] {f.text[:40]} → {f.resolution_text[:40] if f.resolution_text else '...'}")

        return "\n".join(lines)

    # ── P3: Graph insights for Autopilot ──

    # ── Graph insights & Narrative diagnosis (inherited from AnalysisMixin) ──

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


    # ── Narrative diagnosis (inherited from AnalysisMixin) ──



    # ── P4: High-order graph analytics ──

    def _compute_pagerank(self, char_ids: list[str], max_iter: int = 20, damping: float = 0.85) -> dict[str, float]:
        """Compute true iterative PageRank for character nodes.

        Fetches adjacency list from Neo4j and iterates in Python.
        No external dependencies (numpy/scipy) required.
        """
        if not char_ids:
            return {}

        id_set = set(char_ids)
        adj: dict[str, list[str]] = {cid: [] for cid in char_ids}

        rows = self._run("""
            MATCH (c:Entity:Character {project_id: $pid})
            -[:KNOWS|ALLY|FAMILY|ANTAGONIST|ROMANTIC|MASTER_OF|MENTOR_OF|KILLED|SAVED|LOVES]-
            (n:Entity:Character {project_id: $pid})
            RETURN c.id AS src, n.id AS tgt
        """, {"pid": self.project_id})
        for r in rows:
            src, tgt = r["src"], r["tgt"]
            if src in id_set and tgt in id_set and src != tgt:
                adj[src].append(tgt)
                adj[tgt].append(src)

        n = len(char_ids)
        rank = dict.fromkeys(char_ids, 1.0 / n)

        for _ in range(max_iter):
            new_rank = {}
            for cid in char_ids:
                incoming_sum = 0.0
                for neighbor in adj[cid]:
                    out_deg = len(adj[neighbor])
                    if out_deg > 0:
                        incoming_sum += rank[neighbor] / out_deg
                new_rank[cid] = (1 - damping) / n + damping * incoming_sum
            rank = new_rank

        return rank

    def get_character_importance(self) -> list[dict]:
        """Rank characters by composite importance: degree centrality + true PageRank + appearance frequency.

        Returns list sorted by composite_score descending.
        """
        return self._cached("char_importance", self._compute_character_importance)

    def _compute_character_importance(self) -> list[dict]:
        degree_rows = self._run("""
            MATCH (c:Entity:Character {project_id: $pid})
            OPTIONAL MATCH (c)-[r:KNOWS|ALLY|FAMILY|ANTAGONIST|ROMANTIC|MASTER_OF|MENTOR_OF|KILLED|SAVED|LOVES]-(other:Entity:Character)
            RETURN c.id AS id, c.name AS name, count(r) AS degree
        """, {"pid": self.project_id})

        if not degree_rows:
            return []

        char_ids = [r["id"] for r in degree_rows]

        # Use text mention counts from chapter_store (more reliable than timeline events)
        # Timeline INVOLVES edges may be incomplete due to character name matching issues
        appear_map: dict[str, int] = {}
        try:
            from data.json_store import json_store
            mentions_data = json_store.get_character_mentions(self.project_id)
            if mentions_data and mentions_data.get("matrix"):
                for m in mentions_data["matrix"]:
                    appear_map[m.get("charId", "")] = m.get("totalMentions", 0)
        except Exception:
            pass

        # Fallback: if text mentions not available, use timeline event appearances
        if not appear_map:
            appear_rows = self._run("""
                MATCH (t:Timeline {project_id: $pid})-[:INVOLVES|TIMELINE_INVOLVES]->(c:Entity:Character)
                RETURN c.id AS id, count(t) AS appearances
            """, {"pid": self.project_id})
            appear_map = {r["id"]: r["appearances"] for r in appear_rows}

        pagerank = self._compute_pagerank(char_ids)
        max_pr = max(pagerank.values()) if pagerank else 1e-10

        max_degree = max(r["degree"] for r in degree_rows) if degree_rows else 1
        max_appear = max((int(v) for v in appear_map.values()), default=1) if appear_map else 1

        results = []
        for r in degree_rows:
            cid = r["id"]
            deg = int(r["degree"])
            appear = int(appear_map.get(cid, 0))

            deg_norm = (deg / max(max_degree, 1)) * 100
            appear_norm = (appear / max(max_appear, 1)) * 100
            pr_norm = (pagerank.get(cid, 0) / max_pr) * 100

            # Fixed: removed hardcoded baseline (0.20 * 40), weights redistributed
            composite = round(deg_norm * 0.40 + pr_norm * 0.35 + appear_norm * 0.25)

            if composite >= 70:
                role = "主角"
            elif composite >= 45:
                role = "主要配角"
            elif composite >= 25:
                role = "次要配角"
            else:
                role = "背景角色"

            results.append({
                "entity_id": cid,
                "name": r.get("name", ""),
                "composite_score": min(composite, 100),
                "role": role,
                "degree": deg,
                "appearances": appear,
                "pagerank_score": round(pr_norm),
            })

        results.sort(key=lambda x: x["composite_score"], reverse=True)
        return results


    def get_character_communities(self) -> list[dict]:
        """Detect character communities using connected components on character-character graph."""
        return self._cached("char_communities", self._compute_character_communities)

    def _compute_character_communities(self) -> list[dict]:
        rows = self._run("""
            MATCH (c:Entity:Character {project_id: $pid})
            OPTIONAL MATCH path = (c)-[:KNOWS|ALLY|FAMILY|ANTAGONIST|ROMANTIC|MASTER_OF|MENTOR_OF|KILLED|SAVED|LOVES*1..3]-(other:Entity:Character {project_id: $pid})
            WITH c, collect(DISTINCT other.id) + c.id AS component
            WITH c, component, size(component) AS comp_size
            RETURN c.name AS name, c.id AS id, component, comp_size
            ORDER BY comp_size DESC
        """, {"pid": self.project_id})

        if not rows:
            return []

        communities: dict[str, dict] = {}
        assigned: set = set()

        for r in rows:
            if r["id"] in assigned:
                continue
            members = set(r["component"])
            best_community = None
            best_overlap = 0
            for cid, cdata in communities.items():
                overlap = len(members & cdata["member_set"])
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_community = cid

            if best_community and best_overlap >= len(members) * 0.5:
                communities[best_community]["member_set"].update(members)
                communities[best_community]["members"].append(r["name"])
                communities[best_community]["size"] = len(communities[best_community]["member_set"])
            else:
                cid = f"community_{len(communities)+1}"
                communities[cid] = {
                    "id": cid,
                    "members": [r["name"]],
                    "member_set": members,
                    "size": len(members),
                }
            assigned.add(r["id"])

        result = []
        for i, (cid, cdata) in enumerate(sorted(communities.items(), key=lambda x: x[1]["size"], reverse=True)):
            result.append({
                "id": cid,
                "name": f"故事线 {i+1}" if cdata["size"] > 1 else f"孤立角色 {i+1}",
                "members": cdata["members"][:15],
                "size": cdata["size"],
                "is_isolated": cdata["size"] == 1,
            })

        return result


    def get_network_evolution(self) -> dict:
        """Analyze how the relationship network evolves over time.

        Computes cumulative density, new character introduction rate, and dead character detection.
        """
        return self._cached("network_evolution", self._compute_network_evolution)

    def _compute_network_evolution(self) -> dict:
        events = self.list_timeline_events()
        if not events:
            return {"trend": [], "summary": "暂无时间线数据"}

        events.sort(key=lambda e: e.time_order)
        max_order = max(e.time_order for e in events)

        char_appear = self._run("""
            MATCH (t:Timeline {project_id: $pid})-[:INVOLVES|TIMELINE_INVOLVES]->(c:Entity:Character)
            RETURN t.time_order AS time_order, collect(DISTINCT c.name) AS chars
            ORDER BY time_order
        """, {"pid": self.project_id})

        seen_chars: set = set()
        prev_chars: set = set()
        trend = []
        char_lifespan: dict[str, list] = {}

        for row in char_appear:
            order = row["time_order"]
            chars = set(row["chars"])

            for ch in chars:
                if ch not in char_lifespan:
                    char_lifespan[ch] = [order, order]
                else:
                    char_lifespan[ch][1] = order

            new_chars = chars - seen_chars
            disappeared = prev_chars - chars
            seen_chars.update(chars)

            trend.append({
                "time_order": order,
                "active_chars": len(chars),
                "cumulative_chars": len(seen_chars),
                "new_chars": len(new_chars),
                "new_char_names": list(new_chars)[:3],
                "disappeared": len(disappeared),
            })
            prev_chars = chars

        dead_chars = []
        for name, (first, last) in char_lifespan.items():
            if last < max_order - 3:
                dead_chars.append({"name": name, "last_seen": last, "gap": max_order - last})

        total_chars = len(char_lifespan)
        growth_rate = round(total_chars / max(max_order, 1), 1)
        summary = (
            f"共 {total_chars} 个角色，每时间步平均引入 {growth_rate} 个新角色。"
            f"{len(dead_chars)} 个角色已超过3个时间步未出场。"
        )

        return {
            "trend": trend,
            "total_chars": total_chars,
            "growth_rate": growth_rate,
            "dead_characters": dead_chars[:10],
            "summary": summary,
        }


    def get_pacing_analysis(self) -> dict:
        """Analyze story pacing: event density, climax detection, three-act structure."""
        return self._cached("pacing", self._compute_pacing_analysis)

    def _compute_pacing_analysis(self) -> dict:
        events = self.list_timeline_events()
        if not events:
            return {"density": [], "summary": "暂无时间线数据"}

        events.sort(key=lambda e: e.time_order)
        max_order = max(e.time_order for e in events)

        density_map: dict[int, int] = {}
        for e in events:
            density_map[e.time_order] = density_map.get(e.time_order, 0) + 1

        density = []
        for order in range(max_order + 1):
            density.append({"time_order": order, "event_count": density_map.get(order, 0)})

        avg_density = sum(d["event_count"] for d in density) / max(len(density), 1)
        climaxes = [d for d in density if d["event_count"] >= avg_density * 2 and d["event_count"] > 0]
        valleys = [d for d in density if d["event_count"] == 0 and d["time_order"] > 0]

        total_orders = max_order + 1
        act1_end = max(1, total_orders // 4)
        act2_end = max(act1_end + 1, total_orders * 3 // 4)

        act1_events = sum(d["event_count"] for d in density[:act1_end])
        act2_events = sum(d["event_count"] for d in density[act1_end:act2_end])
        act3_events = sum(d["event_count"] for d in density[act2_end:])
        total_events = max(sum(d["event_count"] for d in density), 1)

        acts = [
            {"name": "第一幕", "range": f"T0-T{act1_end-1}", "events": act1_events, "pct": round(act1_events / total_events * 100)},
            {"name": "第二幕", "range": f"T{act1_end}-T{act2_end-1}", "events": act2_events, "pct": round(act2_events / total_events * 100)},
            {"name": "第三幕", "range": f"T{act2_end}-T{max_order}", "events": act3_events, "pct": round(act3_events / total_events * 100)},
        ]

        summary = (
            f"共 {len(events)} 个时间线事件" +
            (f"，发现 {len(climaxes)} 个高潮节点" if climaxes else "，事件分布均匀") +
            (f"，{len(valleys)} 个低谷节点" if valleys else "")
        )

        return {
            "density": density,
            "climaxes": climaxes[:10],
            "valleys": valleys[:10],
            "acts": acts,
            "avg_density": round(avg_density, 1),
            "summary": summary,
        }


    def get_foreshadow_dependency_analysis(self) -> dict:
        """Analyze foreshadow dependencies: chains, resolution cycles, clustering."""
        return self._cached("foreshadow_dep", self._compute_foreshadow_dependency_analysis)

    def _compute_foreshadow_dependency_analysis(self) -> dict:
        fores = self.list_foreshadows()
        if not fores:
            return {"chains": [], "summary": "暂无伏笔数据"}

        unresolved = [f for f in fores if not f.resolved]
        resolved = [f for f in fores if f.resolved]

        chains = []
        dep_rows = self._run("""
            MATCH (f1:Fore {project_id: $pid})-[r:DEPENDS_ON]->(f2:Fore {project_id: $pid})
            RETURN f1.id AS from_id, f1.text AS from_text, f2.id AS to_id, f2.text AS to_text
        """, {"pid": self.project_id})

        for row in dep_rows:
            chains.append({
                "from": {"id": row["from_id"], "text": row["from_text"][:60]},
                "to": {"id": row["to_id"], "text": row["to_text"][:60]},
            })

        total = len(fores)
        resolution_rate = round(len(resolved) / max(total, 1) * 100)

        clusters: dict[str, list] = {}
        for f in unresolved:
            for eid in f.related_entities[:3]:
                clusters.setdefault(eid, []).append({"id": f.id, "text": f.text[:50]})

        top_clusters = sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True)[:5]

        summary = (
            f"共 {total} 个伏笔，回收率 {resolution_rate}%。"
            f"{len(unresolved)} 个待回收，{len(chains)} 条依赖链。"
        )

        return {
            "total": total,
            "unresolved": len(unresolved),
            "resolved": len(resolved),
            "resolution_rate": resolution_rate,
            "chains": chains[:10],
            "clusters": [{"entity_id": eid, "foreshadows": fs[:5]} for eid, fs in top_clusters],
            "summary": summary,
        }


    def get_character_heatmap(self) -> dict:
        """Compute character co-occurrence matrix and triangle detection."""
        return self._cached("char_heatmap", self._compute_character_heatmap)

    def _compute_character_heatmap(self) -> dict:
        co_rows = self._run("""
            MATCH (t:Timeline {project_id: $pid})-[:INVOLVES|TIMELINE_INVOLVES]->(c1:Entity:Character)
            MATCH (t)-[:INVOLVES|TIMELINE_INVOLVES]->(c2:Entity:Character)
            WHERE c1.id < c2.id
            RETURN c1.name AS char_a, c2.name AS char_b, count(t) AS co_count
            ORDER BY co_count DESC
        """, {"pid": self.project_id})

        interactions = []
        for r in co_rows[:30]:
            interactions.append({
                "char_a": r["char_a"],
                "char_b": r["char_b"],
                "co_count": r["co_count"],
            })

        tri_rows = self._run("""
            MATCH (a:Entity:Character {project_id: $pid})
            -[:KNOWS|ALLY|FAMILY|ANTAGONIST|ROMANTIC|MASTER_OF|MENTOR_OF|KILLED|SAVED|LOVES]-
            (b:Entity:Character {project_id: $pid})
            -[:KNOWS|ALLY|FAMILY|ANTAGONIST|ROMANTIC|MASTER_OF|MENTOR_OF|KILLED|SAVED|LOVES]-
            (c:Entity:Character {project_id: $pid})
            WHERE a.id < b.id AND b.id < c.id
            AND EXISTS((a)-[:KNOWS|ALLY|FAMILY|ANTAGONIST|ROMANTIC|MASTER_OF|MENTOR_OF|KILLED|SAVED|LOVES]-(c))
            RETURN a.name AS a, b.name AS b, c.name AS c
        """, {"pid": self.project_id})

        triangles = [{"a": r["a"], "b": r["b"], "c": r["c"]} for r in tri_rows[:15]]

        summary = (
            f"发现 {len(tri_rows)} 个三角关系。" +
            (f"互动最频繁：{interactions[0]['char_a']}↔{interactions[0]['char_b']}（{interactions[0]['co_count']}次）" if interactions else "")
        )

        return {
            "interactions": interactions,
            "triangles": triangles,
            "triangle_count": len(tri_rows),
            "total_pairs": len(interactions),
            "summary": summary,
        }

    # ── P4-ext: Auto-complete missing relations after extraction ──

    def auto_complete_relations(self) -> dict:
        """Auto-complete missing relations using graph reasoning.

        Direction-aware strategies:
        1a. Symmetry: for symmetric types (KNOWS, ALLY, etc.), add same-type reverse.
        1b. Paired: for paired types (PARENT_OF→CHILD_OF), add paired reverse.
        1c. Unidirectional cleanup: remove incorrectly created reverse edges for
            unidirectional types (LOCATED_IN, OWNS, etc.).
        2. Co-occurrence: characters in same timeline event >= 3 times get KNOWS.
        3. Anomaly detection: flag characters with abnormally low degree.
        4. Transitive closure: for transitive types (FAMILY, ALLY, FRIEND).
        5. LLM-driven suggestion for high-co-occurrence unlinked pairs.
        6. Structural equivalence (1-hop): shared non-character entity → KNOWS.
        7. Multi-hop structural equivalence: 2+ shared contexts → KNOWS.
        8. Jaccard link prediction: >50% neighbor overlap → KNOWS.
        """
        from .graph_schema import get_paired_reverse, get_symmetric_types, is_unidirectional

        sym_types = get_symmetric_types()
        stats = {"symmetry_added": 0, "paired_added": 0, "unidirectional_cleaned": 0,
                 "cooccur_added": 0, "transitive_added": 0,
                 "structural_added": 0, "multihop_added": 0, "jaccard_added": 0,
                 "llm_suggested": 0, "anomalies": []}

        # 1a. Symmetry completion (data-driven: only for symmetric types)
        for rtype in sym_types:
            rows = self._run(f"""
                MATCH (a:Entity:Character {{project_id: $pid}})
                -[:{rtype}]->(b:Entity:Character {{project_id: $pid}})
                WHERE NOT (b)-[:{rtype}]->(a)
                RETURN a.id AS aid, b.id AS bid
            """, {"pid": self.project_id})
            for row in rows:
                self._run(f"""
                    MATCH (a:Entity {{id: $aid, project_id: $pid}})
                    MATCH (b:Entity {{id: $bid, project_id: $pid}})
                    MERGE (b)-[:{rtype}]->(a)
                """, {"aid": row["aid"], "bid": row["bid"], "pid": self.project_id})
                stats["symmetry_added"] += 1

        # 1b. Paired completion (A PARENT_OF B → add B CHILD_OF A)
        paired_types = [rt for rt in self._run("""
            MATCH ()-[r]->()
            WHERE r.project_id = $pid
            RETURN DISTINCT type(r) AS rt
        """, {"pid": self.project_id}) if get_paired_reverse(rt["rt"])]
        for p in paired_types:
            rtype = p["rt"]
            reverse_type = get_paired_reverse(rtype)
            if not reverse_type:
                continue
            rows = self._run(f"""
                MATCH (a:Entity {{project_id: $pid}})-[r:{rtype}]->(b:Entity {{project_id: $pid}})
                WHERE NOT (b)-[:{reverse_type}]->(a)
                AND NOT (b)-[:{reverse_type}]->(a)
                RETURN DISTINCT a.id AS aid, b.id AS bid
            """, {"pid": self.project_id})
            for row in rows:
                self._run(f"""
                    MATCH (a:Entity {{id: $aid, project_id: $pid}})
                    MATCH (b:Entity {{id: $bid, project_id: $pid}})
                    MERGE (b)-[:{reverse_type}]->(a)
                """, {"aid": row["bid"], "bid": row["aid"], "pid": self.project_id})
                stats["paired_added"] += 1
                logger.info("Paired completion: %s -[%s]- %s (from %s)",
                            row["bid"], reverse_type, row["aid"], rtype)

        # 1c. Unidirectional cleanup: remove reverse edges for unidirectional types
        # e.g. if A LOCATED_IN B and B LOCATED_IN A, remove the incorrect one
        uni_rows = self._run("""
            MATCH (a:Entity {project_id: $pid})-[r1]->(b:Entity {project_id: $pid})-[r2]->(a)
            WHERE type(r1) = type(r2)
            AND a.id < b.id
            RETURN DISTINCT type(r1) AS rt, a.id AS aid, b.id AS bid,
                   a.name AS aname, b.name AS bname
        """, {"pid": self.project_id})
        for row in uni_rows:
            rt = row["rt"]
            if not is_unidirectional(rt):
                continue
            # Remove B→A (keep A→B, since A was the one that had the edge first)
            # Use name length heuristic: keep edge from longer name (more specific = child)
            if len(row["aname"]) >= len(row["bname"]):
                # A is more specific, keep A→B, remove B→A
                self._run(f"""
                    MATCH (b:Entity {{id: $bid, project_id: $pid}})-[r:{rt}]->(a:Entity {{id: $aid, project_id: $pid}})
                    DELETE r
                """, {"aid": row["aid"], "bid": row["bid"], "pid": self.project_id})
            else:
                # B is more specific, keep B→A, remove A→B
                self._run(f"""
                    MATCH (a:Entity {{id: $aid, project_id: $pid}})-[r:{rt}]->(b:Entity {{id: $bid, project_id: $pid}})
                    DELETE r
                """, {"aid": row["aid"], "bid": row["bid"], "pid": self.project_id})
            stats["unidirectional_cleaned"] += 1
            logger.info("Unidirectional cleanup: removed reverse %s between %s and %s",
                        rt, row["aname"], row["bname"])

        # 2. Co-occurrence inference
        co_rows = self._run("""
            MATCH (t:Timeline {project_id: $pid})-[:INVOLVES|TIMELINE_INVOLVES]->(a:Entity:Character)
            MATCH (t)-[:INVOLVES|TIMELINE_INVOLVES]->(b:Entity:Character)
            WHERE a.id < b.id
            AND NOT (a)-[:KNOWS|ALLY|FAMILY|ANTAGONIST|ROMANTIC|MASTER_OF|MENTOR_OF|KILLED|SAVED|LOVES]-(b)
            WITH a, b, count(t) AS co_count
            WHERE co_count >= 3
            RETURN a.id AS aid, b.id AS bid
        """, {"pid": self.project_id})
        for row in co_rows:
            self._run("""
                MATCH (a:Entity {id: $aid, project_id: $pid})
                MATCH (b:Entity {id: $bid, project_id: $pid})
                MERGE (a)-[:KNOWS]->(b)
                MERGE (b)-[:KNOWS]->(a)
            """, {"aid": row["aid"], "bid": row["bid"], "pid": self.project_id})
            stats["cooccur_added"] += 1

        # 3. Anomaly detection: low-degree characters with high co-occurrence
        anom_rows = self._run("""
            MATCH (c:Entity:Character {project_id: $pid})
            OPTIONAL MATCH (c)-[r:KNOWS|ALLY|FAMILY|ANTAGONIST|ROMANTIC|MASTER_OF|MENTOR_OF|KILLED|SAVED|LOVES]-(other:Entity:Character)
            WITH c, count(r) AS degree
            OPTIONAL MATCH (t:Timeline {project_id: $pid})-[:INVOLVES|TIMELINE_INVOLVES]->(c)
            WITH c, degree, count(t) AS appears
            WHERE appears >= 5 AND degree <= 2
            RETURN c.name AS name, degree, appears
            ORDER BY appears DESC
        """, {"pid": self.project_id})
        stats["anomalies"] = [
            {"name": r["name"], "degree": r["degree"], "appearances": r["appears"]}
            for r in anom_rows[:10]
        ]

        # 4. Transitive closure for FAMILY, ALLY, and FRIEND
        # If A→FAMILY→B and B→FAMILY→C, but A→FAMILY→C missing → add it
        transitive_types = ["FAMILY", "ALLY", "FRIEND"]
        for rtype in transitive_types:
            tri_rows = self._run(f"""
                MATCH (a:Entity:Character {{project_id: $pid}})
                -[:{rtype}]->(b:Entity:Character {{project_id: $pid}})
                -[:{rtype}]->(c:Entity:Character {{project_id: $pid}})
                WHERE a.id <> c.id
                AND NOT (a)-[:{rtype}]-(c)
                RETURN DISTINCT a.id AS aid, c.id AS cid, a.name AS aname, c.name AS cname
            """, {"pid": self.project_id})
            for row in tri_rows:
                self._run(f"""
                    MATCH (a:Entity {{id: $aid, project_id: $pid}})
                    MATCH (c:Entity {{id: $cid, project_id: $pid}})
                    MERGE (a)-[:{rtype}]->(c)
                    MERGE (c)-[:{rtype}]->(a)
                """, {"aid": row["aid"], "cid": row["cid"], "pid": self.project_id})
                stats["transitive_added"] += 1

        # 6. Structural equivalence: two characters sharing the same non-character entity
        # Pattern: A → [ANY_REL] → Org ← [ANY_REL] ← B, where Org is not a Character
        # Fully dynamic — discovers all relationship types from the graph, no hardcoding.
        # Examples: mercenary squad, adventurer guild, star fleet, cultivation sect, etc.

        # Step 1: discover all relationship types that connect Character → non-Character
        type_rows = self._run("""
            MATCH (c:Entity:Character {project_id: $pid})-[r]->(org:Entity {project_id: $pid})
            WHERE NOT org:Character
            WITH type(r) AS rel_type, count(DISTINCT org) AS org_count
            WHERE org_count >= 1
            RETURN rel_type, org_count
            ORDER BY org_count DESC
        """, {"pid": self.project_id})

        discovered_types = [row["rel_type"] for row in type_rows]

        if discovered_types:
            # Step 2: for each discovered type, find pairs of characters sharing
            # the same target entity and infer KNOWS (safe universal default)
            for rel_type in discovered_types:
                s_rows = self._run(f"""
                    MATCH (a:Entity:Character {{project_id: $pid}})
                    -[:{rel_type}]->(org:Entity {{project_id: $pid}})
                    <-[:{rel_type}]-(b:Entity:Character {{project_id: $pid}})
                    WHERE a.id < b.id
                    AND NOT (a)-[:KNOWS|FRIEND|ALLY|FAMILY|ANTAGONIST]-(b)
                    RETURN DISTINCT a.id AS aid, b.id AS bid, a.name AS aname, b.name AS bname,
                           org.name AS org_name, org.entity_type AS org_type
                    LIMIT 50
                """, {"pid": self.project_id})
                for row in s_rows:
                    self._run("""
                        MATCH (a:Entity {id: $aid, project_id: $pid})
                        MATCH (b:Entity {id: $bid, project_id: $pid})
                        MERGE (a)-[:KNOWS]->(b)
                        MERGE (b)-[:KNOWS]->(a)
                    """, {"aid": row["aid"], "bid": row["bid"], "pid": self.project_id})
                    stats["structural_added"] += 1
                    logger.info(
                        "Structural inference: %s -[KNOWS]- %s (%s via %s: %s)",
                        row["aname"], row["bname"],
                        row.get("org_type", "?"), rel_type, row.get("org_name", "?")
                    )

        # 7. Multi-hop structural equivalence: characters sharing 2+ non-character entities
        # If A and B both belong to House X AND both are on Team Y, they're more likely
        # to know each other than if they just share one context.
        # This catches multi-dimensional relationships (same school + same house + same team).
        multi_rows = self._run("""
            MATCH (a:Entity:Character {project_id: $pid})-[r1]->(ctx:Entity {project_id: $pid})
            WHERE NOT ctx:Character
            MATCH (b:Entity:Character {project_id: $pid})-[r2]->(ctx)
            WHERE a.id < b.id
            WITH a, b, count(DISTINCT ctx) AS shared_contexts, collect(DISTINCT ctx.name) AS ctx_names
            WHERE shared_contexts >= 2
            AND NOT (a)-[:KNOWS|FRIEND|ALLY|FAMILY|ANTAGONIST]-(b)
            RETURN DISTINCT a.id AS aid, b.id AS bid, a.name AS aname, b.name AS bname,
                   shared_contexts, ctx_names
            ORDER BY shared_contexts DESC
            LIMIT 30
        """, {"pid": self.project_id})
        for row in multi_rows:
            self._run("""
                MATCH (a:Entity {id: $aid, project_id: $pid})
                MATCH (b:Entity {id: $bid, project_id: $pid})
                MERGE (a)-[:KNOWS]->(b)
                MERGE (b)-[:KNOWS]->(a)
            """, {"aid": row["aid"], "bid": row["bid"], "pid": self.project_id})
            stats["multihop_added"] += 1
            logger.info(
                "Multi-hop inference: %s -[KNOWS]- %s (%d shared contexts: %s)",
                row["aname"], row["bname"], row["shared_contexts"],
                ", ".join(row["ctx_names"][:3])
            )

        # 8. Jaccard link prediction: characters with >50% neighbor overlap
        # Computes Jaccard similarity = |A∩B| / |A∪B| on character neighborhoods.
        # High overlap → likely relationship even without direct edge.
        jaccard_rows = self._run("""
            MATCH (a:Entity:Character {project_id: $pid})-[r1]->(n1:Entity {project_id: $pid})
            WHERE NOT n1:Character
            WITH a, collect(DISTINCT n1.id) AS a_neighbors
            MATCH (b:Entity:Character {project_id: $pid})-[r2]->(n2:Entity {project_id: $pid})
            WHERE NOT n2:Character AND a.id < b.id
            WITH a, a_neighbors, b, collect(DISTINCT n2.id) AS b_neighbors
            WITH a, b,
                size([x IN a_neighbors WHERE x IN b_neighbors]) AS intersection,
                size(a_neighbors) + size(b_neighbors) - size([x IN a_neighbors WHERE x IN b_neighbors]) AS union_size
            WITH a, b, intersection, union_size,
                CASE WHEN union_size > 0 THEN toFloat(intersection) / union_size ELSE 0 END AS jaccard
            WHERE jaccard >= 0.5
            AND NOT (a)-[:KNOWS|FRIEND|ALLY|FAMILY|ANTAGONIST]-(b)
            RETURN a.id AS aid, b.id AS bid, a.name AS aname, b.name AS bname, jaccard
            ORDER BY jaccard DESC
            LIMIT 20
        """, {"pid": self.project_id})
        for row in jaccard_rows:
            self._run("""
                MATCH (a:Entity {id: $aid, project_id: $pid})
                MATCH (b:Entity {id: $bid, project_id: $pid})
                MERGE (a)-[:KNOWS]->(b)
                MERGE (b)-[:KNOWS]->(a)
            """, {"aid": row["aid"], "bid": row["bid"], "pid": self.project_id})
            stats["jaccard_added"] += 1
            logger.info(
                "Jaccard prediction: %s -[KNOWS]- %s (similarity=%.2f)",
                row["aname"], row["bname"], row["jaccard"]
            )

        # 5. LLM-driven suggestion for high-co-occurrence unlinked pairs
        # Build exclusion pattern dynamically from active schema to avoid Neo4j warnings
        # about non-existent relationship types.
        from .graph_schema import get_active_relationship_types as _get_rels
        _structural_rels = {"INVOLVES", "HAS_PHASE", "DEPENDS_ON", "GOVERNS",
                            "BEFORE", "AFTER", "FORESHADOWS", "RESOLVES", "CAUSES",
                            "OCCURRED_AT", "LOCATED_IN", "LOCATED_AT", "PARTICIPATES_IN"}
        _semantic_rels = [r for r in _get_rels() if r not in _structural_rels]
        if _semantic_rels:
            _exclude_pattern = "|".join(_semantic_rels)
        else:
            _exclude_pattern = "KNOWS|ALLY|FAMILY|ANTAGONIST|ROMANTIC|FRIEND"
        llm_rows = self._run(f"""
            MATCH (t:Timeline {{project_id: $pid}})-[:INVOLVES]->(a:Entity:Character)
            MATCH (t)-[:INVOLVES]->(b:Entity:Character)
            WHERE a.id < b.id
            AND NOT (a)-[:{_exclude_pattern}]-(b)
            WITH a, b, count(t) AS co_count
            WHERE co_count >= 5
            RETURN a.name AS aname, a.id AS aid, b.name AS bname, b.id AS bid, co_count
            ORDER BY co_count DESC
            LIMIT 10
        """, {"pid": self.project_id})

        if llm_rows:
            llm_stats = self._llm_suggest_relations(llm_rows)
            stats["llm_suggested"] = llm_stats.get("added", 0)

        if stats["symmetry_added"] or stats["paired_added"] or stats["unidirectional_cleaned"] or stats["cooccur_added"] or stats["transitive_added"] or stats["structural_added"] or stats["multihop_added"] or stats["jaccard_added"] or stats["llm_suggested"]:
            self._invalidate_cache(self.project_id)
        return stats

    def _llm_suggest_relations(self, candidate_pairs: list) -> dict:
        """Use LLM to suggest relationship types for unlinked but co-occurring character pairs.

        Args:
            candidate_pairs: list of dicts with keys: aname, aid, bname, bid, co_count

        Returns:
            dict with "added" count of new relations created.
        """
        if not candidate_pairs:
            return {"added": 0}

        import json as _json

        pair_lines = []
        for i, p in enumerate(candidate_pairs):
            pair_lines.append(
                f"{i+1}. {p['aname']} ↔ {p['bname']}（同场出现{p['co_count']}次，目前无直接关系）"
            )

        try:
            from .graph_schema import get_active_relationship_types
            all_rels = get_active_relationship_types()
            structural = {"INVOLVES", "HAS_PHASE", "DEPENDS_ON", "GOVERNS",
                          "BEFORE", "AFTER", "FORESHADOWS", "RESOLVES", "CAUSES"}
            available = [r for r in all_rels if r not in structural]
            rel_list = ", ".join(available)
        except Exception:
            rel_list = "KNOWS, ALLY, ANTAGONIST, FAMILY, ROMANTIC, FRIEND, MENTOR_OF, MASTER_OF, BELONGS_TO_HOUSE, BELONGS_TO_TEAM, TEAM_MEMBER, TEAM_CAPTAIN, BELONGS_TO_SECT, BELONGS_TO_FACTION"

        prompt = f"""以下角色对在同一场景中多次出现，但目前没有直接关系。请根据常识判断他们最可能的关系类型。

候选角色对：
{chr(10).join(pair_lines)}

可用关系类型: {rel_list}

输出JSON格式：
{{
  "suggestions": [
    {{"pair_index": 1, "from": "角色A", "to": "角色B", "type": "关系类型", "reason": "理由（1句话）"}}
  ]
}}

规则：
- 只输出确有把握的关系，不确定的跳过
- 如果两人只是同场出现但无特殊关系，输出 type="KNOWS"
- 每条建议必须给出简短理由"""

        try:
            from .llm_client import chat as llm_chat
            from .utils import extract_json_from_response
            response = llm_chat(prompt, system="你是小说角色关系分析专家。", temperature=0.2, task="extraction")
            if not response:
                return {"added": 0}

            j = extract_json_from_response(response)
            data = _json.loads(j.strip())
            suggestions = data.get("suggestions", [])

            added = 0
            # Use active schema types instead of hardcoded list to support
            # custom ontologies per book.
            from .graph_schema import get_active_relationship_types as _get_rels
            valid_types = set(_get_rels())
            for s in suggestions:
                idx = s.get("pair_index", 0) - 1
                if idx < 0 or idx >= len(candidate_pairs):
                    continue
                pair = candidate_pairs[idx]
                rtype = s.get("type", "KNOWS").upper()
                if rtype not in valid_types:
                    rtype = "KNOWS"

                self._run(f"""
                    MATCH (a:Entity {{id: $aid, project_id: $pid}})
                    MATCH (b:Entity {{id: $bid, project_id: $pid}})
                    MERGE (a)-[:{rtype}]->(b)
                    MERGE (b)-[:{rtype}]->(a)
                """, {"aid": pair["aid"], "bid": pair["bid"], "pid": self.project_id})
                added += 1
                logger.info("LLM suggested: %s -[%s]- %s (%s)",
                            pair["aname"], rtype, pair["bname"], s.get("reason", ""))

            return {"added": added}
        except Exception as e:
            logger.warning("LLM relation suggestion failed: %s", e)
            return {"added": 0}

    # ── P3: Community detection via simplified label propagation ──

    def detect_communities(self) -> dict:
        """Detect character communities using simplified label propagation.

        Assigns each character to a community based on its neighborhood.
        Characters in the same community but without direct edges are flagged
        as potential missing relationships.

        Returns stats and community assignments.
        """
        # Initialize: assign each character its own ID as community
        self._run("""
            MATCH (c:Entity:Character {project_id: $pid})
            WHERE c.community IS NULL
            SET c.community = c.id
        """, {"pid": self.project_id})

        # 3 rounds of label propagation
        for _round in range(3):
            self._run("""
                MATCH (c:Entity:Character {project_id: $pid})
                -[r:KNOWS|ALLY|FAMILY|BELONGS_TO|BELONGS_TO_HOUSE|BELONGS_TO_TEAM|BELONGS_TO_SECT|TEAM_MEMBER|FRIEND]-
                (neighbor:Entity:Character {project_id: $pid})
                WITH c, neighbor.community AS n_comm, count(*) AS cnt
                ORDER BY cnt DESC
                WITH c, head(collect(n_comm)) AS new_comm
                WHERE new_comm IS NOT NULL AND new_comm <> c.community
                SET c.community = new_comm
            """, {"pid": self.project_id})

        # Collect community assignments
        comm_rows = self._run("""
            MATCH (c:Entity:Character {project_id: $pid})
            RETURN c.community AS community, c.id AS cid, c.name AS name
            ORDER BY community
        """, {"pid": self.project_id})

        communities: dict[str, list] = {}
        for r in comm_rows:
            comm = r["community"] or r["cid"]
            communities.setdefault(comm, []).append({
                "id": r["cid"], "name": r["name"]
            })

        # Find intra-community pairs without direct edges
        intra_missing = []
        for comm_id, members in communities.items():
            if len(members) < 2 or len(members) > 15:
                continue
            for i, a in enumerate(members):
                for b in members[i+1:]:
                    has_edge = self._run_single("""
                        MATCH (a:Entity {id: $aid, project_id: $pid})-[r]-
                        (b:Entity {id: $bid, project_id: $pid})
                        RETURN count(r) AS cnt
                    """, {"aid": a["id"], "bid": b["id"], "pid": self.project_id})
                    if has_edge and has_edge["cnt"] == 0:
                        intra_missing.append({
                            "community": comm_id,
                            "char_a": a["name"], "char_b": b["name"],
                            "aid": a["id"], "bid": b["id"],
                        })

        return {
            "community_count": len(communities),
            "communities": {
                k: [m["name"] for m in v]
                for k, v in communities.items()
                if 2 <= len(v) <= 15
            },
            "intra_community_missing": intra_missing[:20],
        }

    # ── P3: Narrative arc aggregation ──

    def aggregate_narrative_arcs(self) -> dict:
        """Detect and label multi-event narrative arcs in the timeline.

        An arc is a sequence of timeline events that:
        - Share the same key characters (at least 1 common)
        - Are within 3 time_order units of each other
        - Span at least 2 events

        Arcs are labeled with a generated arc_id on the matching events.

        Returns stats about arcs found.
        """
        # Find pairs of events sharing characters and close in time
        arc_rows = self._run("""
            MATCH (t1:Timeline {project_id: $pid})-[:INVOLVES]->(c:Entity:Character)
            <-[:INVOLVES]-(t2:Timeline {project_id: $pid})
            WHERE t1.time_order < t2.time_order
            AND t2.time_order - t1.time_order <= 3
            WITH t1, t2, count(DISTINCT c) AS shared_chars,
                 collect(DISTINCT c.name) AS char_names
            WHERE shared_chars >= 1
            RETURN t1.id AS t1_id, t1.label AS t1_label, t1.time_order AS t1_order,
                   t2.id AS t2_id, t2.label AS t2_label, t2.time_order AS t2_order,
                   shared_chars, char_names
            ORDER BY t1.time_order
        """, {"pid": self.project_id})

        if not arc_rows:
            return {"arcs_found": 0, "events_labeled": 0}

        # Group events into arcs using union-find approach
        # Events linked by shared characters and close time form an arc
        event_to_arc: dict[str, str] = {}
        arc_counter = 0

        for row in arc_rows:
            t1_id = row["t1_id"]
            t2_id = row["t2_id"]
            arc1 = event_to_arc.get(t1_id)
            arc2 = event_to_arc.get(t2_id)

            if arc1 and arc2:
                if arc1 != arc2:
                    # Merge arcs: remap all arc2 → arc1
                    for eid, aid in list(event_to_arc.items()):
                        if aid == arc2:
                            event_to_arc[eid] = arc1
            elif arc1:
                event_to_arc[t2_id] = arc1
            elif arc2:
                event_to_arc[t1_id] = arc2
            else:
                arc_counter += 1
                new_arc = f"arc_{arc_counter}"
                event_to_arc[t1_id] = new_arc
                event_to_arc[t2_id] = new_arc

        # Only keep arcs with 2+ events
        arc_sizes: dict[str, int] = {}
        for arc_id in event_to_arc.values():
            arc_sizes[arc_id] = arc_sizes.get(arc_id, 0) + 1

        valid_arcs = {aid for aid, size in arc_sizes.items() if size >= 2}

        # Set arc_id on timeline events
        labeled = 0
        for event_id, arc_id in event_to_arc.items():
            if arc_id in valid_arcs:
                self._run("""
                    MATCH (t:Timeline {id: $tid, project_id: $pid})
                    SET t.arc_id = $arc
                """, {"tid": event_id, "arc": arc_id, "pid": self.project_id})
                labeled += 1

        self._invalidate_cache(self.project_id)

        return {
            "arcs_found": len(valid_arcs),
            "events_labeled": labeled,
            "arc_details": [
                {"arc_id": aid, "event_count": size}
                for aid, size in arc_sizes.items()
                if aid in valid_arcs
            ],
        }


    # ── P5: Extended graph analytics (multi-node-type + advanced algorithms) ──

    def get_location_importance(self) -> list[dict]:
        """Rank locations by composite importance: degree + event count + character visits."""
        return self._cached("loc_importance", self._compute_location_importance)

    def _compute_location_importance(self) -> list[dict]:
        degree_rows = self._run("""
            MATCH (l:Entity:Location {project_id: $pid})
            OPTIONAL MATCH (l)-[r]-(other:Entity {project_id: $pid})
            RETURN l.id AS id, l.name AS name, count(r) AS degree
        """, {"pid": self.project_id})

        if not degree_rows:
            return []

        event_rows = self._run("""
            MATCH (t:Timeline {project_id: $pid})-[:INVOLVES|TIMELINE_INVOLVES]->(l:Entity:Location {project_id: $pid})
            RETURN l.id AS id, count(t) AS event_count
        """, {"pid": self.project_id})
        event_map = {r["id"]: r["event_count"] for r in event_rows}

        visit_rows = self._run("""
            MATCH (c:Entity:Character {project_id: $pid})-[r:LOCATED_AT|BELONGS_TO]->(l:Entity:Location {project_id: $pid})
            RETURN l.id AS id, count(DISTINCT c) AS char_visits
        """, {"pid": self.project_id})
        visit_map = {r["id"]: r["char_visits"] for r in visit_rows}

        max_degree = max((r["degree"] for r in degree_rows), default=1)
        max_events = max((int(v) for v in event_map.values()), default=1) if event_map else 1
        max_visits = max((int(v) for v in visit_map.values()), default=1) if visit_map else 1

        results = []
        for r in degree_rows:
            lid = r["id"]
            deg = r["degree"]
            events = event_map.get(lid, 0)
            visits = visit_map.get(lid, 0)

            deg_norm = (deg / max(max_degree, 1)) * 100
            event_norm = (events / max(max_events, 1)) * 100
            visit_norm = (visits / max(max_visits, 1)) * 100

            composite = round(deg_norm * 0.30 + event_norm * 0.40 + visit_norm * 0.30)

            if composite >= 70:
                role = "核心地点"
            elif composite >= 45:
                role = "重要地点"
            elif composite >= 25:
                role = "次要地点"
            else:
                role = "边缘地点"

            results.append({
                "entity_id": lid,
                "name": r.get("name", ""),
                "composite_score": min(composite, 100),
                "role": role,
                "degree": deg,
                "event_count": events,
                "character_visits": visits,
            })

        results.sort(key=lambda x: x["composite_score"], reverse=True)
        return results

    def get_organization_importance(self) -> list[dict]:
        """Rank organizations by composite importance: members + events + influence."""
        return self._cached("org_importance", self._compute_organization_importance)

    def _compute_organization_importance(self) -> list[dict]:
        degree_rows = self._run("""
            MATCH (o:Entity:Organization {project_id: $pid})
            OPTIONAL MATCH (o)-[r]-(other:Entity {project_id: $pid})
            RETURN o.id AS id, o.name AS name, count(r) AS degree
        """, {"pid": self.project_id})

        if not degree_rows:
            return []

        member_rows = self._run("""
            MATCH (c:Entity:Character {project_id: $pid})-[r:BELONGS_TO|OWNS|MASTER_OF]->(o:Entity:Organization {project_id: $pid})
            RETURN o.id AS id, count(DISTINCT c) AS member_count
        """, {"pid": self.project_id})
        member_map = {r["id"]: r["member_count"] for r in member_rows}

        event_rows = self._run("""
            MATCH (t:Timeline {project_id: $pid})-[:INVOLVES|TIMELINE_INVOLVES]->(o:Entity:Organization {project_id: $pid})
            RETURN o.id AS id, count(t) AS event_count
        """, {"pid": self.project_id})
        event_map = {r["id"]: r["event_count"] for r in event_rows}

        max_degree = max((r["degree"] for r in degree_rows), default=1)
        max_members = max((int(v) for v in member_map.values()), default=1) if member_map else 1
        max_events = max((int(v) for v in event_map.values()), default=1) if event_map else 1

        results = []
        for r in degree_rows:
            oid = r["id"]
            deg = r["degree"]
            members = member_map.get(oid, 0)
            events = event_map.get(oid, 0)

            deg_norm = (deg / max(max_degree, 1)) * 100
            member_norm = (members / max(max_members, 1)) * 100
            event_norm = (events / max(max_events, 1)) * 100

            composite = round(deg_norm * 0.25 + member_norm * 0.45 + event_norm * 0.30)

            if composite >= 70:
                role = "核心势力"
            elif composite >= 45:
                role = "重要势力"
            elif composite >= 25:
                role = "次要势力"
            else:
                role = "边缘势力"

            results.append({
                "entity_id": oid,
                "name": r.get("name", ""),
                "composite_score": min(composite, 100),
                "role": role,
                "degree": deg,
                "member_count": members,
                "event_count": events,
            })

        results.sort(key=lambda x: x["composite_score"], reverse=True)
        return results

    def get_clustering_coefficient(self) -> list[dict]:
        """Compute local clustering coefficient for each character.

        Clustering coefficient = fraction of a character's neighbors
        that are also connected to each other. High = tight-knit group.
        """
        return self._cached("clustering", self._compute_clustering_coefficient)

    def _compute_clustering_coefficient(self) -> list[dict]:
        rows = self._run("""
            MATCH (c:Entity:Character {project_id: $pid})
            -[:KNOWS|ALLY|FAMILY|ANTAGONIST|ROMANTIC|MASTER_OF|MENTOR_OF|KILLED|SAVED|LOVES]-
            (n:Entity:Character {project_id: $pid})
            WITH c, collect(DISTINCT n.id) AS neighbors, count(DISTINCT n) AS neighbor_count
            WHERE neighbor_count >= 2
            RETURN c.id AS id, c.name AS name, neighbors, neighbor_count
        """, {"pid": self.project_id})

        if not rows:
            return []

        results = []
        for r in rows:
            neighbors = r["neighbors"]
            n_count = r["neighbor_count"]
            max_edges = n_count * (n_count - 1) / 2
            if max_edges == 0:
                continue

            # Count edges between neighbors
            edge_count = 0
            for i, a_id in enumerate(neighbors):
                for b_id in neighbors[i+1:]:
                    check = self._run_single("""
                        MATCH (a:Entity {id: $aid, project_id: $pid})-[r]-
                        (b:Entity {id: $bid, project_id: $pid})
                        RETURN count(r) AS cnt
                    """, {"aid": a_id, "bid": b_id, "pid": self.project_id})
                    if check and check.get("cnt", 0) > 0:
                        edge_count += 1

            cc = round(edge_count / max_edges, 3)
            results.append({
                "entity_id": r["id"],
                "name": r.get("name", ""),
                "clustering_coefficient": cc,
                "neighbor_count": n_count,
                "edges_among_neighbors": edge_count,
            })

        results.sort(key=lambda x: x["clustering_coefficient"], reverse=True)
        return results

    def get_event_causal_chain(self) -> dict:
        """Build a DAG of timeline events from CAUSES/BEFORE/AFTER edges.

        Performs topological sort and finds the critical path
        (longest chain of causally-linked events) — the 'story spine'.
        """
        return self._cached("causal_chain", self._compute_event_causal_chain)

    def _compute_event_causal_chain(self) -> dict:
        events = self.list_timeline_events()
        if not events:
            return {"critical_path": [], "total_events": 0, "summary": "暂无时间线数据"}

        events.sort(key=lambda e: e.time_order)
        event_map = {e.id: e for e in events}

        # Fetch causal edges
        edge_rows = self._run("""
            MATCH (t1:Timeline {project_id: $pid})-[r:CAUSES|BEFORE]->(t2:Timeline {project_id: $pid})
            RETURN t1.id AS from_id, t2.id AS to_id, type(r) AS rel_type
        """, {"pid": self.project_id})

        # Build adjacency (DAG)
        adj: dict[str, list[str]] = {e.id: [] for e in events}
        in_degree: dict[str, int] = {e.id: 0 for e in events}
        for row in edge_rows:
            src, tgt = row["from_id"], row["to_id"]
            if src in event_map and tgt in event_map:
                adj[src].append(tgt)
                in_degree[tgt] = in_degree.get(tgt, 0) + 1

        # Topological sort (Kahn's algorithm)
        queue = [eid for eid in in_degree if in_degree[eid] == 0]
        topo_order = []
        in_deg_copy = dict(in_degree)

        while queue:
            node = queue.pop(0)
            topo_order.append(node)
            for neighbor in adj[node]:
                in_deg_copy[neighbor] -= 1
                if in_deg_copy[neighbor] == 0:
                    queue.append(neighbor)

        # Find critical path (longest path in DAG)
        dist = dict.fromkeys(event_map, 0)
        parent = dict.fromkeys(event_map)

        for eid in topo_order:
            for neighbor in adj[eid]:
                if dist[eid] + 1 > dist[neighbor]:
                    dist[neighbor] = dist[eid] + 1
                    parent[neighbor] = eid

        # Reconstruct critical path
        end_node = max(dist, key=lambda x: dist[x]) if dist else None
        critical_path = []
        node = end_node
        while node is not None:
            critical_path.append(node)
            node = parent[node]
        critical_path.reverse()

        critical_path_details = [
            {
                "id": eid,
                "label": event_map[eid].label,
                "time_order": event_map[eid].time_order,
                "chapter_ref": event_map[eid].chapter_ref,
            }
            for eid in critical_path if eid in event_map
        ]

        total_edges = len(edge_rows)
        summary = (
            f"共 {len(events)} 个时间线事件，{total_edges} 条因果边。"
            f"关键路径长度 {len(critical_path)}（占全部事件的 {round(len(critical_path) / max(len(events), 1) * 100)}%）。"
        )

        return {
            "critical_path": critical_path_details,
            "critical_path_length": len(critical_path),
            "total_events": len(events),
            "total_causal_edges": total_edges,
            "topo_order": topo_order,
            "summary": summary,
        }

    def get_link_prediction(self, top_n: int = 20) -> list[dict]:
        """Predict missing character relationships using Adamic-Adar and Jaccard similarity.

        For each pair of characters without a direct edge, computes:
        - Common neighbors count
        - Adamic-Adar index: sum(1/log(degree + 1) for each common neighbor)
        - Jaccard coefficient: common / union
        Returns top N pairs sorted by Adamic-Adar score.
        """
        cache_key = f"link_pred:{top_n}"
        return self._cached(cache_key, lambda: self._compute_link_prediction(top_n))

    def _compute_link_prediction(self, top_n: int = 20) -> list[dict]:
        import math

        chars = self.list_entities(entity_type="character")
        if len(chars) < 2:
            return []

        char_ids = [c.id for c in chars]
        id_set = set(char_ids)

        # Build adjacency: each character's neighbor set
        adj: dict[str, set[str]] = {cid: set() for cid in char_ids}
        edge_rows = self._run("""
            MATCH (c:Entity:Character {project_id: $pid})
            -[:KNOWS|ALLY|FAMILY|ANTAGONIST|ROMANTIC|MASTER_OF|MENTOR_OF|KILLED|SAVED|LOVES]-
            (n:Entity:Character {project_id: $pid})
            RETURN c.id AS src, n.id AS tgt
        """, {"pid": self.project_id})
        for r in edge_rows:
            src, tgt = r["src"], r["tgt"]
            if src in id_set and tgt in id_set and src != tgt:
                adj[src].add(tgt)
                adj[tgt].add(src)

        # Compute degree for each character
        degree = {cid: len(adj[cid]) for cid in char_ids}

        # For each non-adjacent pair, compute similarity scores
        predictions = []
        for i, a_id in enumerate(char_ids):
            for b_id in char_ids[i+1:]:
                if b_id in adj[a_id]:
                    continue  # already connected

                common = adj[a_id] & adj[b_id]
                if not common:
                    continue  # no common neighbors

                union = adj[a_id] | adj[b_id]
                common_count = len(common)
                jaccard = common_count / len(union) if union else 0

                # Adamic-Adar: sum(1/log(degree+1) for each common neighbor)
                adamic_adar = sum(
                    1.0 / math.log(degree.get(cn, 0) + 2)
                    for cn in common
                )

                char_a = next((c for c in chars if c.id == a_id), None)
                char_b = next((c for c in chars if c.id == b_id), None)

                predictions.append({
                    "char_a_id": a_id,
                    "char_a_name": char_a.name if char_a else a_id,
                    "char_b_id": b_id,
                    "char_b_name": char_b.name if char_b else b_id,
                    "common_neighbors": common_count,
                    "adamic_adar": round(adamic_adar, 4),
                    "jaccard": round(jaccard, 4),
                })

        predictions.sort(key=lambda x: x["adamic_adar"], reverse=True)
        return predictions[:top_n]


def get_store(book_id: str) -> GraphStore:
    store = GraphStore(book_id)
    store.init_schema()
    return store
