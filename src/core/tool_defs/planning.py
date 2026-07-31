"""Outline, timeline, worldbuilding, location map and detailed outline tools.

Part of the ``core.tool_defs`` package (split from ``core/tools.py``).
"""

from __future__ import annotations

from ..tool_registry import Tool, registry

registry.register(
    Tool(
        name="generate_outline",
        description="根据所有章节内容自动生成全书大纲。逐章概括情节要点、关键事件、出场角色，最后生成全书总纲。已有大纲会被覆盖。适用于'生成大纲''概括全文'类指令。",
        parameters={
            "chapters": {"type": "string", "description": "范围：'all' 或 '#1-#5'，默认全部", "required": False},
        },
    )
)
registry.register(
    Tool(
        name="get_outline",
        description="获取当前书籍的大纲。不指定章节时返回全书总纲+所有章节概要。指定章节序号只返回该章大纲。",
        parameters={
            "chapter_index": {"type": "integer", "description": "章节序号（从1开始），留空返回全部", "required": False},
        },
    )
)
registry.register(
    Tool(
        name="update_outline",
        description="手动修改大纲中某章的内容（概要、备注等），或修改全书总纲。番外条目用 is_extra=true。",
        parameters={
            "chapter_index": {
                "type": "integer",
                "description": "章节序号（从1开始），留空则修改全书总纲",
                "required": False,
            },
            "synopsis": {"type": "string", "description": "章节概要", "required": False},
            "notes": {"type": "string", "description": "备注/规划", "required": False},
            "summary": {"type": "string", "description": "全书总纲（仅当不指定chapter_index时）", "required": False},
            "is_extra": {
                "type": "boolean",
                "description": "设为true则操作番外大纲条目（番外用 #E1 引用）",
                "required": False,
            },
        },
    )
)
registry.register(
    Tool(
        name="generate_timeline",
        description="从知识图谱读取已提取的时间线事件（由知识提取 extract_all_chapters 自动创建）。如果知识库中无数据，需先运行知识提取（/s 或 extract_all_chapters）。",
        parameters={},
    )
)
registry.register(
    Tool(
        name="get_timeline",
        description="获取当前时间线（所有轨道和事件）。",
        parameters={},
    )
)
registry.register(
    Tool(
        name="generate_worldbuilding",
        description="分析已有章节和知识库，自动识别该小说的世界观维度（如魔法体系、势力分布、社会规则等），生成分类和条目。每个条目以人类可读的段落形式呈现，注重设定的影响和作用而非角色性格。支持嵌套分类和@交叉引用。",
        parameters={},
    )
)
registry.register(
    Tool(
        name="get_worldbuilding",
        description="查看当前小说的世界观设定（所有分类和条目）。",
        parameters={},
    )
)
registry.register(
    Tool(
        name="add_worldbuilding_entry",
        description="向世界观的指定分类下添加一个条目。内容中可用 @条目名 交叉引用其他条目。",
        parameters={
            "category": {"type": "string", "description": "分类名称（如已存在则添加到该分类，不存在则自动创建）"},
            "title": {"type": "string", "description": "条目标题"},
            "content": {"type": "string", "description": "条目正文（人类可读的段落描述，可用@引用其他条目）"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "标签", "required": False},
            "chapter_refs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "相关章节如#1,#3",
                "required": False,
            },
        },
    )
)
registry.register(
    Tool(
        name="delete_worldbuilding_entry",
        description="删除世界观中的某个条目。",
        parameters={
            "entry_id": {"type": "string", "description": "条目ID，从 get_worldbuilding 获取"},
        },
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="delete_timeline_event",
        description="删除时间线上的一个事件。",
        parameters={
            "event_id": {"type": "string", "description": "事件ID，从 get_timeline 获取"},
        },
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="update_worldbuilding_entry",
        description="编辑已有世界观条目的标题、内容或标签。entry_id 从 get_worldbuilding 获取。",
        parameters={
            "entry_id": {"type": "string", "description": "条目ID，从 get_worldbuilding 获取"},
            "data": {
                "type": "object",
                "description": '要更新的字段，如 {"title": "新标题", "content": "新内容", "tags": ["标签1"]}',
            },
        },
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="generate_location_map",
        description="从知识图谱读取已提取的地点实体和关系（由知识提取 extract_all_chapters 自动创建）。如果知识库中无数据，需先运行知识提取（/s 或 extract_all_chapters）。",
        parameters={},
    )
)
registry.register(
    Tool(
        name="generate_detailed_outline",
        description="生成细纲：逐章提取纯剧情骨架，去掉所有描写、对话、心理活动，只保留'谁做了什么→导致什么结果'的事件链。适用于'生成细纲''提取剧情线''去水分大纲'类指令。",
        parameters={
            "chapters": {"type": "string", "description": "范围：'all' 或 '#1-#5'，默认全部", "required": False},
        },
    )
)
registry.register(
    Tool(
        name="get_detailed_outline",
        description="查看已生成的细纲（纯剧情骨架）。",
        parameters={},
    )
)
registry.register(
    Tool(
        name="update_detailed_outline",
        description="直接写入或修改某章的细纲（剧情事件链和叙事功能）。番外用 is_extra=true。可用于手动规划剧情，不要求已有章节正文。",
        parameters={
            "chapter_index": {"type": "integer", "description": "章节序号（从1开始）", "required": True},
            "title": {"type": "string", "description": "章节标题", "required": False},
            "plot_chain": {
                "type": "array",
                "description": "事件链数组，如 ['事件1: 谁→做了什么→结果', ...]",
                "required": False,
            },
            "chapter_function": {
                "type": "string",
                "description": "本章叙事功能（如'引入反派'、'主角成长转折'）",
                "required": False,
            },
            "is_extra": {"type": "boolean", "description": "设为true则操作番外细纲条目", "required": False},
        },
    )
)
registry.register(
    Tool(
        name="generate_volume_outlines",
        description="根据全书大纲自动划分分卷结构并填写每卷故事主线。无需参数，自动读取大纲分析并创建分卷。已有分卷会被保留并补充缺失的 storyLine。",
        parameters={},
    )
)
registry.register(
    Tool(
        name="expand_outline_pipeline",
        description="大纲逐级展开Pipeline：一句话设定→总纲→分卷纲→章节纲→细纲。每级注入上级结果和知识库上下文，确保一致性。适合从零开始构思新书。",
        parameters={
            "seed": {"type": "string", "description": "一句话故事设定/种子"},
            "levels": {"type": "integer", "description": "展开层级（1-4），默认4", "required": False},
        },
    )
)
