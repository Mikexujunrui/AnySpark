"""
anyspark.template.patterns — 模式库：模板模型 + L2 开发者默认库。

模板四要素元数据：{ 粒度, 位置, 功能, 可变参数 }。
自然语言描述是唯一介质；模板只做探索方向生成器（粗粒度航向），绝不做内容框架。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from anyspark.core.db import connect as sqlite_connect

# 模板四要素默认分类集（S50：内容化——默认建议集；外部模板导入不强制校验，
# 分类是元数据建议非硬约束，内容扩展通道在 ExternalLibrary.import_template）
GRANULARITY_DEFAULT: tuple[str, ...] = ("全书", "卷", "章", "场景", "段落")
POSITION_DEFAULT: tuple[str, ...] = ("开局", "发展", "高潮", "结局")
FUNCTION_DEFAULT: tuple[str, ...] = ("铺垫", "主线", "悬念", "爽点", "情感")
# 类型注解（默认建议集，供 IDE/类型检查；运行时接受任意内容）
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


class ExternalLibrary:
    """外部扩展模式库（机制 6 原 L3：用户导入/平台共享，SQLite）。

    与精选默认库（原 L2）合并供给探索（模板是探索方向生成器，自然语言唯一介质）；
    外部模板可删，精选默认库不可。
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        # S79：连接配置收敛到 anyspark.core.db.connect
        self._conn = sqlite_connect(self._db)
        self._lock = threading.Lock()
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS templates_external (
                name TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                granularity TEXT NOT NULL DEFAULT '章',
                position TEXT NOT NULL DEFAULT '发展',
                function TEXT NOT NULL DEFAULT '主线',
                params TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def import_template(
        self,
        name: str,
        description: str,
        granularity: str = "章",
        position: str = "发展",
        function: str = "主线",
        params: list[str] | None = None,
    ) -> Template:
        import json as _json

        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO templates_external "
                "(name, description, granularity, position, function, params, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    name,
                    description,
                    granularity,
                    position,
                    function,
                    _json.dumps(params or []),
                    now,
                ),
            )
            self._conn.commit()
        return Template(
            name=name,
            description=description,
            granularity=granularity,  # type: ignore[arg-type]
            position=position,  # type: ignore[arg-type]
            function=function,  # type: ignore[arg-type]
            params=params or [],
            layer="external",
        )

    def list_external(self) -> list[Template]:
        import json as _json

        rows = self._conn.execute("SELECT * FROM templates_external ORDER BY rowid DESC").fetchall()
        return [
            Template(
                name=r["name"],
                description=r["description"],
                granularity=r["granularity"],
                position=r["position"],
                function=r["function"],
                params=_json.loads(r["params"] or "[]"),
                layer="external",
            )
            for r in rows
        ]

    def all(self) -> list[Template]:
        """L2 + L3 合并（探索用的完整模式库）。"""
        return default_library() + self.list_external()

    def delete(self, name: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM templates_external WHERE name=?", (name,))
            self._conn.commit()
