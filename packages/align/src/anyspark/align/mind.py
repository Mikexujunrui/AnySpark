"""
anyspark.align.mind — 心智模型会话规划器（S53：心智指导保留，与能力解耦联动）。

主人架构判断（DESIGN §12.17 + S53 修正）：
- 心智模型是复杂系统，**指导主循环规划会话**——不是把偏好机械全量注入写作工具
- **指导性不能去掉**：文风偏好（喜欢白话文风）、习惯（篇幅/节奏偏好）都必须记录
  在心智里并保持指导作用——但不能退化成"全量堆进正文"
- **与能力解耦联动**：心智=偏好（作者喜欢什么），skill=能力（怎么做到）；
  装配时用文风偏好**匹配对应的 skill** 按需注入（作者喜欢白话 → 白话文 skill 进上下文）

本模块落地：
- 心智条目分类（manual.category）：collab（协作=怎么配合）/ style（文风=怎么写）/
  habit（习惯=行为偏好）
- MindPlanner 读**全部类别** → 产出 SessionPlan：
  - collab → 建议档位 + 协作约定
  - style → 文风偏好（驱动 skill 匹配 + 简洁注入，渐进式披露）
  - habit → 习惯（简洁注入，渐进式披露）
- 主循环装配时应用：协作约定/文风偏好/习惯以**简洁指导块**注入（渐进式披露，
  不堆砌全量条目），文风偏好用于选择对应叙事技巧 skill

哲学：机制（分类/规划逻辑/匹配/装配点）硬编码；内容（条目/偏好/协作约定）自然语言。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .manual import ManualEntry, ManualStore


@dataclass
class SessionPlan:
    """一次会话的心智规划（心智模型的输出，指导主循环装配）。"""

    agency_level: int | None = None  # 建议档位（collab 推断；缺省 None=用已存档位）
    collab_notes: list[str] = field(default_factory=list)  # 协作约定（怎么配合）
    style_prefs: list[str] = field(default_factory=list)  # 文风偏好（怎么写）
    habit_notes: list[str] = field(default_factory=list)  # 习惯（行为偏好）
    reason: str = ""  # 规划依据（可观测：为什么这么配）

    def collab_block(self) -> str:
        """渲染协作约定为系统提示块（顶部，非写作内容）。"""
        if not self.collab_notes:
            return ""
        lines = ["# 会话协作约定（怎么配合我，非写作内容）"]
        lines.extend(f"- {n}" for n in self.collab_notes)
        return "\n".join(lines)

    def mind_block(self) -> str:
        """渲染心智指导块（文风偏好 + 习惯，渐进式披露：只列关键条目）。

        指导性保留但不堆砌——心智条目多了只取高置信/锁定条目。
        """
        parts: list[str] = []
        if self.style_prefs:
            lines = ["# 用户文风偏好（写作时体现此风格）"]
            lines.extend(f"- {n}" for n in self.style_prefs)
            parts.append("\n".join(lines))
        if self.habit_notes:
            lines = ["# 用户写作习惯（写作时遵循）"]
            lines.extend(f"- {n}" for n in self.habit_notes)
            parts.append("\n".join(lines))
        return "\n\n".join(parts)


_ACTIVITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _context_overlap(entry: ManualEntry, context: str) -> int:
    """条目与本轮会话意图（context）的关键词重叠数（双字窗口，机制硬编码）。

    S61：渐进式披露的"按本轮相关动态选取"（DESIGN §12.17）——心智块不再静态
    取前 N 条，而是本轮相关条目优先；context 为空时退化为纯置信度排序。
    """
    if not context:
        return 0
    from .manual import keyword_set

    return len(keyword_set(context) & keyword_set(entry.content))


def _key_entries(
    entries: list[ManualEntry], limit: int = 5, context: str = ""
) -> list[ManualEntry]:
    """取关键条目（渐进式披露，限量防堆砌）：

    锁定优先 → 活跃度（high>medium>low，冷条沉没）→ 本轮相关（context 重叠）
    → 置信度。锁定的硬规则永远优先披露；低活跃冷条沉底不占名额。
    """
    if not entries:
        return []

    def score(e: ManualEntry) -> tuple[int, int, int, float]:
        return (
            1 if e.locked else 0,
            -_ACTIVITY_ORDER.get(e.activity, 1),
            _context_overlap(e, context),
            e.confidence,
        )

    return sorted(entries, key=score, reverse=True)[:limit]


class MindPlanner:
    """会话规划器：心智条目（全类别）→ 协作策略 + 偏好/习惯指导。"""

    def __init__(self, manual: ManualStore) -> None:
        self._manual = manual

    def plan(
        self,
        book_id: str = "main",
        base_agency: int | None = None,
        context: str = "",
    ) -> SessionPlan:
        """产出会话规划（读全部心智类别）。

        base_agency：保留参数兼容（S62：档位推断已移除，不再使用）。
        context：本轮会话意图（用户请求），用于渐进式披露按相关动态选取
        （DESIGN §12.17：条目按'本轮相关'动态选取，不静态堆前 N 条）。
        """
        global_entries = self._manual.list("global")
        project_entries = self._manual.list("project", book_id)
        all_entries = [*global_entries, *project_entries]
        collab = [e for e in all_entries if e.category == "collab"]
        style = [e for e in all_entries if e.category == "style"]
        habit = [e for e in all_entries if e.category == "habit"]
        plan = SessionPlan()
        # 协作约定披露（S62：档位不再由关键词启发式推断——内容判断交给 L2 LLM
        # 建议（/api/mind/agency-suggest），不自动应用，用户主权）
        if collab:
            key_collab = _key_entries(collab, context=context)
            plan.collab_notes = [e.content for e in key_collab]
        # 文风偏好（style，指导性保留，驱动 skill 匹配）
        if style:
            plan.style_prefs = [e.content for e in _key_entries(style, context=context)]
        # 习惯（habit，指导性保留）
        if habit:
            plan.habit_notes = [e.content for e in _key_entries(habit, context=context)]
        parts = [f"collab {len(collab)}", f"style {len(style)}", f"habit {len(habit)}"]
        plan.reason = "；".join(parts)
        return plan
