"""Whole-book transform tools.

Part of the ``core.tool_defs`` package (split from ``core/tools.py``).
"""

from __future__ import annotations

from ..tool_registry import Tool, registry

registry.register(
    Tool(
        name="transform_book",
        description=(
            "全书批量变换工具——用自然语言指令对多章执行统一修改。每章自动创建新版本可回滚。"
            "三种模式：\n"
            "  patch（默认）：局部修改。如「把所有'小姐'改成'姑娘'」「战争场面更详细」；\n"
            "  rewrite：完全重写每章，保持情节走向但用全新文字表达。如「把第1-3章改为第一人称」；\n"
            "  restyle：应用指定文风，保持情节不变只调整遣词造句。需传 style_id。\n"
            "自动判断串行/并行：简单替换→并行，前后呼应→串行。"
        ),
        parameters={
            "instruction": {
                "type": "string",
                "description": "自然语言修改指令，如'把所有小姐改成姑娘'、'战争场面描写更详细'、'第一人称改为第三人称'",
            },
            "scope": {
                "type": "string",
                "description": "章节范围：'all' 或 '#1-#5' 或 '#1,#3,#7'，默认 'all'",
                "required": False,
            },
            "mode": {
                "type": "string",
                "description": "变换模式：'patch'(局部修改) | 'rewrite'(完全重写) | 'restyle'(文风调整)。默认 patch",
                "required": False,
            },
            "style_id": {
                "type": "string",
                "description": "文风ID/名称（mode=restyle时必填，从 list_styles 或 /api/styles 获取）",
                "required": False,
            },
            "execution_mode": {
                "type": "string",
                "description": "执行模式：'auto'(自动判断) | 'serial'(串行) | 'parallel'(并行)。默认 auto",
                "required": False,
            },
            "dry_run": {
                "type": "boolean",
                "description": "是否预览模式（不实际修改，只报告匹配数）。默认 false",
                "required": False,
            },
        },
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="find_replace_book",
        description="全书查找替换：对全部（或指定范围）章节执行字面或正则查找替换。每章生成新版本可回滚。适用于改名、统一术语等精确替换场景。",
        parameters={
            "pattern": {"type": "string", "description": "要查找的文本或正则表达式"},
            "replacement": {"type": "string", "description": "替换文本（正则模式支持 $1 等反向引用）"},
            "scope": {
                "type": "string",
                "description": "章节范围：'all' 或 '#1-#5' 或 '#1,#3,#7'，默认 'all'",
                "required": False,
            },
            "regex": {"type": "boolean", "description": "是否使用正则模式。默认 false（字面替换）", "required": False},
            "dry_run": {
                "type": "boolean",
                "description": "是否预览模式（只统计匹配数不修改）。默认 false",
                "required": False,
            },
            "message": {"type": "string", "description": "版本说明", "required": False},
        },
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="summarize_book",
        description="生成或刷新全书摘要：读取所有章节，生成结构化摘要（核心设定、主线剧情、角色列表、关键事件、未解伏笔），存入书籍元数据。长篇小说的摘要会注入 system prompt 作为长程上下文。建议每写完若干章调用一次。",
        parameters={},
    )
)
registry.register(
    Tool(
        name="apply_directive_globally",
        description="全书批量修改工具——用自然语言指令对全部（或指定范围）章节执行统一修改。每章自动创建新版本可回滚。支持常用修改如：统一人物称呼、调整文风、增强场面描写等。自动判断串行/并行执行。",
        parameters={
            "directive": {
                "type": "string",
                "description": "自然语言修改指令，如'把所有小姐改成姑娘'、'战争场面描写更详细'",
            },
            "scope": {
                "type": "string",
                "description": "章节范围：'all' 或 '#1-#5' 或 '#1,#3,#7'，默认 'all'",
                "required": False,
            },
            "execution_mode": {
                "type": "string",
                "description": "执行模式：'auto'(自动判断) | 'serial'(串行) | 'parallel'(并行)。默认 auto",
                "required": False,
            },
            "dry_run": {
                "type": "boolean",
                "description": "是否预览模式（不实际修改，只报告匹配数）。默认 false",
                "required": False,
            },
            "precheck": {
                "type": "boolean",
                "description": "是否两阶段执行：先轻量检查相关性，再全量编辑。默认 true",
                "required": False,
            },
        },
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="restyle_book",
        description="将指定章节应用一种写作风格。保持情节不变，只调整遣词造句、句式结构、修辞手法等文风要素。需指定 style_id（从 list_styles 获取可用风格）。",
        parameters={
            "style_id": {
                "type": "string",
                "description": "风格ID/名称（必填，从 list_styles 或 /api/styles 获取可用风格列表）",
            },
            "scope": {
                "type": "string",
                "description": "章节范围：'all' 或 '#1-#5' 或 '#1,#3,#7'，默认 'all'",
                "required": False,
            },
            "dry_run": {"type": "boolean", "description": "是否预览模式（不实际修改）。默认 false", "required": False},
        },
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="transform_chapters_batch",
        description="对指定章节列表执行批量变换。mode='patch'（局部修改）或 'rewrite'（完全重写）。每章自动创建新版本可回滚。",
        parameters={
            "chapter_ids": {"type": "string", "description": "章节范围，如 '#1-#5' 或 '#1,#3,#7'"},
            "instruction": {"type": "string", "description": "自然语言修改指令"},
            "mode": {
                "type": "string",
                "description": "变换模式：'patch'(局部修改) | 'rewrite'(完全重写)。默认 patch",
                "required": False,
            },
            "dry_run": {"type": "boolean", "description": "是否预览模式。默认 false", "required": False},
        },
        dangerous=True,
    )
)
