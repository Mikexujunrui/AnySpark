"""
anyspark.library.store — 书库存储（S86）。

- 书库文件区：data/library/<book_id>/（每书一个目录，章节 md 文件）
- 关联表 book_references（book_id → ref_type+ref_id）：项目可选若干参考书
  （ref_type=library 书库的书 / project 工作区其他项目）
- 参考书只读：本 store 只提供列举/读取，不提供写入章节（导入除外）
"""

from __future__ import annotations

import re
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anyspark.core.db import connect as sqlite_connect

LIBRARY_DIR_NAME = "library"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_name(name: str) -> str:
    """目录/文件名消毒（防穿越；中文书名保留）。"""
    cleaned = re.sub(r"[\\/:*?\"<>|]", "_", name.strip())
    return cleaned or "untitled"


class LibraryStore:
    """书库存储：书 CRUD（文件区）+ 项目-参考书关联（SQLite）+ 只读检索。

    - 书 = 文件区目录 data/library/<id>/，内含 md 章节文件（导入拆章）
    - 元数据（书名/来源/导入时间）+ 关联表存 SQLite
    - 项目的参考书 = 书库的书 + 工作区其他项目（project 类型存 book_id）
    """

    def __init__(self, db_path: str | Path, library_root: str | Path | None = None) -> None:
        self._db = str(db_path)
        root = Path(library_root) if library_root else Path(self._db).parent / LIBRARY_DIR_NAME
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        # S79：连接配置收敛到 core.db.connect
        self._conn = sqlite_connect(self._db)
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS library_books (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'upload',  -- upload(导入) | link(链接目录)
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS book_references (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id TEXT NOT NULL,      -- 正在写的项目
                    ref_type TEXT NOT NULL,     -- library(书库的书) | project(工作区项目)
                    ref_id TEXT NOT NULL,       -- 书库书 id 或项目 book_id
                    created_at TEXT NOT NULL,
                    UNIQUE(book_id, ref_type, ref_id)
                );
                CREATE INDEX IF NOT EXISTS idx_refs_book ON book_references(book_id);
                """
            )
            self._conn.commit()

    # -- 书库 CRUD --
    def add_book(self, name: str) -> dict[str, Any]:
        """新建书库书（空目录，待导入章节文件）。"""
        bid = _safe_name(name) or uuid.uuid4().hex[:8]
        d = self.root / bid
        d.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO library_books (id, name, source, created_at) "
                "VALUES (?,?,?,?)",
                (bid, name, "upload", _now()),
            )
            self._conn.commit()
        return {"id": bid, "name": name, "path": str(d)}

    def list_books(self) -> list[dict[str, Any]]:
        """全部书库书（含章节数）。"""
        out: list[dict[str, Any]] = []
        with self._lock:
            rows = self._conn.execute("SELECT * FROM library_books ORDER BY created_at").fetchall()
            for r in rows:
                d = self.root / r["id"]
                files = sorted(d.glob("*.md")) if d.exists() else []
                out.append(
                    {
                        "id": r["id"],
                        "name": r["name"],
                        "source": r["source"],
                        "chapters": len(files),
                        "created_at": r["created_at"],
                    }
                )
        return out

    def get_book(self, book_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM library_books WHERE id=?", (book_id,)
            ).fetchone()
        if row is None:
            return None
        d = self.root / row["id"]
        files = sorted(d.glob("*.md")) if d.exists() else []
        return {
            "id": row["id"],
            "name": row["name"],
            "source": row["source"],
            "chapters": len(files),
            "created_at": row["created_at"],
        }

    def import_chapter(self, book_id: str, title: str, content: str, order: int = 0) -> Path:
        """导入一章（md 文件，标题做文件名）。"""
        d = self.root / book_id
        d.mkdir(parents=True, exist_ok=True)
        fname = _safe_name(title) + ".md"
        f = d / fname
        f.write_text(f"# {title}\n\n{content}\n", encoding="utf-8")
        return f

    def read_book(self, book_id: str, max_chars: int | None = 200000) -> str:
        """整本书文本（max_chars 截断保护；None = 不截断，供拆书提炼/导入确认）。"""
        d = self.root / book_id
        if not d.exists():
            return ""
        parts: list[str] = []
        total = 0
        for f in sorted(d.glob("*.md")):
            text = f.read_text(encoding="utf-8")
            parts.append(f"【{f.stem}】\n{text}")
            total += len(text)
            if max_chars is not None and total > max_chars:
                break
        return "\n\n".join(parts)

    def delete_book(self, book_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM library_books WHERE id=?", (book_id,))
            self._conn.commit()
            # 清理引用
            self._conn.execute(
                "DELETE FROM book_references WHERE ref_type='library' AND ref_id=?",
                (book_id,),
            )
            self._conn.commit()
        d = self.root / book_id
        if d.exists():
            import shutil

            shutil.rmtree(d, ignore_errors=True)
        return cur.rowcount > 0

    # -- 项目-参考书关联 --
    def set_references(self, book_id: str, refs: list[dict[str, str]]) -> None:
        """设置项目的参考书（全量替换）：refs=[{type: library|project, id: ...}]。"""
        with self._lock:
            self._conn.execute("DELETE FROM book_references WHERE book_id=?", (book_id,))
            for ref in refs:
                rtype = ref.get("type") or "library"
                rid = ref.get("id") or ""
                if not rid:
                    continue
                self._conn.execute(
                    "INSERT OR IGNORE INTO book_references "
                    "(book_id, ref_type, ref_id, created_at) VALUES (?,?,?,?)",
                    (book_id, rtype, rid, _now()),
                )
            self._conn.commit()

    def get_references(self, book_id: str) -> list[dict[str, Any]]:
        """项目的参考书（含可读信息：书名/类型/章节数）。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM book_references WHERE book_id=? ORDER BY rowid",
                (book_id,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            info: dict[str, Any] = {"type": r["ref_type"], "id": r["ref_id"]}
            if r["ref_type"] == "library":
                b = self.get_book(r["ref_id"])
                if b:
                    info.update(
                        {
                            "name": b["name"],
                            "source": "library",
                            "chapters": b["chapters"],
                            "path": str(self.root / r["ref_id"]),
                        }
                    )
                    out.append(info)
            else:  # project 类型：工作区其他项目（book_id 即项目名）
                out.append(
                    {
                        "type": "project",
                        "id": r["ref_id"],
                        "name": r["ref_id"],
                        "source": "project",
                    }
                )
        return out

    def close(self) -> None:
        self._conn.close()
