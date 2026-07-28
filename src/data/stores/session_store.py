# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Session + message + document storage."""

import logging
from datetime import datetime
from pathlib import Path

from core.book_locks import book_lock
from core.errors import NotFoundError

logger = logging.getLogger(__name__)


class SessionStoreMixin:
    """Mixin providing session/message/document methods.  Requires BaseStore."""

    def load_sessions(self, book_id: str) -> list[dict]:
        return self._read_json(self._sessions_file(book_id))

    def save_sessions(self, book_id: str, sessions: list[dict]):
        self._write_json(self._sessions_file(book_id), sessions)

    def create_session(self, book_id: str, title: str = "") -> dict:
        with book_lock(book_id):
            sessions = self.load_sessions(book_id)
            sid = str(int(datetime.now().timestamp() * 1000))
            if not title:
                title = f"会话 {len(sessions) + 1}"
            session = {
                "id": sid,
                "title": title,
                "createdAt": datetime.now().isoformat(),
                "updatedAt": datetime.now().isoformat(),
                "messageCount": 0,
            }
            sessions.insert(0, session)
            self.save_sessions(book_id, sessions)
        return session

    def update_session(self, book_id: str, session_id: str, data: dict) -> dict:
        with book_lock(book_id):
            sessions = self.load_sessions(book_id)
            for s in sessions:
                if s["id"] == session_id:
                    s.update({k: v for k, v in data.items() if k != "id"})
                    s["updatedAt"] = datetime.now().isoformat()
                    self.save_sessions(book_id, sessions)
                    return s
        raise NotFoundError(f"会话不存在: {session_id}")

    def delete_session(self, book_id: str, session_id: str):
        with book_lock(book_id):
            sessions = self.load_sessions(book_id)
            sessions = [s for s in sessions if s["id"] != session_id]
            self.save_sessions(book_id, sessions)
            msg_file = self._messages_file(session_id)
            if msg_file.exists():
                msg_file.unlink()
            docs_file = self._docs_file(session_id)
            if docs_file.exists():
                docs = self._read_json(docs_file)
                for d in docs:
                    p = Path(d["path"])
                    if p.exists():
                        p.unlink()
                docs_file.unlink()

    def load_docs(self, session_id: str) -> list[dict]:
        """Load uploaded documents metadata for a session."""
        docs_file = self._docs_file(session_id)
        return self._read_json(docs_file, [])

    def save_docs(self, session_id: str, docs: list[dict]):
        """Save uploaded documents metadata for a session."""
        docs_file = self._docs_file(session_id)
        self._write_json(docs_file, docs)

    def add_doc(self, session_id: str, doc_id: str, filename: str, chars: int, path: str) -> dict:
        """Add a document metadata entry."""
        docs = self.load_docs(session_id)
        entry = {
            "id": doc_id,
            "filename": filename,
            "chars": chars,
            "path": path,
            "uploadedAt": datetime.now().isoformat(),
        }
        docs.append(entry)
        self.save_docs(session_id, docs)
        return entry

    def get_doc(self, session_id: str, doc_id: str) -> dict:
        """Get a single document metadata entry by ID."""
        docs = self.load_docs(session_id)
        doc = self._resolve_by_id(docs, doc_id)
        if not doc:
            raise NotFoundError(f"文档不存在: {doc_id}")
        return doc

    def load_messages(self, session_id: str) -> list[dict]:
        """Load conversation messages for a session.

        Returns empty list if the messages file does not exist or is corrupt.
        """
        return self._read_json(self._messages_file(session_id))

    def save_messages(self, book_id: str, session_id: str, messages: list[dict]):
        """Persist conversation messages for a session.

        ``book_id`` is accepted for API compatibility with callers that pass
        it alongside ``session_id``, but only ``session_id`` determines the
        on-disk file path.
        """
        self._write_json(self._messages_file(session_id), messages)
