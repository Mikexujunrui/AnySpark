"""Volume management tools.

Part of the ``core.tool_defs`` package (split from ``core/tools.py``).
"""

from __future__ import annotations

from ..tool_registry import Tool, registry

registry.register(
    Tool(
        name="manage_volumes",
        description=(
            "分卷管理统一入口。action 参数:\n"
            "  list: 列出所有分卷、每卷的章节和故事主线\n"
            "  create: 创建新分卷\n"
            "  update: 修改分卷标题/故事主线/顺序\n"
            "  delete: 删除分卷（章节不删，仅解除分组）\n"
            "  move: 将章节移入指定分卷"
        ),
        parameters={
            "action": {"type": "string", "description": "操作: list/create/update/delete/move"},
            "volume_id": {"type": "string", "description": "分卷ID（update/delete/move时必填）", "required": False},
            "title": {"type": "string", "description": "分卷标题（create/update时可选）", "required": False},
            "story_line": {"type": "string", "description": "故事主线/大纲（create/update时可选）", "required": False},
            "order": {"type": "integer", "description": "排序号（update时可选）", "required": False},
            "chapter_id": {"type": "string", "description": "章节序号或ID（action=move时必填）", "required": False},
        },
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="list_volumes",
        description="列出当前书籍的所有分卷（名称、章节数、故事线）。",
        parameters={},
    )
)
