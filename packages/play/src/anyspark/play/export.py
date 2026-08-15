"""
anyspark.play.export — 推演路径导出灵感卡（md）。

把一次推演的当前路径渲染成 markdown 灵感卡：作为写作参考输入
（接 write_chapter 的 references 或作者浏览）。路径 = 根 → 当前节点，
每步含：场景摘录 + 用户选择 + 结算后的场景。
"""

from __future__ import annotations

from .tree import PlayStore


def export_path_markdown(store: PlayStore, session_id: str) -> str:
    """导出当前路径为 md（根 → 当前节点）。"""
    session = store.get_session(session_id)
    if session is None:
        raise KeyError(f"推演会话不存在：{session_id}")

    lines: list[str] = []
    title = session["title"] or f"互动推演 · 扮演 {session['role']}"
    lines.append(f"# {title}")
    lines.append("")
    lines.append(
        f"- 扮演角色：**{session['role']}**\n"
        f"- 切入场景：{session['seed']}\n"
        f"- 状态：{'进行中' if session['status'] == 'running' else '已结束'} · "
        f"当前深度 {_current_depth(store, session_id)}"
    )
    lines.append("")

    current_id = session["current_node_id"] or ""
    path = store.path_to(current_id)
    if not path:
        lines.append("（推演树为空）")
        return "\n".join(lines)

    for i, entry in enumerate(path, 1):
        node = entry["node"]
        lines.append(f"## 第 {i} 步")
        if entry["chosen_label"]:
            lines.append(f"**选择：** {entry['chosen_label']}")
            lines.append("")
        lines.append(str(node["scene"]).strip())
        lines.append("")
    return "\n".join(lines)


def _current_depth(store: PlayStore, session_id: str) -> int:
    session = store.get_session(session_id)
    if session is None:
        return 0
    node = store.get_node(str(session["current_node_id"] or ""))
    return int(node["depth"]) if node is not None else 0
