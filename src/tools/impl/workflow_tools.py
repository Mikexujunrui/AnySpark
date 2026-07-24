"""Workflow tool implementations — generate, execute, manage workflows.

Extracted from executor.py to keep module sizes manageable.
"""

import json

from data.json_store import json_store


async def _generate_workflow_streaming(loop, args: dict, kb, book_id: str, msg: str = "", queue=None):
    """Streaming version of generate_workflow — emits workflow definition event."""
    desc = args.get("description", "")
    if not desc:
        return "错误: 需要 description 参数"
    from core.graph_store import GraphStore
    from core.workflow_agent import generate_workflow

    kb = GraphStore(book_id)
    kb.init_schema()
    entities = kb.list_entities()[:20]
    context = "、".join([f"{e.type}:{e.name}" for e in entities]) if entities else "空项目"
    if queue:
        await queue.put({"_progress": "正在生成工作流..."})
    definition = await loop.run_in_executor(None, generate_workflow, desc, context)
    steps = definition.get("steps", [])
    if not steps:
        return "工作流生成失败，请提供更具体的需求描述。"
    wf = json_store.add_workflow(
        book_id,
        definition.get("name", "自定义工作流"),
        [
            {"id": f"{i}", "type": s.get("type", ""), "label": s.get("label", ""), "config": s.get("config", {})}
            for i, s in enumerate(steps)
        ],
    )
    # Emit workflow definition event for frontend display
    if queue:
        await queue.put(
            {
                "_workflow": {
                    "action": "generated",
                    "name": wf.get("name", definition.get("name", "自定义工作流")),
                    "id": wf.get("id", ""),
                    "steps": [
                        {"label": s.get("label", ""), "type": s.get("type", ""), "status": "pending"} for s in steps
                    ],
                }
            }
        )
    lines = [f"已生成并自动订阅工作流「{wf['name']}」({len(steps)} 步):"]
    for i, s in enumerate(steps):
        lines.append(f"  {i + 1}. [{s.get('type', '?')}] {s.get('label', '?')}")
    return "\n".join(lines)


async def _execute_workflow_streaming(loop, args: dict, kb, book_id: str, msg: str = "", queue=None):
    """Streaming version of execute_workflow — emits per-step progress events."""
    wid = args.get("workflow_id", "")
    if not wid:
        return "错误: 需要 workflow_id"
    from core.workflow_engine import engine as wf_engine

    wf = wf_engine._active.get(wid)
    if not wf:
        try:
            wf_data = json_store.get_workflow(wid)
            wf = wf_engine.build(wid, {"name": wf_data.get("name", "工作流"), "steps": wf_data.get("steps", [])})
        except Exception:
            return f"工作流不存在: {wid}"

    context = {"book_id": book_id}
    dynamic_params = args.get("params") or {}
    context.update(dynamic_params)
    wf.status = "running"
    results = []
    lines = [f"开始执行工作流「{wf.name}」({len(wf.steps)} 步):\n"]

    # Emit workflow start event with all steps
    if queue:
        await queue.put(
            {
                "_workflow": {
                    "action": "executing",
                    "name": wf.name,
                    "id": wid,
                    "steps": [{"label": s.label, "type": s.type, "status": "pending"} for s in wf.steps],
                }
            }
        )

    for i, step in enumerate(wf.steps):
        wf.current_step = i
        step.status = "running"
        # Emit step_start event
        if queue:
            await queue.put(
                {
                    "_workflow": {
                        "action": "step_start",
                        "index": i,
                        "label": step.label,
                        "type": step.type,
                    }
                }
            )
        lines.append(f"  [{i + 1}/{len(wf.steps)}] {step.label}...")
        try:
            handler = wf_engine.handlers.get(step.type)
            if handler:
                result = await handler(step.config, context, results)
                step.status = "completed"
                results.append({"step": step.label, "result": result, "id": step.id})
                lines.append("    ✓ 完成")
                # Emit step_done event
                if queue:
                    await queue.put(
                        {
                            "_workflow": {
                                "action": "step_done",
                                "index": i,
                                "label": step.label,
                            }
                        }
                    )
            else:
                step.status = "failed"
                error_msg = f"无处理器: {step.type}"
                results.append({"step": step.label, "error": error_msg, "id": step.id})
                lines.append(f"    ✗ {error_msg}")
                if queue:
                    await queue.put(
                        {
                            "_workflow": {
                                "action": "step_error",
                                "index": i,
                                "label": step.label,
                                "error": error_msg,
                            }
                        }
                    )
        except Exception as e:
            step.status = "failed"
            error_msg = str(e)[:100]
            results.append({"step": step.label, "error": error_msg, "id": step.id})
            lines.append(f"    ✗ {error_msg}")
            if queue:
                await queue.put(
                    {
                        "_workflow": {
                            "action": "step_error",
                            "index": i,
                            "label": step.label,
                            "error": error_msg,
                        }
                    }
                )

    wf.status = "completed"
    wf_engine._results[wid] = results
    completed = sum(1 for s in wf.steps if s.status == "completed")
    lines.append(f"\n工作流执行完毕: {completed}/{len(wf.steps)} 步成功")
    # Emit final done event
    if queue:
        await queue.put(
            {
                "_workflow": {
                    "action": "done",
                    "completed": completed,
                    "total": len(wf.steps),
                }
            }
        )
    return "\n".join(lines)


