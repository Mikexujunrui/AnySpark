"""
anyspark.server.tools_extras — Agent 侧扩展能力工具（S32 补齐 Agent 可见性）。

背景：审计发现探索/检测/资料三类核心能力只有 HTTP API（前端面板驱动），
写作 Agent 的注册表里只有 list/read/write/file——"能力存在但智能体看不到"。
本模块按 pi 的扩展注册模式（能力即工具、按需调用）补三个工具：

1. explore_direction — 任务方向不明确时多智能体探索（机制 7 补进 Agent 闭环）
2. read_material    — 查阅已上传资料摘要卡（设定/世界观文档，写正文前查证）
3. check_text       — 检测网审读正文（写完自查硬伤，机制 8 补进 Agent 闭环）

对齐 pi 的渐进式披露：工具描述常驻（schema 自带），完整行为封装在工具内部，
Agent 仅在对应场景调用，不向 system_prompt 平铺大段能力说明。
"""

from __future__ import annotations

from typing import Any

from anyspark.core import ToolCall
from anyspark.core.protocol import ParamSpec, ToolResult, ToolSpec
from anyspark.explore import IntentUnderstander, run_exploration


def make_explore_implementer(model: Any, dim_names: list[str] | None = None) -> tuple[Any, Any]:
    """探索方向工具：意图理解 + 多智能体并行探索 → 候选方向。

    Agent 在任务方向不明确时调用；返回方向卡供 Agent 呈现给用户选择
    （不自动固化——固化仍由用户决定，符合"写作即对话"）。
    dim_names：S50 内容化维度集（用户可增删改）；缺省用默认种子——S62 修正：
    agent 工具路径不再绕过维度内容化（此前回落 DEFAULT_DIMENSIONS，用户自定义
    维度在自主探索时不生效）。
    """

    spec = ToolSpec(
        name="explore_direction",
        description=(
            "当写作任务方向不明确时使用：对任务/种子做多智能体探索，"
            "生成 2-4 个候选写作方向（标题+说明+维度+流派术语），"
            "供你呈现给用户选择。方向明确时不要调用，直接写正文。"
        ),
        params=[
            ParamSpec(
                name="task",
                type="string",
                required=True,
                description="写作任务或种子描述",
            )
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        task = str(arguments.get("task", "")).strip()
        if not task or len(task) > 2000:
            return ToolResult(call=call, ok=False, content="缺少有效的 task 参数。")
        try:
            understander = IntentUnderstander(model)
            concept = understander.understand(task)
            cards = run_exploration(
                model, task, concept, constraints=None, n_explorers=4, dimensions=dim_names
            )
            c = concept.get("concept", {})
            lines = [
                "【意图理解】",
                f"- 画面核心：{c.get('core', '')}",
                f"- 情绪基调：{c.get('mood', '')}",
                f"- 类型直觉：{c.get('genre', '')}",
            ]
            qs = concept.get("questions", [])
            if qs:
                lines.append("关键歧义：")
                lines.extend(f"  - {q}" for q in qs[:3])
            lines.append("")
            lines.append("【候选方向】（请呈现给用户选择）")
            for i, card in enumerate(cards, 1):
                term = f"（{card.term}）" if card.term else ""
                lines.append(
                    f"{i}. {card.title} [{card.dimension}·{card.source}]{term}\n   {card.summary}"
                )
            return ToolResult(
                call=call,
                ok=True,
                content="\n".join(lines),
                data={"cards": [card.to_dict() for card in cards]},
            )
        except Exception as exc:  # 探索失败不阻断写作主链路
            return ToolResult(call=call, ok=False, content=f"探索失败：{exc}")

    return spec, implementer


def make_read_material_implementer(materials: Any) -> tuple[Any, Any]:
    """资料查阅工具：按标题/主题/术语/角色模糊匹配资料摘要卡。"""

    spec = ToolSpec(
        name="read_material",
        description=(
            "查阅已上传的资料摘要卡（设定/世界观/参考文档）。"
            "写正文需要设定细节或查证时使用；title 可给关键词，"
            "不给则列出全部资料标题。"
        ),
        params=[
            ParamSpec(
                name="title",
                type="string",
                required=True,
                description="资料标题关键词（可模糊匹配）",
            )
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        q = str(arguments.get("title", "")).strip()
        cards = materials.list()
        if not q:
            if not cards:
                return ToolResult(call=call, ok=True, content="资料库为空。")
            lines = ["资料库现有材料："]
            lines.extend(f"- {m.title}（{m.topic}）" for m in cards)
            return ToolResult(call=call, ok=True, content="\n".join(lines))
        matched = [
            m
            for m in cards
            if q in m.title
            or q in m.topic
            or any(q in t for t in m.terms)
            or any(q in c for c in m.characters)
        ]
        if not matched:
            titles = "、".join(m.title for m in cards) or "（空）"
            return ToolResult(
                call=call,
                ok=False,
                content=f"未找到与「{q}」匹配的资料。现有：{titles}",
            )
        parts = []
        for m in matched[:2]:
            parts.append(
                f"【{m.title}】\n主题：{m.topic}\n要点：{'；'.join(m.key_points[:5])}"
                f"\n设定：{'；'.join(m.key_settings[:5])}\n角色：{'、'.join(m.characters[:8])}"
                f"\n术语：{'、'.join(m.terms[:8])}"
            )
        return ToolResult(
            call=call,
            ok=True,
            content="\n\n".join(parts),
            data={"ids": [m.id for m in matched[:2]]},
        )

    return spec, implementer


def make_check_implementer(model: Any) -> tuple[Any, Any]:
    """检测网审读工具：写完自查硬伤（机制 8 补进 Agent 闭环）。"""

    from anyspark.check import run_review

    spec = ToolSpec(
        name="check_text",
        description=(
            "用检测网审读正文（一致性/动机因果/情感连贯/信息流/结构节奏/"
            "预期管理/主题连贯），返回硬伤(🔴)与建议(💡)报告。"
            "写完章节后可用来自查。"
        ),
        params=[
            ParamSpec(
                name="target",
                type="string",
                required=True,
                description="审读对象描述（如章节名）",
            ),
            ParamSpec(
                name="text",
                type="string",
                required=True,
                description="要审读的正文全文",
            ),
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        target = str(arguments.get("target", "")).strip()
        text = str(arguments.get("text", ""))
        if not text.strip():
            return ToolResult(call=call, ok=False, content="缺少待审文本。")
        try:
            report = run_review(model, target or "未命名", text[:20000])
            return ToolResult(
                call=call,
                ok=True,
                content=report.render(),
                data={"hard_count": report.hard_count},
            )
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"审读失败：{exc}")

    return spec, implementer
