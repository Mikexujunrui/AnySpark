"""
anyspark.server.subagent — 子 Agent 执行内核（S119/S121 提案 B）。

设计定案（S115）：子 Agent 内核一份（loop 层），两个入口——① workflow agent
节点 delegate（S119 已落地）② 主循环 run_subagent 工具（S121，对话即时委派）。

核心（fresh 隔离，对齐 S56 干净写作治毒化）：
- 独立 InMemoryConversationStore：不受父会话污染、不落库
- 完整 core Agent 循环：复用 S108b 重复检测/取消/工具执行
- 工具白名单 scope.tools：从全量 build_toolkit 过滤（空=全量）
- budget.max_turns → Agent.max_tool_iterations 轮数护栏
- 子 Agent 不默认带 codex（S116 失败关闭）、不递归 workflow/play
- 模型走 model_for_task(deps, "research") 槽位（未配回退激活）
"""

from __future__ import annotations

from typing import Any

from anyspark.core import Agent, CancellationToken, ToolRegistry
from anyspark.core.storage import InMemoryConversationStore
from anyspark.server.agent_factory import model_for_task
from anyspark.server.toolkit import ToolContext, build_toolkit


def build_subagent_registry(
    deps: Any,
    book_id: str,
    scope_tools: list[str] | None = None,
    *,
    enable_search: bool = True,
) -> ToolRegistry:
    """构造子 Agent 工具 registry（全量装配 → 白名单过滤）。"""
    full_registry = build_toolkit(
        ToolRegistry(),
        ToolContext(
            chapters=deps.chapters,
            workspace=deps.workspace,
            model=deps.model,
            graph=deps.graph,
            plots=deps.plots,
            plans=deps.plans,
            settings=deps.settings,
            materials=deps.materials,
            ext_tools=deps.ext_tools,
            dim_store=deps.dim_store,
            manual=deps.manual,
            skills_store=deps.skills,
            workflow_store=deps.workflow_store,
            workflow_engine=deps.workflow_engine,
            workflow_generator=deps.workflow_generator,
            play_engine=deps.play_engine,
            review_panel=deps.review_panel,
            skill_generator=deps.skill_generator,
            book_id=book_id,
            templates=[f"{s.name}：{s.description}" for s in deps.skills.plot_skills()],
            bg_queue=deps.bg_queue,
        ),
        enable_domain=True,
        enable_search=enable_search,
        enable_codex=False,  # S116 失败关闭：子 Agent 不默认带代码沙箱
        enable_workflow=False,  # 防递归委派
        enable_play=False,
    )
    if not scope_tools:
        return full_registry  # 无白名单 = 全量
    sub_registry = ToolRegistry()
    for name in scope_tools:
        got = full_registry.get(name)
        if got is not None:
            spec, impl = got
            sub_registry.register(spec, impl)
    return sub_registry


def run_subagent_task(
    deps: Any,
    instruction: str,
    system_prompt: str = "",
    scope_tools: list[str] | None = None,
    max_turns: int = 10,
    book_id: str = "main",
    task: str = "research",
) -> dict[str, Any]:
    """执行一个子 Agent 任务（独立上下文跑完整工具循环），返回 {ok, output, error}。

    - fresh：InMemoryConversationStore 不受父会话污染（对齐 S56 干净写作）
    - 白名单 scope_tools（空=全量）；轮数护栏 max_turns
    - 主循环工具与 workflow delegate 共用本内核（机制一份）
    """
    sub_registry = build_subagent_registry(deps, book_id, scope_tools)
    sub_model = model_for_task(deps, task)
    sub_agent = Agent(
        model=sub_model,
        registry=sub_registry,
        store=InMemoryConversationStore(),
        system_prompt=system_prompt or f"你是子任务执行者。任务：{instruction}",
        max_tool_iterations=max_turns,
    )
    token = CancellationToken()
    turn = sub_agent.run(instruction, token=token)
    text = (turn.text or "").strip()
    if not text:
        return {"ok": False, "output": "", "error": "子 Agent 空输出"}
    return {"ok": True, "output": text, "error": ""}
