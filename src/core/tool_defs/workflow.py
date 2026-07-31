"""Workflow and skill execution tools.

Part of the ``core.tool_defs`` package (split from ``core/tools.py``).
"""

from __future__ import annotations

from ..tool_registry import Tool, registry

registry.register(
    Tool(
        name="manage_workflows",
        description=(
            "工作流管理统一入口。action 参数:\n"
            "  generate: 根据需求描述自动生成多步骤工作流\n"
            "  list: 列出当前项目已订阅的工作流\n"
            "  browse: 浏览全局工作流池\n"
            "  subscribe: 订阅全局池中的工作流到当前项目\n"
            "  unsubscribe: 取消订阅\n"
            "  delete: 删除工作流\n"
            "  update: 修改工作流名称或步骤"
        ),
        parameters={
            "action": {
                "type": "string",
                "description": "操作: generate/list/browse/subscribe/unsubscribe/delete/update",
            },
            "description": {"type": "string", "description": "需求描述（action=generate时必填）", "required": False},
            "workflow_id": {
                "type": "string",
                "description": "工作流ID（subscribe/unsubscribe/delete/update时必填）",
                "required": False,
            },
            "name": {"type": "string", "description": "新名称（action=update时可选）", "required": False},
            "steps": {
                "type": "array",
                "items": {"type": "object"},
                "description": "新步骤列表（action=update时可选）",
                "required": False,
            },
        },
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="list_workflows",
        description="列出当前项目已订阅的工作流（名称、ID、步骤数、创建时间）。",
        parameters={},
    )
)
registry.register(
    Tool(
        name="browse_workflows",
        description="浏览全局工作流池（包括未订阅的），用于发现可复用的工作流模板。",
        parameters={},
    )
)
registry.register(
    Tool(
        name="execute_workflow",
        description="在会话内执行一个已订阅的工作流。按顺序执行每个步骤并返回结果。可通过 params 传入动态参数覆盖步骤静态配置。",
        parameters={
            "workflow_id": {"type": "string", "description": "工作流ID（从 list_workflows 获取）"},
            "params": {
                "type": "object",
                "description": "动态参数，合并到每个步骤的执行上下文中，优先级高于步骤静态 config",
                "required": False,
                "properties": {
                    "ref_chapters": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "参考书章节列表，如 ['#1','#3']，注入原著章节原文",
                    },
                    "chapter_title": {"type": "string", "description": "目标章节标题"},
                    "instruction": {"type": "string", "description": "覆盖步骤的 writing instruction"},
                },
            },
        },
    )
)
registry.register(
    Tool(
        name="manage_workflow_steps",
        description="工作流步骤管理：列出步骤配置或修改某个步骤的参数。action=list 查看所有步骤详情，action=update 修改指定步骤的配置。",
        parameters={
            "action": {"type": "string", "description": "操作: list(列出步骤) / update(修改步骤配置)"},
            "workflow_id": {"type": "string", "description": "工作流ID"},
            "step_index": {
                "type": "integer",
                "description": "步骤编号（从0开始，action=update时必填）",
                "required": False,
            },
            "config": {
                "type": "object",
                "description": "新的配置参数，会与现有 config 合并（action=update时必填）",
                "required": False,
            },
        },
    )
)
registry.register(
    Tool(
        name="list_skills",
        description="列出所有可用技能（系统预设+用户自定义），支持按来源筛选。",
        parameters={
            "source": {
                "type": "string",
                "description": "过滤来源：'system'（系统预设）或 'user'（自定义），留空列出全部",
                "required": False,
            },
        },
    )
)
registry.register(
    Tool(
        name="manage_skills",
        description=(
            "技能管理统一入口。技能是预定义的工具调用序列，可通过触发器自动推荐。\n"
            "action 参数: list(列出) / create(创建) / update(修改) / delete(删除)"
        ),
        parameters={
            "action": {"type": "string", "description": "操作: list/create/update/delete"},
            "name": {"type": "string", "description": "技能名称（create/update/delete时必填）", "required": False},
            "description": {"type": "string", "description": "技能描述（create/update时可选）", "required": False},
            "triggers": {
                "type": "array",
                "items": {"type": "string"},
                "description": "触发器列表（create/update时可选）",
                "required": False,
            },
            "steps": {
                "type": "array",
                "items": {"type": "object"},
                "description": "步骤列表 [{tool, label, params}]（create/update时可选）",
                "required": False,
            },
            "source": {
                "type": "string",
                "description": "过滤来源: system/user（action=list时可选）",
                "required": False,
            },
        },
        dangerous=True,
    )
)
