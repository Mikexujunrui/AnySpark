# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Constraint CRUD — stores constraints in SQLite.

Reuses the SQLiteStore connection from the caller.  Constraints are stored
in the ``constraints`` table, completely independent of entities / relations.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from .models import Constraint

logger = logging.getLogger(__name__)


class ConstraintStore:
    """CRUD for constraints.  Receives a store (SQLiteStore) instance."""

    def __init__(self, store):
        self._store = store

    # ── Create ──

    def add(
        self,
        description: str,
        constraint_type: str = "custom",
        target_entity: str = "",
        condition: dict | None = None,
        violation_query: str = "",
        severity: str = "hard",
    ) -> Constraint:
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
        self._store._execute(
            """
            INSERT INTO constraints
                (id, description, constraint_type, target_entity, condition,
                 violation_query, severity, active, project_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        """,
            (
                cid,
                description,
                constraint_type,
                target_entity,
                json.dumps(condition or {}, ensure_ascii=False),
                violation_query,
                severity,
                self._store.project_id,
                now,
                now,
            ),
        )
        return constraint

    # ── Read ──

    def list(self, active_only: bool = True) -> list[Constraint]:
        if active_only:
            rows = self._store._run(
                "SELECT * FROM constraints WHERE project_id=? AND active=1 ORDER BY created_at",
                (self._store.project_id,),
            )
        else:
            rows = self._store._run(
                "SELECT * FROM constraints WHERE project_id=? ORDER BY created_at",
                (self._store.project_id,),
            )
        return [self._row_to_constraint(r) for r in rows]

    def get(self, constraint_id: str) -> Constraint | None:
        r = self._store._run_single(
            "SELECT * FROM constraints WHERE id=? AND project_id=?",
            (constraint_id, self._store.project_id),
        )
        return self._row_to_constraint(r) if r else None

    # ── Delete ──

    def delete(self, constraint_id: str) -> bool:
        self._store._execute(
            "DELETE FROM constraints WHERE id=? AND project_id=?",
            (constraint_id, self._store.project_id),
        )
        return True

    # ── Disable (soft delete) ──

    def disable(self, constraint_id: str) -> bool:
        now = datetime.now().isoformat()
        self._store._execute(
            "UPDATE constraints SET active=0, updated_at=? WHERE id=? AND project_id=?",
            (now, constraint_id, self._store.project_id),
        )
        return True

    # ── Helper ──

    @staticmethod
    def _row_to_constraint(row) -> Constraint:
        condition_raw = row["condition"] if row["condition"] else "{}"
        if isinstance(condition_raw, str):
            try:
                condition = json.loads(condition_raw)
            except (json.JSONDecodeError, TypeError):
                condition = {}
        else:
            condition = condition_raw or {}
        active_val = row["active"] if "active" in row.keys() else 1
        return Constraint(
            id=row["id"],
            description=row["description"],
            constraint_type=row["constraint_type"],
            target_entity=row["target_entity"],
            condition=condition,
            violation_query=row["violation_query"],
            severity=row["severity"],
            status="active" if active_val else "disabled",
            created_at=row["created_at"],
        )
