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
