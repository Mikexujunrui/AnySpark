"""Admin tool implementations — skill, task, scope, permissions management.

Extracted from executor.py to keep module sizes manageable.
"""

from core.permissions import permission_manager
from data.json_store import json_store


def _handle_skill_tool(name: str, args: dict) -> str:
    """Handle skill CRUD operations."""
    from core.skills import manager as skill_manager

    if name == "list_skills":
        source = args.get("source")
        skills = skill_manager.list_skills(source=source)
        if not skills:
            return "暂无可用技能。可在 skills/ 目录添加系统级 YAML，或 data/skills/ 添加用户级。"
        lines = [f"可用技能 ({len(skills)}):\n"]
        for sk in skills:
            src_tag = "[系统]" if sk["source"] == "system" else "[用户]"
            lines.append(f"**{sk['name']}** {src_tag}")
            lines.append(f"  {sk['description']}")
            triggers = sk.get("triggers", [])
            if triggers:
                lines.append(f"  触发: {', '.join(triggers)}")
            steps = sk.get("steps", [])
            if steps:
                step_names = " → ".join(s.get("label", s.get("tool", "")) for s in steps)
                lines.append(f"  步骤: {step_names}")
            lines.append("")
        return "\n".join(lines)

    elif name == "create_skill":
        skill_name = args.get("name", "")
        if not skill_name:
            return "错误: 需要 name 参数"
        description = args.get("description", "")
        if not description:
            return "错误: 需要 description 参数"
        steps = args.get("steps", [])
        if not steps:
            return "错误: 需要 steps 参数（至少一个步骤）"
        triggers = args.get("triggers", [])
        definition = {
            "description": description,
            "triggers": triggers,
            "steps": steps,
        }
        try:
            result = skill_manager.add_user_skill(skill_name, definition)
            lines = [f"已创建自定义技能「{result['name']}」:"]
            lines.append(f"  描述: {result['description']}")
            if result.get("triggers"):
                lines.append(f"  触发: {', '.join(result['triggers'])}")
            lines.append(f"  步骤: {len(result.get('steps', []))} 步")
            return "\n".join(lines)
        except ValueError as e:
            return f"创建失败: {e}"

    elif name == "update_skill":
        skill_name = args.get("name", "")
        if not skill_name:
            return "错误: 需要 name 参数"
        definition = {}
        if "description" in args:
            definition["description"] = args["description"]
        if "triggers" in args:
            definition["triggers"] = args["triggers"]
        if "steps" in args:
            definition["steps"] = args["steps"]
        if not definition:
            return "错误: 至少需要一个修改项 (description/triggers/steps)"
        try:
            result = skill_manager.update_user_skill(skill_name, definition)
            return f"已更新技能「{result['name']}」"
        except ValueError as e:
            return f"更新失败: {e}"

    elif name == "delete_skill":
        skill_name = args.get("name", "")
        if not skill_name:
            return "错误: 需要 name 参数"
        try:
            if skill_manager.delete_user_skill(skill_name):
                return f"已删除技能「{skill_name}」"
            return f"技能不存在: {skill_name}"
        except ValueError as e:
            return f"删除失败: {e}"

    return f"未知技能操作: {name}"


def _handle_agent_tasks(args: dict, book_id: str) -> str | dict:
    """Handle agent_tasks tool operations."""
    action = args.get("action", "")
    task_list_id = args.get("task_list_id", "")

    if action == "create":
        title = args.get("title", "未命名任务")
        items = args.get("items", [])
        if not items:
            return "错误: create 需要 items 参数，如 [{\"label\": \"读取章节\", \"tool\": \"read_chapter\"}]"
        try:
            tl = json_store.create_task_list(book_id, title, items)
            return {"type": "task_list", "text": _format_task_list(tl), "items": tl.get("items", [])}
        except Exception as e:
            return f"创建失败: {e}"

    elif action == "get":
        try:
            tl = json_store.get_task_list(book_id, task_list_id or None)
            return {"type": "task_list", "text": _format_task_list(tl), "items": tl.get("items", [])}
        except Exception as e:
            return f"❌ {e}"

    elif action == "list":
        lists = json_store.load_task_lists(book_id)
        if not lists:
            return "没有任务清单。使用 agent_tasks action=create 创建。"
        lines = [f"# 任务清单 ({len(lists)}个)\n"]
        for tl in lists[-5:]:  # Show last 5
            status_icon = {"done": "✅", "in_progress": "🔵", "failed": "❌"}.get(tl.get("status", ""), "⬜")
            done_count = sum(1 for it in tl.get("items", []) if it.get("status") == "done")
            total = len(tl.get("items", []))
            lines.append(f"- {status_icon} **{tl.get('title', '?')}** (id: {tl['id'][:8]}, {done_count}/{total})")
        return "\n".join(lines)

    elif action == "update":
        idx = args.get("item_index")
        status = args.get("status")
        if idx is None or not status:
            return "错误: update 需要 item_index 和 status 参数"
        result_summary = args.get("result_summary")
        try:
            tl = json_store.update_task_item(book_id, task_list_id or None, idx, status, result_summary)
            return {"type": "task_list", "text": _format_task_list(tl), "items": tl.get("items", [])}
        except Exception as e:
            return f"❌ {e}"

    elif action == "add":
        items = args.get("items", [])
        if not items:
            return "错误: add 需要 items 参数"
        try:
            tl = json_store.add_task_items(book_id, task_list_id or None, items)
            return {"type": "task_list", "text": _format_task_list(tl), "items": tl.get("items", [])}
        except Exception as e:
            return f"❌ {e}"

    elif action == "clear":
        lists = json_store.load_task_lists(book_id)
        if task_list_id:
            lists = [t for t in lists if t["id"] != task_list_id and not t["id"].startswith(task_list_id)]
        else:
            lists = [t for t in lists if t.get("status") not in ("done", "failed")]
        json_store._save_task_lists(book_id, lists)
        return {"type": "task_list", "text": f"已清理，剩余 {len(lists)} 个任务清单。", "items": []}

    else:
        return f"未知操作: {action}。支持: create/get/list/update/add/clear"


