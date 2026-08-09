"""
anyspark.review.panel — 拟人化评审团编排。

职责：
- 加载评审员（系统 YAML + 用户附加目录覆盖，内容=persona/维度全在 YAML）
- 并发跑评审员（每评审员独立超时；Model 协议解耦，模型无关）
- 主席汇总（LLM 汇总失败降级启发式，不挂死）

机制硬编码、内容自然语言：本模块无任何评审标准/人设硬编码，全部来自 YAML。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import yaml

from anyspark.core import Message

from .defs import ReviewerDef, ReviewReport, ReviewResult, ScoreDim
from .parse import _to_str_list, extract_scores, parse_review_json
from .prompts import OUTPUT_SCHEMA, SUMMARIZE_SYSTEM

logger = logging.getLogger(__name__)

# 系统默认评审员目录：随包分发（hatch force-include 打进 wheel 的 anyspark/reviewers）
DEFAULT_REVIEWERS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "reviewers"

# 单评审员评审超时（秒）
REVIEW_TIMEOUT = 90
# 主席汇总超时（秒）
SUMMARIZE_TIMEOUT = 60
# 单评审员正文上限（轻量：控制 token 成本）
MAX_TEXT_CHARS = 20000
# 外部上下文块单块上限
MAX_CONTEXT_BLOCK = 4000


class ReviewPanel:
    """评审团：加载评审员 + 并发评审 + 主席汇总。"""

    def __init__(self, system_dir: Path | None = None) -> None:
        self._system_dir = Path(system_dir) if system_dir else DEFAULT_REVIEWERS_DIR
        self._reviewers: dict[str, ReviewerDef] = {}
        self._load_dir(self._system_dir, custom=False)

    # ------------------------------------------------------------------
    # 评审员管理
    # ------------------------------------------------------------------
    def _load_dir(self, path: Path, custom: bool) -> None:
        """加载目录下全部 *.yaml/*.yml。用户目录（custom=True）覆盖系统同名 id。"""
        if not path.is_dir():
            return
        for f in sorted(path.glob("*.yaml")) + sorted(path.glob("*.yml")):
            self._load_file(f, custom)

    def _load_file(self, path: Path, custom: bool) -> None:
        try:
            text = path.read_text(encoding="utf-8")
            data = yaml.safe_load(text)
            if isinstance(data, dict):
                data = [data]
            if not isinstance(data, list):
                logger.warning("评审员文件格式错误（应为 list/dict）: %s", path)
                return
            for d in data:
                if not isinstance(d, dict):
                    continue
                rid = str(d.get("id") or "").strip()
                if not rid:
                    logger.warning("评审员缺 id，跳过: %s", path)
                    continue
                dims = []
                for item in d.get("scoring_dimensions", []) or []:
                    if not isinstance(item, dict):
                        continue
                    try:
                        weight = float(item.get("weight", 0.2))
                    except (TypeError, ValueError):
                        weight = 0.2
                    dims.append(
                        ScoreDim(
                            name=str(item.get("name", "")),
                            weight=weight,
                            desc=str(item.get("desc", "")),
                        )
                    )
                keys = [str(k) for k in (d.get("context_keys", []) or []) if str(k).strip()]
                reviewer = ReviewerDef(
                    id=rid,
                    name=str(d.get("name") or rid),
                    avatar=str(d.get("avatar") or "user"),
                    category=str(d.get("category") or "professional"),
                    active=bool(d.get("active", True)),
                    persona=str(d.get("persona") or ""),
                    scoring_dimensions=dims,
                    context_keys=keys,
                    custom=custom,
                )
                if custom:
                    self._reviewers[rid] = reviewer  # 用户覆盖系统
                else:
                    self._reviewers.setdefault(rid, reviewer)  # 系统不覆盖已存在的
        except Exception as exc:  # 单文件损坏不拖垮整个面板
            logger.error("评审员文件加载失败 %s: %s", path, exc)

    def add_dir(self, path: Path) -> None:
        """挂载用户自定义评审员目录（custom=True，覆盖系统同名 id）。"""
        self._load_dir(path, custom=True)

    def list_reviewers(self, include_inactive: bool = True) -> list[dict[str, object]]:
        result = [r.to_dict() for r in self._reviewers.values()]
        result.sort(key=lambda d: (0 if d["category"] == "professional" else 1, str(d["id"])))
        if include_inactive:
            return result
        return [d for d in result if d["active"]]

    def get_reviewer(self, rid: str) -> ReviewerDef | None:
        return self._reviewers.get(rid)

    def active_reviewers(self) -> list[ReviewerDef]:
        return [r for r in self._reviewers.values() if r.active]

    def set_active(self, rid: str, active: bool) -> bool:
        """启停评审员（内存态；持久化由调用方/自定义文件负责，系统内置只读）。"""
        r = self._reviewers.get(rid)
        if r is None:
            return False
        r.active = active
        return True

    # ------------------------------------------------------------------
    # 评审主流程
    # ------------------------------------------------------------------
    async def run_review(
        self,
        model: Any,
        text: str,
        chapter_ref: str = "",
        reviewer_ids: list[str] | None = None,
        context: dict[str, str] | None = None,
        # 外部上下文块按需注入；每评审员独立超时（asyncio.wait_for 实现）
        timeout: float = REVIEW_TIMEOUT,  # noqa: ASYNC109
    ) -> ReviewReport:
        """并发评审。model 需满足 core Model 协议（respond(messages, tools)）。

        context: 外部上下文块映射（块名 → 文本）。评审员按各自 context_keys
        取用；取不到的块自动跳过（不报错，评审仍继续）。
        """
        report = ReviewReport(chapter_ref=chapter_ref, reviewer_count=len(self._reviewers))

        if reviewer_ids:
            reviewers = [self._reviewers[rid] for rid in reviewer_ids if rid in self._reviewers]
        else:
            reviewers = self.active_reviewers()
        if not reviewers:
            report.summary = "没有激活的评审员。请先激活至少一位评审员。"
            report.reviewer_count = 0
            return report

        report.reviewer_count = len(reviewers)
        results = await asyncio.gather(
            *[self._single_review(model, r, text, context or {}, timeout) for r in reviewers]
        )

        valid = [r for r in results if not r.error]
        report.errors = [r.error for r in results if r.error]
        if not valid:
            report.summary = "所有评审员均未返回有效结果。"
            report.individual_reviews = [
                {"reviewer_id": r.reviewer_id, "reviewer_name": r.reviewer_name, "error": r.error}
                for r in results
            ]
            return report

        # 综合分：各评审员总分平均（总分已在 _parse_review 确定：
        # 维度齐→确定性加权平均，不齐→LLM 自报 overall，均已被 clamp）
        scores = [r.overall_score for r in valid if r.overall_score > 0]
        report.overall_score = round(sum(scores) / len(scores), 1) if scores else 0.0

        report.individual_reviews = [self._result_to_dict(r) for r in results]
        report.timestamp = _now_iso()

        # 主席汇总（LLM；失败降级为启发式）
        summary = await self._summarize(model, valid)
        report.summary = summary.get("summary", "")
        report.consensus = summary.get("consensus", [])
        report.divergences = summary.get("divergences", [])
        report.top_suggestions = summary.get("top_suggestions", [])
        if not report.summary:
            report.summary = _heuristic_summary(valid)
        if not report.top_suggestions:
            report.top_suggestions = [s for r in valid for s in r.suggestions[:1]][:3]
        return report

    def _result_to_dict(self, r: ReviewResult) -> dict[str, object]:
        d: dict[str, object] = {
            "reviewer_id": r.reviewer_id,
            "reviewer_name": r.reviewer_name,
            "category": r.category,
            "overall_score": r.overall_score,
            "scores": r.scores,
            "highlights": r.highlights,
            "issues": r.issues,
            "suggestions": r.suggestions,
            "comment": r.comment,
        }
        if r.error:
            d["error"] = r.error
        return d

    # ------------------------------------------------------------------
    # 单评审员
    # ------------------------------------------------------------------
    async def _single_review(
        self,
        model: Any,
        reviewer: ReviewerDef,
        text: str,
        context: dict[str, str],
        # 每评审员独立超时（asyncio.wait_for 实现）
        timeout: float,  # noqa: ASYNC109
    ) -> ReviewResult:
        system = _build_reviewer_system(reviewer)
        prompt_parts: list[str] = []
        # 按 context_keys 注入外部上下文（取不到的块跳过）
        for key in reviewer.context_keys:
            block = context.get(key)
            if block and block.strip():
                prompt_parts.append(f"# 参考上下文（{key}）\n{block[:MAX_CONTEXT_BLOCK]}")
        prompt_parts.append(f"# 待评审章节\n{text[:MAX_TEXT_CHARS]}")
        user = "\n\n".join(prompt_parts)

        try:
            output = await asyncio.wait_for(
                asyncio.to_thread(
                    model.respond,
                    [Message(role="system", content=system), Message(role="user", content=user)],
                    [],
                ),
                timeout=timeout,
            )
            raw = getattr(output, "text", "") or ""
        except TimeoutError:
            return ReviewResult(
                reviewer_id=reviewer.id,
                reviewer_name=reviewer.name,
                category=reviewer.category,
                error="评审超时",
            )
        except Exception as exc:
            return ReviewResult(
                reviewer_id=reviewer.id,
                reviewer_name=reviewer.name,
                category=reviewer.category,
                error=f"评审异常: {str(exc)[:120]}",
            )
        return _parse_review(raw, reviewer)

    # ------------------------------------------------------------------
    # 主席汇总
    # ------------------------------------------------------------------
    async def _summarize(self, model: Any, results: list[ReviewResult]) -> dict[str, Any]:
        try:
            digest = _digest(results)
            output = await asyncio.wait_for(
                asyncio.to_thread(
                    model.respond,
                    [
                        Message(role="system", content=SUMMARIZE_SYSTEM),
                        Message(role="user", content=f"# 各评审员意见\n{digest}\n\n请汇总："),
                    ],
                    [],
                ),
                timeout=SUMMARIZE_TIMEOUT,
            )
            raw = getattr(output, "text", "") or ""
            data = parse_review_json(raw)
            if not data:
                return {}
            return {
                "summary": str(data.get("summary") or "").strip(),
                "consensus": _to_str_list(data.get("consensus")),
                "divergences": _to_str_list(data.get("divergences")),
                "top_suggestions": _to_str_list(data.get("top_suggestions")),
            }
        except Exception as exc:
            logger.warning("评审团汇总失败，降级启发式: %s", exc)
            return {}


def _build_reviewer_system(reviewer: ReviewerDef) -> str:
    """评审员 system prompt：身份人设 + 评分维度 + 输出格式要求。"""
    parts = ["你是一位小说评审员。以下是你的身份和评审标准：", "", "# 身份", reviewer.persona]
    if reviewer.scoring_dimensions:
        dims = "\n".join(
            f"- {d.name}（权重{d.weight:.0%}）: {d.desc}" for d in reviewer.scoring_dimensions
        )
        parts.extend(["", "# 评分维度", dims])
    parts.extend(["", OUTPUT_SCHEMA])
    return "\n".join(parts)


def _parse_review(raw: str, reviewer: ReviewerDef) -> ReviewResult:
    result = ReviewResult(
        reviewer_id=reviewer.id,
        reviewer_name=reviewer.name,
        category=reviewer.category,
        raw_text=raw[:2000],
    )
    data = parse_review_json(raw)
    if not data:
        result.error = "输出无法解析为 JSON"
        return result
    result.scores = extract_scores(data)
    result.highlights = _to_str_list(data.get("highlights"))
    result.issues = _to_str_list(data.get("issues"))
    result.suggestions = _to_str_list(data.get("suggestions"))
    result.comment = str(data.get("comment") or "").strip()
    # 总分：维度齐 → 确定性加权平均（防 LLM 乱打总分）；不齐 → LLM 自报（clamp）
    weighted = reviewer.weighted_overall(result.scores)
    if weighted is not None:
        result.overall_score = weighted
    else:
        result.overall_score = round(_clamp01(float(data.get("overall_score") or 0.0)), 1)
    return result


def _clamp01(v: float) -> float:
    if v < 0:
        return 0.0
    if v > 10:
        return 10.0
    return v


def _digest(results: list[ReviewResult]) -> str:
    """把各评审员结果压成主席摘要输入（省 token）。"""
    lines = []
    for r in results:
        lines.append(f"## {r.reviewer_name}（{r.category}）— {r.overall_score}/10")
        if r.highlights:
            lines.append("亮点: " + "；".join(r.highlights[:3]))
        if r.issues:
            lines.append("问题: " + "；".join(r.issues[:3]))
        if r.suggestions:
            lines.append("建议: " + "；".join(r.suggestions[:3]))
        if r.comment:
            lines.append(f"评语: {r.comment[:200]}")
    return "\n".join(lines)


def _heuristic_summary(results: list[ReviewResult]) -> str:
    """汇总 LLM 失败时的启发式兜底（不挂死）。"""
    avg = sum(r.overall_score for r in results) / len(results) if results else 0.0
    return f"（自动汇总）{len(results)} 位评审员综合 {avg:.1f}/10。详细意见见各评审员反馈。"


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")


# 默认面板（懒加载：加载一次系统评审员，供便捷入口复用）
_default_panel: ReviewPanel | None = None


def default_panel() -> ReviewPanel:
    global _default_panel
    if _default_panel is None:
        _default_panel = ReviewPanel()
    return _default_panel


async def run_review(
    model: Any,
    text: str,
    chapter_ref: str = "",
    reviewer_ids: list[str] | None = None,
    context: dict[str, str] | None = None,
    panel: ReviewPanel | None = None,
) -> ReviewReport:
    """异步便捷入口：用默认（或指定）面板并发评审 + 主席汇总。

    app 层在 async 端点直接 await；agent 工具在 to_thread 里跑。
    """
    p = panel or default_panel()
    return await p.run_review(
        model, text, chapter_ref=chapter_ref, reviewer_ids=reviewer_ids, context=context
    )
