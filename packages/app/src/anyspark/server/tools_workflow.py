"""
anyspark.server.tools_workflow — 工作流 agent 工具（S59 补充：Agent 可自主使用工作流）。

把工作流从"HTTP API（人驱动）"变成"agent 可自主调用的工具"：
- workflow_generate：按目标让 AI 生成工作流草稿（进草稿表，人工确认后生效——不对，
  agent 工具生成后仍走人工确认闸门，但返回草稿内容供 Agent/用户评估）
- workflow_list：列出可用工作流模板
- workflow_run：运行已有模板（绑定书，快照冻结，后台执行）
- workflow_status：查任务进度/结果

哲学（对齐 tools_domain）：机制（工具结构/查询逻辑）硬编码；内容自然语言；
只读/启动为主，无删除修改权限（内容裁决权在用户/API）。
"""

from __future__ import annotations

from typing import Any

from anyspark.core import ToolCall
from anyspark.core.protocol import ParamSpec, ToolResult, ToolSpec


def make_workflow_tools(
    workflow_store: Any,
    workflow_engine: Any,
    workflow_generator: Any,
) -> list[tuple[Any, Any]]:
    """装配工作流 agent 工具组（返回 [(spec, implementer), ...]）。"""

    # ------------------------------------------------------------------
    # workflow_list：列出可用模板
    # ------------------------------------------------------------------
    list_spec = ToolSpec(
        name="workflow_list",
        description=(
            "列出已保存的工作流模板（固定的分析/改书流程，如'章节质量把关'）。"
            "需要知道有哪些现成流程可跑时使用。"
        ),
        params=[],
    )

    def list_impl(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        try:
            templates = workflow_store.list_templates()
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"查询失败: {exc}")
        if not templates:
            return ToolResult(
                call=call,
                ok=False,
                content="暂无工作流模板。可用 workflow_generate 让 AI 生成一个。",
            )
        lines = [f"可用工作流模板（{len(templates)} 个）："]
        for t in templates:
            lines.append(f"- {t['id']} | {t['name']} | {t.get('description', '')[:80]}")
        return ToolResult(call=call, ok=True, content="\n".join(lines))

    # ------------------------------------------------------------------
    # workflow_run：运行模板（后台执行）
    # ------------------------------------------------------------------
    run_spec = ToolSpec(
        name="workflow_run",
        description=(
            "运行一个工作流模板（如章节质量把关：审读→发现硬伤→改写→作者确认）。"
            "传 template_id（用 workflow_list 查）+ book_id（缺省 main）。"
            "后台执行，返回 task_id；用 workflow_status 查进度。"
        ),
        params=[
            ParamSpec(
                name="template_id",
                type="string",
                required=True,
                description="工作流模板 id（workflow_list 返回的 id）",
            ),
            ParamSpec(
                name="book_id",
                type="string",
                required=False,
                description="目标书（缺省 main）",
            ),
        ],
    )

    def run_impl(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        template_id = str(arguments.get("template_id", "")).strip()
        book_id = str(arguments.get("book_id") or "main")
        if not template_id:
            return ToolResult(call=call, ok=False, content="缺少参数 template_id。")
        try:
            wf = workflow_store.get_template(template_id)
            if wf is None:
                return ToolResult(call=call, ok=False, content=f"模板不存在: {template_id}")
            task_id = workflow_store.create_task(wf, book_id=book_id, template_id=template_id)
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"启动失败: {exc}")

        import contextlib
        import threading

        def _run() -> None:
            # 状态已在任务里，后台异常不抛给 Agent
            with contextlib.suppress(Exception):
                workflow_engine.run_task(task_id)

        threading.Thread(target=_run, daemon=True).start()
        return ToolResult(
            call=call,
            ok=True,
            content=(
                f"已启动工作流「{wf.name}」→ task_id: {task_id}（book={book_id}）。"
                "用 workflow_status 查进度。若含作者确认节点会停在 waiting_approval。"
            ),
        )

    # ------------------------------------------------------------------
    # workflow_status：查任务进度
    # ------------------------------------------------------------------
    status_spec = ToolSpec(
        name="workflow_status",
        description=(
            "查工作流任务进度/结果。传 task_id（workflow_run 返回）。"
            "返回当前状态（done/failed/waiting_approval/running）、各节点状态与输出摘要。"
        ),
        params=[
            ParamSpec(
                name="task_id",
                type="string",
                required=True,
                description="任务 id（workflow_run 返回的 task_id）",
            ),
        ],
    )

    def status_impl(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        task_id = str(arguments.get("task_id", "")).strip()
        if not task_id:
            return ToolResult(call=call, ok=False, content="缺少参数 task_id。")
        try:
            task = workflow_store.get_task(task_id)
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"查询失败: {exc}")
        if task is None:
            return ToolResult(call=call, ok=False, content=f"任务不存在: {task_id}")
        lines = [
            f"任务 {task_id}: {task['status']}",
            f"  名称: {task['name']} | 书: {task['book_id']}",
        ]
        if task.get("error"):
            lines.append(f"  错误: {task['error'][:200]}")
        for s in task["node_states"]:
            out = s["output"][:60].replace("\n", " ")
            status = s["status"]
            if status == "done":
                lines.append(f"  ✓ {s['node_id']}: {out}")
            elif status == "failed":
                lines.append(f"  ✗ {s['node_id']}: {s['error'][:60]}")
            elif status == "running":
                lines.append(f"  … {s['node_id']}: 执行中")
            elif status == "waiting_approval":
                lines.append(f"  ⏸ {s['node_id']}: 等待人工确认")
            else:
                lines.append(f"  · {s['node_id']}: {status}")
        return ToolResult(call=call, ok=True, content="\n".join(lines))

    # ------------------------------------------------------------------
    # workflow_generate：AI 生成草稿（供 Agent 提出流程需求）
    # ------------------------------------------------------------------
    gen_spec = ToolSpec(
        name="workflow_generate",
        description=(
            "按需求让 AI 设计一个工作流草稿（固定分析/改书流程）。"
            "传 goal（自然语言描述想固化的流程，如'每章写完后先审读设定冲突再复检'）。"
            "产出进草稿表（人工确认后转正生效）；返回草稿 id + 结构摘要供评估。"
        ),
        params=[
            ParamSpec(
                name="goal",
                type="string",
                required=True,
                description="想固化的流程描述（自然语言）",
            ),
        ],
    )

    def gen_impl(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        goal = str(arguments.get("goal", "")).strip()
        if not goal:
            return ToolResult(call=call, ok=False, content="缺少参数 goal。")
        try:
            wf = workflow_generator.generate(goal)
            workflow_store.add_draft(wf, hint=goal)
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"生成失败: {exc}")
        nodes_summary = " → ".join(f"{n.kind}" for n in wf.nodes[:8])
        return ToolResult(
            call=call,
            ok=True,
            content=(
                f"已生成工作流草稿 {wf.id}: {wf.name}（{len(wf.nodes)} 节点: {nodes_summary}）。"
                "草稿未生效，需人工确认（API: POST /api/workflows/drafts/{id}/promote）。"
            ),
        )

    return [
        (list_spec, list_impl),
        (run_spec, run_impl),
        (status_spec, status_impl),
        (gen_spec, gen_impl),
    ]
