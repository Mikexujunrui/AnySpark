# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Project memory helper — per-book creative memory for novel writing.

Each book/novel project has its own memory file storing:
- premise: core premise / setting description
- notes: free-form writing notes (title + content + created_at)
- creative_decisions: important plot/writing decisions with rationale
- progress_notes: writing progress updates
- custom_tags: user-defined tags for organization
"""

from __future__ import annotations

import logging
from datetime import datetime

from .store import load_project_memory, save_project_memory

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return datetime.now().strftime("%H%M%S%f")[:10]


class ProjectMemoryHelper:
    """Per-book project memory CRUD."""

    # ── Premise ──

    @staticmethod
    def get_premise(book_id: str) -> str:
        data = load_project_memory(book_id)
        return data.get("premise", "")

    @staticmethod
    def set_premise(book_id: str, premise: str):
        data = load_project_memory(book_id)
        data["premise"] = premise
        save_project_memory(book_id, data)

    # ── Notes ──

    @staticmethod
    def get_notes(book_id: str) -> list[dict]:
        data = load_project_memory(book_id)
        return data.get("notes", [])

    @staticmethod
    def add_note(book_id: str, title: str, content: str) -> dict:
        data = load_project_memory(book_id)
        note = {
            "id": _new_id(),
            "title": title,
            "content": content,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        notes = data.get("notes", [])
        notes.append(note)
        data["notes"] = notes
        save_project_memory(book_id, data)
        return note

    @staticmethod
    def delete_note(book_id: str, note_id: str) -> bool:
        data = load_project_memory(book_id)
        notes = data.get("notes", [])
        new_notes = [n for n in notes if n.get("id") != note_id]
        if len(new_notes) == len(notes):
            return False
        data["notes"] = new_notes
        save_project_memory(book_id, data)
        return True

    # ── Creative decisions ──

    @staticmethod
    def get_decisions(book_id: str) -> list[dict]:
        data = load_project_memory(book_id)
        return data.get("creative_decisions", [])

    @staticmethod
    def record_decision(book_id: str, title: str, rationale: str) -> dict:
        data = load_project_memory(book_id)
        decision = {
            "id": _new_id(),
            "title": title,
            "rationale": rationale,
            "date": datetime.now().strftime("%Y-%m-%d"),
        }
        decisions = data.get("creative_decisions", [])
        decisions.append(decision)
        data["creative_decisions"] = decisions
        save_project_memory(book_id, data)
        return decision

    @staticmethod
    def delete_decision(book_id: str, decision_id: str) -> bool:
        data = load_project_memory(book_id)
        decisions = data.get("creative_decisions", [])
        new_decisions = [d for d in decisions if d.get("id") != decision_id]
        if len(new_decisions) == len(decisions):
            return False
        data["creative_decisions"] = new_decisions
        save_project_memory(book_id, data)
        return True

    # ── Progress notes ──

    @staticmethod
    def get_progress_notes(book_id: str) -> list[dict]:
        data = load_project_memory(book_id)
        return data.get("progress_notes", [])

    @staticmethod
    def add_progress_note(book_id: str, content: str) -> dict:
        data = load_project_memory(book_id)
        note = {
            "id": _new_id(),
            "content": content,
            "date": datetime.now().strftime("%Y-%m-%d"),
        }
        notes = data.get("progress_notes", [])
        notes.append(note)
        data["progress_notes"] = notes
        save_project_memory(book_id, data)
        return note

    @staticmethod
    def delete_progress_note(book_id: str, note_id: str) -> bool:
        data = load_project_memory(book_id)
        notes = data.get("progress_notes", [])
        new_notes = [n for n in notes if n.get("id") != note_id]
        if len(new_notes) == len(notes):
            return False
        data["progress_notes"] = new_notes
        save_project_memory(book_id, data)
        return True

    # ── Tags ──

    @staticmethod
    def get_tags(book_id: str) -> list[str]:
        data = load_project_memory(book_id)
        return data.get("custom_tags", [])

    @staticmethod
    def set_tags(book_id: str, tags: list[str]):
        data = load_project_memory(book_id)
        data["custom_tags"] = tags
        save_project_memory(book_id, data)

    # ── Full snapshot ──

    @staticmethod
    def get_full_snapshot(book_id: str) -> dict:
        return load_project_memory(book_id)

    # ── Formatting for system prompt injection ──

    @staticmethod
    def format_tier1_index(book_id: str) -> str:
        data = load_project_memory(book_id)
        lines = ["## 书籍创作笔记"]
        if data.get("premise"):
            lines.append(f"- 核心设定: {data['premise'][:80]}")
        notes = data.get("notes", [])
        if notes:
            lines.append(f"- 创作笔记: {len(notes)}条")
        decisions = data.get("creative_decisions", [])
        if decisions:
            lines.append(f"- 创作决策: {len(decisions)}条")
        tags = data.get("custom_tags", [])
        if tags:
            lines.append(f"- 标签: {' '.join(tags[:5])}")
        if len(lines) > 1:
            return "\n".join(lines)
        return ""

    @staticmethod
    def format_tier0(book_id: str) -> str:
        data = load_project_memory(book_id)
        counts = []
        notes = data.get("notes", [])
        if notes:
            counts.append(f"{len(notes)}条笔记")
        decisions = data.get("creative_decisions", [])
        if decisions:
            counts.append(f"{len(decisions)}条决策")
        if counts:
            return f"书籍记忆 | {' | '.join(counts)}"
        return ""
