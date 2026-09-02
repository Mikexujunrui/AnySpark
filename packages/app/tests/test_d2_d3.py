"""D2/D3 校园硬能力 e2e（S250）：引用元数据迁移/citation_export/arXiv 导入/LaTeX 导出。"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from anyspark.core.protocol import ToolSpec
from anyspark.core.types import ToolResult
from anyspark.library import LibraryStore
from anyspark.library.connectors import import_arxiv_paper
from anyspark.server.app import build_app


class _FakeModel:
    model_name = "fake"

    def respond(self, messages: list[Any], tools: Any) -> Any:  # pragma: no cover
        raise AssertionError("本测试不应触发模型调用")


def _client() -> TestClient:
    return TestClient(build_app(model=_FakeModel(), db_path=_db()))


def _db() -> Path:
    return Path(tempfile.mkdtemp()) / "t.db"


def _call(impl: Callable[[ToolSpec, dict[str, Any]], ToolResult], **kwargs: Any) -> ToolResult:
    return impl(ToolSpec(name="t", description="t", params=[]), kwargs)


# ---------------------------------------------------------------------------
# cite_meta 迁移与读写（旧库重开幂等）
# ---------------------------------------------------------------------------
def test_store_cite_meta_roundtrip() -> None:
    db = _db()
    store = LibraryStore(str(db))
    book = store.add_book("某论文")
    got_book = store.get_book(book["id"])
    assert got_book is not None
    assert got_book["cite_meta"] is None
    assert got_book["has_cite_meta"] is False
    meta = {"entry_type": "article", "authors": ["张三"], "title": "T", "year": "2024"}
    assert store.set_cite_meta(book["id"], meta) is True
    got = store.get_book(book["id"])
    assert got is not None
    assert got["cite_meta"] == meta
    assert got["has_cite_meta"] is True
    assert store.set_cite_meta("不存在", meta) is False
    # 旧库重开（列已存在的迁移路径）不报错、数据仍在
    store2 = LibraryStore(str(db))
    got2 = store2.get_book(book["id"])
    assert got2 is not None
    assert got2["cite_meta"] == meta


def test_citation_export_tool() -> None:
    """工具：有元数据出规范条目；无元数据诚实降级「待补全」。"""
    from anyspark.server.tools_reference import make_citation_export_implementer

    store = LibraryStore(str(_db()))
    b1 = store.add_book("论文A")
    store.set_cite_meta(
        b1["id"],
        {
            "entry_type": "article",
            "authors": ["Smith, John", "Jane Doe"],
            "title": "Sleep & phones",
            "venue": "Nature",
            "year": "2024",
            "pages": "1-9",
        },
    )
    b2 = store.add_book("裸书B")
    impl = make_citation_export_implementer(store)[1]

    res = _call(impl, library_book_id=b1["id"], style="bibtex")
    assert res.ok
    assert "@article{smith2024sleep," in res.content
    assert "author = {Smith, John and Jane Doe}" in res.content

    res2 = _call(impl, library_book_id=b2["id"])
    assert "待补全" in res2.content
    assert "裸书B" in res2.content

    assert not _call(impl, library_book_id="不存在").ok


def test_citations_http_route() -> None:
    """HTTP：cite-meta 写入 → citations 导出（gbt7714）。"""
    client = _client()
    bid = client.post("/api/library", json={"name": "论文C"}).json()["id"]
    meta = {
        "entry_type": "thesis",
        "degree": "phd",
        "authors": ["李四"],
        "title": "手机依赖研究",
        "venue": "清华大学",
        "year": "2023",
    }
    assert client.post(f"/api/library/{bid}/cite-meta", json=meta).json() == {"ok": True}
    r = client.get(f"/api/library/{bid}/citations?style=gbt7714").json()
    assert r["entry"] == "李四. 手机依赖研究[D]. 清华大学, 2023."
    assert r["note"] == ""
    assert client.get("/api/library/不存在/citations").status_code == 404


# ---------------------------------------------------------------------------
# arXiv 导入（D3）：mock 网络层，验证建书/摘要章节/cite_meta 落全
# ---------------------------------------------------------------------------
def test_import_arxiv_mocked(monkeypatch: Any) -> None:
    from anyspark.library import connectors

    def fake_fetch(raw: str) -> dict[str, Any]:
        assert "2101.00001" in raw
        return {
            "arxiv_id": "2101.00001",
            "meta": {
                "entry_type": "online",
                "authors": ["John Smith", "Jane Doe"],
                "title": "A Study of Phone Dependence and Sleep",
                "venue": "arXiv:2101.00001",
                "year": "2021",
                "doi": "",
                "url": "https://arxiv.org/abs/2101.00001",
                "pdf_url": "https://arxiv.org/pdf/2101.00001",
            },
            "abstract": "We study phone dependence.",
        }

    monkeypatch.setattr(connectors, "fetch_arxiv", fake_fetch)
    store = LibraryStore(str(_db()))
    out = import_arxiv_paper(store, "https://arxiv.org/abs/2101.00001")
    bid = out["book_id"]
    assert (store.root / bid / "00-摘要.md").read_text(encoding="utf-8").startswith("# 摘要")
    final_book = store.get_book(bid)
    assert final_book is not None
    assert final_book["cite_meta"]["title"].startswith("A Study of Phone")


def test_import_arxiv_http_route(monkeypatch: Any) -> None:
    client = _client()

    def fake_fetch(raw: str) -> dict[str, Any]:
        from anyspark.library import connectors as _conn

        aid = _conn._normalize_arxiv_id(raw)  # 保留真实 id 校验（“垃圾”→ ValueError）
        assert aid == "2101.00002"
        return {
            "arxiv_id": "2101.00002",
            "meta": {
                "entry_type": "online",
                "authors": ["Jane Roe"],
                "title": "Route Test Paper",
                "venue": "arXiv:2101.00002",
                "year": "2021",
                "doi": "",
                "url": "https://arxiv.org/abs/2101.00002",
                "pdf_url": "",
            },
            "abstract": "Route level test.",
        }

    # 补丁打在抓取层（fetch_arxiv），保留真实 import 路径（含 id 归一/校验/建书）
    monkeypatch.setattr("anyspark.library.connectors.fetch_arxiv", fake_fetch)
    r = client.post("/api/library/import-arxiv", json={"arxiv_id": "2101.00002"})
    assert r.status_code == 200
    bid = r.json()["book_id"]
    books = {b["id"]: b for b in client.get("/api/library").json()}
    assert books[bid]["has_cite_meta"] is True
    assert client.post("/api/library/import-arxiv", json={}).status_code == 400
    assert client.post("/api/library/import-arxiv", json={"arxiv_id": "垃圾"}).status_code == 400


# ---------------------------------------------------------------------------
# LaTeX 导出（D2）：同库走 HTTP 建章 → format=latex 全链路
# ---------------------------------------------------------------------------
def test_export_latex_route() -> None:
    client = _client()
    chapter = {
        "book_id": "main",
        "title": "第一章 引言&背景",
        "content": "## 数据来源\n\n问卷 (n=200)，显著性 p<0.05_注1。\n\n- 要点甲\n- 要点乙\n",
    }
    created = client.post("/api/chapters", json=chapter).json()
    assert created.get("title"), created
    r = client.get("/api/export/book?format=latex&book_id=main")
    assert r.status_code == 200
    body = r.text
    assert "\\documentclass[UTF8]{ctexart}" in body
    assert "\\section{第一章 引言\\&背景}" in body
    assert "\\subsection{数据来源}" in body
    assert "p<0.05\\_注1" in body
    assert "\\begin{itemize}" in body and "\\item 要点甲" in body
    assert "attachment; filename=book.tex" in r.headers["Content-Disposition"]
