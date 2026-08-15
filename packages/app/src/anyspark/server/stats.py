"""
anyspark.server.stats — T7 验证指标（代理指标，纯 SQL 统计现有表）。

设计依据：DESIGN.md §9 T7——"核心只看三个：修改率 / 提问率 / 完成率，其余辅助"。
- 修改率 ↓  用户改 AI 产出的比例随时间下降（对齐生效）
- 提问率 ↓  AI 每千字提问递减（默契度增长的可视化）
- 完成率 ↑  种子→第一章完成率（漏斗）

实现约束（遵守 DESIGN 第 1 节方法论）：
- 零新表、零埋点：全部基于现有 signals / messages / chapters / archived_directions
  （操作即语义——信号本身就是埋点，无需额外埋点）
- 模型无关：只做统计，不改任何业务数据；代理指标不过度指标化
- 趋势可见：修改率按天分桶、提问率按会话先后排序，让"随时间下降/上升"可观测
"""

from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

# 判别型信号：用户对 AI 产出的接受/修改/删除/拒绝（操作即语义，零打字成本）
# accepted = 接受原样；其余 = 用户改了/否了 AI 产出 → 修改率分母
_JUDGE_KINDS = ("accepted", "modified", "deleted", "rejected")

# 问句判定：句子以中/英文问号结尾（极简启发式，代理指标不追求精确）
_QUESTION_ENDS = ("?", "？")


def _question_count(text: str) -> int:
    """问句数：以 ?/？ 结尾的句子数量。

    极简启发式：匹配「非句末标点字符序列 + 问号」的个数，
    正确处理连续问句（"雾来了吗？雨停了吗？" = 2）。代理指标不追求精确。
    """
    if not text:
        return 0
    return len(re.findall(r"[^。！？!?\n]*[？?]", text))


def compute_stats(db_path: str | Path) -> dict[str, Any]:
    """计算 T7 三项代理指标（只读，不写任何业务数据）。"""
    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row
    try:
        return {
            "modify_rate": _modify_rate(db),
            "question_rate": _question_rate(db),
            "completion_rate": _completion_rate(db),
        }
    finally:
        db.close()


def _modify_rate(db: sqlite3.Connection) -> dict[str, Any]:
    """修改率：判别型信号中"非接受"占比；按天分桶给出趋势（↓ = 对齐生效）。"""
    placeholders = ",".join("?" for _ in _JUDGE_KINDS)
    rows = db.execute(
        f"SELECT kind, created_at FROM signals WHERE kind IN ({placeholders})",
        _JUDGE_KINDS,
    ).fetchall()
    total = len(rows)
    accepted = sum(1 for r in rows if r["kind"] == "accepted")
    changed = total - accepted
    # 按天分桶：[接受数, 改动数]
    by_day: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        day = (r["created_at"] or "")[:10] or "unknown"
        if r["kind"] == "accepted":
            by_day[day][0] += 1
        else:
            by_day[day][1] += 1
    buckets: list[dict[str, Any]] = []
    for day, (ac, ch) in sorted(by_day.items()):
        buckets.append(
            {"bucket": day, "rate": round(ch / (ac + ch), 3) if ac + ch else None, "total": ac + ch}
        )
    return {
        "overall": round(changed / total, 3) if total else None,
        "accepted": accepted,
        "changed": changed,
        "total": total,
        "by_day": buckets,
    }


def _question_rate(db: sqlite3.Connection) -> dict[str, Any]:
    """提问率：AI 每千字问句数；按会话先后排序（↓ = 默契度增长可视化）。"""
    rows = db.execute(
        "SELECT conversation_id, content FROM messages WHERE role='assistant' ORDER BY id"
    ).fetchall()
    total_chars = 0
    total_questions = 0
    # 按会话聚合：[字数, 问句数]
    by_conv: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    conv_order: list[str] = []
    for r in rows:
        cid = str(r["conversation_id"])
        if cid not in by_conv:
            conv_order.append(cid)
        content = r["content"] or ""
        by_conv[cid][0] += len(content)
        by_conv[cid][1] += _question_count(content)
        total_chars += len(content)
        total_questions += _question_count(content)
    per_conv: list[dict[str, Any]] = []
    for cid in conv_order:
        chars, questions = by_conv[cid]
        per_conv.append(
            {
                "conversation_id": cid,
                "per_1k_chars": round(questions / (chars / 1000), 2) if chars else None,
                "chars": chars,
                "questions": questions,
            }
        )
    return {
        "overall_per_1k_chars": (
            round(total_questions / (total_chars / 1000), 2) if total_chars else None
        ),
        "total_chars": total_chars,
        "total_questions": total_questions,
        "by_conversation": per_conv,
    }


