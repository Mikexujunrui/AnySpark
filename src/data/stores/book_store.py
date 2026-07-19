# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Book CRUD operations (load, create, update, delete, reference books)."""

import logging
from datetime import datetime
from pathlib import Path

from core.book_locks import book_lock
from core.config import DATA_DIR
from core.errors import NotFoundError
from core.event_bus import Event, EventType, bus

logger = logging.getLogger(__name__)


class BookStoreMixin:
    """Mixin providing book management methods.  Requires BaseStore."""

    # ── Books ──

    def load_books(self) -> list[dict]:
        return self._read_json(self._books_file)

    def save_books(self, books: list[dict]):
        self._write_json(self._books_file, books)

    def get_book(self, book_id: str) -> dict:
        books = self.load_books()
        book = next((b for b in books if b["id"] == book_id), None)
        if not book:
            raise NotFoundError(f"书籍不存在: {book_id}")
        return book

    def create_book(self, title: str, description: str = "", genre: str = "") -> dict:
        with book_lock("_global"):
            books = self.load_books()
            bid = str(int(datetime.now().timestamp() * 1000))
            new_book = {
                "id": bid,
                "title": title,
                "description": description,
                "genre": genre or "novel",
                "entityCount": 0,
                "chapterCount": 0,
                "createdAt": datetime.now().isoformat(),
                "updatedAt": datetime.now().isoformat(),
            }
            books.append(new_book)
            self.save_books(books)
            return new_book

    def delete_book(self, book_id: str):
        with book_lock(book_id):
            sessions = self.load_sessions(book_id)
            for s in sessions:
                sid = s["id"]
                msg_file = self._messages_file(sid)
                if msg_file.exists():
                    msg_file.unlink()
                docs_file = self._docs_file(sid)
                if docs_file.exists():
                    docs = self._read_json(docs_file)
                    for d in docs:
                        p = Path(d.get("path", ""))
                        if p.exists():
                            p.unlink(missing_ok=True)
                    docs_file.unlink()

            sessions_file = self._sessions_file(book_id)
            if sessions_file.exists():
                sessions_file.unlink()

            chapters_file = self._chapters_file(book_id)
            if chapters_file.exists():
                chapters_file.unlink()

            notes_file = self._notes_file(book_id)
            if notes_file.exists():
                notes_file.unlink()

            outline_file = self._outline_file(book_id)
            if outline_file.exists():
                outline_file.unlink()

            timeline_file = self._timeline_file(book_id)
            if timeline_file.exists():
                timeline_file.unlink()

            detailed_file = self._detailed_outline_file(book_id)
            if detailed_file.exists():
                detailed_file.unlink()

            # Location map and worldbuilding (now inside the lock)
            locmap_file = self._location_map_file(book_id)
            if locmap_file.exists():
                locmap_file.unlink()

            wb_file = self._worldbuilding_file(book_id)
            if wb_file.exists():
                wb_file.unlink()

            # Additional data files that were previously missed
            for getter in (
                self._reviews_file, self._volumes_file,
                self._material_subs_file, self._tasks_file,
                self._plot_chain_file,
            ):
                f = getter(book_id)
                if f.exists():
                    f.unlink()

            # Character mentions cache
            mentions_file = DATA_DIR / f"char_mentions_{self._safe_id(book_id)}.json"
            if mentions_file.exists():
                mentions_file.unlink()

            # Workflow subscriptions
            wf_subs_file = DATA_DIR / f"workflow_subs_{self._safe_id(book_id)}.json"
            if wf_subs_file.exists():
                wf_subs_file.unlink()

            # Clean up FTS indices
            try:
                from core.search import fts as fts_engine
                fts_engine.clear_book(book_id)
            except Exception:
                logger.warning("Failed to clear FTS index for book %s", book_id)

        with book_lock("_global"):
            books = self.load_books()
            books = [b for b in books if b["id"] != book_id]
            self.save_books(books)

        bus.emit_sync(Event(type=EventType.BOOK_DELETED, data={"book_id": book_id}, source="book_store"))

    def update_book(self, book_id: str, data: dict) -> dict:
        with book_lock("_global"):
            books = self.load_books()
            for b in books:
                if b["id"] == book_id:
                    for key, value in data.items():
                        b[key] = value
                    b["updatedAt"] = datetime.now().isoformat()
                    self.save_books(books)
                    return b
            raise NotFoundError(f"书籍不存在: {book_id}")

    def update_book_stats(self, book_id: str, entity_count: int = None, chapter_count: int = None):
        with book_lock("_global"):
            books = self.load_books()
            for b in books:
                if b["id"] == book_id:
                    if entity_count is not None:
                        b["entityCount"] = entity_count
                    if chapter_count is not None:
                        b["chapterCount"] = chapter_count
                    b["updatedAt"] = datetime.now().isoformat()
                    break
            self.save_books(books)

    def set_reference_books(self, book_id: str, ref_ids: list[str]):
        with book_lock("_global"):
            books = self.load_books()
            for b in books:
                if b["id"] == book_id:
                    b["referenceBookIds"] = ref_ids
                    b["updatedAt"] = datetime.now().isoformat()
                    break
            self.save_books(books)

    def get_reference_books(self, book_id: str) -> list[str]:
        try:
            book = self.get_book(book_id)
            return book.get("referenceBookIds", [])
        except (KeyError, TypeError):
            return []