def _format_task_list(tl: dict) -> str:
    """Format a task list for display."""
    status_map = {
        "pending": "⬜", "in_progress": "🔵", "done": "✅",
        "skipped": "⏭️", "failed": "❌"
    }
    lines = [f"# 任务清单: {tl.get('title', '?')}\n"]
    lines.append(f"状态: {tl.get('status', 'pending')}\n")
    for item in tl.get("items", []):
        icon = status_map.get(item.get("status", "pending"), "⬜")
        label = item.get("label", "?")
        idx = item.get("index", "?")
        tool = item.get("tool", "")
        result = item.get("result_summary")
        line = f"{icon} [{idx}] {label}"
        if tool:
            line += f" (工具: {tool})"
        lines.append(line)
        if result:
            lines.append(f"    └─ {result[:80]}")
    return "\n".join(lines)


def _manage_scope(args: dict, book_id: str) -> str:
    from core.knowledge_scope import ExposureLevel, scope_manager

    action = args.get("action", "show")
    scope = scope_manager.get_scope(book_id)

    if action == "show":
        if not scope:
            return "当前没有活跃的写作知识范围。使用 delegate_writing 创建。"
        return scope.to_summary()

    if not scope:
        scope = scope_manager.get_scope(book_id)
        if not scope:
            return "当前没有活跃的作用域。请先使用 delegate_writing，或直接用 manage_scope add 创建。"
        # Handle creation on-the-fly
        from core.knowledge_scope import WritingKnowledgeScope
        scope = WritingKnowledgeScope(book_id=book_id)
        scope_manager.set_scope(book_id, scope)

    entity_name = args.get("entity_name", "").strip()
    entity_type = args.get("entity_type", "character").strip()
    level_str = args.get("level", "full").strip()
    reason = args.get("reason", "手动调整").strip()

    try:
        level = ExposureLevel(level_str)
    except ValueError:
        level = ExposureLevel.FULL

    if action == "add":
        if not entity_name:
            return "错误: add 操作需要 entity_name"
        add_methods = {
            "character": scope.add_character,
            "location": scope.add_location,
            "concept": scope.add_concept,
            "item": scope.add_item,
        }
        method = add_methods.get(entity_type)
        if method:
            method(entity_name, level, reason)
            return f"已添加 {entity_name} [{entity_type}] 到作用域 (级别: {level.value})"
        return f"未知实体类型: {entity_type}。可用: character/location/concept/item 或自定义类型"

    elif action == "remove":
        if not entity_name:
            return "错误: remove 操作需要 entity_name"
        scope.remove_entity(entity_name)
        return f"已从作用域移除: {entity_name}"

    elif action == "forbid":
        if not entity_name:
            return "错误: forbid 操作需要 entity_name"
        if entity_name not in scope.forbidden_characters:
            scope.forbidden_characters.append(entity_name)
        return f"已禁止 {entity_name} 出场"

    elif action == "allow":
        if not entity_name:
            return "错误: allow 操作需要 entity_name"
        if entity_name in scope.forbidden_characters:
            scope.forbidden_characters.remove(entity_name)
        return f"已解除 {entity_name} 的出场禁令"

    elif action == "rules":
        new_rules = args.get("reason", "")
        scope.writing_rules = new_rules
        return f"已更新写作规则:\n{new_rules}"

    return f"未知操作: {action}。可用: show/add/remove/forbid/allow/rules"


def _manage_permissions(args: dict) -> str:
    """Toggle autonomous mode or view current permission status."""
    action = args.get("action", "status")

    if action == "status":
        lines = ["## 权限状态\n"]
        lines.append(f"- 自主模式: {'✅ 已启用' if permission_manager.autonomous_mode else '❌ 已关闭'}")
        lines.append(f"- 会话批准: {len(permission_manager._session_approved)} 个工具")
        if permission_manager.autonomous_mode:
            lines.append("\n⚠️ **自主模式启用中** — Agent 可直接执行删除章节/实体等危险操作，无需用户确认。")
            lines.append("使用 `action='disable'` 关闭自主模式恢复确认机制。")
        else:
            lines.append("\n💡 Agent 执行危险操作前会弹出确认提示。")
            lines.append("如果需要批量操作（如删除多个章节），使用 `action='enable'` 暂时关闭确认。")
        return "\n".join(lines)

    elif action == "enable":
        permission_manager.autonomous_mode = True
        return ("✅ **自主模式已启用**\n\n"
                "从现在起，Agent 可以直接执行以下操作而无需每次确认：\n"
                "- 删除章节 (delete_chapter / delete_all_chapters)\n"
                "- 删除实体 (delete_entity)\n"
                "- 删除世界观条目/时间线事件/伏笔\n"
                "- 批量编辑章节\n"
                "- 清除版本历史\n\n"
                "⚠️ 请谨慎使用。完成批量操作后建议关闭。")

    elif action == "disable":
        permission_manager.autonomous_mode = False
        permission_manager.reset_session()
        return "🔒 **自主模式已关闭** — Agent 执行危险操作前将恢复确认提示。"

    else:
        return f"未知操作: {action}。可用: status / enable / disable"
