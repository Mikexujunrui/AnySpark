"""S244：书库 RAG——分块/向量索引/混合检索测试（fake embedder，无网络）。"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from anyspark.library import LibraryStore
from anyspark.library.embedding import EmbeddingClient
from anyspark.library.search import search_library_hybrid, search_library_keyword
from anyspark.library.vectors import LibraryVectors, chunk_text, cosine


def _store() -> LibraryStore:
    d = Path(tempfile.mkdtemp())
    return LibraryStore(d / "lib.db", library_root=d / "library")


class FakeEmbedder:
    """确定性 fake embedder：文本哈希 → 固定维度向量（相似词共现→相似向量）。

    规则：向量 [出现'a'次数, 出现'b'次数, 出现'c'次数, 1] 归一化省略——
    测试用余弦只比较方向，共现结构即可区分语义远近。
    """

    available = True
    model = "fake-embed"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            out.append([
                float(t.count("魔法")),
                float(t.count("剑")),
                float(t.count("行会")),
                float(t.count("权力")),
                1.0,
            ])
        return out


def _seed_library(ls: LibraryStore) -> None:
    ls.add_book("魔法之书")
    ls.import_chapter("魔法之书", "第一章", "少年握紧法杖，魔法的光辉照亮了塔顶。" * 3)
    ls.import_chapter("魔法之书", "第二章", "剑与魔法交织的年代，骑士团向王座进发。")
    ls.add_book("市井之书")
    ls.import_chapter("市井之书", "第一章", "行会的权力斗争从未停歇，商人们明争暗斗。")


# ---------------------------------------------------------------------------
# 分块
# ---------------------------------------------------------------------------


def test_chunk_text_merges_short_paragraphs() -> None:
    """短段落聚合到目标大小，保留段落边界。"""
    paras = [f"第{i}段，" + "内容" * 20 for i in range(10)]
    chunks = chunk_text("\n".join(paras), size=200, overlap=30)
    assert len(chunks) >= 2
    assert all(len(c) <= 260 for c in chunks)  # 允许略超（单段不超 size 时）


def test_chunk_text_hard_splits_long_paragraph() -> None:
    """超长单段硬切：块数覆盖全文 + 相邻块有重叠。"""
    text = "字" * 1500
    chunks = chunk_text(text, size=500, overlap=60)
    assert sum(len(c) for c in chunks) >= 1500  # 重叠导致总长 >= 原文
    assert all(len(c) <= 500 for c in chunks)


def test_chunk_text_empty() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n  \n ") == []


# ---------------------------------------------------------------------------
# 余弦
# ---------------------------------------------------------------------------


def test_cosine_basic() -> None:
    assert abs(cosine([1, 0], [1, 0]) - 1.0) < 1e-9
    assert abs(cosine([1, 0], [0, 1])) < 1e-9
    assert abs(cosine([1, 0], [-1, 0]) + 1.0) < 1e-9
    assert cosine([0, 0], [1, 1]) == 0.0  # 零向量防护


# ---------------------------------------------------------------------------
# 向量索引：增量 + 检索
# ---------------------------------------------------------------------------


def _vec_db() -> str:
    return str(Path(tempfile.mkdtemp()) / "vec.db")


def test_index_and_semantic_search() -> None:
    """索引后语义检索：相关 chunk 得分高于无关 chunk。"""
    ls = _store()
    _seed_library(ls)
    vecs = LibraryVectors(_vec_db())
    emb = FakeEmbedder()
    files = ls.iter_book_files("魔法之书")
    r = vecs.index_book_signed("魔法之书", files, emb.embed)
    assert r["indexed"] == 2 and r["chunks"] >= 2

    # 查询"魔法" → 魔法之书的 chunk 命中
    qvec = emb.embed(["魔法的光辉"])[0]
    hits = vecs.search(qvec)
    assert len(hits) > 0
    assert all(h["book_id"] == "魔法之书" for h in hits)
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)  # 降序


def test_incremental_index_skips_unchanged() -> None:
    """签名未变的文件跳过（mtime/size 相同），变更的重索引。"""
    import time

    ls = _store()
    ls.add_book("书")
    ls.import_chapter("书", "第一章", "魔法初现。")
    vecs = LibraryVectors(_vec_db())
    emb = FakeEmbedder()

    files1 = ls.iter_book_files("书")
    r1 = vecs.index_book_signed("书", files1, emb.embed)
    assert r1["indexed"] == 1

    # 未变更 → 全跳过
    files2 = ls.iter_book_files("书")
    r2 = vecs.index_book_signed("书", files2, emb.embed)
    assert r2["skipped"] == 1 and r2["indexed"] == 0

    # 变更内容（新增一章）→ 只重索引新文件（旧文件签名未变跳过），chunk 总数 >= 2
    time.sleep(0.02)
    ls.import_chapter("书", "第二章", "新的魔法篇章。")
    files3 = ls.iter_book_files("书")
    r3 = vecs.index_book_signed("书", files3, emb.embed)
    assert r3["indexed"] == 1 and r3["skipped"] == 1 and r3["chunks"] >= 2


def test_stale_file_chunks_cleaned() -> None:
    """文件消失后残留索引被清理。"""
    ls = _store()
    ls.add_book("书")
    ls.import_chapter("书", "第一章", "魔法初现。")
    ls.import_chapter("书", "第二章", "剑指苍穹。")
    vecs = LibraryVectors(_vec_db())
    emb = FakeEmbedder()
    vecs.index_book_signed("书", ls.iter_book_files("书"), emb.embed)
    st = vecs.stats()
    assert st["chunks"] >= 2

    # 删一章再增量索引 → 残留清掉
    import os

    d = ls.root / "书"
    target = d / "第二章.md"
    os.remove(target)
    vecs.index_book_signed("书", ls.iter_book_files("书"), emb.embed)
    st2 = vecs.stats()
    assert st2["chunks"] < st["chunks"]


def test_dimension_mismatch_skipped() -> None:
    """换过 embedding 模型（维度变化）→ 旧 chunk 跳过不报错。"""

    class DimShift(FakeEmbedder):
        _shifted = False

        def embed(self, texts: list[str]) -> list[list[float]]:
            base = super().embed(texts)
            if getattr(self, "_shifted", False):
                return [[*v, 0.5] for v in base]  # 多一维
            return base

    ls = _store()
    _seed_library(ls)
    vecs = LibraryVectors(_vec_db())
    emb = DimShift()
    vecs.index_book_signed("魔法之书", ls.iter_book_files("魔法之书"), emb.embed)

    emb._shifted = True  # 查询时维度不符
    qvec = emb.embed(["魔法"])[0]
    hits = vecs.search(qvec)  # 应全部跳过，不抛异常
    assert hits == []


# ---------------------------------------------------------------------------
# 混合检索
# ---------------------------------------------------------------------------


def test_hybrid_search_both_channels() -> None:
    """混合检索：语义 + 关键词双通道都有结果。"""
    ls = _store()
    _seed_library(ls)
    vecs = LibraryVectors(_vec_db())
    emb = FakeEmbedder()
    for bid in ("魔法之书", "市井之书"):
        vecs.index_book_signed(bid, ls.iter_book_files(bid), emb.embed)

    res = search_library_hybrid(ls, vecs, emb, "行会权力", top_k=5)
    assert res["degraded"] is False
    assert len(res["semantic"]) > 0  # 语义通道：行会/权力共现
    assert any(h["book_name"] == "市井之书" for h in res["semantic"])
    assert not res["keyword"]  # 无精确"行会权力"连写 → 关键词通道空

    # 精确词 → 关键词通道也命中
    res2 = search_library_hybrid(ls, vecs, emb, "行会")
    assert len(res2["keyword"]) > 0
    assert res2["keyword"][0]["book_name"] == "市井之书"


def test_hybrid_degrades_without_embedder() -> None:
    """embedding 未配置 → 降级纯关键词（degraded=True，不报错）。"""
    ls = _store()
    _seed_library(ls)
    res = search_library_hybrid(ls, None, None, "魔法")
    assert res["degraded"] is True
    assert res["semantic"] == []
    assert len(res["keyword"]) > 0


def test_hybrid_empty_query() -> None:
    ls = _store()
    res = search_library_hybrid(ls, None, None, "  ")
    assert res == {
        "query": "",
        "semantic": [],
        "keyword": [],
        "degraded": False,
        "indexed_chunks": 0,
    }


def test_keyword_search_whole_library() -> None:
    """全书库关键词检索（不限于项目参考书——区别于 search_reference_books）。"""
    ls = _store()
    _seed_library(ls)
    hits = search_library_keyword(ls, "骑士")
    assert len(hits) == 1
    assert hits[0]["book_name"] == "魔法之书"


# ---------------------------------------------------------------------------
# Embedding 客户端配置解析
# ---------------------------------------------------------------------------


def test_embedding_client_unavailable_without_key(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("EMBEDDING_BASE_URL", raising=False)
    monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    c = EmbeddingClient()
    assert c.available is False


def test_embedding_client_falls_back_to_deepseek_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
    monkeypatch.delenv("EMBEDDING_BASE_URL", raising=False)
    monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
    c = EmbeddingClient()
    assert c.available is True
    assert c.model == "text-embedding-v3"  # 默认模型


def test_embedding_batching(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """25 条文本 → 3 次 API 调用（batch=10），顺序保真。"""
    calls: list[int] = []

    class FakeResp:
        status_code = 200

        def __init__(self, inputs: list[str]) -> None:
            self._inputs = inputs

        def json(self) -> dict[str, Any]:
            calls.append(len(self._inputs))
            # embedding 编码全局序号（从文本 t<N> 解析）——验证跨批顺序保真
            return {
                "data": [
                    {"index": i, "embedding": [float(n[1:])] * 4}
                    for i, n in enumerate(self._inputs)
                ]
            }

    class FakeClient:
        def post(self, url: str, json: Any, headers: Any) -> FakeResp:
            return FakeResp(json["input"])

    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
    c = EmbeddingClient()
    c._client = FakeClient()  # type: ignore[assignment]
    out = c.embed([f"t{i}" for i in range(25)])
    assert len(out) == 25
    assert calls == [10, 10, 5]  # 分批正确
    assert out[24] == [24.0, 24.0, 24.0, 24.0]  # 顺序保真（按 index 排序）
