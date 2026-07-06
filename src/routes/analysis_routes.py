# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Reference work analysis REST API — trigger and fetch analysis reports.

Endpoints:
  POST /api/books/{book_id}/analyses/structure?ref_book_id=...
  POST /api/books/{book_id}/analyses/style?ref_book_id=...
  GET  /api/books/{book_id}/analyses/structure?ref_book_id=...
  GET  /api/books/{book_id}/analyses/style?ref_book_id=...
  GET  /api/books/{book_id}/analyses  — list all cached analyses for the book's refs
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from core.reference_analyzer import (
    analyze_structure,
    load_analysis,
    quantify_style,
)
from data.json_store import json_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analysis"])


def _resolve_ref_book_id(book_id: str, ref_book_id: str | None) -> str:
    """Resolve the reference book ID from query param or the book's first ref."""
    if ref_book_id:
        return ref_book_id
    ref_ids = json_store.get_reference_books(book_id)
    if not ref_ids:
        raise HTTPException(400, "当前项目没有参考书。先用 set_reference_books 设置。")
    return ref_ids[0]


# ── Structure analysis ───────────────────────────────────────────────────


@router.post("/books/{book_id}/analyses/structure")
async def trigger_structure_analysis(book_id: str, ref_book_id: str | None = None):
    """Run structural analysis on a reference book. Results are cached."""
    target_ref = _resolve_ref_book_id(book_id, ref_book_id)
    try:
        report = analyze_structure(target_ref)
    except Exception as e:
        logger.exception("Structure analysis failed for %s", target_ref)
        raise HTTPException(500, f"分析失败: {str(e)[:100]}")

    if not report.chapter_count:
        raise HTTPException(400, f"参考书 {target_ref} 没有章节内容，无法分析。")

    return report.to_dict()


@router.get("/books/{book_id}/analyses/structure")
def get_structure_analysis(book_id: str, ref_book_id: str | None = None):
    """Get cached structural analysis report. Returns 404 if not yet analyzed."""
    target_ref = _resolve_ref_book_id(book_id, ref_book_id)
    cached = load_analysis("structure", target_ref)
    if not cached:
        raise HTTPException(404, "尚未分析。请先 POST 触发分析。")
    return cached


# ── Style quantification ─────────────────────────────────────────────────


@router.post("/books/{book_id}/analyses/style")
async def trigger_style_analysis(book_id: str, ref_book_id: str | None = None):
    """Run style quantification on a reference book. Results are cached."""
    target_ref = _resolve_ref_book_id(book_id, ref_book_id)
    try:
        fingerprint = quantify_style(target_ref)
    except Exception as e:
        logger.exception("Style analysis failed for %s", target_ref)
        raise HTTPException(500, f"分析失败: {str(e)[:100]}")

    if not fingerprint.sentence_length_distribution:
        raise HTTPException(400, f"参考书 {target_ref} 没有章节内容，无法分析。")

    return fingerprint.to_dict()


@router.get("/books/{book_id}/analyses/style")
def get_style_analysis(book_id: str, ref_book_id: str | None = None):
    """Get cached style fingerprint. Returns 404 if not yet analyzed."""
    target_ref = _resolve_ref_book_id(book_id, ref_book_id)
    cached = load_analysis("style_fingerprint", target_ref)
    if not cached:
        raise HTTPException(404, "尚未分析。请先 POST 触发分析。")
    return cached


# ── List all analyses for a book's references ────────────────────────────


@router.get("/books/{book_id}/analyses")
def list_analyses(book_id: str):
    """List all cached analysis reports for the book's reference books."""
    ref_ids = json_store.get_reference_books(book_id)
    results: list[dict] = []
    for ref_id in ref_ids:
        entry: dict = {"ref_book_id": ref_id}
        structure = load_analysis("structure", ref_id)
        if structure:
            entry["structure"] = {
                "chapter_count": structure.get("chapter_count", 0),
                "total_words": structure.get("total_words", 0),
                "avg_chapter_length": structure.get("avg_chapter_length", 0),
                "avg_dialogue_ratio": structure.get("avg_dialogue_ratio", 0),
            }
        style = load_analysis("style_fingerprint", ref_id)
        if style:
            entry["style_fingerprint"] = {
                "vocabulary_richness_ttr": style.get("vocabulary_richness_ttr", 0),
                "dialogue_density": style.get("dialogue_density", 0),
                "four_char_idiom_density": style.get("four_char_idiom_density", 0),
            }
        if "structure" in entry or "style_fingerprint" in entry:
            results.append(entry)
    return {"analyses": results}
