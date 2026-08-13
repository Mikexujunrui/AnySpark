"""
anyspark.server.tools_subagent — 主循环 run_subagent 工具（S121 提案 B 第二入口）。

设计定案：子 Agent 内核一份（subagent.py），两个入口——workflow delegate（S119）
+ 主循环 run_subagent 工具（本模块，对话即时委派）。

场景：对话里随口"帮我查一下这个设定冲突""起草一章试试"——主 Agent 判断值得
派子 Agent，直接调本工具（独立 fresh 上下文，不占主循环；产出回传为工具结果）。
"""

from __future__ import annotations

from typing import Any

from anyspark.core.protocol import ParamSpec, ToolResult, ToolSpec
from anyspark.core.types import ToolCall
from anyspark.server.subagent import run_subagent_task


def make_subagent_implementer(subagent_deps: Any, book_id: str = "main") -> tuple[ToolSpec, Any]:
    """注册 run_subagent 工具（enable_domain 名下，默认可用）。"""

    spec = ToolSpec(
        name="run_subagent",
        description=(
            "把子任务委派给独立子 Agent 执行（fresh 上下文，不受本会话污染，不占主循环）。"
            "适合：资料调研（网络搜索+读书收集）、并行起草、独立调查、批量审读等"
            "值得外包的重活。子 Agent 带完整工具循环，产出作为结果返回。"
            "参数：instruction=给子 Agent 的任务指令；tools=子 Agent 可用工具白名单"
            "（可选，缺省全量；如 search_web,fetch_page 调研 / list_chapters,read_chapter 查章）；"
            "max_turns=轮数上限（默认 10）。"
        ),
        params=[
            ParamSpec(
                name="instruction",
                type="string",
                required=True,
                description="子 Agent 的任务指令（明确可执行，如'围绕主题搜索 3 页并总结'）",
            ),
            ParamSpec(
                name="tools",
                type="string",
                required=False,
                description=(
                    "子 Agent 工具白名单（逗号分隔，可选；缺省全量，如 search_web,fetch_page）"
                ),
            ),
            ParamSpec(
                name="max_turns",
                type="string",
                required=False,
                description="子 Agent 轮数上限（默认 10，护栏防失控）",
            ),
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        instruction = str(arguments.get("instruction", "")).strip()
        if not instruction:
            return ToolResult(call=call, ok=False, content="缺少参数 instruction。")
        if subagent_deps is None:
            return ToolResult(
                call=call, ok=False, content="子 Agent 未装配（缺依赖），请联系管理员。"
            )
        tools_raw = arguments.get("tools") or ""
        scope_tools = (
            [t.strip() for t in str(tools_raw).split(",") if t.strip()]
            if isinstance(tools_raw, str)
            else [str(t) for t in tools_raw if t]
        )
        try:
            max_turns = int(str(arguments.get("max_turns", "10")) or "10")
        except ValueError:
            max_turns = 10
        max_turns = max(1, min(max_turns, 30))  # 护栏：1-30 轮

        r = run_subagent_task(
            subagent_deps,
            instruction=instruction,
            scope_tools=scope_tools or None,
            max_turns=max_turns,
            book_id=book_id,
        )
        if not r["ok"]:
            return ToolResult(call=call, ok=False, content=f"子 Agent 失败：{r['error']}")
        return ToolResult(call=call, ok=True, content=r["output"])

    return spec, implementer
