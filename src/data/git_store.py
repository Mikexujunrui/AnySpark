# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""GitStore — Git-based chapter and version management using pygit2.

Replaces JSON-based version arrays with Git commits.
Each book has a Git repo at DATA_DIR/repos/{book_id}/.git
Each chapter is a file on disk: chapters/{chapter_id}.md
Git content is managed via pure object model (no working tree).
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path

from core.config import DATA_DIR, config
from core.errors import NotFoundError

logger = logging.getLogger(__name__)

REPOS_DIR = DATA_DIR / "repos"

try:
    import pygit2

    _GIT_AVAILABLE = True
except ImportError:
    _GIT_AVAILABLE = False
    logger.warning("pygit2 not installed, GitStore unavailable. Install: pip install pygit2")


class GitStore:
    def __init__(self, book_id: str = "default"):
        self.book_id = book_id
        self._repo_path = (REPOS_DIR / book_id).resolve()
        self._git_dir = self._repo_path / ".git"
        self._lock = threading.RLock()
        self._ensure_repo()

    def _ensure_repo(self):
        with self._lock:
            self._repo_path.mkdir(parents=True, exist_ok=True)
            if not self._git_dir.exists():
                (self._repo_path / "chapters").mkdir(exist_ok=True)
                pygit2.init_repository(str(self._git_dir), True)

    def _repo_open(self):
        if not _GIT_AVAILABLE:
            raise RuntimeError("pygit2 not installed")
        return pygit2.Repository(str(self._git_dir))

    def _chapter_file(self, chapter_id: str) -> str:
        return f"chapters/{chapter_id}.md"

    def _chapter_content_path(self, chapter_id: str) -> Path:
        return self._repo_path / self._chapter_file(chapter_id)

    def _chapter_meta_path(self, chapter_id: str) -> Path:
        return self._repo_path / "chapters" / f"{chapter_id}.meta.json"

    def _read_meta(self, chapter_id: str) -> dict:
        mp = self._chapter_meta_path(chapter_id)
        if mp.exists():
            import json

            return json.loads(mp.read_text(encoding="utf-8"))
        return {"status": "draft", "is_extra": False}

    def _write_meta(self, chapter_id: str, meta: dict):
        mp = self._chapter_meta_path(chapter_id)
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(json.dumps(meta), encoding="utf-8")

    def set_chapter_status(self, chapter_id: str, status: str) -> dict:
        self._check_git()
        meta = self._read_meta(chapter_id)
        meta["status"] = status
        self._write_meta(chapter_id, meta)
        ch = self.get_chapter(chapter_id)
        ch["status"] = status
        return ch

    def _commit(self, message: str) -> str:
        repo = self._repo_open()
        sig = pygit2.Signature("NovelAgent", "agent@novel.local")

        try:
            base_tree = repo.head.peel().tree
        except Exception:
            base_tree = None

        tb = repo.TreeBuilder()
        sub_dirs: dict[str, pygit2.TreeBuilder] = {}

        for f in sorted(self._repo_path.rglob("*.md")):
            rel = str(f.relative_to(self._repo_path)).replace("\\", "/")
            if "/" in rel:
                dir_name, file_name = rel.split("/", 1)
                if dir_name not in sub_dirs:
                    src = None
                    if base_tree:
                        try:
                            src = base_tree[dir_name].id
                        except KeyError:
                            pass
                    sub_dirs[dir_name] = repo.TreeBuilder(src) if src else repo.TreeBuilder()
                sub_dirs[dir_name].insert(file_name, repo.create_blob(f.read_bytes()), pygit2.GIT_FILEMODE_BLOB)
            else:
                tb.insert(rel, repo.create_blob(f.read_bytes()), pygit2.GIT_FILEMODE_BLOB)

        for dir_name, dir_tb in sub_dirs.items():
            tb.insert(dir_name, dir_tb.write(), pygit2.GIT_FILEMODE_TREE)

        tree_oid = tb.write()
        parents = []
        try:
            parents = [repo.head.target]
        except Exception:
            pass

        commit_oid = repo.create_commit(None, sig, sig, message, tree_oid, parents)
        try:
            repo.head.set_target(commit_oid)
        except Exception:
            pass
        return str(commit_oid)

    def _check_git(self):
        if not _GIT_AVAILABLE:
            raise RuntimeError("pygit2 not installed. Run: pip install pygit2")

    # ── Chapter CRUD ──

    def add_chapter(self, title: str, content: str, status: str = "draft") -> dict:
        self._check_git()
        ch_id = str(int(datetime.now().timestamp() * 1000))
        path = self._chapter_content_path(ch_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {title}\n\n{content[: config.storage.max_chapter_chars]}", encoding="utf-8")

        oid = self._commit(f"create: {title}")
        # Store metadata alongside content
        meta_path = self._chapter_meta_path(ch_id)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps({"status": status, "is_extra": False}), encoding="utf-8")
        return {
            "id": ch_id,
            "title": title,
            "content": content,
            "current_version": oid,
            "version_count": 1,
            "status": status,
        }

    def edit_chapter(self, chapter_id: str, content: str, title: str = None, message: str = "edit") -> dict:
        self._check_git()
        path = self._chapter_content_path(chapter_id)
        if not path.exists():
            raise NotFoundError(f"chapter not found: {chapter_id}")
        if title is None:
            old = path.read_text(encoding="utf-8")
            title = old.split("\n")[0].lstrip("# ").strip() or "chapter"

        path.write_text(f"# {title}\n\n{content[: config.storage.max_chapter_chars]}", encoding="utf-8")
        oid = self._commit(message)
        return {"id": chapter_id, "title": title, "content": content, "current_version": oid, "version_count": -1}

    def get_chapter(self, chapter_id: str) -> dict:
        self._check_git()
        path = self._chapter_content_path(chapter_id)
        if not path.exists():
            raise NotFoundError(f"chapter not found: {chapter_id}")
        md = path.read_text(encoding="utf-8")
        lines = md.split("\n")
        title = lines[0].lstrip("# ").strip() if lines else "chapter"
        content = "\n".join(lines[2:]) if len(lines) > 2 else ""
        return {"id": chapter_id, "title": title, "content": content}

    def delete_chapter(self, chapter_id: str) -> bool:
        self._check_git()
        path = self._chapter_content_path(chapter_id)
        if not path.exists():
            return False
        path.unlink()
        self._commit(f"delete: {chapter_id}")
        return True

    def list_chapters(self) -> list[dict]:
        self._check_git()
        chapters_dir = self._repo_path / "chapters"
        if not chapters_dir.exists():
            return []
        chapters = []
        for f in sorted(chapters_dir.glob("*.md")):
            md = f.read_text(encoding="utf-8")
            lines = md.split("\n")
            title = lines[0].lstrip("# ").strip() if lines else f.stem
            content = "\n".join(lines[2:]) if len(lines) > 2 else ""
            chapters.append({"id": f.stem, "title": title, "content": content})
        return chapters

    # ── Version History ──

    def chapter_history(self, chapter_id: str) -> list[dict]:
        self._check_git()
        file_path = self._chapter_file(chapter_id)
        repo = self._repo_open()
        history = []
        try:
            walker = repo.walk(repo.head.target)
            for commit in walker:
                try:
                    commit.tree[file_path]
                except KeyError:
                    continue
                history.append(
                    {
                        "id": str(commit.id),
                        "message": commit.message.strip() if commit.message else "",
                        "timestamp": datetime.fromtimestamp(commit.committer.time).isoformat(),
                        "word_count": 0,
                        "is_current": len(history) == 0,
                    }
                )
        except Exception:
            pass
        return history

    def revert_chapter(self, chapter_id: str, version_id: str) -> dict:
        self._check_git()
        file_path = self._chapter_file(chapter_id)
        repo = self._repo_open()
        try:
            commit = repo.get(pygit2.Oid(hex=version_id))
            blob = commit.tree[file_path]
            content = repo[blob.id].data.decode("utf-8")
        except Exception as e:
            raise NotFoundError(f"version not found: {str(e)[:60]}")

        path = self._chapter_content_path(chapter_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

        oid = self._commit(f"revert to {version_id[:8]}")
        lines = content.split("\n")
        title = lines[0].lstrip("# ").strip() if lines else "chapter"
        return {"id": chapter_id, "title": title, "content": content, "current_version": oid}

    def diff_chapters(self, chapter_id: str, version_a: str, version_b: str = "") -> str:
        self._check_git()
        repo = self._repo_open()
        try:
            a = repo.revparse_single(version_a)
            b = repo.revparse_single(version_b) if version_b else repo.head.peel()
            diff = repo.diff(a, b)
            return diff.patch or "(no diff)"
        except Exception as e:
            return f"diff error: {str(e)[:80]}"


def get_store(book_id: str, backend: str = ""):
    if _GIT_AVAILABLE and (REPOS_DIR / book_id / ".git").exists():
        return GitStore(book_id)
    if backend == "git" and _GIT_AVAILABLE:
        return GitStore(book_id)
    from data.json_store import json_store

    return json_store