def _completion_rate(db: sqlite3.Connection) -> dict[str, Any]:
    """完成率漏斗：方向固化（探索完成）→ 章节产出（第一章完成）。

    种子层当前无落盘（探索意图不持久化）；v1 用现有两层代理漏斗，不新增表（YAGNI）。
    后续如需完整漏斗，可把种子数加进 explore intent 落盘（改动需决策确认）。
    """
    directions = db.execute("SELECT COUNT(*) AS c FROM archived_directions").fetchone()["c"]
    chapters = db.execute("SELECT COUNT(*) AS c FROM chapters").fetchone()["c"]
    return {
        "directions": int(directions),
        "chapters": int(chapters),
        "direction_to_chapter": (round(int(chapters) / int(directions), 3) if directions else None),
        "note": "种子层未落盘（探索意图不持久化）；v1 以 方向固化→章节 两层代理漏斗，不新增表",
    }


# ---------------------------------------------------------------------------
# S101 写作进度统计（作者视角，纯 SQL 读现有表，零新表/零埋点）
# 数据源：chapters（按天字数/趋势/streak）、chapter_versions（版本质量）、
#        story_plan（大纲完成度）、signals（T7 指标复用）
# ---------------------------------------------------------------------------


def compute_writing_stats(db_path: str | Path) -> dict[str, Any]:
    """作者视角写作统计：趋势/连续写作/日均/版本质量/大纲完成度/线进度/每章明细。

    与 compute_stats（T7 代理指标）互补：T7 回答「AI 对齐效果」，
    本函数回答「作者写了多少、勤不勤、质量如何」。
    """
    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row
    try:
        daily = _daily_words(db)
        totals = _writing_totals(db, daily)
        dist = _word_distribution(db)
        vers = _version_stats(db)
        outline = _outline_completion(db)
        lines = _line_progress(db)
        per_chapter = _per_chapter(db)
        return {
            "daily": daily,
            "totals": totals,
            "wordDistribution": dist,
            "versionStats": vers,
            "outline": outline,
            "lines": lines,
            "perChapter": per_chapter,
        }
    finally:
        db.close()


