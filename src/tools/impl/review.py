"""Review tool implementations — review panel and reviewer management."""

import asyncio

from core.review_panel import ReviewResult
from data.json_store import json_store

_CURRENT_BOOK_SAMPLE_CHARS = 2400
_REFERENCE_SAMPLE_CHARS = 1800


def _chapter_excerpt(text: str, limit: int) -> str:
    """Keep both ends of a chapter so evidence is not first-page biased."""

    text = (text or "").strip()
    if len(text) <= limit:
        return text
    half = max(limit // 2, 1)
    return text[:half] + "\n...（样本中段省略）...\n" + text[-half:]


def _build_review_evidence(book_id: str, chapter_ref: str, kb=None) -> str:
    """Build provenance-labelled evidence instead of asking reviewers to guess."""

    parts: list[str] = []
    try:
        book = json_store.get_book(book_id)
    except Exception:
        book = {}
    book_title = book.get("title", book_id) if isinstance(book, dict) else book_id
    parts.append(
        "# 评审证据边界\n"
        f"- 当前项目：{book_title}\n"
        f"- 待评审目标：{chapter_ref or '直接提供的文本'}\n"
        "- 只能依据下列带来源标签的材料，不得猜测作品名、作者、角色或原著事实。\n"
        "- [当前书正文] 可用于当前作品的事实与文风对照。\n"
        "- [参考书·只学文风] 只能比较句式、节奏、视角和措辞，不是当前作品的事实。\n"
        "- 没有相应证据时必须写“证据不足”。"
    )

    if kb:
        try:
            summary = kb.get_knowledge_summary()
            if summary and "知识库为空" not in summary:
                parts.append(f"# [当前书知识库·事实]\n{summary[:4000]}")
        except Exception:
            pass

    try:
        chapters = json_store.load_chapters(book_id)
        target_id = ""
        try:
            target = json_store.get_chapter(book_id, chapter_ref) if chapter_ref else None
            if target:
                target_id = str(target.get("id", ""))
        except Exception:
            pass
        source_views = []
        for raw in chapters:
            view = json_store._chapter_view(raw)
            if target_id and str(view.get("id", "")) == target_id:
                continue
            if view.get("content"):
                source_views.append(view)
        for view in source_views[-3:]:
            excerpt = _chapter_excerpt(view.get("content", ""), _CURRENT_BOOK_SAMPLE_CHARS)
            parts.append(f"# [当前书正文·文风/事实样本] {view.get('title', '?')}\n{excerpt}")
    except Exception:
        pass

    try:
        ref_ids = json_store.get_reference_books(book_id) or []
        profiles = json_store.get_reference_profiles(book_id) or {}
        for ref_id in ref_ids:
            usage = profiles.get(ref_id, "style")
            try:
                ref_book = json_store.get_book(ref_id)
                ref_title = ref_book.get("title", ref_id)
            except Exception:
                ref_title = ref_id

            if usage == "style":
                label = "参考书·只学文风·不得作为当前书原著事实"
            elif usage == "canon":
                label = "参考书·原著事实源·不自动代表当前书文风"
            else:
                label = "参考书·文风与原著事实源"

            ref_sections = [f"# [{label}] {ref_title}"]
            try:
                views = [json_store._chapter_view(raw) for raw in json_store.load_chapters(ref_id)]
                views = [view for view in views if view.get("content")]
                chosen = views[:1]
                if len(views) > 1:
                    chosen.append(views[-1])
                for view in chosen:
                    excerpt = _chapter_excerpt(view.get("content", ""), _REFERENCE_SAMPLE_CHARS)
                    ref_sections.append(f"## 文本样本：{view.get('title', '?')}\n{excerpt}")
            except Exception:
                pass

            if usage in ("canon", "both"):
                try:
                    from core.graph_store import GraphStore

                    ref_kb = GraphStore(ref_id)
                    ref_kb.init_schema()
                    ref_summary = ref_kb.get_knowledge_summary()
                    ref_kb.close()
                    if ref_summary and "知识库为空" not in ref_summary:
                        ref_sections.append(f"## 原著事实摘要\n{ref_summary[:2500]}")
                except Exception:
                    pass

            if usage in ("style", "both"):
                try:
                    from core.writer import _build_reference_context

                    analyzed = _build_reference_context(book_id)
                    marker = f"## 参考书: {ref_title}"
                    if marker in analyzed:
                        section = analyzed.split(marker, 1)[1]
                        if "\n## 参考书:" in section:
                            section = section.split("\n## 参考书:", 1)[0]
                        ref_sections.append(f"## 已缓存文风分析\n{section[:3500]}")
                except Exception:
                    pass

            parts.append("\n".join(ref_sections))
    except Exception:
        pass

    return "\n\n---\n\n".join(parts)


async def _patch_slow_reviews(report_id: str, book_id: str, pending_tasks: dict, queue):

    for coro, reviewer in pending_tasks.items():
        try:
            result = await coro
        except Exception as e:
            result = ReviewResult(
                reviewer_id=reviewer.id, reviewer_name=reviewer.name, category=reviewer.category, error=str(e)[:100]
            )

        stored = json_store.get_review(book_id, report_id)
        if not stored:
            return

        updated = False
        for i, rev in enumerate(stored.get("individual_reviews", [])):
            if rev.get("reviewer_id") == reviewer.id:
                if result.error:
                    stored["individual_reviews"][i] = {
                        "reviewer_id": reviewer.id,
                        "reviewer_name": reviewer.name,
                        "category": reviewer.category,
                        "error": result.error,
                    }
                else:
                    stored["individual_reviews"][i] = {
                        "reviewer_id": result.reviewer_id,
                        "reviewer_name": result.reviewer_name,
                        "category": result.category,
                        "overall_score": result.overall_score,
                        "scores": result.scores,
                        "highlights": result.highlights,
                        "issues": result.issues,
                        "suggestions": result.suggestions,
                        "comment": result.raw_text[:500],
                    }
                updated = True
                break

        if not updated:
            if result.error:
                stored["individual_reviews"].append(
                    {
                        "reviewer_id": reviewer.id,
                        "reviewer_name": reviewer.name,
                        "category": reviewer.category,
                        "error": result.error,
                    }
                )
            else:
                stored["individual_reviews"].append(
                    {
                        "reviewer_id": result.reviewer_id,
                        "reviewer_name": result.reviewer_name,
                        "category": result.category,
                        "overall_score": result.overall_score,
                        "scores": result.scores,
                        "highlights": result.highlights,
                        "issues": result.issues,
                        "suggestions": result.suggestions,
                        "comment": result.raw_text[:500],
                    }
                )

        scores = [
            r.get("overall_score", 0)
            for r in stored["individual_reviews"]
            if not r.get("error") and r.get("overall_score", 0) > 0
        ]
        stored["overall_score"] = round(sum(scores) / len(scores), 1) if scores else 0

        json_store.update_review(book_id, stored)

        if queue:
            msg = f"  📥 {reviewer.name} 后台评审完成！评分已追加到评审报告。"
            try:
                await queue.put({"_progress": msg})
            except Exception:
                pass


async def _run_review(loop, args: dict, kb, book_id: str, msg: str = "", queue=None) -> str:
    import logging

    from core.review_panel import panel

    logger = logging.getLogger(__name__)

    chapter_ref = args.get("chapter", "")
    reviewers_str = args.get("reviewers", "")
    mode = args.get("mode", "concurrent")
    excerpt_limit = int(args.get("excerpt_limit", 0) or 0)

    # Ensure chapter_ref is a string (LLM may pass int)
    if not isinstance(chapter_ref, str):
        chapter_ref = str(chapter_ref)

    logger.info(
        "run_review called: chapter=%r reviewers=%r mode=%r book_id=%r",
        chapter_ref[:100] if isinstance(chapter_ref, str) else chapter_ref,
        reviewers_str,
        mode,
        book_id,
    )

    chapter_text = ""
    if chapter_ref.startswith("#") or (chapter_ref and len(chapter_ref) < 20):
        try:
            ch = json_store.get_chapter(book_id, chapter_ref)
            chapter_text = ch.get("content", "")
            if not chapter_ref.startswith("#"):
                chapter_ref = f"#{chapter_ref}"
            logger.info("run_review loaded chapter %s: %d chars", chapter_ref, len(chapter_text))
        except Exception as e:
            logger.warning("run_review failed to load chapter %r: %s", chapter_ref, e)

    if not chapter_text:
        chapter_text = chapter_ref

    if excerpt_limit > 0:
        chapter_text = chapter_text[: max(50, min(excerpt_limit, 20_000))]

    if not chapter_text or len(chapter_text) < 50:
        return "错误: 需要提供章节内容。请指定章节序号（如 #1）或直接传入文本。"

    knowledge_context = _build_review_evidence(book_id, chapter_ref, kb)

    reviewer_ids = None
    if reviewers_str:
        reviewer_ids = [r.strip() for r in reviewers_str.split(",") if r.strip()]

    report = await panel.run_review(
        chapter_text=chapter_text,
        book_id=book_id,
        chapter_ref=chapter_ref,
        knowledge_context=knowledge_context,
        reviewer_ids=reviewer_ids,
        mode=mode,
        queue=queue,
    )

    json_store.save_review(
        book_id,
        {
            "id": report.id,
            "chapter_ref": report.chapter_ref,
            "timestamp": report.timestamp,
            "overall_score": report.overall_score,
            "summary": report.summary,
            "consensus": report.consensus,
            "divergences": report.divergences,
            "top_suggestions": report.top_suggestions,
            "individual_reviews": report.individual_reviews,
            "reviewer_count": report.reviewer_count,
        },
    )

    if hasattr(report, "_pending_tasks") and report._pending_tasks:
        asyncio.ensure_future(_patch_slow_reviews(report.id, book_id, report._pending_tasks, queue))

    parts = [f"## 评审团报告 — {report.chapter_ref or '章节'}", ""]
    parts.append(f"**综合评分: {report.overall_score}/10** ({report.reviewer_count} 位评审员)")
    parts.append("")

    if report.summary:
        parts.append(f"### 综合评价\n{report.summary}")
        parts.append("")

    if report.consensus:
        parts.append("### 共识")
        for c in report.consensus:
            parts.append(f"- {c}")
        parts.append("")

    if report.divergences:
        parts.append("### 分歧")
        for d in report.divergences:
            parts.append(f"- {d}")
        parts.append("")

    if report.top_suggestions:
        parts.append("### 改进建议")
        for i, s in enumerate(report.top_suggestions, 1):
            parts.append(f"{i}. {s}")
        parts.append("")

    parts.append("---")
    parts.append("### 各评审员详细反馈")
    for rev in report.individual_reviews:
        if rev.get("error"):
            parts.append(f"\n**{rev['reviewer_name']}**: 评审失败 — {rev['error']}")
            continue
        score = rev.get("overall_score", 0)
        parts.append(f"\n**{rev['reviewer_name']}** ({rev['category']}) — {score}/10")
        if rev.get("scores"):
            scores_str = " | ".join(f"{k}:{v}" for k, v in rev["scores"].items())
            parts.append(f"  维度: {scores_str}")
        if rev.get("highlights"):
            parts.append(f"  亮点: {'; '.join(rev['highlights'][:3])}")
        if rev.get("issues"):
            parts.append(f"  问题: {'; '.join(rev['issues'][:3])}")
        if rev.get("suggestions"):
            parts.append(f"  建议: {'; '.join(rev['suggestions'][:3])}")
        if rev.get("comment"):
            parts.append(f"  评语: {rev['comment'][:200]}")

    return "\n".join(parts)


def _manage_reviewers(args: dict) -> str:
    from core.review_panel import panel

    action = args.get("action", "list")
    reviewer_id = args.get("reviewer_id", "")

    if action == "list":
        reviewers = panel.list_reviewers(include_inactive=True)
        if not reviewers:
            return "当前没有评审员。"
        lines = ["评审员列表:"]
        for r in reviewers:
            lines.append(f"- {r.get('name', '?')} ({r.get('category', '?')}) — {r.get('description', '')}")
        return "\n".join(lines)

    elif action == "activate":
        if not reviewer_id:
            return "错误: 需要提供 reviewer_id"
        # Placeholder for reviewer activation
        return f"评审员 {reviewer_id} 激活功能暂未实现。"

    elif action == "deactivate":
        if not reviewer_id:
            return "错误: 需要提供 reviewer_id"
        return f"评审员 {reviewer_id} 停用功能暂未实现。"

    return "请指定 action: list/activate/deactivate"
