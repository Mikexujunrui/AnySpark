"""Style tool implementations — list, set, suggest, get, manage user styles.

Extracted from executor.py to keep module sizes manageable.
"""


def _list_styles(book_id: str = "") -> str:
    from core.styles import manager as sm

    styles = sm.list_styles()
    active = sm.get_active_style(book_id) if book_id else ""
    lines = [f"可用写作风格 ({len(styles)} 个):\n"]
    sys_styles = [s for s in styles if s.get("source") == "system"]
    user_styles = [s for s in styles if s.get("source") == "user"]

    def _render(st_list, label):
        for s in st_list:
            mark = " ★活跃" if s["name"] == active else ""
            p = s.get("priority", "suggest")
            p_label = {"suggest": "建议", "apply": "应用", "strict": "强制"}.get(p, p)
            tags = ", ".join(s.get("applies_to", []))
            lines.append(f"**{s['name']}**{mark} [{p_label}] [{label}]")
            lines.append(f"  {s['description']}")
            lines.append(f"  适用场景: {tags}")
            lines.append("")

    _render(sys_styles, "系统")
    _render(user_styles, "自定义")
    lines.append(f"当前活跃: {active or '(未设置)'}")
    lines.append("使用 set_style(名称) 切换，或用 manage_styles 管理自定义风格")
    return "\n".join(lines)


def _set_style(args: dict, book_id: str = "") -> str:
    from core.styles import manager as sm

    name = args.get("name", "")
    if not name:
        return "错误: 需要 name 参数。使用 list_styles 查看可用风格。"
    style = sm.get(name)
    if not style:
        names = ", ".join(s["name"] for s in sm.list_styles())
        return f"未知风格: {name}。可用: {names}"
    sm.set_active_style(book_id, name)
    label = "用户" if style.source == "user" else "系统"
    p_labels = {"suggest": "建议级（角色设定优先）", "apply": "应用级", "strict": "强制执行"}
    p_label = p_labels.get(style.priority, style.priority)
    style_text = style.prompt_for_targets("system", "scene")
    return f"风格已切换为「{name}」[{label}|{p_label}]\n\n风格指引:\n{style_text[:500]}"


def _suggest_style(args: dict) -> str:
    from core.styles import manager as sm

    content = args.get("content", "")
    if not content:
        return "错误: 需要 content 参数（场景描述或大纲内容）"
    suggested = sm.suggest_for_content(content)
    if not suggested:
        return "未找到匹配的风格。可用: " + ", ".join(s["name"] for s in sm.list_styles())
    style = sm.get(suggested)
    label = "用户" if style.source == "user" else "系统"
    return (
        f"推荐风格: **{suggested}** [{label}]\n"
        f"{style.description}\n"
        f"适用场景: {', '.join(style.applies_to)}\n"
        f"使用 set_style('{suggested}') 应用此风格。"
    )


def _get_style(book_id: str = "") -> str:
    from core.styles import manager as sm

    active = sm.get_active_style(book_id) if book_id else ""
    if not active:
        names = ", ".join(s["name"] for s in sm.list_styles())
        return f"当前未设置活跃风格。可用: {names}\n使用 set_style(名称) 或 suggest_style(描述) 选择风格。"
    style = sm.get(active)
    if not style:
        return f"活跃风格 {active} 已不存在。"
    label = "用户" if style.source == "user" else "系统"
    return (
        f"当前风格: **{active}** [{label}]\n"
        f"{style.description}\n\n"
        f"完整写作规则:\n{style.prompt_for_targets('system', 'scene', 'knowledge')}"
    )


def _manage_styles(args: dict) -> str:
    """CRUD for user styles. System styles are read-only."""
    from core.styles import manager as sm

    action = args.get("action", "list")

    if action == "list":
        return _list_styles()

    name = args.get("name", "")

    if action in ("get", "view"):
        if not name:
            return "错误: 需要 name 参数。"
        style = sm.get(name)
        if not style:
            return f"风格不存在: {name}"
        label = "用户" if style.source == "user" else "系统"
        slots_text = "\n".join(f"  [{s.get('target', '?')}] {s.get('content', '')[:80]}..." for s in style.slots)
        return (
            f"**{style.name}** [{label}]\n"
            f"优先级: {style.priority}\n"
            f"适用场景: {', '.join(style.applies_to)}\n"
            f"描述: {style.description}\n"
            f"提示槽:\n{slots_text}"
        )

    elif action == "add":
        if not name:
            return "错误: 需要 name 参数。"
        definition = {
            "description": args.get("description", ""),
            "priority": args.get("priority", "suggest"),
            "applies_to": args.get("applies_to", []),
            "slots": args.get("slots", []),
        }
        try:
            sm.add_user_style(name, definition)
            return f"已创建自定义风格「{name}」。\n使用 set_style('{name}') 应用。"
        except ValueError as e:
            return str(e)

    elif action == "update":
        if not name:
            return "错误: 需要 name 参数。"
        definition = {}
        if "description" in args:
            definition["description"] = args["description"]
        if "priority" in args:
            definition["priority"] = args["priority"]
        if "applies_to" in args:
            definition["applies_to"] = args["applies_to"]
        if "slots" in args:
            definition["slots"] = args["slots"]
        try:
            sm.update_user_style(name, definition)
            return f"已更新自定义风格「{name}」。"
        except ValueError as e:
            return str(e)

    elif action == "delete":
        if not name:
            return "错误: 需要 name 参数。"
        try:
            sm.delete_user_style(name)
            return f"已删除自定义风格「{name}」。"
        except ValueError as e:
            return str(e)

    return f"未知操作: {action}。可用: list/get/add/update/delete"
