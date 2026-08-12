# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Author DNA laboratory API."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.author_dna import (
    LAYER_LABELS,
    add_interpretation,
    build_corpus_map,
    compile_writer_package,
    create_analysis_job,
    delete_interpretation,
    get_author_dna_availability,
    get_evidence_chunk,
    load_state,
    retry_analysis_job,
    save_scene_contract,
    schedule_analysis_job,
    update_interpretation,
    update_layer,
    verify_interpretation,
)

router = APIRouter(tags=["author-dna"])


def _require_author_dna_access(book_id: str) -> None:
    availability = get_author_dna_availability(book_id)
    if not availability["available"]:
        raise HTTPException(403, availability["reason"])


class CorpusMapRequest(BaseModel):
    reference_ids: list[str] | None = None
    chunk_chars: int = Field(default=5000, ge=1800, le=12000)
    batch_size: int = Field(default=3, ge=1, le=6)


class AnalysisJobRequest(BaseModel):
    force: bool = False


class LayerUpdateRequest(BaseModel):
    status: str | None = None
    summary: str | None = None
    rules: list[dict[str, Any]] | None = None
    anti_style: list[dict[str, Any]] | None = None


class InterpretationRequest(BaseModel):
    ref_book_id: str = ""
    statement: str
    classification: str = "unverified"
    confidence: str = "unknown"
    evidence_ids: list[str] = Field(default_factory=list)
    accepted: bool = False


class InterpretationUpdateRequest(BaseModel):
    statement: str | None = None
    classification: str | None = None
    confidence: str | None = None
    evidence_ids: list[str] | None = None
    status: str | None = None
    promoted: bool | None = None


class SceneContractRequest(BaseModel):
    enabled: bool = True
    title: str = ""
    purpose: str = ""
    creative_intent: str = ""
    story_function: str = ""
    pov: str = ""
    start_state: str = ""
    end_state: str = ""
    stop_anchor: str = ""
    beats: list[str] = Field(default_factory=list)
    allowed: list[str] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)
    active_characters: list[str] = Field(default_factory=list)
    relevant_canon: list[str] = Field(default_factory=list)
    new_canon: list[str] = Field(default_factory=list)
    hidden_intent: str = ""
    target_words: int = Field(default=1600, ge=100, le=30000)


@router.get("/books/{book_id}/author-dna")
def get_author_dna(book_id: str):
    _require_author_dna_access(book_id)
    return load_state(book_id)


@router.post("/books/{book_id}/author-dna/corpus")
def create_corpus_map(book_id: str, body: CorpusMapRequest):
    _require_author_dna_access(book_id)
    try:
        return build_corpus_map(
            book_id,
            reference_ids=body.reference_ids,
            chunk_chars=body.chunk_chars,
            batch_size=body.batch_size,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/books/{book_id}/author-dna/evidence/{chunk_id}")
def read_author_dna_evidence(book_id: str, chunk_id: str):
    _require_author_dna_access(book_id)
    chunk = get_evidence_chunk(book_id, chunk_id)
    if not chunk:
        raise HTTPException(404, "证据块不存在；参考书内容可能已经变化")
    return chunk


@router.post("/books/{book_id}/author-dna/jobs")
async def start_author_dna_job(book_id: str, body: AnalysisJobRequest):
    _require_author_dna_access(book_id)
    try:
        job = create_analysis_job(book_id, force=body.force)
        return schedule_analysis_job(book_id, job["id"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/books/{book_id}/author-dna/jobs/{job_id}")
def get_author_dna_job(book_id: str, job_id: str):
    _require_author_dna_access(book_id)
    state = load_state(book_id)
    job = state.get("job", {})
    if job.get("id") != job_id:
        raise HTTPException(404, "作者 DNA 分析任务不存在")
    return job


@router.post("/books/{book_id}/author-dna/jobs/{job_id}/retry")
async def retry_author_dna_job(book_id: str, job_id: str):
    _require_author_dna_access(book_id)
    try:
        retry_analysis_job(book_id, job_id)
    except KeyError as exc:
        raise HTTPException(404, "作者 DNA 分析任务不存在") from exc
    return schedule_analysis_job(book_id, job_id)


@router.put("/books/{book_id}/author-dna/layers/{layer_key}")
def put_author_dna_layer(book_id: str, layer_key: str, body: LayerUpdateRequest):
    _require_author_dna_access(book_id)
    if layer_key not in LAYER_LABELS:
        raise HTTPException(404, "作者 DNA 层不存在")
    try:
        return update_layer(book_id, layer_key, body.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/books/{book_id}/author-dna/interpretations")
def create_author_interpretation(book_id: str, body: InterpretationRequest):
    _require_author_dna_access(book_id)
    try:
        return add_interpretation(book_id, body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.put("/books/{book_id}/author-dna/interpretations/{entry_id}")
def put_author_interpretation(book_id: str, entry_id: str, body: InterpretationUpdateRequest):
    _require_author_dna_access(book_id)
    try:
        return update_interpretation(book_id, entry_id, body.model_dump(exclude_none=True))
    except KeyError as exc:
        raise HTTPException(404, "用户解读不存在") from exc


@router.post("/books/{book_id}/author-dna/interpretations/{entry_id}/verify")
async def verify_author_interpretation(book_id: str, entry_id: str):
    _require_author_dna_access(book_id)
    try:
        return await asyncio.to_thread(verify_interpretation, book_id, entry_id)
    except KeyError as exc:
        raise HTTPException(404, "用户解读不存在") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/books/{book_id}/author-dna/interpretations/{entry_id}")
def remove_author_interpretation(book_id: str, entry_id: str):
    _require_author_dna_access(book_id)
    if not delete_interpretation(book_id, entry_id):
        raise HTTPException(404, "用户解读不存在")
    return {"ok": True}


@router.put("/books/{book_id}/author-dna/scene-contract")
def put_scene_contract(book_id: str, body: SceneContractRequest):
    _require_author_dna_access(book_id)
    return save_scene_contract(book_id, body.model_dump())


@router.post("/books/{book_id}/author-dna/writer-package")
def create_writer_package(book_id: str, body: SceneContractRequest | None = None):
    _require_author_dna_access(book_id)
    return compile_writer_package(book_id, body.model_dump() if body else None)
