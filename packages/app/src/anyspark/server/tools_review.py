"""
anyspark.server.tools_review — 拟人化评审团 agent 工具（S64）。

把评审团从"HTTP API（人驱动）"变成 agent 可自主调用的工具：
- panel_review：按章节标题评审（并发评审员 + 主席汇总裁决），返回紧凑报告。

哲学（对齐 tools_domain）：机制（工具结构/并发编排）硬编码；内容（评审员人设）
自然语言；agent 只读评审、不改写（改写走 workflow review_chapter 循环）。
无条件注册（对齐 explore_direction）：用户喊"帮我看看这章"时 agent 自主调用，
不预设开关——S63 教训：默认关的工具=没人用的残废通道。
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from anyspark.core import ToolCall
from anyspark.core.protocol import ParamSpec, ToolResult, ToolSpec


def _run_coro_safely(factory: Any) -> Any:
    """在任意线程安全运行协程。

    Agent 单工具路径在事件循环线程同步执行实现器——asyncio.run 会抛
    "running event loop"；检测到在 loop 内则转线程池执行。
    """
    try:
        asyncio.get_running_loop()
        in_loop = True
    except RuntimeError:
        in_loop = False
    if in_loop:
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(factory())).result()
    return asyncio.run(factory())


def make_review_tools(
    panel: Any, chapters: Any, model: Any, book_id: str = "main"
) -> list[tuple[Any, Any]]:
    """装配评审团 agent 工具组（返回 [(spec, implementer), ...]）。"""

    spec = ToolSpec(
        name="panel_review",
        description=(
            "用户要求评审某章（'帮我看看这章/评审/把关'）时使用："
            "召集拟人化评审员（编剧/文学编辑/逻辑审校/爽文读者等）并发评审该章，"
            "输出综合评分+共识+分歧+优先建议。评审员是人格化角色，报告生动可操作。"
            "仅评审不改写；用户要改写请用 workflow 流程。"
        ),
        params=[
            ParamSpec(
                name="chapter_title",
                type="string",
                required=True,
                description="章节标题（必须是已存在的章节）",
            ),
            ParamSpec(
                name="reviewer_ids",
                type="string",
                required=False,
                description=(
                    "指定评审员（逗号分隔 id，如 screenwriter,thriller_reader）；缺省全部激活"
                ),
            ),
        ],
    )

    def panel_review_impl(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        title = str(arguments.get("chapter_title") or "").strip()
        if not title:
            return ToolResult(call=call, ok=False, content="缺少 chapter_title 参数。")
        ch = next((c for c in chapters.list_by_book(book_id) if c.title == title), None)
        if ch is None:
            return ToolResult(call=call, ok=False, content=f"章节不存在: {title}")
        ids_raw = str(arguments.get("reviewer_ids") or "").strip()
        reviewer_ids = [x.strip() for x in ids_raw.split(",") if x.strip()] if ids_raw else None

        from anyspark.check import run_review as check_run

        async def _review() -> Any:
            context: dict[str, str] = {}
            # check 硬伤清单（check 内部 asyncio.run → to_thread 保证在线程池跑）
            try:
                # S109：审读告知边界——agent 循环内模型可用 read_chapter 补读全文
                ch_content = ch.content or ""
                if len(ch_content) > 20000:
                    ch_content = (
                        f"【注意：本章全文 {len(ch.content)} 字，以下仅前 20000 字——"
                        "如需检查后半章请用 read_chapter 读全文】\n" + ch_content[:20000]
                    )
                cr = await asyncio.to_thread(check_run, model, ch.title, ch_content)
                context["check_report"] = (
                    f"规则引擎硬伤检测（{cr.hard_count} 处硬伤，供核实）：\n{cr.render()}"
                )
            except Exception:
                pass  # 硬伤清单取不到不阻断评审
            return await panel.run_review(
                model,
                ch.content,
                chapter_ref=ch.title,
                reviewer_ids=reviewer_ids,
                context=context,
            )

        try:
            # 工具实现器可能在事件循环线程（单工具路径）→ 安全包装统一调度
            report = _run_coro_safely(_review)
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"评审失败: {str(exc)[:150]}")
        return ToolResult(
            call=call,
            ok=True,
            content=report.render_compact(),
            data={"overall_score": report.overall_score},
        )

    return [(spec, panel_review_impl)]
