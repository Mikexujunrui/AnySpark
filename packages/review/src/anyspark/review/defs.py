"""
anyspark.review.defs — 评审团数据模型。

评审员 = 内容（YAML persona + 评分维度）；评审团 = 机制（并发编排 + 汇总）。
本模块只定义数据模型：无 I/O、无 LLM 依赖（纯机制层，可独立单测）。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScoreDim:
    """一个评分维度（带权重）。内容随 YAML 定义，机制只做加权平均。"""

    name: str
    weight: float
    desc: str = ""


@dataclass
class ReviewerDef:
    """评审员定义：人格 + 评分维度 + 外部上下文需求。

    context_keys: 评审员需要的外部上下文块名（如 "check_report"/"foreshadow"/
    "graph"/"role_cards"）。调用方按名注入，取不到的块跳过（评审员仍可评审，
    只是缺少该参考）。缺省空列表 = 纯文本评审，不需要外部上下文。
    """

    id: str
    name: str
    persona: str
    category: str = "professional"
    avatar: str = "user"
    active: bool = True
    scoring_dimensions: list[ScoreDim] = field(default_factory=list)
    context_keys: list[str] = field(default_factory=list)
    custom: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "avatar": self.avatar,
            "category": self.category,
            "active": self.active,
            "scoring_dimensions": [
                {"name": d.name, "weight": d.weight, "desc": d.desc}
                for d in self.scoring_dimensions
            ],
            "context_keys": list(self.context_keys),
            "custom": self.custom,
        }

    def to_detail(self) -> dict[str, object]:
        d = self.to_dict()
        d["persona"] = self.persona
        return d

    def weighted_overall(self, scores: dict[str, float]) -> float | None:
        """按评分维度权重计算综合分（确定性，防 LLM 乱打总分）。

        全部已评分维度（带正权重）都齐时返回加权平均；缺失或空维度时返回
        None（调用方回退到 LLM 自报 overall_score）。
        """
        dims = [d for d in self.scoring_dimensions if d.weight > 0]
        if not dims:
            return None
        pairs = [(d, scores.get(d.name)) for d in dims]
        if any(s is None for _, s in pairs):
            return None
        total = sum(d.weight * float(s) for d, s in pairs if s is not None)
        return round(total, 1)


@dataclass
class ReviewResult:
    """单个评审员的评审结果（LLM 输出解析后的结构化形态）。"""

    reviewer_id: str
    reviewer_name: str
    category: str
    scores: dict[str, float] = field(default_factory=dict)
    overall_score: float = 0.0
    highlights: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    comment: str = ""  # 人格语气的整体评价（人设管语气、结构管质量）
    raw_text: str = ""
    error: str = ""


@dataclass
class ReviewReport:
    """评审团汇总报告：综合分 + 主席汇总裁决 + 各评审员详情。

    render()        → markdown 完整报告（给人看，进对话流/审读面板）
    render_compact() → 紧凑摘要（给 agent 工具回填，省 token）
    """

    chapter_ref: str = ""
    overall_score: float = 0.0
    summary: str = ""
    consensus: list[str] = field(default_factory=list)
    divergences: list[str] = field(default_factory=list)
    top_suggestions: list[str] = field(default_factory=list)
    individual_reviews: list[dict[str, object]] = field(default_factory=list)
    reviewer_count: int = 0
    timestamp: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def valid_count(self) -> int:
        """成功返回结果的评审员数（不含错误占位）。"""
        return sum(1 for r in self.individual_reviews if not r.get("error"))

    def _score_line(self) -> str:
        if self.overall_score > 0:
            return (
                f"综合评分：**{self.overall_score:.1f}/10**"
                f"（{self.valid_count}/{self.reviewer_count} 位评审员）"
            )
        return f"（{self.valid_count}/{self.reviewer_count} 位评审员完成评审）"

    def render(self) -> str:
        """完整报告（markdown，给人看）。"""
        lines = [f"# 评审团报告：{self.chapter_ref or '（未指定章节）'}", ""]
        lines.append(self._score_line())
        if self.summary:
            lines.extend(["", "## 主席汇总裁决", self.summary])
        if self.consensus:
            lines.extend(["", "**共识**"])
            lines.extend(f"- {c}" for c in self.consensus)
        if self.divergences:
            lines.extend(["", "**分歧**"])
            lines.extend(f"- {d}" for d in self.divergences)
        if self.top_suggestions:
            lines.extend(["", "**优先建议**"])
            lines.extend(f"- {s}" for s in self.top_suggestions)
        for r in self.individual_reviews:
            if r.get("error"):
                lines.extend(["", f"## {r.get('reviewer_name', '?')} — ⚠️ {r['error']}"])
                continue
            name = r.get("reviewer_name", "?")
            avatar = r.get("avatar", "")
            score = r.get("overall_score", 0)
            head = f"{avatar} {name}" if avatar else name
            score_txt = f"{score:.1f}/10" if isinstance(score, (int, float)) and score else "未打分"
            lines.extend(["", f"## {head} — {score_txt}"])
            comment = r.get("comment")
            if comment:
                lines.append(str(comment))
            raw_scores = r.get("scores")
            scores = raw_scores if isinstance(raw_scores, dict) else {}
            if scores:
                dims_txt = "；".join(f"{k} {v}/10" for k, v in scores.items())
                lines.append(f"评分：{dims_txt}")
            for label, key in (("亮点", "highlights"), ("问题", "issues"), ("建议", "suggestions")):
                raw_items = r.get(key) or []
                items = raw_items if isinstance(raw_items, list) else []
                if items:
                    lines.append(f"**{label}**")
                    lines.extend(f"- {i}" for i in items[:5])
        if self.errors:
            lines.extend(["", "## 未完成", *[f"- {e}" for e in self.errors]])
        return "\n".join(lines)

    def render_compact(self) -> str:
        """紧凑摘要（agent 工具回填 / API 摘要用，省 token）。"""
        lines = [f"评审团报告：{self.chapter_ref or '（未指定章节）'}"]
        if self.overall_score > 0:
            lines.append(
                f"综合 {self.overall_score:.1f}/10（{self.valid_count}/{self.reviewer_count} 位）"
            )
        if self.summary:
            lines.append(f"主席：{self.summary}")
        if self.top_suggestions:
            lines.append("优先建议：" + "；".join(self.top_suggestions[:3]))
        for r in self.individual_reviews:
            if r.get("error"):
                lines.append(f"- {r.get('reviewer_name', '?')}: ⚠️ {r['error']}")
                continue
            score = r.get("overall_score", 0)
            score_txt = f"{score:.1f}/10" if isinstance(score, (int, float)) and score else "未打分"
            lines.append(f"- {r.get('reviewer_name', '?')} {score_txt}")
        return "\n".join(lines)
