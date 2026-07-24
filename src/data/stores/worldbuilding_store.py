# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.


"""Worldbuilding, outline, timeline, notes, and location map storage."""

import logging
from datetime import datetime

from core.book_locks import book_lock
from core.errors import NotFoundError

logger = logging.getLogger(__name__)


class WorldbuildingStoreMixin:
    """Mixin providing worldbuilding/outline/timeline/notes methods.  Requires BaseStore."""

    def load_worldbuilding(self, book_id: str) -> dict:
        return self._read_json(self._worldbuilding_file(book_id), default={})

    def save_worldbuilding(self, book_id: str, data: dict):
        with book_lock(book_id):
            data["updatedAt"] = datetime.now().isoformat()
            self._write_json(self._worldbuilding_file(book_id), data)

    def get_worldbuilding(self, book_id: str) -> dict:
        d = self.load_worldbuilding(book_id)
        if not d:
            return {"categories": [], "updatedAt": ""}
        return d

    def add_worldbuilding_category(self, book_id: str, name: str, icon: str = "", parent_id: str = None) -> dict:
        with book_lock(book_id):
            wb = self.get_worldbuilding(book_id)
            cid = f"cat_{int(datetime.now().timestamp() * 1000)}"
            new_cat = {"id": cid, "name": name, "icon": icon, "entries": [], "children": []}
            if parent_id:
                self._insert_child(wb.get("categories", []), parent_id, new_cat)
            else:
                wb.setdefault("categories", []).append(new_cat)
            self.save_worldbuilding(book_id, wb)
        return new_cat

    def _insert_child(self, categories, parent_id, child):
        for cat in categories:
            if cat["id"] == parent_id:
                cat.setdefault("children", []).append(child)
                return True
            if self._insert_child(cat.get("children", []), parent_id, child):
                return True
        return False

    def add_worldbuilding_entry(self, book_id: str, category_id: str, entry: dict) -> dict:
        with book_lock(book_id):
            wb = self.get_worldbuilding(book_id)
            if "id" not in entry:
                entry["id"] = f"ent_{int(datetime.now().timestamp() * 1000)}"
            cat = self._find_category(wb.get("categories", []), category_id)
            if cat:
                cat.setdefault("entries", []).append(entry)
                self.save_worldbuilding(book_id, wb)
        return entry

    def update_worldbuilding_entry(self, book_id: str, entry_id: str, data: dict) -> dict:
        with book_lock(book_id):
            wb = self.get_worldbuilding(book_id)
            entry = self._find_entry(wb.get("categories", []), entry_id)
            if entry:
                entry.update({k: v for k, v in data.items() if k != "id"})
                self.save_worldbuilding(book_id, wb)
        return entry or {}

    def delete_worldbuilding_entry(self, book_id: str, entry_id: str):
        with book_lock(book_id):
            wb = self.get_worldbuilding(book_id)
            self._remove_entry(wb.get("categories", []), entry_id)
            self.save_worldbuilding(book_id, wb)

    def _find_category(self, categories, cat_id):
        """Find category by exact ID or unique prefix match."""
        for cat in categories:
            if cat["id"] == cat_id or cat["id"].startswith(cat_id):
                # Prefix match: only return if unique across all categories at this level
                all_ids = [c["id"] for c in categories]
                prefix_matches = [i for i in all_ids if i.startswith(cat_id)]
                if len(prefix_matches) == 1 or cat["id"] == cat_id:
                    return cat
            found = self._find_category(cat.get("children", []), cat_id)
            if found:
                return found
        return None

    def _find_entry(self, categories, entry_id):
        """Find entry by exact ID or unique prefix match."""
        for cat in categories:
            for e in cat.get("entries", []):
                eid = e.get("id", "")
                if eid == entry_id or eid.startswith(entry_id):
                    # Prefix match: only return if unique at this level
                    all_eids = [en.get("id", "") for en in cat.get("entries", [])]
                    prefix_matches = [i for i in all_eids if i.startswith(entry_id)]
                    if len(prefix_matches) == 1 or eid == entry_id:
                        return e
            found = self._find_entry(cat.get("children", []), entry_id)
            if found:
                return found
        return None

    def _remove_entry(self, categories, entry_id):
        """Remove entry by exact ID or unique prefix match."""
        for cat in categories:
            # Resolve truncated ID for entries in this category
            all_eids = [e.get("id", "") for e in cat.get("entries", [])]
            prefix_matches = [i for i in all_eids if i.startswith(entry_id)]
            resolved_id = entry_id
            if len(prefix_matches) == 1 and prefix_matches[0] != entry_id:
                resolved_id = prefix_matches[0]
            cat["entries"] = [e for e in cat.get("entries", []) if e.get("id") != resolved_id]
            self._remove_entry(cat.get("children", []), entry_id)

    # ── Location Map ──

    def load_location_map(self, book_id: str) -> dict:
        return self._read_json(self._location_map_file(book_id), default={"locations": []})

    def save_location_map(self, book_id: str, data: dict):
        self._write_json(self._location_map_file(book_id), data)

    def get_location_map(self, book_id: str) -> dict:
        return self.load_location_map(book_id)

    # ── Detailed Outline ──

    def load_detailed_outline(self, book_id: str) -> dict:
        return self._read_json(self._detailed_outline_file(book_id), default={"chapters": []})

    def save_detailed_outline(self, book_id: str, data: dict):
        self._write_json(self._detailed_outline_file(book_id), data)

    def get_detailed_outline(self, book_id: str) -> dict:
        return self.load_detailed_outline(book_id)

    def update_detailed_outline_chapter(self, book_id: str, chapter_index: int, data: dict) -> dict:
        outline = self.load_detailed_outline(book_id)
        chapters = outline.get("chapters", [])
        while len(chapters) <= chapter_index:
            chapters.append({})
        chapters[chapter_index].update(data)
        outline["chapters"] = chapters
        self.save_detailed_outline(book_id, outline)
        return outline

    def update_detailed_outline_extra(self, book_id: str, extra_index: int, data: dict) -> dict:
        outline = self.load_detailed_outline(book_id)
        extras = outline.get("extras", [])
        while len(extras) <= extra_index:
            extras.append({})
        extras[extra_index].update(data)
        outline["extras"] = extras
        self.save_detailed_outline(book_id, outline)
        return outline

    # ── Continuity Cards ──

    def load_continuity_cards(self, book_id: str) -> dict:
        return self._read_json(self._continuity_cards_file(book_id), default={"chapters": {}})

    def save_continuity_card(self, book_id: str, chapter_index: int, card: dict):
        with book_lock(book_id):
            data = self.load_continuity_cards(book_id)
            data["chapters"][str(chapter_index)] = card
            self._write_json(self._continuity_cards_file(book_id), data)

    def get_recent_continuity_cards(self, book_id: str, before_chapter: int, count: int = 3) -> list[dict]:
        """Get continuity cards for the `count` chapters before `before_chapter`."""
        data = self.load_continuity_cards(book_id)
        chapters = data.get("chapters", {})
        cards = []
        for i in range(max(1, before_chapter - count), before_chapter):
            card = chapters.get(str(i))
            if card:
                cards.append(card)
        return cards

    # ── AI Flavor Reports ──

    def load_flavor_reports(self, book_id: str) -> dict:
        return self._read_json(self._flavor_reports_file(book_id), default={"chapters": {}})

    def save_flavor_report(self, book_id: str, chapter_index: int, report: dict):
        with book_lock(book_id):
            data = self.load_flavor_reports(book_id)
            data["chapters"][str(chapter_index)] = report
            self._write_json(self._flavor_reports_file(book_id), data)

    # ── Timeline ──

    def load_timeline(self, book_id: str) -> dict:
        return self._read_json(self._timeline_file(book_id), default={"tracks": [], "events": []})

    def save_timeline(self, book_id: str, timeline: dict):
        self._write_json(self._timeline_file(book_id), timeline)

    def add_timeline_track(self, book_id: str, name: str, color: str = "#a78bfa") -> dict:
        tl = self.load_timeline(book_id)
        track = {"id": str(int(datetime.now().timestamp() * 1000)), "name": name, "color": color}
        tl.setdefault("tracks", []).append(track)
        self.save_timeline(book_id, tl)
        return track

    def add_timeline_event(self, book_id: str, event: dict) -> dict:
        tl = self.load_timeline(book_id)
        event["id"] = str(int(datetime.now().timestamp() * 1000))
        tl.setdefault("events", []).append(event)
        self.save_timeline(book_id, tl)
        return event

    def update_timeline_event(self, book_id: str, event_id: str, data: dict) -> dict:
        tl = self.load_timeline(book_id)
        for e in tl.get("events", []):
            if e.get("id") == event_id or e.get("id", "").startswith(event_id):
                e.update(data)
                self.save_timeline(book_id, tl)
                return e
        raise NotFoundError(f"Timeline event not found: {event_id}")

    def delete_timeline_event(self, book_id: str, event_id: str):
        tl = self.load_timeline(book_id)
        tl["events"] = [
            e for e in tl.get("events", []) if e.get("id") != event_id and not e.get("id", "").startswith(event_id)
        ]
        self.save_timeline(book_id, tl)

    def delete_timeline_track(self, book_id: str, track_id: str):
        tl = self.load_timeline(book_id)
        tl["tracks"] = [t for t in tl.get("tracks", []) if t.get("id") != track_id]
        self.save_timeline(book_id, tl)

    # ── Outline ──

    def load_outline(self, book_id: str) -> dict:
        return self._read_json(self._outline_file(book_id), default={"chapters": []})

    def save_outline(self, book_id: str, outline: dict):
        self._write_json(self._outline_file(book_id), outline)

    def get_outline(self, book_id: str) -> dict:
        return self.load_outline(book_id)

    def update_outline_chapter(self, book_id: str, chapter_index: int, data: dict) -> dict:
        outline = self.load_outline(book_id)
        chapters = outline.get("chapters", [])
        while len(chapters) <= chapter_index:
            chapters.append({})
        chapters[chapter_index].update(data)
        outline["chapters"] = chapters
        self.save_outline(book_id, outline)
        return outline

    def update_outline_summary(self, book_id: str, summary: str) -> dict:
        outline = self.load_outline(book_id)
        outline["summary"] = summary
        self.save_outline(book_id, outline)
        return outline

    def update_outline_extra(self, book_id: str, extra_index: int, data: dict) -> dict:
        outline = self.load_outline(book_id)
        extras = outline.get("extras", [])
        while len(extras) <= extra_index:
            extras.append({})
        extras[extra_index].update(data)
        outline["extras"] = extras
        self.save_outline(book_id, outline)
        return outline

    # ── Notes ──

    def load_notes(self, book_id: str) -> list[dict]:
        return self._read_json(self._notes_file(book_id))

    def save_notes(self, book_id: str, notes: list[dict]):
        self._write_json(self._notes_file(book_id), notes)

    def add_note(self, book_id: str, content: str, tags: list[str] = None) -> dict:
        notes = self.load_notes(book_id)
        note = {
            "id": str(int(datetime.now().timestamp() * 1000)),
            "content": content,
            "tags": tags or [],
            "createdAt": datetime.now().isoformat(),
        }
        notes.append(note)
        self.save_notes(book_id, notes)
        return note

    def delete_note(self, book_id: str, note_id: str) -> bool:
        notes = self.load_notes(book_id)
        original_len = len(notes)
        filtered = [n for n in notes if n.get("id") != note_id]
        if len(filtered) == original_len:
            return False
        self.save_notes(book_id, filtered)
        return True
