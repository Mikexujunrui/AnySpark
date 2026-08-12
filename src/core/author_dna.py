# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Evidence-backed author-DNA analysis and scene-package compilation.

The existing reference analyzer measures prose statistics.  This module adds
the missing semantic layer while keeping model conclusions reviewable:

* source text is divided into stable evidence chunks;
* one extraction pass records six-layer observations with chunk IDs;
* each layer is synthesized independently and remains ``needs_review``;
* only user-accepted rules are injected into writing prompts;
* reader interpretations and continuation canon are stored separately;
* an active scene contract exposes only the current scene to the prose model.

Long-running analysis is checkpointed after every model call, so reopening the
application never requires starting an expensive corpus run from zero.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config import DATA_DIR
from core.settings import get_settings
from core.utils import safe_json_parse
from data.json_store import json_store

DNA_DIR = DATA_DIR / "analyses" / "author_dna"
DNA_DIR.mkdir(parents=True, exist_ok=True)

LAYER_LABELS: dict[str, str] = {
    "story_engine": "故事发动机",
    "character_engine": "人物行为",
    "scene_grammar": "场景语法",
    "narrative_camera": "叙事镜头",
    "prose_style": "文字风格",
    "rhythm_pacing": "节奏与展开倍率",
}

_lock = threading.RLock()
_running: dict[str, asyncio.Task] = {}


class AuthorDnaUnavailableError(RuntimeError):
    """Raised between checkpoints when the user disables the experiment."""


def get_author_dna_availability(book_id: str) -> dict[str, Any]:
    """Return both opt-in gates without mutating preserved experiment data."""

    settings = get_settings()
    globally_enabled = bool((settings.experimental_features or {}).get("author_dna_lab", False))
    try:
        book = json_store.get_book(book_id)
        project_type = str(book.get("projectType", "original"))
    except Exception:
        project_type = "missing"
    continuation_project = project_type == "continuation"
    return {
        "available": globally_enabled and continuation_project,
        "globally_enabled": globally_enabled,
        "project_type": project_type,
        "continuation_project": continuation_project,
        "reason": (
            ""
            if globally_enabled and continuation_project
            else "请先在设置 → 实验性功能中开启作者 DNA 实验室"
            if not globally_enabled
            else "作者 DNA 实验室只对标记为续写的项目开放"
        ),
    }


