"""Inspiration management tool implementation.

Bridges the AI agent to the inspiration inbox system
(core/inspiration_box.py + routes/inspiration.py).

Both AI and user share the same inspiration kanban (sidebar → 灵感).
"""

import logging

from core.inspiration_box import (
    add_inspiration,
    delete_inspiration,
    get_inspiration,
    list_inspirations,
    search_inspirations,
    update_inspiration,
)

logger = logging.getLogger(__name__)


def _manage_inspirations(args: dict, book_id: str, msg: str) -> str:
    action = args.get("action", "list")

    if action == "add":
        content = args.get("content", "")
        if not content:
            return "错误: 添加灵感需要 content 参数"
        tags = args.get("tags", [])
        insp = add_inspiration(
            book_id=book_id,
            content=content,
            tags=tags,
        )
        insp_id_short = insp.get("id", "?")[:12]
        tag_info = f" 标签: {', '.join(tags)}" if tags else ""
        return f"灵感已添加 (id: {insp_id_short}){tag_info}"

    elif action == "list":
        status_filter = args.get("status")
        inspirations = list_inspirations(book_id, status_filter)
        if not inspirations:
            status_hint = f"（状态: {status_filter}）" if status_filter else ""
            return f"暂无灵感碎片{status_hint}。"
        lines = [f"共 {len(inspirations)} 条灵感碎片:"]
        for i, insp in enumerate(inspirations, 1):
            insp_id_short = insp.get("id", "?")[:12]
            content = insp.get("content", "")[:80]
            status = insp.get("status", "inbox")
            tags = insp.get("tags", [])
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            lines.append(f"  {i}. [{insp_id_short}] [{status}] {content}{tag_str}")
        return "\n".join(lines)

    elif action == "get":
        insp_id = args.get("inspiration_id", "")
        if not insp_id:
            return "错误: 查看灵感需要 inspiration_id 参数"
        insp = get_inspiration(book_id, insp_id)
        if not insp:
            return f"未找到灵感: {insp_id[:12]}"
        content = insp.get("content", "")
        status = insp.get("status", "inbox")
        tags = ", ".join(insp.get("tags", []))
        chars = ", ".join(insp.get("linked_characters", []))
        chaps = ", ".join(insp.get("linked_chapters", []))
        lines = [
            f"灵感: {content}",
            f"状态: {status}",
        ]
        if tags:
            lines.append(f"标签: {tags}")
        if chars:
            lines.append(f"关联角色: {chars}")
        if chaps:
            lines.append(f"关联章节: {chaps}")
        return "\n".join(lines)

    elif action == "update":
        insp_id = args.get("inspiration_id", "")
        if not insp_id:
            return "错误: 更新灵感需要 inspiration_id 参数"
        updates = {}
        content = args.get("content")
        if content is not None:
            updates["content"] = content
        tags = args.get("tags")
        if tags is not None:
            updates["tags"] = tags
        status = args.get("status")
        if status is not None:
            updates["status"] = status
        if not updates:
            return "错误: 更新灵感需要提供 content/tags/status 至少一个参数"
        result = update_inspiration(book_id, insp_id, updates)
        if not result:
            return f"未找到灵感: {insp_id[:12]}"
        return f"灵感已更新 (id: {insp_id[:12]})"

    elif action == "delete":
        insp_id = args.get("inspiration_id", "")
        if not insp_id:
            return "错误: 删除灵感需要 inspiration_id 参数"
        ok = delete_inspiration(book_id, insp_id)
        return "灵感已删除" if ok else f"未找到灵感: {insp_id[:12]}"

    elif action == "search":
        query = args.get("query", "")
        if not query:
            return "错误: 搜索灵感需要 query 参数"
        results = search_inspirations(book_id, query)
        if not results:
            return f"未找到匹配「{query}」的灵感碎片。"
        lines = [f"搜索「{query}」结果 ({len(results)} 条):"]
        for insp in results:
            insp_id_short = insp.get("id", "?")[:12]
            content = insp.get("content", "")[:80]
            status = insp.get("status", "inbox")
            lines.append(f"  [{insp_id_short}] [{status}] {content}")
        return "\n".join(lines)

    else:
        return f"未知操作: {action}，支持 add | list | get | update | delete | search"
