"""
anyspark.align.mind — 心智模型会话规划器（S50：心智从写作工具循环移除）。

主人架构判断（DESIGN §12.17）：心智模型是复杂系统，应**指导主循环规划会话**，
而不是把偏好直接注入写作工具。心智记录的多是**习惯/协作方式**，直接进正文
上下文无意义甚至有害（token 浪费、限制发挥）。

本模块落地：
- 心智条目分类（manual.category）：collab（协作=怎么配合）/ style（文风=怎么写）/
  habit（习惯=行为）——旧库默认 style，可编辑
- MindPlanner 读取 **collab 类**条目 → 产出会话协作策略（建议档位 + 协作约定）
- 主循环装配时应用策略（agency_level 未显式给时用规划建议；协作约定注入
  系统提示**顶部**作为协作方式引导，**不是**写作内容）
- style/habit 类条目**不再注入写作工具**（渐进式披露的渐进第一步：全退场，
  将来心智系统完整化后按需引入，但绝不会回到"全量注入正文"）

哲学：机制（分类/规划逻辑/装配点）硬编码；内容（条目/协作约定）自然语言。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .manual import ManualEntry, ManualStore


@dataclass
class SessionPlan:
    """一次会话的协作策略（心智模型的输出，指导主循环装配）。"""

    agency_level: int | None = None  # 建议档位（collab 条目推断；缺省 None=用已存档位）
    collab_notes: list[str] = field(default_factory=list)  # 协作约定（自然语言）
    reason: str = ""  # 规划依据（可观测：为什么这么配）

    def collab_block(self) -> str:
        """渲染协作约定为系统提示块（顶部，非写作内容）。"""
        if not self.collab_notes:
            return ""
        lines = ["# 会话协作约定（怎么配合我，非写作内容）"]
        lines.extend(f"- {n}" for n in self.collab_notes)
        return "\n".join(lines)


# 协作关键词 → 档位偏移（机制：轻量启发式，硬编码；内容判定靠关键词自然语言）
_AGENCY_HINTS: list[tuple[list[str], int]] = [
    (["直接写", "别啰嗦", "别问", "少确认", "一口气", "放手"], 1),  # 用户要自主 → 档位升
    (["先给方案", "先看", "确认", "问一下", "一步步", "别自己发挥", "保守"], -1),  # 要确认 → 档位降
]


def _infer_agency(entries: list[ManualEntry], base: int) -> int:
    """从协作类条目推断档位（base 为已存档位，正负偏移累计后钳制 0-4）。

    同一条目可含正负信号（如'先给方案但直接写'）——累计抵消取净。
    """
    delta = 0
    for e in entries:
        text = e.content
        for kws, off in _AGENCY_HINTS:
            if any(k in text for k in kws):
                delta += off
    return max(0, min(4, base + delta))


class MindPlanner:
    """会话规划器：心智条目（collab）→ 协作策略。"""

    def __init__(self, manual: ManualStore) -> None:
        self._manual = manual

    def plan(self, book_id: str = "main", base_agency: int | None = None) -> SessionPlan:
        """产出协作策略。

        base_agency：当前已存档位（未显式指定时）。从 collab 条目推断偏移。
        """
        global_entries = self._manual.list("global")
        project_entries = self._manual.list("project", book_id)
        collab = [e for e in [*global_entries, *project_entries] if e.category == "collab"]
        plan = SessionPlan()
        if not collab:
            return plan
        # 档位推断（取锁定优先，按置信度排序）
        locked = [e for e in collab if e.locked]
        by_conf = sorted(locked or collab, key=lambda e: e.confidence, reverse=True)
        if base_agency is None:
            base_agency = 2  # 默认中位档
        plan.agency_level = _infer_agency(by_conf, base_agency)
        plan.collab_notes = [e.content for e in by_conf[:5]]
        plan.reason = f"collab 条目 {len(collab)} 条 → 档位 {plan.agency_level}"
        return plan