def _all_chapters(db: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = db.execute(
        "SELECT id, book_id, title, content, order_index, narrative_line, created_at, updated_at "
        "FROM chapters ORDER BY created_at"
    ).fetchall()
    out = []
    for r in rows:
        words = len((r["content"] or "").replace("\n", "").replace(" ", ""))
        out.append(
            {
                "id": r["id"],
                "book_id": r["book_id"],
                "title": r["title"],
                "words": words,
                "line": r["narrative_line"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
        )
    return out


def _day_key(iso: str | None) -> str | None:
    return (iso or "")[:10] or None


def _daily_words(db: sqlite3.Connection) -> list[dict[str, Any]]:
    """近 90 天按天：新建章节字数/章数（created_at 为准）。"""
    from datetime import date, timedelta

    window_start = date.today() - timedelta(days=89)
    by_day: dict[str, dict[str, int]] = {}
    for c in _all_chapters(db):
        day = _day_key(c["created_at"])
        if not day:
            continue
        bucket = by_day.setdefault(day, {"words": 0, "chapters": 0})
        bucket["words"] += c["words"]
        bucket["chapters"] += 1
    out = []
    for i in range(90):
        day = (window_start + timedelta(days=i)).isoformat()
        b = by_day.get(day, {"words": 0, "chapters": 0})
        out.append({"date": day, "words": b["words"], "chapters": b["chapters"]})
    return out


def _writing_totals(db: sqlite3.Connection, daily: list[dict[str, Any]]) -> dict[str, Any]:
    """总字数/章节/连续写作/活跃天数/近7·30天/日均（活跃日口径）。"""
    chapters = _all_chapters(db)
    total_words = sum(c["words"] for c in chapters)
    total_chapters = len(chapters)
    active_days = sorted({d for c in chapters if (d := _day_key(c["created_at"]))})
    # 连续写作：从最近活跃日往回数连续天数
    from datetime import date, timedelta

    streak = 0
    if active_days:
        cursor = date.today()
        active_set = set(active_days)
        while (cursor.isoformat()) in active_set:
            streak += 1
            cursor -= timedelta(days=1)
    # 近 7/30 天字数
    today = date.today()

    def _recent(days: int) -> int:
        cutoff = (today - timedelta(days=days)).isoformat()
        return sum(c["words"] for c in chapters if (c["created_at"] or "")[:10] >= cutoff)

    recent7 = _recent(7)
    recent30 = _recent(30)
    active_writing_days = len(active_days)
    daily_avg = round(recent30 / 30) if active_writing_days else 0
    return {
        "totalWords": total_words,
        "totalChapters": total_chapters,
        "currentStreak": streak,
        "activeDays": active_writing_days,
        "recent7Words": recent7,
        "recent30Words": recent30,
        "dailyAvg": daily_avg,
        "avgWordsPerChapter": round(total_words / total_chapters) if total_chapters else 0,
    }


def _word_distribution(db: sqlite3.Connection) -> dict[str, Any]:
    """每章字数分布：min/max/median/stdDev。"""
    words = sorted(c["words"] for c in _all_chapters(db))
    if not words:
        return {"min": 0, "max": 0, "median": 0, "stdDev": 0, "count": 0}
    import statistics

    n = len(words)
    median = statistics.median(words)
    std = statistics.pstdev(words) if n > 1 else 0
    return {
        "min": words[0],
        "max": words[-1],
        "median": round(median),
        "stdDev": round(std, 1),
        "count": n,
    }


def _version_stats(db: sqlite3.Connection) -> dict[str, Any]:
    """章节版本质量：平均修改/一次通过率（版本=write_chapter 落盘快照，代理口径）。"""
    rows = db.execute(
        "SELECT chapter_id, COUNT(*) AS n FROM chapter_versions GROUP BY chapter_id"
    ).fetchall()
    if not rows:
        return {
            "avgRevisions": 0,
            "onePassRate": 0,
            "maxRevisions": 0,
            "totalVersions": 0,
            "count": 0,
        }
    counts = [r["n"] for r in rows]
    total_versions = sum(counts)
    one_pass = sum(1 for n in counts if n <= 1)
    return {
        "avgRevisions": round(sum(n - 1 for n in counts) / len(counts), 1),
        "onePassRate": round(one_pass / len(counts) * 100),
        "maxRevisions": max(n - 1 for n in counts),
        "totalVersions": total_versions,
        "count": len(counts),
    }


def _outline_completion(db: sqlite3.Connection) -> dict[str, Any]:
    """大纲完成度：story_plan 计划章节 vs chapters 已写（按标题匹配 + status）。"""
    try:
        plans = db.execute("SELECT title, status FROM story_plan").fetchall()
    except sqlite3.OperationalError:
        plans = []
    chapters = db.execute("SELECT title FROM chapters").fetchall()
    written_titles = {str(c["title"]).strip() for c in chapters}
    planned = len(plans)
    written = 0
    for p in plans:
        title = str(p["title"] or "").strip()
        if title and (title in written_titles or str(p["status"]).strip() == "written"):
            written += 1
    percent = round(written / planned * 100) if planned else 0
    return {"planned": planned, "written": written, "percent": percent}


def _line_progress(db: sqlite3.Connection) -> list[dict[str, Any]]:
    """线进度（narrative_line）：每线章节数/字数（替代老版「卷进度」，贴合 V4 概念）。"""
    by_line: dict[str, dict[str, int]] = {}
    for c in _all_chapters(db):
        line = c["line"] or "main"
        b = by_line.setdefault(line, {"chapterCount": 0, "words": 0})
        b["chapterCount"] += 1
        b["words"] += c["words"]
    return [
        {"line": k, "chapterCount": v["chapterCount"], "words": v["words"]}
        for k, v in sorted(by_line.items())
    ]


def _per_chapter(db: sqlite3.Connection) -> list[dict[str, Any]]:
    """每章明细：标题/字数/版本数/更新时间/线。"""
    chapters = _all_chapters(db)
    vcount = db.execute(
        "SELECT chapter_id, COUNT(*) AS n FROM chapter_versions GROUP BY chapter_id"
    ).fetchall()
    vmap = {r["chapter_id"]: r["n"] for r in vcount}
    return [
        {
            "title": c["title"],
            "words": c["words"],
            "versions": vmap.get(c["id"], 0),
            "createdAt": c["created_at"],
            "updatedAt": c["updated_at"],
            "line": c["line"],
        }
        for c in chapters
    ]
