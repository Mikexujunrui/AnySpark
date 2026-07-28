# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Constraint checker — executes violation queries and returns violations.

Read-only: only runs SELECT queries.  Custom SQL fragments are sanitized
to reject any write operations (INSERT / UPDATE / DELETE / DROP / ALTER).
"""

from __future__ import annotations

import logging
import re

from .constraint_store import ConstraintStore
from .models import Constraint, ConstraintViolation

logger = logging.getLogger(__name__)

# SQL keywords that indicate a write operation — rejected for safety.
_WRITE_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|MERGE|REPLACE|TRUNCATE|SET|CALL)\b",
    re.IGNORECASE,
)


class ConstraintChecker:
    """Runs violation queries for active constraints."""

    def __init__(self, store):
        self._store = store
        self._constraint_store = ConstraintStore(store)

    # ── Public API ──

    def check_all(self) -> list[ConstraintViolation]:
        """Check every active constraint. Returns violations only (passing
        constraints are omitted to keep output concise)."""
        constraints = self._constraint_store.list(active_only=True)
        violations: list[ConstraintViolation] = []
        for c in constraints:
            v = self.check_one(c)
            if v and v.violations:
                violations.append(v)
        return violations

    def check_one(self, constraint: Constraint) -> ConstraintViolation | None:
        """Execute the constraint's violation_query and return results."""
        if not constraint.violation_query:
            # No Cypher fragment — cannot check programmatically.
            return ConstraintViolation(
                constraint_id=constraint.id,
                description=constraint.description,
                severity=constraint.severity,
                violations=[],
            )

        if not self._is_safe_query(constraint.violation_query):
            logger.warning(
                "Constraint %s has unsafe violation_query (contains write keywords), skipping",
                constraint.id,
            )
            return ConstraintViolation(
                constraint_id=constraint.id,
                description=constraint.description,
                severity=constraint.severity,
                violations=[{"error": "约束查询包含写操作，已被安全检查拦截"}],
            )

        rows = self._store._run(constraint.violation_query, {"pid": self._store.project_id})
        violations = []
        for row in rows:
            entry = {}
            for key in row.keys():
                val = row[key]
                # sqlite3.Row returns plain values
                if val is not None:
                    entry[key] = str(val)
                else:
                    entry[key] = ""
            violations.append(entry)

        return ConstraintViolation(
            constraint_id=constraint.id,
            description=constraint.description,
            severity=constraint.severity,
            violations=violations,
        )

    # ── Auto-check hook (called on chapter save) ──

    def auto_check_on_chapter_save(self, chapter_id: str) -> list[ConstraintViolation]:
        """Lightweight check that can be called after a chapter is saved.

        Currently delegates to check_all().  Future enhancement: filter
        constraints to only those governing entities mentioned in the chapter.
        """
        return self.check_all()

    # ── Safety ──

    @staticmethod
    def _is_safe_query(query: str) -> bool:
        """Return True if the query contains only read-only Cypher."""
        if not query or not query.strip():
            return False
        if _WRITE_KEYWORDS.search(query):
            return False
        return True
