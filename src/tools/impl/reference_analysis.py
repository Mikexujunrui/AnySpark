# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Tool handlers for reference work analysis (analyze_structure, quantify_style).

Thin wrappers that extract parameters, call the reference_analyzer module,
and format the result for the agent.
"""

from __future__ import annotations

from core.thread_pools import llm_pool as _ai_executor


def _resolve_ref_book_id(args: dict, book_id: str) -> str | None:
    """Resolve the reference book ID from args or the current book's refs."""
    from data.json_store import json_store

    ref_book_id = args.get("ref_book_id", "")
    if ref_book_id:
        return ref_book_id
    ref_ids = json_store.get_reference_books(book_id)
    if not ref_ids:
        return None
    return ref_ids[0]


def _format_structure_output(data: dict) -> str:
    """Format a structure report dict as human-readable output."""
    lines = ["## 原著结构分析报告"]
    ch_count = data.get("chapter_count", 0)
    total = data.get("total_words", 0)
    avg = data.get("avg_chapter_length", 0)
    lines.append(f"共 {ch_count} 章，{total} 字，平均每章 {avg:.0f} 字")

    avg_dr = data.get("avg_dialogue_ratio", 0)
    lines.append(f"平均对话占比: {avg_dr:.1%}")

    para = data.get("paragraph_stats", {})
    if para.get("avg_per_chapter"):
        lines.append(
            f"段落: 平均每章 {para['avg_per_chapter']:.0f} 段，"
            f"每段约 {para['avg_length']:.0f} 字"
        )

    sent = data.get("sentence_stats", {})
    if sent.get("avg_per_chapter"):
        lines.append(
            f"句子: 平均每章 {sent['avg_per_chapter']:.0f} 句，"
            f"每句约 {sent['avg_length']:.0f} 字"
        )

    # Show chapter length distribution (first 10 + last 5 if long)
    dist = data.get("chapter_length_distribution", [])
    if dist:
        lines.append("\n逐章字数:")
        show = dist[:10] if len(dist) <= 15 else dist[:10] + ["..."] + dist[-5:]
        for i, wc in enumerate(show):
            if isinstance(wc, int):
                lines.append(f"  第{i+1 if i < 10 else len(dist)-5+len(show)-10}章: {wc}字")
            else:
                lines.append(f"  {wc}")

    # Show pacing curve highlights
    curve = data.get("pacing_curve", [])
    if curve:
        fastest = max(curve, key=lambda x: x.get("pace_score", 0))
        slowest = min(curve, key=lambda x: x.get("pace_score", 0))
        lines.append(
            f"\n节奏: 最快章 第{fastest.get('chapter', '?')}章"
            f"(pace={fastest.get('pace_score', 0):.3f}), "
            f"最慢章 第{slowest.get('chapter', '?')}章"
            f"(pace={slowest.get('pace_score', 0):.3f})"
        )

    return "\n".join(lines)


def _format_style_output(data: dict) -> str:
    """Format a style fingerprint dict as human-readable output."""
    lines = ["## 文风量化指纹"]

    dist = data.get("sentence_length_distribution", {})
    if dist:
        lines.append("句长分布:")
        for bucket in ["<10", "10-20", "20-40", ">40"]:
            val = dist.get(bucket, 0)
            if val:
                lines.append(f"  {bucket}字: {val:.1%}")

    ttr = data.get("vocabulary_richness_ttr", 0)
    lines.append(f"词汇丰富度(TTR): {ttr:.3f}")

    idiom = data.get("four_char_idiom_density", 0)
    lines.append(f"四字成语密度: {idiom:.4f}")

    punct = data.get("punctuation_pattern", {})
    if punct:
        top = sorted(punct.items(), key=lambda x: -x[1])[:5]
        lines.append("标点模式:")
        for k, v in top:
            lines.append(f"  {k}: {v:.4f}")

    para = data.get("paragraph_length_stats", {})
    if para.get("mean"):
        lines.append(
            f"段落长度: 均值{para['mean']:.0f}字, "
            f"中位数{para.get('median', 0):.0f}字, "
            f"标准差{para.get('std', 0):.0f}"
        )

    dd = data.get("dialogue_density", 0)
    lines.append(f"对话密度: {dd:.1%}")

    lines.append("\n写作时将自动注入以上文风量化指标作为约束。")
    return "\n".join(lines)


async def _analyze_structure_tool(loop, args: dict, book_id: str) -> str:
    """Tool handler for analyze_structure."""
    from core.reference_analyzer import analyze_structure, load_analysis

    ref_book_id = _resolve_ref_book_id(args, book_id)
    if not ref_book_id:
        return "错误: 当前项目没有参考书。先用 set_reference_books 设置。"

    # Check cache
    cached = load_analysis("structure", ref_book_id)
    if cached:
        return f"（已缓存）{_format_structure_output(cached)}"

    # Execute analysis (pure Python, runs in thread pool)
    report = await loop.run_in_executor(
        _ai_executor, analyze_structure, ref_book_id
    )

    if not report.chapter_count:
        return f"错误: 参考书 {ref_book_id} 没有章节内容，无法分析。"

    return _format_structure_output(report.to_dict())


async def _quantify_style_tool(loop, args: dict, book_id: str) -> str:
    """Tool handler for quantify_style."""
    from core.reference_analyzer import load_analysis, quantify_style

    ref_book_id = _resolve_ref_book_id(args, book_id)
    if not ref_book_id:
        return "错误: 当前项目没有参考书。先用 set_reference_books 设置。"

    # Check cache
    cached = load_analysis("style_fingerprint", ref_book_id)
    if cached:
        return f"（已缓存）{_format_style_output(cached)}"

    # Execute analysis (pure Python, runs in thread pool)
    fingerprint = await loop.run_in_executor(
        _ai_executor, quantify_style, ref_book_id
    )

    if not fingerprint.sentence_length_distribution:
        return f"错误: 参考书 {ref_book_id} 没有章节内容，无法分析。"

    return _format_style_output(fingerprint.to_dict())