async def _handle_workflow_tool(name: str, args: dict, book_id: str) -> str:
    if name == "generate_workflow":
        desc = args.get("description", "")
        if not desc:
            return "错误: 需要 description 参数"
        from core.graph_store import GraphStore
        from core.workflow_agent import generate_workflow

        kb = GraphStore(book_id)
        kb.init_schema()
        entities = kb.list_entities()[:20]
        context = "、".join([f"{e.type}:{e.name}" for e in entities]) if entities else "空项目"
        definition = generate_workflow(desc, context)
        steps = definition.get("steps", [])
        if not steps:
            return "工作流生成失败，请提供更具体的需求描述。"
        wf = json_store.add_workflow(
            book_id,
            definition.get("name", "自定义工作流"),
            [
                {"id": f"{i}", "type": s.get("type", ""), "label": s.get("label", ""), "config": s.get("config", {})}
                for i, s in enumerate(steps)
            ],
        )
        lines = [f"已生成并自动订阅工作流「{wf['name']}」({len(steps)} 步):"]
        for i, s in enumerate(steps):
            lines.append(f"  {i + 1}. [{s.get('type', '?')}] {s.get('label', '?')}")
        return "\n".join(lines)

    elif name == "list_workflows":
        wfs = json_store.load_workflows(book_id)
        if not wfs:
            return "当前项目还没有订阅的工作流。用 browse_workflows 浏览全局池，subscribe_workflow 订阅。"
        lines = [f"已订阅的工作流 ({len(wfs)}):"]
        for w in wfs:
            lines.append(f"\n**{w['name']}** (id: {w['id']})")
            lines.append(f"  步骤: {len(w.get('steps', []))} | 创建: {w.get('createdAt', '')[:16].replace('T', ' ')}")
            for i, s in enumerate(w.get("steps", [])):
                lines.append(f"  {i + 1}. [{s.get('type', '?')}] {s.get('label', '?')}")
        return "\n".join(lines)

    elif name == "browse_workflows":
        wfs = json_store.load_workflows_global()
        if not wfs:
            return "全局工作流池为空。用 generate_workflow 创建第一个。"
        lines = [f"全局工作流池 ({len(wfs)}):"]
        for w in wfs:
            lines.append(f"- **{w['name']}** (id: {w['id']}) — {len(w.get('steps', []))} 步")
        return "\n".join(lines)

    elif name == "subscribe_workflow":
        wid = args.get("workflow_id", "")
        if not wid:
            return "错误: 需要 workflow_id"
        try:
            wf = json_store.get_workflow(wid)
        except Exception:
            return f"工作流不存在: {wid}"
        json_store.subscribe_workflow(book_id, wid)
        return f"已订阅工作流「{wf['name']}」"

    elif name == "unsubscribe_workflow":
        wid = args.get("workflow_id", "")
        if not wid:
            return "错误: 需要 workflow_id"
        json_store.unsubscribe_workflow(book_id, wid)
        return f"已取消订阅工作流 (id: {wid})"

    elif name == "delete_workflow":
        wid = args.get("workflow_id", "")
        if not wid:
            return "错误: 需要 workflow_id"
        json_store.delete_workflow(book_id, wid)
        return f"已从全局池删除工作流 (id: {wid})"

    elif name == "execute_workflow":
        wid = args.get("workflow_id", "")
        if not wid:
            return "错误: 需要 workflow_id"
        from core.workflow_engine import engine as wf_engine

        # Try to get workflow from active engine or rebuild from storage
        wf = wf_engine._active.get(wid)
        if not wf:
            # Try to load from storage and rebuild
            try:
                wf_data = json_store.get_workflow(wid)
                wf = wf_engine.build(wid, {"name": wf_data.get("name", "工作流"), "steps": wf_data.get("steps", [])})
            except Exception:
                return f"工作流不存在: {wid}"

        context = {"book_id": book_id}
        # Merge dynamic params from args into context
        dynamic_params = args.get("params") or {}
        context.update(dynamic_params)
        wf.status = "running"
        results = []
        lines = [f"开始执行工作流「{wf.name}」({len(wf.steps)} 步):\n"]

        for i, step in enumerate(wf.steps):
            wf.current_step = i
            step.status = "running"
            lines.append(f"  [{i + 1}/{len(wf.steps)}] {step.label}...")
            try:
                handler = wf_engine.handlers.get(step.type)
                if handler:
                    result = await handler(step.config, context, results)
                    step.status = "completed"
                    results.append({"step": step.label, "result": result, "id": step.id})
                    lines.append("    ✓ 完成")
                else:
                    step.status = "failed"
                    error_msg = f"无处理器: {step.type}"
                    results.append({"step": step.label, "error": error_msg, "id": step.id})
                    lines.append(f"    ✗ {error_msg}")
            except Exception as e:
                step.status = "failed"
                error_msg = str(e)[:100]
                results.append({"step": step.label, "error": error_msg, "id": step.id})
                lines.append(f"    ✗ {error_msg}")

        wf.status = "completed"
        wf_engine._results[wid] = results
        completed = sum(1 for s in wf.steps if s.status == "completed")
        lines.append(f"\n工作流执行完毕: {completed}/{len(wf.steps)} 步成功")
        return "\n".join(lines)

    elif name == "update_workflow":
        wid = args.get("workflow_id", "")
        if not wid:
            return "错误: 需要 workflow_id"
        updates = {}
        if "name" in args and args["name"]:
            updates["name"] = args["name"]
        if "steps" in args and args["steps"]:
            updates["steps"] = args["steps"]
        if not updates:
            return "错误: 至少需要一个修改项 (name/steps)"
        try:
            wf = json_store.update_workflow(wid, updates)
            lines = [f"已更新工作流「{wf['name']}」:"]
            if "name" in updates:
                lines.append(f"  名称: {wf['name']}")
            if "steps" in updates:
                lines.append(f"  步骤: {len(wf['steps'])} 步")
                for i, s in enumerate(wf["steps"]):
                    lines.append(f"    {i + 1}. [{s.get('type', '?')}] {s.get('label', '?')}")
            return "\n".join(lines)
        except Exception as e:
            return f"更新失败: {e}"

    elif name == "list_workflow_steps":
        wid = args.get("workflow_id", "")
        if not wid:
            return "错误: 需要 workflow_id"
        try:
            wf = json_store.get_workflow(wid)
            lines = [f"工作流「{wf['name']}」的步骤 (ID: {wid}):\n"]
            steps = wf.get("steps", [])
            if not steps:
                lines.append("  (暂无步骤)")
            else:
                for i, step in enumerate(steps):
                    step_type = step.get("type", "?")
                    label = step.get("label", "未命名")
                    config = step.get("config", {})
                    lines.append(f"  **步骤 {i}** [{step_type}] {label}")
                    if config:
                        lines.append(f"    配置: {json.dumps(config, ensure_ascii=False, indent=2)}")
                    lines.append("")
            lines.append(
                "**提示**: 使用 `update_workflow_step(workflow_id, step_index, config)` 可修改特定步骤的参数。"
            )
            lines.append('  例如添加参考章节: `config: {"ref_chapters": ["book_id:#1", "book_id:#2"]}`')
            lines.append("  使用 `list_reference_chapters` 可查看可用的参考书章节。")
            return "\n".join(lines)
        except Exception as e:
            return f"获取工作流失败: {e}"

    elif name == "update_workflow_step":
        wid = args.get("workflow_id", "")
        step_index = args.get("step_index")
        new_config = args.get("config", {})

        if not wid:
            return "错误: 需要 workflow_id"
        if step_index is None:
            return "错误: 需要 step_index (从 0 开始)"
        if not isinstance(step_index, int):
            try:
                step_index = int(step_index)
            except (ValueError, TypeError):
                return "错误: step_index 必须是整数"

        try:
            wf = json_store.get_workflow(wid)
            steps = wf.get("steps", [])

            if step_index < 0 or step_index >= len(steps):
                return f"错误: step_index 超出范围 (0-{len(steps) - 1})"

            step = steps[step_index]
            old_config = step.get("config", {})

            # Merge new config into existing config
            merged_config = {**old_config, **new_config}
            steps[step_index]["config"] = merged_config

            json_store.update_workflow(wid, {"steps": steps})

            lines = [f"已更新工作流「{wf['name']}」的步骤 {step_index}:"]
            lines.append(f"  类型: {step.get('type', '?')}")
            lines.append(f"  标签: {step.get('label', '?')}")
            lines.append("  更新后的配置:")
            for key, value in merged_config.items():
                lines.append(
                    f"    {key}: {json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value}"
                )

            if "ref_chapters" in new_config:
                lines.append("\n✅ 已添加参考章节。执行工作流时将注入这些章节的原文。")

            return "\n".join(lines)
        except Exception as e:
            return f"更新失败: {e}"

    return f"未知工作流操作: {name}"
