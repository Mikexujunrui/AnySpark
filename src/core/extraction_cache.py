"""Content-fingerprint cache for knowledge extraction.

Re-running whole-book extraction on unchanged chapters previously repeated
the same expensive LLM calls. This cache records only successful chapter
fingerprints; edits naturally invalidate the matching entry.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .config import DATA_DIR


class ExtractionCache:
    def __init__(self, book_id: str):
        safe_id = "".join(char if char.isalnum() or char in "-_" else "_" for char in book_id)
        self.path = DATA_DIR / f"extraction_cache_{safe_id or 'default'}.json"
        self.entries = self._load()

    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def fingerprint(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def is_current(self, chapter_key: str, content: str) -> bool:
        return self.entries.get(str(chapter_key)) == self.fingerprint(content)

    def mark(self, chapter_key: str, content: str) -> None:
        self.entries[str(chapter_key)] = self.fingerprint(content)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = Path(f"{self.path}.tmp")
        temp_path.write_text(json.dumps(self.entries, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.path)
