"""
anyspark.check.reviewers — 多检测者并行（复用多智能体模式）。

设计（DESIGN 机制 9）：一个查一致性/一个查情感弧/一个查信息流……轻量并行，
汇总成审读报告。AI 动态生成检测项针对当前作品+阶段具体化。
"""

from __future__ import annotations

import asyncio
from typing import Any

from anyspark.core import Message

from .report import Finding, ReviewReport
from .skeleton import SkeletonCheckItem

REVIEW_PROMPT = (
    """你是小说审读专家，负责检测：「%(category)s」。
检测标准：%(description)s

下面是章节正文。请找出违反该标准的**具体问题**（不是泛泛评价）。
对每个问题输出一条，含：问题描述 / 证据（原文摘录）/ 建议。

输出格式（严格 JSON 数组，不要其它文字）：
"""
    + """[{"message": "问题描述", "evidence": "原文摘录", "suggestion": "建议", "severity": "hard|suggestion"}]
"""  # noqa: E501
    + """severity: hard=硬伤（设定矛盾/断章失忆等必须修的错）；suggestion=改进建议。

正文：
"""
)


class ReviewEngine:
    """多检测者并行审读引擎。"""

    def __init__(self, model: object) -> None:
        self._model = model

    def review(self, target: str, text: str, checks: list[SkeletonCheckItem]) -> ReviewReport:
        """并行跑全部检测项，汇总报告。"""
        report = ReviewReport(target=target)
        results = asyncio.run(self._parallel(text, checks))
        for findings in results:
            report.findings.extend(findings)
        return report

    async def _parallel(self, text: str, checks: list[SkeletonCheckItem]) -> list[list[Finding]]:
        return await asyncio.gather(*[self._call_one(text, check) for check in checks])

    async def _call_one(self, text: str, check: SkeletonCheckItem) -> list[Finding]:
        prompt = REVIEW_PROMPT % {
            "category": check.category,
            "description": check.description,
        }
        prompt += text[:6000]  # 限制 token（轻量）
        output = await asyncio.to_thread(
            self._model.respond,  # type: ignore[attr-defined]
            [Message(role="system", content=prompt)],
            [],
        )
        return _parse_findings(output.text, check.category)


def _parse_findings(raw: str, category: str) -> list[Finding]:
    """宽容解析检测结果 JSON。"""
    import json
    import re

    cleaned = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    findings = []
    for d in data:
        if not isinstance(d, dict):
            continue
        severity = d.get("severity", "suggestion")
        sev: Any = "hard" if severity == "hard" else "suggestion"
        findings.append(
            Finding(
                category=category,
                severity=sev,
                message=str(d.get("message", "")),
                evidence=str(d.get("evidence", "")),
                suggestion=str(d.get("suggestion", "")),
                source="dynamic",
            )
        )
    return findings


def run_review(
    model: object,
    target: str,
    text: str,
    checks: list[SkeletonCheckItem] | None = None,
) -> ReviewReport:
    """便捷入口：默认跑全部骨架检测项。"""
    from .skeleton import SKELETON_CHECKS

    return ReviewEngine(model).review(target, text, checks or SKELETON_CHECKS)
