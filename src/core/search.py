"""Full-text Search — sqlite FTS5 index for chapters, entities, worldbuilding, and materials."""

import logging
import sqlite3
import threading
from pathlib import Path

from .config import DATA_DIR

logger = logging.getLogger(__name__)

FTS_DB = DATA_DIR / "search_fts.db"


class FullTextSearch:
    def __init__(self, db_path: str | Path = None):
        self._db_path = Path(db_path or FTS_DB)
        self._local = threading.local()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self._db_path))
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._init_tables()
        return self._local.conn

    def _init_tables(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chapters_fts
            USING fts5(book_id, chapter_id, title, content, tokenize='unicode61')
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts
            USING fts5(book_id, entity_id, name, type, aliases, data, tokenize='unicode61')
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS worldbuilding_fts
            USING fts5(book_id, category, entry_title, content, tokenize='unicode61')
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS materials_fts
            USING fts5(mat_id, title, tags, content, tokenize='unicode61')
        """)

    # ── Chapter Index ──

    def index_chapter(self, book_id: str, chapter: dict):
        conn = self._get_conn()
        content = chapter.get("content", "")
        title = chapter.get("title", "")
        ch_id = chapter.get("id", "")
        if not content and not title:
            return
        conn.execute(
            "INSERT OR REPLACE INTO chapters_fts(book_id, chapter_id, title, content) VALUES (?, ?, ?, ?)",
            (book_id, ch_id, title, content),
        )
        conn.commit()

    def index_chapters_batch(self, book_id: str, chapters: list[dict]):
        conn = self._get_conn()
        for ch in chapters:
            content = ch.get("content", "") or (ch.get("versions", [{}])[-1].get("content", "") if ch.get("versions") else "")
            title = ch.get("title", "") or (ch.get("versions", [{}])[-1].get("title", "") if ch.get("versions") else "")
            ch_id = ch.get("id", "")
            if content or title:
                conn.execute(
                    "INSERT OR REPLACE INTO chapters_fts(book_id, chapter_id, title, content) VALUES (?, ?, ?, ?)",
                    (book_id, ch_id, title, content),
                )
        conn.commit()

    def remove_chapter(self, chapter_id: str):
        conn = self._get_conn()
        conn.execute("DELETE FROM chapters_fts WHERE chapter_id = ?", (chapter_id,))
        conn.commit()

    def rebuild_chapters(self, book_id: str, chapters: list[dict]):
        conn = self._get_conn()
        conn.execute("DELETE FROM chapters_fts WHERE book_id = ?", (book_id,))
        conn.commit()
        self.index_chapters_batch(book_id, chapters)

    # ── Entity Index ──

    def index_entity(self, book_id: str, entity_id: str, name: str, etype: str, aliases: list[str], data: dict):
        conn = self._get_conn()
        aliases_str = " ".join(aliases)
        data_str = " ".join(str(v) for v in data.values() if v)
        conn.execute(
            "INSERT OR REPLACE INTO entities_fts(book_id, entity_id, name, type, aliases, data) VALUES (?, ?, ?, ?, ?, ?)",
            (book_id, entity_id, name, etype, aliases_str, data_str),
        )
        conn.commit()

    def remove_entity(self, entity_id: str):
        conn = self._get_conn()
        conn.execute("DELETE FROM entities_fts WHERE entity_id = ?", (entity_id,))
        conn.commit()

    def rebuild_entities(self, book_id: str, entities: list):
        conn = self._get_conn()
        conn.execute("DELETE FROM entities_fts WHERE book_id = ?", (book_id,))
        conn.commit()
        for e in entities:
            self.index_entity(book_id, e.id, e.name, e.type, e.aliases, e.data)

    # ── Worldbuilding Index ──

    def index_worldbuilding(self, book_id: str, wb_data: dict):
        conn = self._get_conn()
        conn.execute("DELETE FROM worldbuilding_fts WHERE book_id = ?", (book_id,))
        conn.commit()
        for cat in wb_data.get("categories", []):
            self._index_category(conn, book_id, cat)
        conn.commit()

    def _index_category(self, conn, book_id: str, cat: dict, parent_name: str = ""):
        cat_name = cat.get("name", parent_name)
        for entry in cat.get("entries", []):
            conn.execute(
                "INSERT INTO worldbuilding_fts(book_id, category, entry_title, content) VALUES (?, ?, ?, ?)",
                (book_id, cat_name, entry.get("title", ""), entry.get("content", "")),
            )
        for child in cat.get("children", []):
            self._index_category(conn, book_id, child, cat_name)

    # ── Material Index ──

    def index_material(self, mat: dict):
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO materials_fts(mat_id, title, tags, content) VALUES (?, ?, ?, ?)",
            (mat["id"], mat.get("title", ""), " ".join(mat.get("tags", [])),
             mat.get("content", "")),
        )
        conn.commit()

    def remove_material(self, mid: str):
        conn = self._get_conn()
        conn.execute("DELETE FROM materials_fts WHERE mat_id = ?", (mid,))
        conn.commit()

    def search_materials(self, query: str, subscribed_ids: list[str] | None = None,
                         limit: int = 15) -> list[dict]:
        if not query or len(query.strip()) < 1:
            return []
        conn = self._get_conn()
        q = self._sanitize_query(query)
        if not q:
            return []

        try:
            if subscribed_ids is not None and len(subscribed_ids) == 0:
                return []
            if subscribed_ids:
                placeholders = ",".join("?" * len(subscribed_ids))
                id_filter = " AND mat_id IN (" + placeholders + ")"
            else:
                id_filter = ""
            rows = conn.execute(
                f"SELECT mat_id, title, snippet(materials_fts, 2, '[[', ']]', '...', 40) as snip "
                f"FROM materials_fts WHERE materials_fts MATCH ?{id_filter} ORDER BY rank LIMIT ?",
                (q, *subscribed_ids, limit) if subscribed_ids else (q, limit),
            ).fetchall()
            return [{"id": r[0], "title": r[1], "snippet": r[2]} for r in rows]
        except sqlite3.OperationalError:
            return []

    # ── Search ──

    def search(self, book_id: str, query: str, limit: int = 20) -> dict:
        if not query or len(query.strip()) < 1:
            return {"chapters": [], "entities": [], "worldbuilding": []}

        conn = self._get_conn()
        q = self._sanitize_query(query)
        if not q:
            return {"chapters": [], "entities": [], "worldbuilding": []}

        chapters = []
        try:
            rows = conn.execute(
                "SELECT chapter_id, title, snippet(chapters_fts, 2, '[[', ']]', '...', 40) as snip "
                "FROM chapters_fts WHERE book_id = ? AND chapters_fts MATCH ? ORDER BY rank LIMIT ?",
                (book_id, q, limit),
            ).fetchall()
            chapters = [{"id": r[0], "title": r[1], "snippet": r[2]} for r in rows]
        except sqlite3.OperationalError:
            pass

        entities = []
        try:
            rows = conn.execute(
                "SELECT entity_id, name, type, snippet(entities_fts, 2, '[[', ']]', '...', 40) as snip "
                "FROM entities_fts WHERE book_id = ? AND entities_fts MATCH ? ORDER BY rank LIMIT ?",
                (book_id, q, limit),
            ).fetchall()
            entities = [{"id": r[0], "name": r[1], "type": r[2], "snippet": r[3]} for r in rows]
        except sqlite3.OperationalError:
            pass

        worldbuilding = []
        try:
            rows = conn.execute(
                "SELECT category, entry_title, snippet(worldbuilding_fts, 2, '[[', ']]', '...', 40) as snip "
                "FROM worldbuilding_fts WHERE book_id = ? AND worldbuilding_fts MATCH ? ORDER BY rank LIMIT ?",
                (book_id, q, limit),
            ).fetchall()
            worldbuilding = [{"category": r[0], "title": r[1], "snippet": r[2]} for r in rows]
        except sqlite3.OperationalError:
            pass

        return {"chapters": chapters, "entities": entities, "worldbuilding": worldbuilding}

    def search_entities(self, book_id: str, query: str, limit: int = 10) -> list[dict]:
        result = self.search(book_id, query, limit)
        return result.get("entities", [])

    def search_chapters(self, book_id: str, query: str, limit: int = 10) -> list[dict]:
        result = self.search(book_id, query, limit)
        return result.get("chapters", [])

    @staticmethod
    def _sanitize_query(query: str) -> str:
        q = query.strip().replace("'", "''")
        if not q:
            return ""
        words = q.split()
        if len(words) == 1:
            return f'"{q}"*' if len(q) > 1 else q
        return ' AND '.join(f'"{w}"*' if len(w) > 1 else w for w in words)

    def clear_book(self, book_id: str):
        conn = self._get_conn()
        for table in ("chapters_fts", "entities_fts", "worldbuilding_fts"):
            try:
                conn.execute(f"DELETE FROM {table} WHERE book_id = ?", (book_id,))
            except sqlite3.OperationalError:
                pass
        conn.commit()


fts = FullTextSearch()
