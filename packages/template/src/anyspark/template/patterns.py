"""
anyspark.template.patterns — 模式库：模板模型 + L2 开发者默认库。

模板四要素元数据：{ 粒度, 位置, 功能, 可变参数 }。
自然语言描述是唯一介质；模板只做探索方向生成器（粗粒度航向），绝不做内容框架。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# 模板四要素
Granularity = Literal["全书", "卷", "章", "场景", "段落"]
Position = Literal["开局", "发展", "高潮", "结局"]
Function = Literal["铺垫", "主线", "悬念", "爽点", "情感"]


@dataclass
class Template:
    """一个模式模板（自然语言描述 + 轻量元数据）。"""

    name: str
    description: str  # 自然语言描述（怎么用，能变出什么）
    granularity: Granularity = "章"
    position: Position = "发展"
    function: Function = "主线"
    params: list[str] = field(default_factory=list)  # 可变参数（如"反派身份"）
    layer: Literal["default", "external"] = "default"

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "granularity": self.granularity,
            "position": self.position,
            "function": self.function,
            "params": self.params,
            "layer": self.layer,
        }


# L2 开发者默认库：精选少量高质量模式（解决个人用户大部分问题）
DEFAULT_TEMPLATES: list[Template] = [
    Template(
        name="废柴流开局·反差铺垫",
        description=(
            "主角以废柴/边缘人身份登场，通过反差暗示隐藏潜力（天赋/血脉/身份），"
            "铺垫后续觉醒。可变参数：废柴形态（灵力尽失/体质孱弱/被误解）、觉醒契机。"
        ),
        granularity="场景",
        position="开局",
        function="铺垫",
        params=["废柴形态", "觉醒契机"],
    ),
    Template(
        name="三幕·先抑后扬",
        description=(
            "故事按三幕推进：压低(困境/损失)→谷底(最坏时刻)→逆转(蓄力爆发)。"
            "情绪峰值在后半段，前半段克制蓄力。可变参数：谷底事件、逆转资源。"
        ),
        granularity="卷",
        position="发展",
        function="主线",
        params=["谷底事件", "逆转资源"],
    ),
    Template(
        name="双线·明线暗线交织",
        description=(
            "一条明线（当下行动）与一条暗线（历史真相/隐藏身份）交织推进，"
            "暗线线索逐章洒落，结局汇合。可变参数：暗线内容、汇合方式。"
        ),
        granularity="全书",
        position="发展",
        function="悬念",
        params=["暗线内容", "汇合方式"],
    ),
    Template(
        name="误会→真相·延迟揭示",
        description=(
            "以误会制造冲突与张力，真相延迟揭示（角色都基于错误认知行动），"
            "揭示时机=情绪峰值。可变参数：误会内容、揭示代价。"
        ),
        granularity="章",
        position="高潮",
        function="情感",
        params=["误会内容", "揭示代价"],
    ),
    Template(
        name="氛围先行·情绪锚点",
        description=(
            "不急着推进情节，先用场景/感官细节建立情绪基调，用情绪锚点"
            "（意象/动作/物件）承载人物心理。可变参数：情绪基调、锚点意象。"
        ),
        granularity="场景",
        position="开局",
        function="情感",
        params=["情绪基调", "锚点意象"],
    ),
]


def default_library() -> list[Template]:
    """L2 默认库（副本，调用方可增删）。"""
    return [Template(**t.to_dict()) for t in DEFAULT_TEMPLATES]  # type: ignore[arg-type]
