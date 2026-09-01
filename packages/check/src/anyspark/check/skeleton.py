"""
anyspark.check.skeleton — 系统骨架检测项（硬编码默认值，第一性原理）。

设计（DESIGN 机制 9）：静态骨架只覆盖已预见的错（一致性/动机因果/情感连贯/
信息流/结构节奏/预期管理/主题连贯）。用户可增删。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SkeletonCheckItem:
    """一个骨架检测项（硬编码默认值）。"""

    category: str
    description: str  # 检测什么（自然语言，供 AI 检测者理解）


# 系统骨架（第一性原理，硬编码默认值）
SKELETON_CHECKS: list[SkeletonCheckItem] = [
    SkeletonCheckItem(
        "一致性",
        "事实/设定/时间线是否自洽：人物年龄、地点、已知设定不得前后矛盾；时间顺序合理。",
    ),
    SkeletonCheckItem(
        "动机因果",
        "角色行为是否有清晰动机，事件是否有因果链；无因之果/无果之因要标出。",
    ),
    SkeletonCheckItem(
        "情感连贯",
        "角色情绪变化是否连贯自然，不突兀断裂；情绪峰值是否有铺垫。",
    ),
    SkeletonCheckItem(
        "信息流",
        "悬念揭示节奏是否合理：关键信息揭示时机、伏笔铺设与回收是否失衡。",
    ),
    SkeletonCheckItem(
        "结构节奏",
        "段落/章节节奏是否单调或失衡：动作-对话-描写密度；拖沓或过快的段落。",
    ),
    SkeletonCheckItem(
        "预期管理",
        "吊起的期待是否兑现：承诺的回报、埋下的钩子是否被遗忘。",
    ),
    SkeletonCheckItem(
        "主题连贯",
        "母题/主题是否漂移：核心主题线索在中途丢失或转向。",
    ),
]

# 用户可增删骨架：扩展点（后续可持久化用户增删）


# ── S247：学术骨架（学术体裁的第一性原理默认值，与 SKELETON_CHECKS 同型）──
# 演化说明：S246 曾以"种子入库用户骨架"交付学术七项，实测缺陷——用户骨架
# 无体裁维度，小说文本的检测也被学术项污染（成本翻倍+无关发现）。修正为
# 内置双骨架 + 按文体选择（get_pack）；用户增删仍在所选骨架之上叠加。
ACADEMIC_CHECKS: list[SkeletonCheckItem] = [
    SkeletonCheckItem(
        "术语一致性",
        "同一概念在全文中的称谓是否统一：术语、译名、缩写不得随意变换；首次出现应有定义。",
    ),
    SkeletonCheckItem(
        "论断证据",
        "每个论断是否有数据/文献/推导支撑：无出处的断言、以'显然''众所周知'搪塞的要标出。",
    ),
    SkeletonCheckItem(
        "结构完备",
        "结构要素是否完整且各司其职：引言是否交代问题与贡献、方法是否可复现、结论是否回应引言。",
    ),
    SkeletonCheckItem(
        "逻辑链条",
        "推理步骤是否衔接：有无逻辑跳跃、循环论证、前提与结论错位。",
    ),
    SkeletonCheckItem(
        "语言规范",
        "是否存在口语化表达、绝对化断言（'证明了'应为'结果表明'）、无意义修饰与冗余。",
    ),
    SkeletonCheckItem(
        "数据一致",
        "数字/单位/统计指标在摘要、正文、图表描述之间是否一致；前后引用同一数据是否同值。",
    ),
    SkeletonCheckItem(
        "诚信自查",
        "是否有疑似空泛套话、无出处的引文、语焉不详的关键表述——提示作者逐条核实（诚信护栏：辅助自查，不代替作者判断）。",
    ),
]

# 内置骨架注册表：按文体选择基础集（novel=缺省，历史行为不变）
CHECK_PACKS: dict[str, list[SkeletonCheckItem]] = {
    "novel": SKELETON_CHECKS,
    "academic": ACADEMIC_CHECKS,
}


def get_pack(name: str | None) -> list[SkeletonCheckItem]:
    """按文体名取内置骨架；未知/缺省回退 novel（向后兼容）。"""
    return CHECK_PACKS.get((name or "novel").strip().lower(), SKELETON_CHECKS)
