"""
anyspark.check.report — 审读报告模型。

报告 = 检测项结果列表。每项：问题/证据/建议/严重度（硬伤 vs 建议）。
定位：建议而非门禁；硬伤标红提醒；决定权在用户。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["hard", "suggestion"]


@dataclass
class Finding:
    """一条检测结果。"""

    category: str  # 检测类别（一致性/动机因果/情感连贯/信息流/结构节奏/预期管理/主题连贯/用户规则）
    severity: Severity
    message: str  # 问题描述（自然语言）
    evidence: str = ""  # 证据（原文摘录）
    suggestion: str = ""  # 建议
    source: str = "skeleton"  # skeleton|dynamic|user|reviewer


@dataclass
class ReviewReport:
    """一章/一部的审读报告。"""

    target: str  # 检测对象（如"第三章"）
    findings: list[Finding] = field(default_factory=list)

    @property
    def hard_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "hard")

    def render(self) -> str:
        """渲染成可读报告（自然语言，给用户看）。"""
        lines = [f"# 审读报告：{self.target}"]
        if not self.findings:
            lines.append("未发现明显问题。")
            return "\n".join(lines)
        for f in self.findings:
            tag = "🔴 硬伤" if f.severity == "hard" else "💡 建议"
            lines.append(f"\n## {tag} · {f.category}")
            lines.append(f"{f.message}")
            if f.evidence:
                lines.append(f"证据：{f.evidence[:120]}")
            if f.suggestion:
                lines.append(f"建议：{f.suggestion}")
        return "\n".join(lines)
