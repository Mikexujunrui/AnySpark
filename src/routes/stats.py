from datetime import datetime, timedelta

from fastapi import APIRouter

from data.json_store import json_store

router = APIRouter(tags=["stats"])


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
        },
    }
