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
    后续如需完整漏斗，可把种子数加进 explore intent 落盘（改动需主人确认）。
    """
    directions = db.execute("SELECT COUNT(*) AS c FROM archived_directions").fetchone()["c"]
    chapters = db.execute("SELECT COUNT(*) AS c FROM chapters").fetchone()["c"]
    return {
        "directions": int(directions),
        "chapters": int(chapters),
        "direction_to_chapter": (round(int(chapters) / int(directions), 3) if directions else None),
        "note": "种子层未落盘（探索意图不持久化）；v1 以 方向固化→章节 两层代理漏斗，不新增表",
    }
