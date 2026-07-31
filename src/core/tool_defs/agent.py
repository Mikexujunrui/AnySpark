"""Agent-facing tools: tasks, autopilot, permissions, web, notes, inspirations.

Part of the ``core.tool_defs`` package (split from ``core/tools.py``).
"""

from __future__ import annotations

from ..tool_registry import Tool, registry

registry.register(
    Tool(
        name="manage_notes",
        description="管理项目笔记。action参数：add(添加笔记) | list(列出所有笔记) | delete(删除指定笔记)。笔记用于记录统领全书的思路、创作规划、灵感碎片等自由文本。Agent和用户都可以写入和查看。",
        parameters={
            "action": {"type": "string", "description": "操作类型：add | list | delete"},
            "content": {"type": "string", "description": "笔记内容（action=add时必填）", "required": False},
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "标签（action=add时可选）",
                "required": False,
            },
            "note_id": {
                "type": "string",
                "description": "笔记ID（action=delete时必填，从list获取）",
                "required": False,
            },
        },
    )
)
registry.register(
    Tool(
        name="manage_inspirations",
        description="管理灵感碎片看板。action参数：add(添加灵感) | list(列出所有灵感) | get(查看单条详情) | update(更新内容/标签/状态) | delete(删除灵感) | search(关键词搜索)。灵感用于沉淀创作中的零散想法，Agent 和用户共享同一个灵感看板。",
        parameters={
            "action": {"type": "string", "description": "操作类型：add | list | get | update | delete | search"},
            "content": {"type": "string", "description": "灵感内容（action=add 时必填）", "required": False},
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "灵感标签（action=add/update 时可选）",
                "required": False,
            },
            "status": {
                "type": "string",
                "description": "灵感状态（action=update/list 时可选）",
                "required": False,
            },
            "inspiration_id": {
                "type": "string",
                "description": "灵感ID（action=get/update/delete 时必填，从 list 获取）",
                "required": False,
            },
            "query": {
                "type": "string",
                "description": "搜索关键词（action=search 时必填）",
                "required": False,
            },
        },
    )
)
registry.register(
    Tool(
        name="ask_user",
        description="向用户提问。支持多个问题依次展示、单选/多选、自定义输入。仅当指令存在真正歧义且无法从上下文推断时使用。",
        parameters={
            "question": {"type": "string", "description": "向用户提出的问题（简单单问题场景）"},
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "可选答案列表（简单单问题场景）",
                "required": False,
            },
            "questions": {
                "type": "array",
                "description": "多个问题（复杂场景）。每个问题包含 question/header/options/multiple/custom 字段",
                "required": False,
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "问题文本"},
                        "header": {"type": "string", "description": "问题标题（显示在标签页）"},
                        "options": {
                            "type": "array",
                            "description": "选项列表",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string"},
                                    "description": {"type": "string"},
                                },
                            },
                        },
                        "multiple": {"type": "boolean", "description": "是否允许多选（默认false）"},
                        "custom": {"type": "boolean", "description": "是否允许自定义输入（默认true）"},
                    },
                },
            },
        },
    )
)
registry.register(
    Tool(
        name="task",
        description=(
            "启动独立的子 Agent 执行复杂的多步子任务。子 Agent 有独立对话上下文，"
            "完成后把最终文本作为 tool result 返回给主 Agent。子 Agent 不能再嵌套 spawn 子 Agent（系统级约束）。\n\n"
            "可用子 Agent 类型（按读写能力分组）：\n"
            "【只读型 — 所有模式下均可】：\n"
            "  - research: 联网调研助手（多次搜索+阅读外部资料）\n"
            "  - plan: 只读分析助手（检索知识库+章节分析）\n"
            "  - consistency: 一致性校验助手（检测知识库矛盾）\n"
            "  - reviewer: 评审助手（从多角色视角评审章节）\n"
            "【读写型 — 仅 Write 模式下可用】：\n"
            "  - extract: 知识提取专家\n"
            "  - write: 写作助手\n"
            "  - edit: 编辑助手（拆解/复写章节）\n"
            "  - general: 通用全能助手（处理复杂多步任务）\n\n"
            "典型场景：并行多个只读调研 / 卸载复杂子任务 / 主 agent 上下文快满了需要分流"
        ),
        parameters={
            "prompt": {"type": "string", "description": "子任务的详细描述"},
            "agent_type": {
                "type": "string",
                "enum": ["research", "plan", "consistency", "reviewer", "extract", "write", "edit", "general"],
                "description": "子 Agent 类型（只读型所有模式可用，读写型仅 Write 模式）",
            },
            "task_id": {"type": "string", "description": "恢复已有子任务会话的 ID（可选）", "required": False},
        },
    )
)
registry.register(
    Tool(
        name="manage_permissions",
        description="管理 Agent 权限模式。status(查看当前状态) / enable(启用自主模式，Agent 执行删除等危险操作无需确认) / disable(关闭自主模式，恢复确认机制)。⚠️ 启用后 Agent 可直接删除章节/实体/世界观条目等。",
        parameters={
            "action": {
                "type": "string",
                "description": "操作: status(查看状态) / enable(开启自主模式) / disable(关闭自主模式)",
            },
        },
    )
)
registry.register(
    Tool(
        name="web_search",
        description="联网搜索。通过 Exa/Parallel 搜索引擎查找实时信息。用于查找历史典故、地理知识、文化风俗、科学原理、时事新闻等写作素材。当知识库中没有相关信息、或问题涉及真实世界且超出 AI 知识截止日期时使用。",
        parameters={
            "query": {"type": "string", "description": "搜索关键词（建议用精确短语）"},
            "num_results": {"type": "integer", "description": "结果数量（默认8，最多20）", "required": False},
        },
    )
)
registry.register(
    Tool(
        name="web_fetch",
        description="抓取指定网页的文本内容。用于深入阅读 web_search 搜索结果中的链接，或访问用户提供的参考资料 URL。返回页面的纯文本提取结果。",
        parameters={
            "url": {"type": "string", "description": "网页 URL（http/https）"},
            "format": {"type": "string", "description": "输出格式: text（默认）", "required": False},
            "timeout": {"type": "integer", "description": "超时秒数（默认30，最大120）", "required": False},
        },
    )
)
registry.register(
    Tool(
        name="agent_tasks",
        description="Agent任务清单：规划、追踪多步操作。支持创建清单、查看进度、更新任务状态。",
        parameters={
            "action": {
                "type": "string",
                "description": "操作: create(创建新清单) / get(查看清单) / update(更新任务状态) / add(追加任务) / list(列出所有清单) / clear(清除已完成清单)",
            },
            "task_list_id": {
                "type": "string",
                "description": "清单ID（get/update/add时必填，留空则操作最近清单）",
                "required": False,
            },
            "title": {"type": "string", "description": "清单标题（create时必填）", "required": False},
            "items": {
                "type": "array",
                "items": {"type": "object"},
                "description": "任务项列表 [{label, tool?}]（create/add时可选）",
                "required": False,
            },
            "item_index": {"type": "number", "description": "任务项序号（update时必填，从0开始）", "required": False},
            "status": {
                "type": "string",
                "description": "新状态: pending/in_progress/done/skipped/failed（update时必填）",
                "required": False,
            },
            "result_summary": {"type": "string", "description": "执行结果摘要（update时可选）", "required": False},
        },
    )
)
registry.register(
    Tool(
        name="start_autopilot",
        description="启动 Autopilot 自主写作引擎，让 Agent 自主写完整本书或指定范围。此工具会先展示执行计划，等待用户确认后才开始执行。后台运行不阻塞聊天，断开连接也继续。⚠️ 调用前必须先读取大纲确定需要写哪些章节。",
        parameters={
            "instruction": {"type": "string", "description": "写作指令，如'按大纲写完剩余章节'、'续写后5章'"},
            "max_chapters": {"type": "integer", "description": "最多写几章，默认10", "required": False},
            "audit_mode": {
                "type": "string",
                "description": "审核模式：'soft'(质量低时暂停) | 'hard'(每章需确认) | 'autonomous'(全自动)。默认 soft",
                "required": False,
            },
            "auto_review": {"type": "boolean", "description": "是否每章写完自动评审，默认 true", "required": False},
            "auto_extract": {
                "type": "boolean",
                "description": "是否每章写完自动提取知识（不推荐，定稿后用 finalize_chapter 即可），默认 false",
                "required": False,
            },
        },
        dangerous=True,
    )
)
