# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Persistent, resumable reference-book analysis jobs.

HTTP requests only enqueue work.  Source chapters are fingerprinted in fixed
batches so an interrupted job can resume without re-reading unchanged input;
each completed analysis dimension is independently cached and retryable.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import uuid
from collections.abc import Callable
from datetime import datetime
from functools import partial
from typing import Any

from core.config import DATA_DIR
from data.json_store import json_store

JOBS_FILE = DATA_DIR / "analyses" / "reference_jobs.json"
DEFAULT_STEPS = [
    "structure",
    "style_fingerprint",
    "sentence_rhythm",
    "rhetoric_density",
    "prophecy_signature",
    "narrative_pov",
    "emotional_curve",
]

_lock = threading.RLock()
_running: dict[str, asyncio.Task] = {}


def _now() -> str:
    return datetime.now().isoformat()


def _load_jobs() -> list[dict]:
    if not JOBS_FILE.exists():
        return []
    try:
        data = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_jobs(jobs: list[dict]) -> None:
    JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = JOBS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(JOBS_FILE)


def _update_job(job_id: str, mutate: Callable[[dict], None]) -> dict:
    with _lock:
        jobs = _load_jobs()
        job = next((item for item in jobs if item.get("id") == job_id), None)
        if not job:
            raise KeyError(job_id)
        mutate(job)
        job["updated_at"] = _now()
        _save_jobs(jobs)
        return dict(job)


def get_job(job_id: str) -> dict | None:
    with _lock:
        job = next((item for item in _load_jobs() if item.get("id") == job_id), None)
        if not job:
            return None
        result = dict(job)
        task = _running.get(job_id)
        if result.get("status") == "running" and (task is None or task.done()):
            result["status"] = "interrupted"
            result["message"] = "应用曾在任务运行时退出，可点击继续从检查点恢复"
        return result


def latest_job(book_id: str, ref_book_id: str) -> dict | None:
    jobs = [
        job for job in _load_jobs()
        if job.get("book_id") == book_id and job.get("ref_book_id") == ref_book_id
    ]
    if not jobs:
        return None
    return get_job(max(jobs, key=lambda item: item.get("created_at", ""))["id"])


def create_job(
    book_id: str,
    ref_book_id: str,
    *,
    steps: list[str] | None = None,
    chunk_size: int = 20,
    force: bool = False,
) -> dict:
    selected = [step for step in (steps or DEFAULT_STEPS) if step in DEFAULT_STEPS]
    if not selected:
        raise ValueError("至少选择一个分析维度")
    job = {
        "id": f"raj_{uuid.uuid4().hex[:12]}",
        "book_id": book_id,
        "ref_book_id": ref_book_id,
        "status": "queued",
        "progress": 0,
        "message": "等待开始",
        "chunk_size": max(5, min(int(chunk_size), 100)),
        "source_chunks": [],
        "source_fingerprint": "",
        "force": bool(force),
        "steps": [{"name": name, "status": "pending", "error": ""} for name in selected],
        "created_at": _now(),
        "updated_at": _now(),
    }
    with _lock:
        jobs = _load_jobs()
        jobs.append(job)
        _save_jobs(jobs[-100:])
    return job


def schedule_job(job_id: str) -> dict:
    task = _running.get(job_id)
    if task and not task.done():
        return get_job(job_id) or {}
    _running[job_id] = asyncio.create_task(run_job(job_id))
    return get_job(job_id) or {}


def _chapter_payloads(ref_book_id: str) -> list[dict[str, str]]:
    payloads = []
    for chapter in json_store.load_chapters(ref_book_id):
        view = json_store._chapter_view(chapter)
        payloads.append({"title": str(view.get("title", "")), "content": str(view.get("content", ""))})
    return payloads


