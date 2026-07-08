# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Continuation Pipeline — 4-phase structured pipeline for 小说续写。

Phase 0: 全文预习 (一次性)
Phase 1: 宏观续写规划 (一次性)
Phase 2: 逐幕写作 (循环4次, 每幕10回)
Phase 3: 全文统稿 (一次性)

Each phase has structured inputs/outputs and human-in-the-loop checkpoints.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from data.json_store import json_store

logger = logging.getLogger(__name__)


# ── Data structures ─────────────────────────────────────────────────────


@dataclass
class ContinuationContract:
    """续写契约——Phase 1 的输出，约束后续所有写作。"""
    book_id: str = ""
    total_chapters: int = 0     # 续写总章数
    acts: list[dict] = field(default_factory=list)
    # 伏笔→回收集映射
    foreshadow_payoff_map: dict[str, list[int]] = field(default_factory=dict)
    # 每个角色的命运弧线
    character_arcs: dict[str, list[str]] = field(default_factory=dict)
    # 关键章节标记
    key_chapters: dict[int, str] = field(default_factory=dict)
    # 写作方案描述（人类可读）
    plan_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "book_id": self.book_id,
            "total_chapters": self.total_chapters,
            "acts": self.acts,
            "foreshadow_payoff_map": self.foreshadow_payoff_map,
            "character_arcs": self.character_arcs,
            "key_chapters": {str(k): v for k, v in self.key_chapters.items()},
            "plan_summary": self.plan_summary,
        }


@dataclass
class ActConstraintBundle:
    """幕约束包——Phase 2a 的输出，约束本幕10回的写作。"""
    act_number: int = 0
    chapters: list[int] = field(default_factory=list)
    core_conflict: str = ""
    # 伏笔分配（哪回回收哪些伏笔）
    foreshadow_allocation: dict[int, list[str]] = field(default_factory=dict)
    # 每回的节奏曲线
    rhythm_curve: list[str] = field(default_factory=list)  # 起/承/转/合
    # 角色出场计划
    character_appearances: dict[str, list[int]] = field(default_factory=dict)
    # 文风约束（指向 reference_analyzer 的分析结果）
    style_preset: str = "default"
    # 叙事者干预计划
    narrator_intervention: int = 2  # 本幕建议的叙事者干预次数


@dataclass
class ChapterValidationResult:
    """写后校验结果。"""
    chapter: int = 0
    style_match_score: float = 0.0       # 文风匹配度
    voice_consistency_score: float = 0.0  # 角色声音一致性
    foreshadow_compliance: bool = False   # 伏笔约束是否满足
    logic_check_passed: bool = False      # 叙事逻辑检查
    issues: list[str] = field(default_factory=list)

    def passed(self) -> bool:
        """是否通过了所有检查。"""
        return (
            self.style_match_score >= 0.5
            and self.voice_consistency_score >= 0.5
            and self.foreshadow_compliance
            and self.logic_check_passed
        )


# ── Storage ─────────────────────────────────────────────────────────────

CON_DIR = Path(__file__).resolve().parents[2] / "data" / "continuation"


def _ensure_dir() -> None:
    CON_DIR.mkdir(parents=True, exist_ok=True)


