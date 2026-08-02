"""
anyspark.align.inject — 注入器（说明书 → 写作/探索上下文）。

设计（DESIGN 第 6 节）：注入优先级 项目级 > 全局级；项目级永远可覆盖全局。
注入内容为自然语言说明书（跨模型可读），组装进 Agent 的系统提示。
"""

from __future__ import annotations

from .manual import ManualStore, render_manual
from .summarize import MemoryStore


class ManualInjector:
    """把说明书（项目级 + 全局级）渲染成可注入的自然语言段落。"""

    def __init__(self, manual: ManualStore) -> None:
        self._manual = manual

    def build_system_block(self, book_id: str = "main") -> str:
        """组装对齐注入块：全局级（极小化）+ 项目级（主体），项目级优先展示在后（覆盖语义）。"""
        global_entries = self._manual.list("global")
        project_entries = self._manual.list("project", book_id)

        blocks: list[str] = []
        if global_entries:
            blocks.append(render_manual(global_entries, title="全局写作偏好"))
        if project_entries:
            blocks.append(render_manual(project_entries, title=f"本书写作偏好（{book_id}）"))
        if not blocks:
            return ""
        return "\n\n".join(blocks)


class MemoryInjector:
    """把最近场景记忆注入上下文（跨会话延续性）。"""

    def __init__(self, memories: MemoryStore) -> None:
        self._memories = memories

    def build_block(self, book_id: str = "main") -> str:
        latest = self._memories.latest(book_id)
        if latest is None:
            return ""
        return f"# 上轮会话记忆\n（{latest.created_at[:19]}）\n{latest.content}"