def _chunk_fingerprint(chapters: list[dict[str, str]]) -> str:
    digest = hashlib.sha256()
    for chapter in chapters:
        digest.update(chapter["title"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(chapter["content"].encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _cached(step: str, ref_book_id: str) -> bool:
    if step == "emotional_curve":
        from core.emotion_analyzer import load_emotional_curve

        return bool(load_emotional_curve(ref_book_id))
    from core.reference_analyzer import load_analysis

    return bool(load_analysis(step, ref_book_id))


def _run_step(step: str, ref_book_id: str) -> Any:
    from core.emotion_analyzer import analyze_emotional_curve
    from core.reference_analyzer import (
        analyze_narrative_pov,
        analyze_prophecy_signature,
        analyze_rhetoric_density,
        analyze_sentence_rhythm,
        analyze_structure,
        quantify_style,
    )

    analyzers: dict[str, Callable[[str], Any]] = {
        "structure": analyze_structure,
        "style_fingerprint": quantify_style,
        "sentence_rhythm": analyze_sentence_rhythm,
        "rhetoric_density": analyze_rhetoric_density,
        "prophecy_signature": analyze_prophecy_signature,
        "narrative_pov": analyze_narrative_pov,
        "emotional_curve": analyze_emotional_curve,
    }
    return analyzers[step](ref_book_id)


def _record_chunks(job: dict, *, chunks: list[dict], done: int, total: int) -> None:
    job.update(
        {
            "source_chunks": chunks,
            "progress": min(20, round(done / total * 20)),
            "message": f"已检查输入分块 {done}/{total}",
        }
    )


async def run_job(job_id: str) -> dict:
    job = get_job(job_id)
    if not job:
        raise KeyError(job_id)

    def _start(item: dict) -> None:
        item["status"] = "running"
        item["message"] = "正在建立参考书分块检查点"
        item["error"] = ""

    job = _update_job(job_id, _start)
    try:
        chapters = await asyncio.to_thread(_chapter_payloads, job["ref_book_id"])
        if not chapters:
            raise ValueError("参考书没有章节内容")

        chunk_size = int(job.get("chunk_size", 20))
        chunks: list[dict] = []
        for index, start in enumerate(range(0, len(chapters), chunk_size)):
            batch = chapters[start : start + chunk_size]
            fingerprint = await asyncio.to_thread(_chunk_fingerprint, batch)
            chunks.append(
                {
                    "index": index,
                    "chapter_start": start + 1,
                    "chapter_end": start + len(batch),
                    "fingerprint": fingerprint,
                    "status": "completed",
                }
            )
            _update_job(
                job_id,
                partial(
                    _record_chunks,
                    chunks=list(chunks),
                    done=index + 1,
                    total=(len(chapters) + chunk_size - 1) // chunk_size,
                ),
            )

        source_fingerprint = hashlib.sha256("".join(chunk["fingerprint"] for chunk in chunks).encode()).hexdigest()
        job = get_job(job_id) or job
        source_changed = bool(job.get("source_fingerprint") and job.get("source_fingerprint") != source_fingerprint)

        def _checkpoint(item: dict) -> None:
            item["source_chunks"] = chunks
            item["source_fingerprint"] = source_fingerprint
            if source_changed:
                for step in item.get("steps", []):
                    step.update({"status": "pending", "error": ""})

        _update_job(job_id, _checkpoint)

        steps = (get_job(job_id) or {}).get("steps", [])
        total_steps = max(len(steps), 1)
        for index, step_info in enumerate(steps):
            step = step_info["name"]
            force = bool((get_job(job_id) or {}).get("force")) or source_changed
            if step_info.get("status") in {"completed", "cached"} and not force:
                continue
            if _cached(step, job["ref_book_id"]) and not force:
                _update_job(
                    job_id,
                    partial(
                        _mark_step,
                        name=step,
                        status="cached",
                        error="",
                        progress=20 + round((index + 1) / total_steps * 80),
                    ),
                )
                continue

            _update_job(
                job_id,
                partial(
                    _mark_step,
                    name=step,
                    status="running",
                    error="",
                    progress=20 + round(index / total_steps * 80),
                ),
            )
            try:
                result = await asyncio.to_thread(_run_step, step, job["ref_book_id"])
                if hasattr(result, "chapter_count") and not result.chapter_count:
                    raise ValueError("参考书没有可分析的正文")
            except Exception as exc:
                _update_job(
                    job_id,
                    partial(_fail_step, name=step, error=str(exc)[:300]),
                )
                return get_job(job_id) or {}
            _update_job(
                job_id,
                partial(
                    _mark_step,
                    name=step,
                    status="completed",
                    error="",
                    progress=20 + round((index + 1) / total_steps * 80),
                ),
            )

        def _complete(item: dict) -> None:
            item["status"] = "completed"
            item["progress"] = 100
            item["message"] = "参考书分析全部完成"

        return _update_job(job_id, _complete)
    except Exception as exc:
        error = str(exc)[:300]

        def _fail(item: dict, failure: str = error) -> None:
            item["status"] = "failed"
            item["error"] = failure
            item["message"] = "任务失败，可从检查点重试"

        return _update_job(job_id, _fail)
    finally:
        _running.pop(job_id, None)


def _mark_step(job: dict, name: str, status: str, error: str, progress: int) -> None:
    for step in job.get("steps", []):
        if step.get("name") == name:
            step.update({"status": status, "error": error})
            break
    job["status"] = "running"
    job["progress"] = progress
    job["message"] = f"{name}: {status}"


def _fail_step(job: dict, name: str, error: str) -> None:
    _mark_step(job, name, "failed", error, int(job.get("progress", 0)))
    job["status"] = "failed"
    job["error"] = error
    job["message"] = f"{name} 失败，可点击重试"


def prepare_retry(job_id: str) -> dict:
    def _reset(item: dict) -> None:
        for step in item.get("steps", []):
            if step.get("status") in {"failed", "running"}:
                step.update({"status": "pending", "error": ""})
        item["status"] = "queued"
        item["error"] = ""
        item["message"] = "将从已完成检查点继续"

    return _update_job(job_id, _reset)