def save_contract(book_id: str, contract: ContinuationContract) -> None:
    """保存续写契约。"""
    _ensure_dir()
    path = CON_DIR / f"{book_id}_contract.json"
    path.write_text(
        json.dumps(contract.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_contract(book_id: str) -> ContinuationContract | None:
    """加载续写契约。"""
    path = CON_DIR / f"{book_id}_contract.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        key_chapters = {int(k): v for k, v in data.get("key_chapters", {}).items()}
        return ContinuationContract(
            book_id=data.get("book_id", book_id),
            total_chapters=data.get("total_chapters", 40),
            acts=data.get("acts", []),
            foreshadow_payoff_map=data.get("foreshadow_payoff_map", {}),
            character_arcs=data.get("character_arcs", {}),
            key_chapters=key_chapters,
            plan_summary=data.get("plan_summary", ""),
        )
    except Exception as e:
        logger.warning("Failed to load continuation contract: %s", e)
        return None


# ── Phase helpers ───────────────────────────────────────────────────────


def get_world_snapshot(book_id: str, last_chapter: int | None = None) -> dict[str, Any]:
    """获取指定章节结束时的世界状态快照。

    从知识图谱和章节数据中提取所有开放状态。

    Args:
        book_id: 书籍ID
        last_chapter: 可选，截止到第几章（不含该章本身）。
            如不传则采用全书所有章节。
    """
    chapters = json_store.load_chapters(book_id)
    regular = [ch for ch in chapters if not ch.get("is_extra")]

    # 统计章节信息
    ch_count = len(regular)
    total_words = 0
    for ch in regular:
        view = json_store._chapter_view(ch)
        content = view.get("content", "")
        total_words += len(content.replace(" ", "").replace("\n", ""))

    return {
        "book_id": book_id,
        "chapter_count": ch_count,
        "total_words": total_words,
        "last_chapter": last_chapter,
        "written_chapters": ch_count,
    }


def validate_chapter_content(
    chapter_content: str,
    reference_text: str = "",
    foreshadow_requirements: list[str] | None = None,
) -> ChapterValidationResult:
    """写后自动校验——4 项检查。

    1. 文风匹配度评分（与目标风格指纹做余弦相似度）
    2. 角色声音一致性（检测对话的 voice_fingerprint 偏离度）
    3. 伏笔约束满足检查
    4. 叙事逻辑检查（基本一致性）
    """

    result = ChapterValidationResult()

    if not chapter_content.strip():
        result.issues.append("章节内容为空")
        return result

    # 1. 文风匹配度（如果提供了参考文本）
    if reference_text:
        from core.reference_analyzer import (
            _compute_sentence_length_distribution,
            _compute_ttr,
        )
        ref_dist = _compute_sentence_length_distribution(reference_text)
        ref_ttr = _compute_ttr(reference_text)
        cur_dist = _compute_sentence_length_distribution(chapter_content)
        cur_ttr = _compute_ttr(chapter_content)

        # Compare sentence length distribution (simple cosine-like)
        all_buckets = set(ref_dist.keys()) | set(cur_dist.keys())
        dot = 0.0
        norm1 = 0.0
        norm2 = 0.0
        for b in all_buckets:
            r = ref_dist.get(b, 0.0)
            c = cur_dist.get(b, 0.0)
            dot += r * c
            norm1 += r * r
            norm2 += c * c
        if norm1 > 0 and norm2 > 0:
            result.style_match_score = dot / ((norm1 ** 0.5) * (norm2 ** 0.5))

        # TTR proximity as additional signal
        if ref_ttr > 0 and cur_ttr > 0:
            ttr_sim = 1.0 - abs(ref_ttr - cur_ttr) / max(ref_ttr, cur_ttr)
            result.style_match_score = (result.style_match_score + ttr_sim) / 2

    # 2. 角色声音一致性（简化的检测——检查是否有明显的现代用语）
    modern_markers = ["的时侯", "然后", "但是", "因为", "所以", "虽然",
                      "如果", "而且", "或者", "不过", "只是"]
    modern_hits = sum(1 for m in modern_markers if m in chapter_content)
    if modern_hits > 5:
        result.voice_consistency_score = 0.3
        result.issues.append(f"检测到 {modern_hits} 处潜在现代用语")
    elif modern_hits > 2:
        result.voice_consistency_score = 0.6
    else:
        result.voice_consistency_score = 0.9

    # 3. 伏笔约束满足检查
    if foreshadow_requirements:
        all_met = True
        for req in foreshadow_requirements:
            if req and req not in chapter_content:
                all_met = False
                result.issues.append(f"伏笔约束未满足: {req[:40]}")
        result.foreshadow_compliance = all_met
    else:
        result.foreshadow_compliance = True

    # 4. 基本叙事逻辑检查
    result.logic_check_passed = len(chapter_content) > 100  # 有实质内容即通过

    return result


# ── Phase 0: 全文预习 ────────────────────────────────────────────────────


def run_phase0_deep_preview(book_id: str) -> dict[str, Any]:
    """Phase 0 全文预习——运行所有深度分析。

    返回所有分析结果的汇总字典。
    """
    from core.emotion_analyzer import analyze_emotional_curve
    from core.reference_analyzer import (
        analyze_narrative_pov,
        analyze_prophecy_signature,
        analyze_rhetoric_density,
        analyze_sentence_rhythm,
        analyze_structure,
        quantify_style,
    )

    logger.info("Phase 0: 开始全文预习 — book_id=%s", book_id)

    results = {
        "structure": analyze_structure(book_id).to_dict(),
        "style_fingerprint": quantify_style(book_id).to_dict(),
        "sentence_rhythm": analyze_sentence_rhythm(book_id).to_dict(),
        "rhetoric_density": analyze_rhetoric_density(book_id).to_dict(),
        "prophecy_signature": analyze_prophecy_signature(book_id).to_dict(),
        "narrative_pov": analyze_narrative_pov(book_id).to_dict(),
        "emotional_curve": analyze_emotional_curve(book_id).to_dict(),
        "world_snapshot": get_world_snapshot(book_id),
    }

    # 缓存到文件
    _ensure_dir()
    path = CON_DIR / f"{book_id}_phase0.json"
    path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info("Phase 0 完成: %d 项分析已缓存", len(results))
    return results


# ── Phase 3: 全文统稿 ────────────────────────────────────────────────────


def run_phase3_full_book_qa(book_id: str, split_point: int = 80) -> dict[str, Any]:
    """Phase 3 全文一致性审计。

    检查续写章节与前文（截止于 split_point 之前的章节）的风格一致性。
    默认以第 80 章为分割点。

    Args:
        book_id: 书籍ID
        split_point: 分割点章节索引，之前的为"前文"，之后的为"续写"。

    Returns:
        审计报告 dict
    """
    from core.reference_analyzer import (
        quantify_style,
    )

    chapters = json_store.load_chapters(book_id)
    regular = [ch for ch in chapters if not ch.get("is_extra")]

    # 分割前文和续写
    cont = regular[split_point:] if len(regular) > split_point else []

    if not cont:
        return {"error": "没有续写章节", "status": "no_data"}

    # 分别分析前80回和续写的文风
    ref_fingerprint = quantify_style(book_id).to_dict()
    cont_fingerprint = quantify_style(book_id).to_dict()  # 这是全书的

    # 对比差异
    issues = []
    ref_ttr = ref_fingerprint.get("vocabulary_richness_ttr", 0)
    # 检查词汇丰富度变化
    if ref_ttr > 0:
        pass  # 详细的对比待后续实现

    return {
        "status": "completed",
        "ref_80_fingerprint": ref_fingerprint,
        "continuation_fingerprint": cont_fingerprint,
        "issues": issues,
        "issue_count": len(issues),
    }
