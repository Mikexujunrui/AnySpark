# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Memory system REST API routes.

Project memory (per-book) and user preference (global) CRUD endpoints.
All operations are gated by the memory system's global enabled state.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.memory import (
    ConfidenceLevel,
    get_memory_manager,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


# ── Request models ──


class PreferenceCreate(BaseModel):
    category: str
    content: str
    summary: str = ""
    keywords: list[str] = []
    confidence: str = "pending"
    source: str = "manual"
    source_ref: str = ""


class PreferenceUpdate(BaseModel):
    content: str | None = None
    summary: str | None = None
    keywords: list[str] | None = None
    confidence: str | None = None


# ── Helpers ──


def _require_memory():
    mm = get_memory_manager()
    if not mm:
        raise HTTPException(404, "记忆系统已全局关闭")
    return mm


# ── Project memory endpoints (per-book, require book_id) ──


@router.get("/project/{book_id}")
def get_project_memory(book_id: str):
    mm = _require_memory()
    return mm.project.get_full_snapshot(book_id)


@router.put("/project/{book_id}")
def update_project_memory(book_id: str, premise: str | None = None, tags: list[str] | None = None):
    mm = _require_memory()
    if premise is not None:
        mm.project.set_premise(book_id, premise)
    if tags is not None:
        mm.project.set_tags(book_id, tags)
    return mm.project.get_full_snapshot(book_id)


@router.post("/project/{book_id}/note")
def add_note(book_id: str, title: str, content: str):
    mm = _require_memory()
    note = mm.project.add_note(book_id, title, content)
    return {"ok": True, "note": note}


@router.delete("/project/{book_id}/note/{note_id}")
def delete_note(book_id: str, note_id: str):
    mm = _require_memory()
    ok = mm.project.delete_note(book_id, note_id)
    if not ok:
        raise HTTPException(404, f"笔记不存在: {note_id}")
    return {"ok": True}


@router.post("/project/{book_id}/decision")
def record_decision(book_id: str, title: str, rationale: str):
    mm = _require_memory()
    decision = mm.project.record_decision(book_id, title, rationale)
    return {"ok": True, "decision": decision}


@router.delete("/project/{book_id}/decision/{decision_id}")
def delete_decision(book_id: str, decision_id: str):
    mm = _require_memory()
    ok = mm.project.delete_decision(book_id, decision_id)
    if not ok:
        raise HTTPException(404, f"决策不存在: {decision_id}")
    return {"ok": True}


@router.post("/project/{book_id}/progress")
def add_progress(book_id: str, content: str):
    mm = _require_memory()
    note = mm.project.add_progress_note(book_id, content)
    return {"ok": True, "note": note}


@router.delete("/project/{book_id}/progress/{note_id}")
def delete_progress(book_id: str, note_id: str):
    mm = _require_memory()
    ok = mm.project.delete_progress_note(book_id, note_id)
    if not ok:
        raise HTTPException(404, f"进度不存在: {note_id}")
    return {"ok": True}


# ── Preference endpoints (global) ──


@router.get("/preferences")
def list_preferences():
    mm = _require_memory()
    entries = mm.preferences.list_all()
    return {
        "total": len(entries),
        "entries": [e.to_dict() for e in entries],
        "category_counts": mm.get_category_counts(),
    }


@router.get("/preferences/categories/{category}")
def list_preferences_by_category(category: str):
    mm = _require_memory()
    entries = mm.preferences.list_by_category(category)
    return {
        "category": category,
        "total": len(entries),
        "entries": [e.to_dict() for e in entries],
    }


@router.post("/preferences")
def create_preference(data: PreferenceCreate):
    mm = _require_memory()
    entry = mm.preferences.add_entry(
        category=data.category,
        content=data.content,
        summary=data.summary,
        keywords=data.keywords,
        confidence=data.confidence,
        source=data.source,
        source_ref=data.source_ref,
    )
    return {"ok": True, "entry": entry.to_dict()}


@router.patch("/preferences/{entry_id}")
def update_preference(entry_id: str, data: PreferenceUpdate):
    mm = _require_memory()
    kwargs = {k: v for k, v in data.model_dump().items() if v is not None}
    if not kwargs:
        raise HTTPException(400, "没有提供要更新的字段")
    ok = mm.preferences.update_entry(entry_id, **kwargs)
    if not ok:
        raise HTTPException(404, f"偏好条目不存在: {entry_id}")
    entry = mm.preferences.get_by_id(entry_id)
    return {"ok": True, "entry": entry.to_dict() if entry else None}


@router.post("/preferences/{entry_id}/confirm")
def confirm_preference(entry_id: str):
    mm = _require_memory()
    ok = mm.preferences.confirm_entry(entry_id)
    if not ok:
        raise HTTPException(404, f"偏好条目不存在: {entry_id}")
    entry = mm.preferences.get_by_id(entry_id)
    return {"ok": True, "entry": entry.to_dict() if entry else None}


@router.delete("/preferences/{entry_id}")
def delete_preference(entry_id: str):
    mm = _require_memory()
    ok = mm.preferences.hard_delete(entry_id)
    if not ok:
        raise HTTPException(404, f"偏好条目不存在: {entry_id}")
    return {"ok": True}


@router.get("/preferences/pending")
def list_pending_preferences():
    mm = _require_memory()
    pending = [e.to_dict() for e in mm.preferences.list_all() if e.confidence == ConfidenceLevel.PENDING]
    return {"total": len(pending), "entries": pending}


# ── Stats ──


@router.get("/stats/{book_id}")
def get_memory_stats(book_id: str):
    mm = _require_memory()
    project_data = mm.project.get_full_snapshot(book_id)
    counts = mm.get_category_counts(book_id)
    return {
        "project": project_data,
        "stats": counts,
        "tier0_preview": mm.inject_tier0(book_id),
    }


# ── Settings toggle (global) ──


class ToggleRequest(BaseModel):
    enabled: bool


@router.post("/toggle")
def toggle_memory(data: ToggleRequest):
    from core.memory import reset_memory_manager
    from core.settings import get_settings, update_settings

    s = get_settings()
    old = s.memory_enabled
    if old == data.enabled:
        return {"ok": True, "enabled": data.enabled, "message": "已经是此状态"}

    s.memory_enabled = data.enabled
    update_settings(s)
    reset_memory_manager()
    return {
        "ok": True,
        "enabled": data.enabled,
        "message": f"记忆系统已{'启用' if data.enabled else '关闭'}",
    }
