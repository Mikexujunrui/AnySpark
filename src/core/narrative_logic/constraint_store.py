# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Constraint CRUD — stores :Constraint nodes in Neo4j.

Reuses the shared Neo4j driver from GraphStore.  Constraint nodes are
completely independent of Entity / Relation / Timeline nodes — they only
link to entities via :GOVERNS edges.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from core.graph_store import GraphStore

from .models import Constraint

logger = logging.getLogger(__name__)


class ConstraintStore:
    """CRUD for :Constraint nodes.  Receives a GraphStore instance so it
    shares the same Neo4j driver — no new connections."""

    def __init__(self, store: GraphStore):
        self._store = store

    # ── Create ──

    def add(self, description: str, constraint_type: str = "custom",
            target_entity: str = "", condition: dict | None = None,
            violation_query: str = "", severity: str = "hard") -> Constraint:
        cid = f"C{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()
        constraint = Constraint(
            id=cid,
            description=description,
            constraint_type=constraint_type,
            target_entity=target_entity,
            condition=condition or {},
            violation_query=violation_query,
            severity=severity,
            status="active",
            created_at=now,
        )
        self._store._run("""
            CREATE (c:Constraint {
                id: $id, description: $desc, constraint_type: $type,
                target_entity: $target, condition: $condition,
                violation_query: $vq, severity: $severity,
                status: $status, created_at: $created,
                project_id: $pid
            })
        """, {
            "id": cid, "desc": description, "type": constraint_type,
            "target": target_entity,
            "condition": json.dumps(condition or {}, ensure_ascii=False),
            "vq": violation_query, "severity": severity,
            "status": "active", "created": now,
            "pid": self._store.project_id,
        })
        # Link to target entity if we can find it by name
        if target_entity:
            self._store._run("""
                MATCH (c:Constraint {id: $cid, project_id: $pid})
                MATCH (e:Entity {project_id: $pid})
                WHERE e.name = $target OR $target IN e.aliases
                MERGE (c)-[:GOVERNS]->(e)
            """, {"cid": cid, "target": target_entity, "pid": self._store.project_id})
        return constraint

    # ── Read ──

    def list(self, active_only: bool = True) -> list[Constraint]:
        if active_only:
            rows = self._store._run("""
                MATCH (c:Constraint {project_id: $pid, status: 'active'})
                RETURN c ORDER BY c.created_at
            """, {"pid": self._store.project_id})
        else:
            rows = self._store._run("""
                MATCH (c:Constraint {project_id: $pid})
                RETURN c ORDER BY c.created_at
            """, {"pid": self._store.project_id})
        return [self._row_to_constraint(r["c"]) for r in rows]

    def get(self, constraint_id: str) -> Constraint | None:
        r = self._store._run_single("""
            MATCH (c:Constraint {id: $cid, project_id: $pid})
            RETURN c
        """, {"cid": constraint_id, "pid": self._store.project_id})
        return self._row_to_constraint(r["c"]) if r else None

    # ── Delete ──

    def delete(self, constraint_id: str) -> bool:
        self._store._run("""
            MATCH (c:Constraint {id: $cid, project_id: $pid})
            DETACH DELETE c
        """, {"cid": constraint_id, "pid": self._store.project_id})
        return True

    # ── Disable (soft delete) ──

    def disable(self, constraint_id: str) -> bool:
        self._store._run("""
            MATCH (c:Constraint {id: $cid, project_id: $pid})
            SET c.status = 'disabled'
        """, {"cid": constraint_id, "pid": self._store.project_id})
        return True

    # ── Helper ──

    @staticmethod
    def _row_to_constraint(node) -> Constraint:
        condition_raw = node.get("condition", "{}")
        if isinstance(condition_raw, str):
            try:
                condition = json.loads(condition_raw)
            except (json.JSONDecodeError, TypeError):
                condition = {}
        else:
            condition = condition_raw or {}
        return Constraint(
            id=node["id"],
            description=node.get("description", ""),
            constraint_type=node.get("constraint_type", "custom"),
            target_entity=node.get("target_entity", ""),
            condition=condition,
            violation_query=node.get("violation_query", ""),
            severity=node.get("severity", "hard"),
            status=node.get("status", "active"),
            created_at=node.get("created_at", ""),
        )
