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
from .skeleton import SKELETON_CHECKS, SkeletonCheckItem

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

正文（可能是长章的一部分分块；若正文在此处截断，只检测本块内的具体问题）：
"""
)


class ReviewEngine:
    """多检测者并行审读引擎。

    S71 已知重复标记：与 anyspark.review.panel.ReviewPanel 是同一机制模式
    （并行 LLM 调用 → 宽容 JSON 解析 → 汇总报告），语义分工：本引擎=确定性
    硬伤检测（S7 检测网），ReviewPanel=人格化评价（S64）。跨包抽公共成本 >
    收益（core 零依赖约束不宜放编排），接受重复；若未来出现第三处并行
    LLM 编排，再抽 core 公共组件。

    S145（第三方评审 4.3）：长章覆盖修复——此前 text[:6000] 截断导致
    >6000 字章节后半段全部检测者零覆盖。改为滑动窗口分块（CHUNK 字 + 重叠），
    每检测者逐块检测汇总；短文本保持单块原行为。
    """

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
        findings: list[Finding] = []
        for chunk in _split_chunks(text):
            prompt = REVIEW_PROMPT % {
                "category": check.category,
                "description": check.description,
            }
            prompt += chunk
            output = await asyncio.to_thread(
                self._model.respond,  # type: ignore[attr-defined]
                [Message(role="system", content=prompt)],
                [],
            )
            findings.extend(_parse_findings(output.text, check.category))
        return findings


# S145：长章分块参数（评审 4.3）——6000 字窗口 + 500 字重叠，避免切断上下文
CHUNK_SIZE = 6000
CHUNK_OVERLAP = 500


def _split_chunks(text: str) -> list[str]:
    """长文滑动窗口分块：短文本（≤CHUNK_SIZE）单块原行为；长文本切块，
    相邻块重叠 CHUNK_OVERLAP 字（衔接处上下文不丢）。空文本返回空列表。"""
    if not text:
        return []
    if len(text) <= CHUNK_SIZE:
        return [text]
    chunks: list[str] = []
    step = CHUNK_SIZE - CHUNK_OVERLAP
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += step
    return chunks


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
    *,
    book_context: str = "",
) -> ReviewReport:
    """便捷入口：默认跑全部骨架检测项。

    S194：传 book_context 时自动生成作品专属检测项，与静态骨架合并执行
    （DESIGN 机制 9 第②层落地）。
    """
    all_checks = list(checks or SKELETON_CHECKS)
    if book_context.strip():
        all_checks.extend(generate_dynamic_checks(model, book_context))
    return ReviewEngine(model).review(target, text, all_checks)


# 动态检测项生成提示词（DESIGN 机制 9 第②层：AI 针对当前作品具体化检测项）
_DYNAMIC_CHECKS_PROMPT = (
    "你是小说审读专家。根据以下作品信息，生成 2-4 条**作品专属**检测项。\n"
    "每条针对这个作品的具体设定/角色/伏笔——不要泛泛的通用检测项。\n"
    "\n"
    "输出格式（严格 JSON 数组，不要其它文字）：\n"
    '[{"category": "一致性", "description": "检查XX是否与第N章设定一致"}]\n'
    "\n"
    "示例（针对哈利波特）：\n"
    '[{"category": "一致性", "description": "检查哈利的伤疤位置描述是否前后一致（额头闪电形）"},\n'
    ' {"category": "伏笔", "description": "检查奇洛触碰哈利时是否与伏地魔寄生设定一致"}]\n'
)


def generate_dynamic_checks(
    model: object,
    book_context: str,
) -> list[SkeletonCheckItem]:
    """DESIGN 机制 9 第②层：AI 动态生成检测项。

    根据当前作品的图谱实体/设定档/伏笔状态，让 LLM 生成作品专属的检测项
    （如"检查陈渡的灯塔看守人身份是否前后一致"），与静态骨架合并执行。

    book_context = 作品上下文摘要（图谱实体 + 设定档 + 伏笔状态的文本块）。
    """
    if not book_context.strip():
        return []
    from anyspark.core.jsonutil import parse_json_array

    messages = [
        Message(role="system", content=_DYNAMIC_CHECKS_PROMPT),
        Message(role="user", content=f"作品上下文：\n{book_context[:4000]}"),
    ]
    out = model.respond(messages, [])  # type: ignore[attr-defined]
    text = (out.text or "").strip()
    if not text:
        return []
    items = parse_json_array(text)
    if not items:
        return []
    checks: list[SkeletonCheckItem] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category", "")).strip()
        description = str(item.get("description", "")).strip()
        if category and description:
            checks.append(SkeletonCheckItem(category=category, description=description))
    return checks
