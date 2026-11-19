"""
anyspark.library.vectors — 书库向量索引（S244，语义检索存储层）。

设计：
- 分块：中文友好——按段落聚合到 ~CHUNK_SIZE 字，段间少量重叠上下文
- 存储：SQLite（与书库元数据同库）——chunk 文本 + float32 BLOB 向量 +
  索引状态（filename/mtime/size），书库规模（千级 chunk）纯 Python 余弦足够
- 增量：按文件 mtime+size 判断跳过未变文件；书删除/文件消失时清残留
- 依赖：无 numpy——1024 维点积纯 Python ~50µs，万级 chunk 检索 <1s
"""

from __future__ import annotations

import struct
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anyspark.core.db import connect as sqlite_connect

CHUNK_SIZE = 500  # 每块目标字数（中文）
CHUNK_OVERLAP = 60  # 相邻块重叠字数（保上下文连贯）
DEFAULT_TOP_K = 8
SCORE_THRESHOLD = 0.25  # 余弦阈值：低于此基本无关（经验值，宁缺毋滥）

_SCHEMA = """
CREATE TABLE IF NOT EXISTS library_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    chunk_idx INTEGER NOT NULL,
    text TEXT NOT NULL,
    dim INTEGER NOT NULL,
    embedding BLOB NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(book_id, filename, chunk_idx)
);
CREATE TABLE IF NOT EXISTS library_index_state (
    book_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    mtime REAL NOT NULL,
    size INTEGER NOT NULL,
    chunks INTEGER NOT NULL,
    dim INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (book_id, filename)
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def pack_vector(vec: list[float]) -> bytes:
    """float 列表 → float32 BLOB（4x 体积省一半，精度对余弦足够）。"""
    return struct.pack(f"<{len(vec)}f", *vec)


def unpack_vector(blob: bytes) -> list[float]:
    return list(struct.unpack(f"<{len(blob) // 4}f", blob))


def cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度（纯 Python；调用方保证等维）。"""
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=True):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / ((na**0.5) * (nb**0.5))  # type: ignore[no-any-return]


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """中文友好分块：按空行分段 → 聚合到目标大小；超长单段硬切带重叠。

    短段聚合保留段落边界（语义完整）；单段超长按 size 硬切并回退 overlap 字，
    避免句子被腰斩后检索片段不可读。
    """
    text = (text or "").strip()
    if not text:
        return []
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for p in paras:
        # 单段超长：硬切（带重叠回退）
        if len(p) > size:
            if buf:
                chunks.append(buf)
                buf = ""
            step = size - overlap
            for i in range(0, len(p), step):
                piece = p[i : i + size]
                chunks.append(piece)
                if i + size >= len(p):
                    break
            continue
        # 聚合：放得下就并，放不下先落一块
        if buf and len(buf) + len(p) + 1 > size:
            chunks.append(buf)
            buf = p
        else:
            buf = f"{buf}\n{p}" if buf else p
    if buf:
        chunks.append(buf)
    return chunks


@dataclass
class _NpCache:
    """numpy 检索缓存（签名失效；S62 风格：dataclass 替代元组魔法索引）。"""

    signature: tuple[int, int]  # (chunk 总数, max id)
    metas: list[tuple[str, str, int, str]]  # (book_id, filename, chunk_idx, text)
    matrix: Any  # np.ndarray (N, dim) float32


