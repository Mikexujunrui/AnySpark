"""
anyspark.server.tools_check — 检测工具（S104：智能体自行调用，替代人用 /api/check）。

背景：S63 退役 check_text（彼时弱化版无图谱证据/默认关）；S59 workflow review_chapter
覆盖"审读+改写循环"但偏重。设计定案：检测是智能体能力（写作中自查硬伤/自定义规则），
不是人类手工调用的面板。重建强化版：

- 无规则：run_review 硬伤检测（多检测者骨架项，并行）→ 报告文本
- 有规则：compile_with_model 自然语言规则编译 → 确定性执行器命中列表
  （模板 fallback；模型/模板都识别不了时明确告知，不静默丢弃——对齐 DESIGN §1）

注册于 enable_domain（写作必需自查能力，默认开）。
"""

from __future__ import annotations

from typing import Any

from anyspark.check import compile_rule, compile_with_model, run_review
from anyspark.core import ParamSpec, ToolCall, ToolResult, ToolSpec


def make_check_implementer(model: Any) -> tuple[Any, Any]:
    """硬伤检测 + 自然语言规则检测工具（S104 重建）。

    model：ToolContext.model（agent 当前模型——按 S98 任务分流后的模型）。
    """

    spec = ToolSpec(
        name="check_text",
        description=(
            "检测一段写作正文的硬伤（S104：智能体自查能力）。"
            "写完章节/段落自查，或审读他人文本时使用——"
            "无规则时返回硬伤检测报告（逻辑矛盾/重复赘述/角色/时序等骨架项）；"
            "传 rule 时按自然语言规则检测命中（如'不要用破折号'/'主角不能 OOC'）。"
            "适合在 write_chapter 之后、或改稿前自查一遍再交付。"
        ),
        params=[
            ParamSpec(
                name="text",
                type="string",
                required=True,
                description="要检测的正文文本",
            ),
            ParamSpec(
                name="rule",
                type="string",
                required=False,
                description="可选：自然语言自定义规则（如'不要用破折号'）；缺省=标准硬伤检测",
            ),
        ],
    )

    def impl(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        text = str(arguments.get("text", "")).strip()
        rule = str(arguments.get("rule", "")).strip()
        if not text:
            return ToolResult(call=call, ok=False, content="缺少参数 text。")
        try:
            if rule:
                # 自然语言规则：LLM 编译（内容判断）→ 失败回退轻量模板
                compiled = compile_with_model(rule, model) or compile_rule(rule)
                if compiled is None:
                    return ToolResult(
                        call=call,
                        ok=True,
                        content=(
                            "未能识别的规则：请用更具体的字面/结构描述"
                            "（如'不要用破折号'/'每段不超过 3 行'）。"
                        ),
                    )
                hits = compiled.checker(text)
                if not hits:
                    return ToolResult(
                        call=call,
                        ok=True,
                        content=f"规则「{compiled.description}」：未命中，全部通过。",
                    )
                lines = [f"规则「{compiled.description}」命中 {len(hits)} 处："]
                lines.extend(f"- {h}" for h in hits[:20])
                if len(hits) > 20:
                    lines.append(f"…等共 {len(hits)} 处")
                return ToolResult(call=call, ok=True, content="\n".join(lines))
            # 标准硬伤检测
            report = run_review(model, "自查", text)
            if report.hard_count == 0:
                return ToolResult(
                    call=call,
                    ok=True,
                    content="硬伤检测通过：未发现硬伤（逻辑矛盾/重复赘述/骨架项）。",
                )
            return ToolResult(
                call=call,
                ok=True,
                content=(
                    f"硬伤检测发现 {report.hard_count} 处：\n"
                    + "\n".join(
                        f"- [{f.severity}] {f.message}"
                        + (f"（{f.evidence}）" if f.evidence else "")
                        for f in report.findings[:20]
                    )
                    + (f"\n…共 {report.hard_count} 处" if report.hard_count > 20 else "")
                ),
            )
        except Exception as exc:  # 检测失败不阻断写作主链路
            return ToolResult(call=call, ok=False, content=f"检测失败：{str(exc)[:160]}")

    return spec, impl
