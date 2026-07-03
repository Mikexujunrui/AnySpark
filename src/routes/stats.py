import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter

from core.config import DATA_DIR
from core.cost_tracker import get_book_cost, get_cost_trend
from core.dedup import dedup_book
from data.json_store import json_store

router = APIRouter(tags=["stats"])

TARGET_WORDS = 200_000  # 20万字终局目标


def _day_key(iso: str) -> str | None:
    """Parse ISO timestamp and return 'YYYY-MM-DD' or None on failure."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")) if "T" in iso else datetime.strptime(iso[:10], "%Y-%m-%d")
        return dt.date().isoformat()
    except (ValueError, TypeError):
        return None


@router.get("/books/{book_id}/stats")
def writing_stats(book_id: str):
    chapters = json_store.load_chapters(book_id)
    regular = [c for c in chapters if not c.get("is_extra")]
    extras = [c for c in chapters if c.get("is_extra")]

    now = datetime.now().date()
    window_start = now - timedelta(days=89)
    days = [(window_start + timedelta(days=i)).isoformat() for i in range(90)]
    daily: dict[str, dict] = {
        d: {"date": d, "wordsCreated": 0, "wordsEdited": 0,
            "chaptersCreated": 0, "chaptersEdited": 0} for d in days
    }

    per_chapter = []
    total_words = 0

    for idx, ch in enumerate(regular, 1):
        cur = json_store._get_current_version(ch)
        wc = cur.get("word_count")
        if not wc:
            content = cur.get("content", "")
            wc = len(content.replace("\n", "").replace(" ", "")) if content else 0
        total_words += wc

        versions = ch.get("versions", [])
        created_at = ch.get("createdAt", "")
        updated_at = ch.get("updatedAt", "")

        first_version_day = _day_key(versions[0].get("timestamp")) if versions else None
        if first_version_day and first_version_day in daily:
            daily[first_version_day]["chaptersCreated"] += 1
            daily[first_version_day]["wordsCreated"] += wc

        for v in versions[1:]:
            vday = _day_key(v.get("timestamp"))
            if not vday or vday not in daily:
                continue
            prev_id = v.get("parent")
            prev = next((x for x in versions if x["id"] == prev_id), None) if prev_id else None
            prev_wc = (prev.get("word_count") if prev else 0) or 0
            delta = wc - prev_wc if prev else wc
            daily[vday]["wordsEdited"] += max(delta, 0)
            daily[vday]["chaptersEdited"] += 1

        per_chapter.append({
            "idx": idx,
            "title": cur.get("title", ch.get("title", "")),
            "wordCount": wc,
            "isExtra": False,
            "createdAt": created_at,
            "updatedAt": updated_at,
        })

    extra_idx = len(regular) + 1
    for ch in extras:
        cur = json_store._get_current_version(ch)
        wc = cur.get("word_count")
        if not wc:
            content = cur.get("content", "")
            wc = len(content.replace("\n", "").replace(" ", "")) if content else 0
        total_words += wc
        per_chapter.append({
            "idx": extra_idx,
            "title": cur.get("title", ch.get("title", "")),
            "wordCount": wc,
            "isExtra": True,
            "createdAt": ch.get("createdAt", ""),
            "updatedAt": ch.get("updatedAt", ""),
        })
        extra_idx += 1

    avg = round(total_words / len(regular)) if regular else 0

    active_days = sorted({d for d, v in daily.items() if v["wordsCreated"] or v["wordsEdited"]})
    current_streak = 0
    if active_days:
        d = now.isoformat()
        while d in active_days:
            current_streak += 1
            d = (datetime.fromisoformat(d).date() - timedelta(days=1)).isoformat()

    best_streak = 0
    if active_days:
        cur = 1
        for prev, nxt in zip(active_days, active_days[1:], strict=False):
            try:
                gap = (datetime.fromisoformat(nxt).date()
                       - datetime.fromisoformat(prev).date()).days
            except ValueError:
                continue
            if gap == 1:
                cur += 1
            else:
                best_streak = max(best_streak, cur)
                cur = 1
        best_streak = max(best_streak, cur)

    daily_list = [daily[d] for d in days]

    # ── 章节字数分布统计 ──
    chapter_wcs = [p["wordCount"] for p in per_chapter if not p["isExtra"]]
    word_distribution = _compute_distribution(chapter_wcs)

    # ── 修改/版本统计 ──
    revision_stats = _compute_revision_stats(chapters)

    # ── 大纲完成度 ──
    outline_completion = _compute_outline_completion(book_id, len(regular))

    # ── 分卷进度 ──
    volume_progress = _compute_volume_progress(book_id)

    # ── 评审统计 ──
    review_stats = _compute_review_stats(book_id)

    # ── 日均产出 & 预估完成 ──
    active_writing_days = len(active_days)
    daily_avg = round(total_words / active_writing_days) if active_writing_days else 0
    remaining_words = max(0, TARGET_WORDS - total_words)
    estimated_days = round(remaining_words / daily_avg) if daily_avg > 0 else None

    # ── 近7天/近30天产出 ──
    recent_7 = sum(d["wordsCreated"] + d["wordsEdited"] for d in daily_list[-7:])
    recent_30 = sum(d["wordsCreated"] + d["wordsEdited"] for d in daily_list[-30:])

    return {
        "daily": daily_list,
        "perChapter": per_chapter,
        "totals": {
            "totalWords": total_words,
            "totalChapters": len(regular),
            "extrasCount": len(extras),
            "avgWordsPerChapter": avg,
            "currentStreak": current_streak,
            "bestStreak": best_streak,
            "lastActiveDate": active_days[-1] if active_days else None,
            # 新增维度
            "targetWords": TARGET_WORDS,
            "completionPercent": round(total_words / TARGET_WORDS * 100, 1) if TARGET_WORDS else 0,
            "dailyAvg": daily_avg,
            "estimatedDaysToComplete": estimated_days,
            "recent7DaysWords": recent_7,
            "recent30DaysWords": recent_30,
            "activeWritingDays": active_writing_days,
        },
        "wordDistribution": word_distribution,
        "revisionStats": revision_stats,
        "outlineCompletion": outline_completion,
        "volumeProgress": volume_progress,
        "reviewStats": review_stats,
    }


# ── 辅助函数 ──

def _compute_distribution(wcs: list[int]) -> dict:
    """计算字数分布统计量。"""
    if not wcs:
        return {"min": 0, "max": 0, "median": 0, "p25": 0, "p75": 0, "stdDev": 0}
    sorted_wc = sorted(wcs)
    n = len(sorted_wc)
    mean = sum(wcs) / n
    var = sum((x - mean) ** 2 for x in wcs) / n
    return {
        "min": sorted_wc[0],
        "max": sorted_wc[-1],
        "median": sorted_wc[n // 2],
        "p25": sorted_wc[n // 4] if n > 3 else sorted_wc[0],
        "p75": sorted_wc[3 * n // 4] if n > 3 else sorted_wc[-1],
        "stdDev": round(var ** 0.5, 1),
    }


def _compute_revision_stats(chapters: list[dict]) -> dict:
    """计算章节修改/版本统计。"""
    if not chapters:
        return {"avgRevisions": 0, "onePassRate": 0, "maxRevisions": 0, "totalRevisions": 0}
    revision_counts = []
    one_pass = 0
    for ch in chapters:
        versions = ch.get("versions", [])
        rev_count = max(0, len(versions) - 1)  # versions[0]是初始版本，后续是修改
        revision_counts.append(rev_count)
        if rev_count == 0:
            one_pass += 1
    total_rev = sum(revision_counts)
    return {
        "avgRevisions": round(total_rev / len(chapters), 1),
        "onePassRate": round(one_pass / len(chapters) * 100, 1),
        "maxRevisions": max(revision_counts) if revision_counts else 0,
        "totalRevisions": total_rev,
    }


def _compute_outline_completion(book_id: str, written_count: int) -> dict:
    """计算大纲完成度。"""
    try:
        outline = json_store.get_outline(book_id)
        planned = len(outline.get("chapters", [])) if outline else 0
    except Exception:
        planned = 0
    return {
        "planned": planned,
        "written": written_count,
        "percent": round(written_count / planned * 100, 1) if planned > 0 else 0,
    }


def _compute_volume_progress(book_id: str) -> list[dict]:
    """计算分卷进度。"""
    try:
        volumes = json_store.load_volumes(book_id)
        if not volumes:
            return []
        result = []
        for vol in sorted(volumes, key=lambda v: v.get("order", 0)):
            vol_chapters = vol.get("chapters", [])
            result.append({
                "id": vol.get("id", ""),
                "title": vol.get("title", ""),
                "chapterCount": len(vol_chapters),
                "order": vol.get("order", 0),
            })
        return result
    except Exception:
        return []


def _compute_review_stats(book_id: str) -> dict:
    """计算评审统计。"""
    try:
        reviews = json_store.load_reviews(book_id)
        if not reviews:
            return {"totalReviews": 0, "avgScore": 0, "scoreTrend": [], "passRate": 0}
        scores = [r.get("overall_score", 0) for r in reviews if r.get("overall_score")]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0
        # 按时间排序的趋势
        sorted_reviews = sorted(reviews, key=lambda r: r.get("timestamp", ""))
        trend = [
            {"date": _day_key(r.get("timestamp", "")), "score": r.get("overall_score", 0)}
            for r in sorted_reviews if r.get("overall_score")
        ]
        pass_rate = round(len([s for s in scores if s >= 7.0]) / len(scores) * 100, 1) if scores else 0
        return {
            "totalReviews": len(reviews),
            "avgScore": avg_score,
            "scoreTrend": trend,
            "passRate": pass_rate,
        }
    except Exception:
        return {"totalReviews": 0, "avgScore": 0, "scoreTrend": [], "passRate": 0}


# ── Agent 效能聚合路由 ──

@router.get("/books/{book_id}/agent-metrics")
def agent_metrics(book_id: str):
    """聚合 metrics.jsonl 中该书的 Agent 循环指标。"""
    metrics_file: Path = DATA_DIR / "metrics.jsonl"
    if not metrics_file.exists():
        return _empty_agent_metrics()

    records = []
    for line in metrics_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("book_id") == book_id:
            records.append(rec)

    if not records:
        return _empty_agent_metrics()

    n = len(records)
    rounds_list = [r.get("rounds", 0) for r in records]
    llm_list = [r.get("llm_calls", 0) for r in records]
    tool_list = [r.get("tool_calls", 0) for r in records]
    token_list = [r.get("total_tokens", 0) for r in records]
    hall_count = sum(sum(r.get("hallucination_hits", {}).values()) for r in records)
    drift_count = sum(r.get("drift_corrections", 0) for r in records)

    # finish_reason 分布
    finish_reasons = Counter(r.get("finish_reason", "unknown") for r in records)
    success_count = finish_reasons.get("done", 0) + finish_reasons.get("plan_complete", 0)

    # 工具使用 Top10
    tool_counter: Counter = Counter()
    for r in records:
        for tname, cnt in r.get("tool_names", {}).items() if isinstance(r.get("tool_names"), dict) else []:
            tool_counter[tname] += cnt
    # 兼容旧记录没有 tool_names 的情况 — 从 user_message 推断 agent_type 分布
    agent_types = Counter(r.get("agent_type", "unknown") for r in records)

    # 高消耗 outlier (rounds >= 20)
    outliers = [
        {
            "timestamp": r.get("timestamp", ""),
            "agentType": r.get("agent_type", ""),
            "rounds": r.get("rounds", 0),
            "llmCalls": r.get("llm_calls", 0),
            "tokens": r.get("total_tokens", 0),
            "finishReason": r.get("finish_reason", ""),
            "message": r.get("user_message", "")[:60],
        }
        for r in records if r.get("rounds", 0) >= 20
    ]
    outliers.sort(key=lambda x: x["rounds"], reverse=True)

    # 按日趋势（最近30天）
    by_date: dict[str, list] = {}
    for r in records:
        day = _day_key(r.get("timestamp", ""))
        if day:
            by_date.setdefault(day, []).append(r)
    trend = []
    for day in sorted(by_date.keys())[-30:]:
        day_recs = by_date[day]
        trend.append({
            "date": day,
            "runs": len(day_recs),
            "avgRounds": round(sum(r.get("rounds", 0) for r in day_recs) / len(day_recs), 1),
            "avgTokens": round(sum(r.get("total_tokens", 0) for r in day_recs) / len(day_recs)),
        })

    return {
        "totalRuns": n,
        "avgRounds": round(sum(rounds_list) / n, 1),
        "avgLlmCalls": round(sum(llm_list) / n, 1),
        "avgToolCalls": round(sum(tool_list) / n, 1),
        "avgTokens": round(sum(token_list) / n),
        "totalTokens": sum(token_list),
        "hallucinationRate": round(hall_count / n * 100, 1),
        "driftCorrections": drift_count,
        "successRate": round(success_count / n * 100, 1),
        "finishReasons": dict(finish_reasons.most_common()),
        "agentTypes": dict(agent_types.most_common()),
        "topTools": dict(tool_counter.most_common(10)),
        "outliers": outliers[:10],
        "trend": trend,
    }


def _empty_agent_metrics() -> dict:
    return {
        "totalRuns": 0,
        "avgRounds": 0,
        "avgLlmCalls": 0,
        "avgToolCalls": 0,
        "avgTokens": 0,
        "totalTokens": 0,
        "hallucinationRate": 0,
        "driftCorrections": 0,
        "successRate": 0,
        "finishReasons": {},
        "agentTypes": {},
        "topTools": {},
        "outliers": [],
        "trend": [],
    }


@router.get("/books/{book_id}/dedup")
def dedup_stats(book_id: str):
    """Cross-chapter content deduplication analysis."""
    return dedup_book(book_id)


@router.get("/books/{book_id}/cost")
def book_cost(book_id: str):
    """Aggregate cost summary for a book."""
    return get_book_cost(book_id).to_dict()


@router.get("/books/{book_id}/cost/trend")
def book_cost_trend(book_id: str, days: int = 30):
    """Daily cost trend for the last N days."""
    return {"book_id": book_id, "days": days, "trend": get_cost_trend(book_id, days)}