def _ensure_author_dna_available(book_id: str) -> None:
    availability = get_author_dna_availability(book_id)
    if not availability["available"]:
        raise AuthorDnaUnavailableError(str(availability["reason"]))


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_book_id(book_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", book_id)[:120]


def _state_path(book_id: str) -> Path:
    return DNA_DIR / f"author_dna_{_safe_book_id(book_id)}.json"


def _empty_layer(key: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": LAYER_LABELS[key],
        "status": "pending",
        "summary": "",
        "rules": [],
        "anti_style": [],
        "evidence_ids": [],
        "updated_at": "",
    }


def _empty_state(book_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "book_id": book_id,
        "corpus": {
            "status": "empty",
            "signature": "",
            "reference_ids": [],
            "total_chars": 0,
            "total_chapters": 0,
            "total_chunks": 0,
            "estimated_calls": 0,
            "coverage": [],
            "chunks": [],
        },
        "layers": {key: _empty_layer(key) for key in LAYER_LABELS},
        "observations": [],
        "audit": {"status": "pending", "passed": False, "conflicts": [], "warnings": []},
        "interpretations": [],
        "scene_contract": {"enabled": False},
        "job": {"status": "none", "progress": 0, "message": "尚未开始"},
        "updated_at": _now(),
    }


def load_state(book_id: str) -> dict[str, Any]:
    path = _state_path(book_id)
    with _lock:
        if not path.exists():
            return _empty_state(book_id)
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _empty_state(book_id)
    state = _empty_state(book_id)
    if isinstance(loaded, dict):
        state.update(loaded)
        saved_layers = loaded.get("layers", {})
        state["layers"] = {
            key: {**_empty_layer(key), **(saved_layers.get(key, {}) if isinstance(saved_layers, dict) else {})}
            for key in LAYER_LABELS
        }
    job = state.get("job", {})
    if job.get("status") == "running":
        job_id = str(job.get("id", ""))
        task = _running.get(job_id)
        if not task or task.done():
            job["status"] = "interrupted"
            job["message"] = "应用曾在分析时退出，可从检查点继续"
    return state


def save_state(book_id: str, state: dict[str, Any]) -> dict[str, Any]:
    state["book_id"] = book_id
    state["updated_at"] = _now()
    path = _state_path(book_id)
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    return state


def _split_content(content: str, target_chars: int) -> list[tuple[int, int]]:
    """Split at paragraph boundaries while retaining exact source offsets."""

    if not content.strip():
        return []
    target_chars = max(1800, min(int(target_chars), 12000))
    ranges: list[tuple[int, int]] = []
    start = 0
    length = len(content)
    while start < length:
        ideal = min(length, start + target_chars)
        if ideal < length:
            floor = start + max(800, int(target_chars * 0.62))
            split = content.rfind("\n", floor, ideal + 1)
            if split <= start:
                split = ideal
        else:
            split = length
        while split < length and content[split] == "\n":
            split += 1
        if split <= start:
            split = min(length, start + target_chars)
        ranges.append((start, split))
        start = split
    return ranges


def _reference_sources(book_id: str, requested: list[str] | None = None) -> list[str]:
    configured = json_store.get_reference_books(book_id) or []
    profiles = json_store.get_reference_profiles(book_id)
    if requested:
        invalid = [ref_id for ref_id in requested if ref_id not in configured]
        if invalid:
            raise ValueError("只能分析当前项目已添加的参考书")
        return list(dict.fromkeys(requested))
    # A canon-only reference may be a different author.  Do not silently use
    # it as style evidence unless the user explicitly selects it.
    selected = [ref_id for ref_id in configured if profiles.get(ref_id, "style") in {"style", "both"}]
    return selected


def build_corpus_map(
    book_id: str,
    *,
    reference_ids: list[str] | None = None,
    chunk_chars: int = 5000,
    batch_size: int = 3,
) -> dict[str, Any]:
    ref_ids = _reference_sources(book_id, reference_ids)
    if not ref_ids:
        raise ValueError("没有可用于作者 DNA 的文风参考书；请先添加参考书并设为“只学文风”或“文风＋设定”")

    chunks: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    signature = hashlib.sha256()
    total_chars = 0
    total_chapters = 0

    for ref_id in ref_ids:
        try:
            ref_book = json_store.get_book(ref_id)
        except Exception as exc:
            raise ValueError(f"参考书不存在：{ref_id}") from exc
        chapters = [ch for ch in json_store.load_chapters(ref_id) if not ch.get("is_extra")]
        views = [json_store._chapter_view(ch) for ch in chapters]
        work_total = sum(len(str(view.get("content", ""))) for view in views)
        if work_total <= 0:
            continue
        work_cursor = 0
        quartile_counts = {"0-25%": 0, "25-50%": 0, "50-75%": 0, "75-100%": 0}
        ref_chunk_count = 0
        ref_tag = hashlib.sha1(ref_id.encode("utf-8")).hexdigest()[:8]
        for chapter_index, (chapter, view) in enumerate(zip(chapters, views, strict=False), start=1):
            content = str(view.get("content", ""))
            if not content.strip():
                continue
            chapter_ranges = _split_content(content, chunk_chars)
            for block_index, (start, end) in enumerate(chapter_ranges, start=1):
                midpoint = work_cursor + (start + end) / 2
                fraction = midpoint / work_total
                quartile = (
                    "0-25%" if fraction < 0.25 else
                    "25-50%" if fraction < 0.50 else
                    "50-75%" if fraction < 0.75 else
                    "75-100%"
                )
                chunk_id = f"R-{ref_tag}-C{chapter_index:04d}-B{block_index:03d}"
                text = content[start:end]
                fingerprint = hashlib.sha256(text.encode("utf-8")).hexdigest()
                signature.update(chunk_id.encode("utf-8"))
                signature.update(fingerprint.encode("ascii"))
                chunks.append(
                    {
                        "id": chunk_id,
                        "ref_book_id": ref_id,
                        "ref_title": str(ref_book.get("title", ref_id)),
                        "chapter_id": str(chapter.get("id", "")),
                        "chapter_index": chapter_index,
                        "chapter_title": str(view.get("title", f"第{chapter_index}章")),
                        "block_index": block_index,
                        "start": start,
                        "end": end,
                        "chars": len(text),
                        "quartile": quartile,
                        "fingerprint": fingerprint,
                        "preview": re.sub(r"\s+", " ", text[:120]).strip(),
                    }
                )
                quartile_counts[quartile] += 1
                ref_chunk_count += 1
                total_chars += len(text)
            work_cursor += len(content)
            total_chapters += 1
        coverage.append(
            {
                "ref_book_id": ref_id,
                "title": str(ref_book.get("title", ref_id)),
                "chapters": len(views),
                "chars": work_total,
                "chunks": ref_chunk_count,
                "quartiles": quartile_counts,
            }
        )

    if not chunks:
        raise ValueError("所选参考书没有可分析的章节正文")

    batch_size = max(1, min(int(batch_size), 6))
    batch_count = (len(chunks) + batch_size - 1) // batch_size
    state = load_state(book_id)
    previous_signature = state.get("corpus", {}).get("signature", "")
    new_signature = signature.hexdigest()
    state["corpus"] = {
        "status": "ready",
        "portable_confirmed": False,
        "signature": new_signature,
        "reference_ids": ref_ids,
        "total_chars": total_chars,
        "total_chapters": total_chapters,
        "total_chunks": len(chunks),
        "chunk_chars": max(1800, min(int(chunk_chars), 12000)),
        "batch_size": batch_size,
        "batch_count": batch_count,
        # evidence batches + six independent syntheses + cross-layer audit
        "estimated_calls": batch_count + len(LAYER_LABELS) + 1,
        "coverage": coverage,
        "chunks": chunks,
    }
    if previous_signature and previous_signature != new_signature:
        state["observations"] = []
        state["layers"] = {key: _empty_layer(key) for key in LAYER_LABELS}
        state["audit"] = {"status": "pending", "passed": False, "conflicts": [], "warnings": []}
        state["job"] = {"status": "none", "progress": 0, "message": "语料已变化，请重新分析"}
    return save_state(book_id, state)


def _read_chunk(chunk: dict[str, Any]) -> str:
    chapters = json_store.load_chapters(str(chunk["ref_book_id"]))
    chapter = next((item for item in chapters if str(item.get("id", "")) == str(chunk.get("chapter_id", ""))), None)
    if not chapter:
        return ""
    content = str(json_store._chapter_view(chapter).get("content", ""))
    start = max(0, int(chunk.get("start", 0)))
    end = max(start, int(chunk.get("end", start)))
    return content[start:end]


def get_evidence_chunk(book_id: str, chunk_id: str) -> dict[str, Any] | None:
    state = load_state(book_id)
    chunk = next(
        (item for item in state.get("corpus", {}).get("chunks", []) if item.get("id") == chunk_id),
        None,
    )
    if not chunk:
        return None
    return {**chunk, "text": _read_chunk(chunk)}


def _call_json(book_id: str, prompt: str, system: str) -> dict[str, Any]:
    from core.llm_client import chat, llm_book_context

    with llm_book_context(book_id):
        raw = chat(prompt, system=system, temperature=0.1, task="extraction")
    parsed = safe_json_parse(raw, default=None)
    if not isinstance(parsed, dict):
        raise ValueError("模型没有返回可解析的 JSON；已保留检查点，可重试当前步骤")
    return parsed


def _extract_batch(book_id: str, batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valid_ids = {str(item["id"]) for item in batch}
    source = "\n\n".join(
        f"## [{item['id']}] {item['ref_title']} / {item['chapter_title']}\n{_read_chunk(item)}"
        for item in batch
    )
    prompt = f"""从以下原作证据块中提取可复核的写作规律候选。不要续写、评价或复述剧情。

六层键名只能使用：{', '.join(LAYER_LABELS)}

每条 observation 必须包含：
- layer：六层键名之一
- claim：具体、可执行的“在什么情况下怎样写”，禁止“细腻、生动、节奏好”等空话
- evidence_ids：真正支持此结论的证据块 ID；只能使用本批 ID
- counterexample_ids：本批中存在反例时填写
- confidence：high / medium / low
- scope：author / work / character / scene_type；不能把单一人物习惯冒充作者规律

没有证据就不要输出。不要长篇引用原句。只输出 JSON：
{{"observations":[{{"layer":"scene_grammar","claim":"...","evidence_ids":["..."],"counterexample_ids":[],"confidence":"medium","scope":"work"}}]}}

证据：
{source}"""
    result = _call_json(
        book_id,
        prompt,
        "你是证据优先的文学语料编码员。每条结论必须能回到证据块核验，不得把常见网文经验当成样本事实。",
    )
    observations = result.get("observations", [])
    normalized: list[dict[str, Any]] = []
    if not isinstance(observations, list):
        return normalized
    for item in observations:
        if not isinstance(item, dict) or item.get("layer") not in LAYER_LABELS:
            continue
        claim = str(item.get("claim", "")).strip()[:600]
        evidence = [str(value) for value in item.get("evidence_ids", []) if str(value) in valid_ids]
        if not claim or not evidence:
            continue
        counter = [str(value) for value in item.get("counterexample_ids", []) if str(value) in valid_ids]
        confidence = str(item.get("confidence", "low"))
        scope = str(item.get("scope", "work"))
        normalized.append(
            {
                "id": f"obs_{uuid.uuid4().hex[:10]}",
                "layer": item["layer"],
                "claim": claim,
                "evidence_ids": list(dict.fromkeys(evidence)),
                "counterexample_ids": list(dict.fromkeys(counter)),
                "confidence": confidence if confidence in {"high", "medium", "low"} else "low",
                "scope": scope if scope in {"author", "work", "character", "scene_type"} else "work",
            }
        )
    return normalized


def _synthesize_layer(book_id: str, key: str, observations: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = [item for item in observations if item.get("layer") == key]
    allowed_evidence = {
        str(evidence_id)
        for item in candidates
        for field in ("evidence_ids", "counterexample_ids")
        for evidence_id in item.get(field, [])
    }
    compact = [
        {
            "claim": str(item.get("claim", ""))[:500],
            "evidence_ids": item.get("evidence_ids", []),
            "counterexample_ids": item.get("counterexample_ids", []),
            "confidence": item.get("confidence", "low"),
            "scope": item.get("scope", "work"),
        }
        for item in candidates[:180]
    ]
    prompt = f"""将候选观察蒸馏为“{LAYER_LABELS[key]}”规则。只能使用给定观察，不得凭文学常识补全。

要求：
1. 合并重复结论，区分作者通用、单部作品、人物特有和场景条件规律。
2. author 级强规则原则上应有跨作品证据；不足时降低 scope/confidence。
3. 每条规则保留证据块 ID；有反例就写条件，不要强行绝对化。
4. anti_style 只收录证据能够支持的回避项。
5. 输出是给正文模型执行的规则，不是文学评论。

只输出 JSON：
{{"summary":"不超过500字","rules":[{{"text":"可执行规则","level":"core|contextual|character_specific|uncertain","scope":"author|work|character|scene_type","confidence":"high|medium|low","evidence_ids":["..."],"counterexample_ids":["..."]}}],"anti_style":[{{"text":"避免项","evidence_ids":["..."]}}]}}

候选观察：
{json.dumps(compact, ensure_ascii=False)}"""
    result = _call_json(book_id, prompt, "你是作者写作系统的审计编辑，只压缩证据，不创造证据。")
    rules = result.get("rules", []) if isinstance(result.get("rules"), list) else []
    anti_style = result.get("anti_style", []) if isinstance(result.get("anti_style"), list) else []
    all_evidence: list[str] = []
    normalized_rules = []
    for rule in rules[:40]:
        if not isinstance(rule, dict) or not str(rule.get("text", "")).strip():
            continue
        evidence_ids = [str(value) for value in rule.get("evidence_ids", []) if str(value) in allowed_evidence]
        if not evidence_ids:
            continue
        counterexample_ids = [
            str(value) for value in rule.get("counterexample_ids", []) if str(value) in allowed_evidence
        ]
        all_evidence.extend(evidence_ids)
        normalized_rules.append(
            {
                **rule,
                "text": str(rule["text"]).strip()[:800],
                "evidence_ids": evidence_ids,
                "counterexample_ids": counterexample_ids,
            }
        )
    normalized_anti = []
    for item in anti_style[:20]:
        if isinstance(item, str):
            item = {"text": item, "evidence_ids": []}
        if isinstance(item, dict) and str(item.get("text", "")).strip():
            evidence_ids = [
                str(value) for value in item.get("evidence_ids", []) if str(value) in allowed_evidence
            ]
            if not evidence_ids:
                continue
            all_evidence.extend(evidence_ids)
            normalized_anti.append({"text": str(item["text"]).strip()[:800], "evidence_ids": evidence_ids})
    return {
        "key": key,
        "label": LAYER_LABELS[key],
        "status": "needs_review",
        "summary": str(result.get("summary", "")).strip()[:2000],
        "rules": normalized_rules,
        "anti_style": normalized_anti,
        "evidence_ids": list(dict.fromkeys(all_evidence)),
        "updated_at": _now(),
    }


def _cross_audit(book_id: str, layers: dict[str, Any]) -> dict[str, Any]:
    compact = {
        key: {
            "summary": value.get("summary", ""),
            "rules": [rule.get("text", "") for rule in value.get("rules", [])[:20]],
        }
        for key, value in layers.items()
    }
    prompt = f"""审计以下六层作者规律是否互相矛盾、把人物规律误作作者规律、或缺少证据条件。
只指出真实问题，不重写规则。只输出 JSON：
{{"passed":true,"conflicts":[{{"layers":["..."],"description":"..."}}],"warnings":["..."]}}

六层结果：
{json.dumps(compact, ensure_ascii=False)}"""
    result = _call_json(book_id, prompt, "你是六层作者 DNA 的交叉审计员。")
    conflicts = result.get("conflicts", []) if isinstance(result.get("conflicts"), list) else []
    warnings = result.get("warnings", []) if isinstance(result.get("warnings"), list) else []
    return {
        "status": "needs_review",
        "passed": bool(result.get("passed", not conflicts)),
        "conflicts": conflicts[:30],
        "warnings": [str(item)[:800] for item in warnings[:30]],
        "updated_at": _now(),
    }


def create_analysis_job(book_id: str, *, force: bool = False) -> dict[str, Any]:
    state = load_state(book_id)
    corpus = state.get("corpus", {})
    if corpus.get("status") != "ready" or not corpus.get("chunks"):
        state = build_corpus_map(book_id)
        corpus = state["corpus"]
    current = state.get("job", {})
    if current.get("status") in {"queued", "running"}:
        return dict(current)
    job = {
        "id": f"dna_{uuid.uuid4().hex[:12]}",
        "status": "queued",
        "phase": "evidence",
        "next_batch": 0,
        "next_layer": 0,
        "progress": 0,
        "message": "等待开始",
        "error": "",
        "force": bool(force),
        "corpus_signature": corpus.get("signature", ""),
        "estimated_calls": corpus.get("estimated_calls", 0),
        "created_at": _now(),
        "updated_at": _now(),
    }
    if force or current.get("corpus_signature") != corpus.get("signature"):
        state["observations"] = []
        state["layers"] = {key: _empty_layer(key) for key in LAYER_LABELS}
        state["audit"] = {"status": "pending", "passed": False, "conflicts": [], "warnings": []}
    state["job"] = job
    save_state(book_id, state)
    return job


def _job_progress(job: dict[str, Any], batch_count: int) -> int:
    total = max(1, batch_count + len(LAYER_LABELS) + 1)
    completed = int(job.get("next_batch", 0)) + int(job.get("next_layer", 0))
    if job.get("phase") == "audit":
        completed = batch_count + len(LAYER_LABELS)
    if job.get("status") == "completed":
        return 100
    return min(99, round(completed / total * 100))


async def run_analysis_job(book_id: str, job_id: str) -> dict[str, Any]:
    try:
        state = load_state(book_id)
        if state.get("job", {}).get("id") != job_id:
            raise KeyError(job_id)
        corpus = state["corpus"]
        if state["job"].get("corpus_signature") != corpus.get("signature"):
            raise ValueError("参考书内容已变化，请重新建立语料地图")
        chunks = corpus.get("chunks", [])
        batch_size = int(corpus.get("batch_size", 3))
        batches = [chunks[index : index + batch_size] for index in range(0, len(chunks), batch_size)]

        state["job"].update({"status": "running", "message": "正在逐批建立六层证据账本", "error": ""})
        save_state(book_id, state)

        next_batch = int(state["job"].get("next_batch", 0))
        for index in range(next_batch, len(batches)):
            _ensure_author_dna_available(book_id)
            observations = await asyncio.to_thread(_extract_batch, book_id, batches[index])
            state = load_state(book_id)
            existing = state.get("observations", [])
            existing_keys = {
                (item.get("layer"), item.get("claim"), tuple(item.get("evidence_ids", []))) for item in existing
            }
            for item in observations:
                observation_key = (
                    item.get("layer"),
                    item.get("claim"),
                    tuple(item.get("evidence_ids", [])),
                )
                if observation_key not in existing_keys:
                    existing.append(item)
                    existing_keys.add(observation_key)
            state["observations"] = existing
            state["job"].update(
                {
                    "phase": "evidence",
                    "next_batch": index + 1,
                    "message": f"证据批次 {index + 1}/{len(batches)}，已提取 {len(existing)} 条候选",
                }
            )
            state["job"]["progress"] = _job_progress(state["job"], len(batches))
            save_state(book_id, state)

        state = load_state(book_id)
        state["job"]["phase"] = "synthesis"
        save_state(book_id, state)
        layer_keys = list(LAYER_LABELS)
        next_layer = int(state["job"].get("next_layer", 0))
        for index in range(next_layer, len(layer_keys)):
            _ensure_author_dna_available(book_id)
            layer_key = layer_keys[index]
            state = load_state(book_id)
            layer = await asyncio.to_thread(
                _synthesize_layer,
                book_id,
                layer_key,
                state.get("observations", []),
            )
            state = load_state(book_id)
            state["layers"][layer_key] = layer
            state["job"].update(
                {
                    "phase": "synthesis",
                    "next_layer": index + 1,
                    "message": f"已完成 {LAYER_LABELS[layer_key]}，等待全部分析后人工确认",
                }
            )
            state["job"]["progress"] = _job_progress(state["job"], len(batches))
            save_state(book_id, state)

        state = load_state(book_id)
        state["job"].update({"phase": "audit", "message": "正在进行六层交叉审计"})
        state["job"]["progress"] = _job_progress(state["job"], len(batches))
        save_state(book_id, state)
        _ensure_author_dna_available(book_id)
        audit = await asyncio.to_thread(_cross_audit, book_id, state["layers"])
        state = load_state(book_id)
        state["audit"] = audit
        state["job"].update({"status": "completed", "progress": 100, "message": "分析完成；请逐层确认后再用于写作"})
        save_state(book_id, state)
        return dict(state["job"])
    except Exception as exc:
        state = load_state(book_id)
        if state.get("job", {}).get("id") == job_id:
            unavailable = isinstance(exc, AuthorDnaUnavailableError)
            state["job"].update(
                {
                    "status": "interrupted" if unavailable else "failed",
                    "error": str(exc)[:500],
                    "message": (
                        "实验功能已停用；检查点已保留，重新开启后可继续"
                        if unavailable
                        else "分析中断，检查点已保留，可继续"
                    ),
                }
            )
            save_state(book_id, state)
        return dict(state.get("job", {}))
    finally:
        _running.pop(job_id, None)


def schedule_analysis_job(book_id: str, job_id: str) -> dict[str, Any]:
    task = _running.get(job_id)
    if task and not task.done():
        return dict(load_state(book_id).get("job", {}))
    _running[job_id] = asyncio.create_task(run_analysis_job(book_id, job_id))
    return dict(load_state(book_id).get("job", {}))


def retry_analysis_job(book_id: str, job_id: str) -> dict[str, Any]:
    state = load_state(book_id)
    job = state.get("job", {})
    if job.get("id") != job_id:
        raise KeyError(job_id)
    if job.get("status") not in {"failed", "interrupted", "queued"}:
        return dict(job)
    job.update({"status": "queued", "error": "", "message": "将从已完成检查点继续"})
    save_state(book_id, state)
    return dict(job)


def update_layer(book_id: str, key: str, changes: dict[str, Any]) -> dict[str, Any]:
    if key not in LAYER_LABELS:
        raise KeyError(key)
    state = load_state(book_id)
    layer = state["layers"][key]
    status = changes.get("status")
    if status is not None:
        if status not in {"needs_review", "accepted", "rejected"}:
            raise ValueError("无效的层级状态")
        layer["status"] = status
    for field in ("summary", "rules", "anti_style"):
        if field in changes:
            layer[field] = changes[field]
    layer["updated_at"] = _now()
    save_state(book_id, state)
    return dict(layer)


def add_interpretation(book_id: str, data: dict[str, Any]) -> dict[str, Any]:
    statement = str(data.get("statement", "")).strip()
    if not statement:
        raise ValueError("请输入你的原作理解")
    state = load_state(book_id)
    entry = {
        "id": f"interp_{uuid.uuid4().hex[:10]}",
        "ref_book_id": str(data.get("ref_book_id", "")),
        "statement": statement[:6000],
        "classification": str(data.get("classification", "unverified")),
        "confidence": str(data.get("confidence", "unknown")),
        "evidence_ids": [str(item) for item in data.get("evidence_ids", [])],
        "status": "accepted" if data.get("accepted") else "draft",
        "promoted": False,
        "created_at": _now(),
    }
    state.setdefault("interpretations", []).append(entry)
    save_state(book_id, state)
    return dict(entry)


def update_interpretation(book_id: str, entry_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    state = load_state(book_id)
    entry = next((item for item in state.get("interpretations", []) if item.get("id") == entry_id), None)
    if not entry:
        raise KeyError(entry_id)
    for field in ("statement", "classification", "confidence", "evidence_ids", "status"):
        if field in changes:
            entry[field] = changes[field]
    if "promoted" in changes:
        entry["promoted"] = bool(changes["promoted"])
        if entry["promoted"]:
            entry["status"] = "accepted"
    entry["updated_at"] = _now()
    save_state(book_id, state)
    return dict(entry)


def verify_interpretation(book_id: str, entry_id: str) -> dict[str, Any]:
    """Cross-check a reader interpretation without promoting it to canon."""

    state = load_state(book_id)
    entry = next((item for item in state.get("interpretations", []) if item.get("id") == entry_id), None)
    if not entry:
        raise KeyError(entry_id)
    references = _style_references(state, str(entry.get("statement", "")), limit=6)
    if not references:
        raise ValueError("语料地图中没有可用证据，请先重新建立语料地图")
    evidence = "\n\n".join(
        f"[{item['evidence_id']}] {item['source']}\n{item['excerpt']}" for item in references
    )
    prompt = f"""检查下面的读者解读与原作证据是否相容。它不是事实声明，也不能自动成为作者 DNA。

读者解读：
{entry.get('statement', '')}

候选证据：
{evidence}

分类只能是 strongly_supported / plausible / ambiguous / weakly_supported / contradicted。
只输出 JSON：
{{"classification":"plausible","confidence":"high|medium|low","reason":"不超过500字","evidence_ids":["真正支持判断的块ID"],"counter_evidence_ids":["反证块ID"]}}
"""
    result = _call_json(book_id, prompt, "你是原作解读核验员。区分原文事实、合理推断和读者选择的解释。")
    allowed_ids = {item["evidence_id"] for item in references}
    classification = str(result.get("classification", "ambiguous"))
    valid_classes = {"strongly_supported", "plausible", "ambiguous", "weakly_supported", "contradicted"}
    entry.update(
        {
            "classification": classification if classification in valid_classes else "ambiguous",
            "confidence": str(result.get("confidence", "low")),
            "reason": str(result.get("reason", "")).strip()[:2000],
            "evidence_ids": [str(item) for item in result.get("evidence_ids", []) if str(item) in allowed_ids],
            "counter_evidence_ids": [
                str(item) for item in result.get("counter_evidence_ids", []) if str(item) in allowed_ids
            ],
            "verified_at": _now(),
        }
    )
    save_state(book_id, state)
    return dict(entry)


def delete_interpretation(book_id: str, entry_id: str) -> bool:
    state = load_state(book_id)
    items = state.get("interpretations", [])
    filtered = [item for item in items if item.get("id") != entry_id]
    if len(filtered) == len(items):
        return False
    state["interpretations"] = filtered
    save_state(book_id, state)
    return True


def save_scene_contract(book_id: str, data: dict[str, Any]) -> dict[str, Any]:
    """Persist only current-scene fields; future-plan fields are discarded."""

    allowed_fields = {
        "enabled",
        "title",
        "purpose",
        "creative_intent",
        "story_function",
        "pov",
        "start_state",
        "end_state",
        "stop_anchor",
        "beats",
        "allowed",
        "forbidden",
        "active_characters",
        "relevant_canon",
        "new_canon",
        "hidden_intent",
        "target_words",
    }
    contract = {key: value for key, value in data.items() if key in allowed_fields}
    contract["enabled"] = bool(contract.get("enabled", False))
    contract["updated_at"] = _now()
    state = load_state(book_id)
    state["scene_contract"] = contract
    save_state(book_id, state)
    return contract


def get_active_scene_contract(book_id: str) -> dict[str, Any]:
    if not get_author_dna_availability(book_id)["available"]:
        return {}
    contract = load_state(book_id).get("scene_contract", {})
    return dict(contract) if contract.get("enabled") else {}


def _accepted_dna_lines(state: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key, label in LAYER_LABELS.items():
        layer = state.get("layers", {}).get(key, {})
        if layer.get("status") != "accepted":
            continue
        rules = [str(item.get("text", "")).strip() for item in layer.get("rules", []) if item.get("text")]
        anti = [str(item.get("text", "")).strip() for item in layer.get("anti_style", []) if item.get("text")]
        if rules or anti:
            lines.append(f"### {label}")
            lines.extend(f"- {rule}" for rule in rules[:24])
            lines.extend(f"- 禁止/避免：{item}" for item in anti[:12])
    return lines


def build_author_dna_context(book_id: str) -> str:
    """Render accepted semantic rules; unreviewed model output never leaks."""

    if not get_author_dna_availability(book_id)["available"]:
        return ""

    state = load_state(book_id)
    corpus_refs = set(state.get("corpus", {}).get("reference_ids", []))
    configured_refs = set(json_store.get_reference_books(book_id) or [])
    portable_confirmed = bool(state.get("corpus", {}).get("portable_confirmed"))
    if not portable_confirmed and (not corpus_refs or not corpus_refs.issubset(configured_refs)):
        # A removed reference must not keep influencing prose through stale
        # cached DNA.  Re-adding/rebuilding the corpus makes it eligible again.
        return ""
    dna_lines = _accepted_dna_lines(state)
    interpretations = [
        item for item in state.get("interpretations", [])
        if item.get("status") == "accepted" and not item.get("promoted")
    ]
    continuation = [
        item for item in state.get("interpretations", [])
        if item.get("status") == "accepted" and item.get("promoted")
    ]
    if not dna_lines and not interpretations and not continuation:
        return ""
    lines = ["## 已确认的作者 DNA（抽象规则，不得复用原文句子）"]
    lines.extend(dna_lines or ["（尚未确认任何六层规则）"])
    if interpretations:
        lines.append("\n### 用户的作品解读（解释框架，不是原作明示事实）")
        lines.extend(f"- {item['statement']}" for item in interpretations[:20])
    if continuation:
        lines.append("\n### 本续写采用的解释 Canon")
        lines.extend(f"- {item['statement']}" for item in continuation[:20])
    return "\n".join(lines)


def _as_lines(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [line.strip(" -") for line in value.splitlines() if line.strip(" -")]
    return []


def _query_terms(text: str) -> set[str]:
    cjk = "".join(re.findall(r"[\u4e00-\u9fff]", text))
    terms = {cjk[index : index + 2] for index in range(max(0, len(cjk) - 1))}
    terms.update(word.lower() for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text))
    return {term for term in terms if term}


def _style_references(state: dict[str, Any], query: str, limit: int = 3) -> list[dict[str, str]]:
    terms = _query_terms(query)
    scored: list[tuple[int, dict[str, Any], str]] = []
    configured_refs = set(json_store.get_reference_books(str(state.get("book_id", ""))) or [])
    for chunk in state.get("corpus", {}).get("chunks", []):
        if chunk.get("ref_book_id") not in configured_refs:
            continue
        text = _read_chunk(chunk)
        if not text:
            continue
        score = sum(1 for term in terms if term in text)
        # Keep zero-score chunks as a deterministic fallback.  A reader's
        # interpretation may be semantic rather than share literal keywords;
        # the verifier must be able to return "ambiguous" instead of claiming
        # no corpus exists at all.
        scored.append((score, chunk, text))
    scored.sort(key=lambda item: (-item[0], item[1].get("id", "")))
    results = []
    for _score, chunk, text in scored[:limit]:
        excerpt = text[:650].strip()
        results.append(
            {
                "evidence_id": str(chunk.get("id", "")),
                "source": f"{chunk.get('ref_title', '')} / {chunk.get('chapter_title', '')}",
                "excerpt": excerpt,
            }
        )
    return results


def compile_writer_package(
    book_id: str,
    contract: dict[str, Any] | None = None,
    *,
    include_author_dna: bool = True,
    include_beats: bool = True,
) -> dict[str, Any]:
    state = load_state(book_id)
    scene = dict(contract or state.get("scene_contract", {}))
    if not scene:
        return {"text": "", "style_references": []}
    query = "\n".join(
        [str(scene.get("purpose", "")), str(scene.get("hidden_intent", ""))]
        + _as_lines(scene.get("beats"))
    )
    references = _style_references(state, query)
    sections = [
        "# 当前场景 Writer Package",
        "你不是故事总规划者。你只负责把本场景合同渲染成正文，无权决定未来剧情。",
    ]
    dna = build_author_dna_context(book_id) if include_author_dna else ""
    if dna:
        sections.append(f"\n## A. 已确认作者规则\n{dna}")

    def add_block(title: str, value: Any) -> None:
        lines = _as_lines(value)
        if lines:
            sections.append(f"\n## {title}\n" + "\n".join(f"- {line}" for line in lines))

    add_block("B. 当前出场人物状态", scene.get("active_characters"))
    add_block("C. 当前场景所需原作事实", scene.get("relevant_canon"))
    add_block("D. 本次续写新增 Canon", scene.get("new_canon"))
    sections.append("\n## E. 场景合同")
    scalar_labels = (
        ("title", "场景"),
        ("creative_intent", "优先保留的创作意图"),
        ("story_function", "剧情功能"),
        ("purpose", "唯一目的"),
        ("pov", "POV"),
        ("start_state", "开始状态"),
        ("end_state", "结束状态"),
        ("stop_anchor", "停止锚点"),
        ("hidden_intent", "表层之下的意图"),
        ("target_words", "目标字数"),
    )
    for field, label in scalar_labels:
        value = scene.get(field)
        if value not in (None, "", []):
            sections.append(f"- {label}：{value}")
    list_fields = [("allowed", "可自由发挥"), ("forbidden", "禁止")]
    if include_beats:
        list_fields.insert(0, ("beats", "只允许发生"))
    for field, label in list_fields:
        values = _as_lines(scene.get(field))
        if values:
            sections.append(f"- {label}：" + "；".join(values))
    sections.append("- 到达停止锚点后立刻结束。未提供给你的未来事件不得猜测、总结或提前完成。")
    if references:
        sections.append("\n## F. 相似场景原文证据（只学习组织方法，禁止复用句子、人物和情节）")
        for item in references:
            sections.append(f"[{item['evidence_id']}] {item['source']}\n{item['excerpt']}")
    return {"text": "\n".join(sections).strip(), "style_references": references}


def build_active_writer_package(book_id: str, *, include_beats: bool = False) -> str:
    if not get_author_dna_availability(book_id)["available"]:
        return ""
    state = load_state(book_id)
    contract = state.get("scene_contract", {})
    if not contract.get("enabled"):
        return ""
    # Accepted DNA is already carried by ``_build_reference_context``.  The
    # active package adds only scene-local state and retrieved exemplars, so
    # the same rules do not consume context twice.
    return str(
        compile_writer_package(
            book_id,
            contract,
            include_author_dna=False,
            include_beats=include_beats,
        ).get("text", "")
    )
