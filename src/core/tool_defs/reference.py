"""Reference materials and reference-book tools.

Part of the ``core.tool_defs`` package (split from ``core/tools.py``).
"""

from __future__ import annotations

from ..tool_registry import Tool, registry

registry.register(
    Tool(
        name="add_material",
        description="添加研究资料到共享资料库（所有项目可订阅引用）。可手动输入或从网页搜索结果收藏。",
        parameters={
            "title": {"type": "string", "description": "资料标题"},
            "content": {"type": "string", "description": "资料正文/摘要内容"},
            "tags": {"type": "array", "description": "标签列表，如['历史','服饰','唐代']", "required": False},
            "source": {"type": "string", "description": "来源说明，如'web_search'或书名", "required": False},
            "source_url": {"type": "string", "description": "来源URL（可选）", "required": False},
        },
    )
)
registry.register(
    Tool(
        name="search_materials",
        description="全文搜索共享资料库。仅返回当前项目已订阅的资料条目。未订阅的资料可通过 browse_materials 发现。",
        parameters={
            "query": {"type": "string", "description": "搜索关键词"},
        },
    )
)
registry.register(
    Tool(
        name="browse_materials",
        description="浏览全局资料池（包括未订阅的），用于发现新资料。搜索结果不受项目订阅限制。",
        parameters={
            "query": {"type": "string", "description": "搜索关键词（留空则为全部列表）", "required": False},
            "tags": {"type": "array", "description": "按标签筛选", "required": False},
        },
    )
)
registry.register(
    Tool(
        name="subscribe_material",
        description="将资料库中的条目订阅到当前项目，使其可在 search_materials 和写作上下文中使用。",
        parameters={
            "material_id": {"type": "string", "description": "资料ID（从 browse_materials 获取）"},
        },
    )
)
registry.register(
    Tool(
        name="unsubscribe_material",
        description="从当前项目取消订阅某条资料（不删除资料本身）。",
        parameters={
            "material_id": {"type": "string", "description": "资料ID"},
        },
    )
)
registry.register(
    Tool(
        name="delete_material",
        description="从全局资料库永久删除一条资料。影响所有订阅该项目。",
        parameters={
            "material_id": {"type": "string", "description": "资料ID"},
        },
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="set_reference_books",
        description=(
            "设置当前小说项目的参考书。新增参考书默认“只学文风”，不会把人物/地点/剧情事实注入当前书；"
            "可在参考书面板改成“原著设定”或“文风+设定”。先用 list_books 查看项目ID。"
        ),
        parameters={
            "book_ids": {
                "type": "array",
                "description": "参考书的项目ID数组，如['1781356752676']。传入空数组取消所有参考书",
            },
        },
    )
)
registry.register(
    Tool(
        name="list_books",
        description="列出系统中所有项目/书籍（包括书名、ID、实体数、章节数）。用于查找参考书的ID。",
        parameters={},
    )
)
registry.register(
    Tool(
        name="list_references",
        description="列出当前项目已设置的参考书摘要（书名、实体数、章节数、核心角色）。",
        parameters={},
    )
)
registry.register(
    Tool(
        name="list_reference_chapters",
        description="列出参考书的所有章节（标题、字数、章节ID）。用于在写作前选择原著章节注入上下文。",
        parameters={
            "ref_book_id": {
                "type": "string",
                "description": "参考书项目ID（留空则列出所有参考书的章节）",
                "required": False,
            },
        },
    )
)
registry.register(
    Tool(
        name="import_reference_chapters",
        description='从参考书批量导入章节到当前书籍。支持传入多个章节ID，或传 ["*"] 导入全部章节。自动跳过已存在的同名章节。',
        parameters={
            "ref_book_id": {"type": "string", "description": "参考书的 book_id（从 list_reference_books 获取）"},
            "chapter_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": '要导入的章节 ID 列表（从 list_reference_chapters 获取）。传 ["*"] 或 ["all"] 导入全部章节',
            },
        },
    )
)
registry.register(
    Tool(
        name="search_reference",
        description=(
            "在用途为“原著设定”或“文风+设定”的参考书中搜索角色和设定。“只学文风”的书会被硬隔离并跳过事实搜索。"
        ),
        parameters={
            "query": {"type": "string", "description": "搜索关键词（角色名、术语、事件等）"},
        },
    )
)
registry.register(
    Tool(
        name="migrate_reference_knowledge",
        description="将参考书中的实体迁移到当前书的知识库。当本书缺少某个角色/地点/设定的知识点、但参考书中存在时使用。可复制原样迁移，也可修改后再迁移（参考书的知识点不会被修改）。",
        parameters={
            "ref_book_id": {"type": "string", "description": "参考书项目ID"},
            "entity_name": {"type": "string", "description": "参考书中要迁移的实体名称（精确匹配）"},
            "new_name": {"type": "string", "description": "迁移后新实体的名称（留空则保持原名）", "required": False},
            "new_data": {
                "type": "object",
                "description": "迁移后修改的数据字段（留空则完全复制参考书数据）。可修改 personality/appearance/description/abilities 等字段以适应本书",
                "required": False,
            },
        },
    )
)