class LibraryVectors:
    """书库向量索引：增量索引 + 余弦检索（SQLite 持久化）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._conn = sqlite_connect(str(db_path))
        self._lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._np_cache: _NpCache | None = None
        self._indexing: set[str] = set()  # 在索引的书（防同书并发重入）
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # -- 索引 --

    def index_book_signed(
        self,
        book_id: str,
        signed_files: list[tuple[str, str, float, int]],  # (filename, text, mtime, size)
        embed: Any,
    ) -> dict[str, Any]:
        """增量索引（带文件签名版）。签名未变的文件跳过。

        三阶段分离（S263 锁根治）：读计划（持锁只读）→ embed 网络（不持锁
        不开事务）→ 短事务落库。旧实现在写事务打开期间调 embed（含重试
        退避），WAL 写锁被占数分钟 → 全应用 database is locked（实测事故）。
        网络阶段也不持 _lock：索引期间检索/.drop 不被阻塞。
        """
        # ── 阶段 1：只读计划（签名比对 + 切块 + 残留清单）──
        plan: list[tuple[str, float, int, list[str]]] = []
        skipped = 0
        total_chunks = 0
        seen_files: set[str] = set()
        with self._lock:
            if book_id in self._indexing:
                return {"indexed": 0, "skipped": 0, "chunks": 0, "already_indexing": True}
            self._indexing.add(book_id)
            for filename, text, mtime, size in signed_files:
                seen_files.add(filename)
                st = self._state(book_id, filename)
                if st and st["mtime"] == mtime and st["size"] == size:
                    skipped += 1
                    total_chunks += st["chunks"]
                    continue
                plan.append((filename, mtime, size, chunk_text(text)))
            rows = self._conn.execute(
                "SELECT DISTINCT filename FROM library_index_state WHERE book_id=?",
                (book_id,),
            ).fetchall()
            stale = [fname for (fname,) in rows if fname not in seen_files]
        # ── 阶段 2：网络 embed（无锁无事务；失败抛异常→旧索引保持原样）──
        embedded: list[tuple[str, float, int, list[str], list[Any]]] = []
        try:
            for filename, mtime, size, chunks in plan:
                vecs = embed(chunks) if chunks else []
                embedded.append((filename, mtime, size, chunks, vecs))
        finally:
            with self._lock:
                self._indexing.discard(book_id)
        # ── 阶段 3：短事务落库（清旧 chunk + 写新 + 签名 + 清残留）──
        indexed = 0
        with self._lock:
            for filename, mtime, size, chunks, vecs in embedded:
                self._conn.execute(
                    "DELETE FROM library_chunks WHERE book_id=? AND filename=?",
                    (book_id, filename),
                )
                if chunks:
                    dim = len(vecs[0]) if vecs else 0
                    now = _now()
                    self._conn.executemany(
                        "INSERT OR REPLACE INTO library_chunks"
                        " (book_id, filename, chunk_idx, text, dim, embedding, created_at)"
                        " VALUES (?,?,?,?,?,?,?)",
                        [
                            (book_id, filename, i, c, dim, pack_vector(v), now)
                            for i, (c, v) in enumerate(zip(chunks, vecs, strict=True))
                        ],
                    )
                    self._conn.execute(
                        "INSERT OR REPLACE INTO library_index_state"
                        " (book_id, filename, mtime, size, chunks, dim, updated_at)"
                        " VALUES (?,?,?,?,?,?,?)",
                        (book_id, filename, mtime, size, len(chunks), dim, now),
                    )
                    total_chunks += len(chunks)
                else:
                    self._conn.execute(
                        "DELETE FROM library_index_state WHERE book_id=? AND filename=?",
                        (book_id, filename),
                    )
                indexed += 1
            for fname in stale:
                self._conn.execute(
                    "DELETE FROM library_chunks WHERE book_id=? AND filename=?",
                    (book_id, fname),
                )
                self._conn.execute(
                    "DELETE FROM library_index_state WHERE book_id=? AND filename=?",
                    (book_id, fname),
                )
            self._conn.commit()
        self._invalidate_cache()
        return {"indexed": indexed, "skipped": skipped, "chunks": total_chunks}

    def drop_book(self, book_id: str) -> None:
        self._invalidate_cache()
        with self._lock:
            self._conn.execute("DELETE FROM library_chunks WHERE book_id=?", (book_id,))
            self._conn.execute("DELETE FROM library_index_state WHERE book_id=?", (book_id,))
            self._conn.commit()

    def _invalidate_cache(self) -> None:
        with self._cache_lock:
            self._np_cache = None

    def _state(self, book_id: str, filename: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT mtime, size, chunks, dim FROM library_index_state"
            " WHERE book_id=? AND filename=?",
            (book_id, filename),
        ).fetchone()
        if not row:
            return None
        return {"mtime": row[0], "size": row[1], "chunks": row[2], "dim": row[3]}

    # -- 检索 --

    def search(
        self,
        query_vec: list[float],
        book_ids: list[str] | None = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> list[dict[str, Any]]:
        """余弦检索 top-K（可选限定书范围）。返回 [{book_id, filename, chunk_idx, text, score}]。

        S247：numpy 矩阵化 + 内存缓存——万级 chunk 检索从秒级降到毫秒级。
        缓存以 (chunk 总数, max_id) 为签名，索引变更自动失效重载。
        numpy 不可用时回落纯 Python 逐条计算（正确性一致，量大时较慢）。
        """
        try:
            import numpy as np
        except ImportError:  # pragma: no cover —— 纯 Python 兜底路径
            np = None

        if np is not None:
            q = np.asarray(query_vec, dtype=np.float32)
            cache = self._matrix_cache_np()
            if cache.matrix.shape[0] == 0:
                return []
            mat, metas = cache.matrix, cache.metas
            # 同维过滤（换过 embedding 模型后旧维度 chunk 跳过）
            if len(query_vec) != mat.shape[1]:
                return []
            if book_ids:
                wanted = set(book_ids)  # 循环外建一次（勿在生成器内重建）
                mask = np.fromiter((m[0] in wanted for m in metas), dtype=bool, count=len(metas))
                mat = mat[mask]
                metas = [m for m, keep in zip(metas, mask.tolist(), strict=True) if keep]
                if len(mat) == 0:
                    return []
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            qn = np.linalg.norm(q)
            if qn == 0:
                return []
            scores = (mat @ q) / (norms.ravel() * qn)
            order = np.argsort(scores)[::-1]
            hits: list[dict[str, Any]] = []
            for idx in order[: top_k * 2]:  # 多取一些再过阈值
                s = float(scores[idx])
                if s <= SCORE_THRESHOLD:
                    break
                book_id, filename, chunk_idx, text = metas[idx]
                hits.append(
                    {
                        "book_id": book_id,
                        "filename": filename,
                        "chunk_idx": chunk_idx,
                        "text": text,
                        "score": round(s, 4),
                    }
                )
            return hits[:top_k]

        # 纯 Python 兜底（numpy 缺失时；正确性一致，量大时较慢）
        rows = self._conn.execute(
            "SELECT book_id, filename, chunk_idx, text, embedding FROM library_chunks"
        ).fetchall()
        scored: list[dict[str, Any]] = []
        for book_id, filename, chunk_idx, text, blob in rows:
            vec = unpack_vector(blob)
            if len(vec) != len(query_vec):
                continue  # 维度不符（换过模型）——跳过，重索引后恢复
            score = cosine(query_vec, vec)
            if score > SCORE_THRESHOLD:  # 阈值：低于此基本无关（经验值，宁缺毋滥）
                scored.append(
                    {
                        "book_id": book_id,
                        "filename": filename,
                        "chunk_idx": chunk_idx,
                        "text": text,
                        "score": round(score, 4),
                    }
                )
        scored.sort(key=lambda h: h["score"], reverse=True)
        return scored[:top_k]

    def _matrix_cache_np(self) -> _NpCache:
        """numpy 矩阵内存缓存（S247）：签名 (chunk 数, max id) 变更才重载。

        50K chunk × 1024 维 float32 ≈ 200MB 常驻——书库属长尾增长，
        索引变更频率远低于检索频率，缓存收益显著（免每次拉 200MB blob）。
        """
        import numpy as np

        sig = self._conn.execute(
            "SELECT COUNT(*), COALESCE(MAX(id), 0) FROM library_chunks"
        ).fetchone()
        cached = self._np_cache
        if cached is not None and cached.signature == (sig[0], sig[1]):
            return cached
        rows = self._conn.execute(
            "SELECT id, book_id, filename, chunk_idx, text, embedding FROM library_chunks"
        ).fetchall()
        metas = [(r[1], r[2], r[3], r[4]) for r in rows]
        if rows:
            mat = np.stack([np.frombuffer(r[5], dtype=np.float32) for r in rows])
        else:
            mat = np.zeros((0, 1), dtype=np.float32)
        cache = _NpCache(signature=(sig[0], sig[1]), metas=metas, matrix=mat)
        with self._cache_lock:
            self._np_cache = cache
        return cache

    def stats(self) -> dict[str, Any]:
        """索引概况（书数/chunk 数/维度）。"""
        with self._lock:
            books = self._conn.execute(
                "SELECT COUNT(DISTINCT book_id) FROM library_chunks"
            ).fetchone()[0]
            chunks = self._conn.execute("SELECT COUNT(*) FROM library_chunks").fetchone()[0]
            dim = self._conn.execute("SELECT dim FROM library_chunks LIMIT 1").fetchone()
        return {"books": books, "chunks": chunks, "dim": dim[0] if dim else None}
