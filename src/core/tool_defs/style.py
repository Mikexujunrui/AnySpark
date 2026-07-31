"""Style, voice, structure and review tools.

Part of the ``core.tool_defs`` package (split from ``core/tools.py``).
"""

from __future__ import annotations

from ..tool_registry import Tool, registry

registry.register(
    Tool(
        name="set_style",
        description="设置当前写作风格，切换后 write_chapter/delegate_writing 将自动遵循新风格。不传 name 时根据 content 自动推荐并设置。查看当前风格用 manage_styles action=get。",
        parameters={
            "name": {
                "type": "string",
                "description": "风格名（从 manage_styles action=list 获取）。不传则根据 content 自动推荐",
                "required": False,
            },
            "content": {
                "type": "string",
                "description": "场景描述或章节关键词（如'战斗''回忆''悬疑'），用于自动推荐风格。仅当不传 name 时使用",
                "required": False,
            },
        },
    )
)
registry.register(
    Tool(
        name="get_style",
        description="获取当前激活的写作风格详情。",
        parameters={},
    )
)
registry.register(
    Tool(
        name="list_styles",
        description="列出所有可用的写作风格（系统预设+自定义），支持按来源筛选。",
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
        name="manage_styles",
        description="管理自定义写作风格：查看详情、添加、修改、删除。系统预设风格只读不可修改。",
        parameters={
            "action": {
                "type": "string",
                "description": "操作: list(列出所有) / get(查看详情) / add(添加自定义) / update(修改自定义) / delete(删除自定义)",
            },
            "name": {"type": "string", "description": "风格名称（get/add/update/delete时必填）", "required": False},
            "description": {"type": "string", "description": "风格描述（add/update时可选）", "required": False},
            "priority": {
                "type": "string",
                "description": "优先级: suggest/apply/strict（add/update时可选）",
                "required": False,
            },
            "applies_to": {
                "type": "array",
                "items": {"type": "string"},
                "description": "适用场景标签列表",
                "required": False,
            },
            "slots": {
                "type": "array",
                "items": {"type": "object"},
                "description": "提示槽列表 [{target, content}]",
                "required": False,
            },
        },
    )
)
registry.register(
    Tool(
        name="extract_style",
        description="从章节文本中提取并分析写作风格特征（句式、修辞、节奏、用词习惯等）。",
        parameters={
            "chapter_id": {"type": "string", "description": "章节序号（如 #1）或完整ID"},
        },
    )
)
registry.register(
    Tool(
        name="compare_plot",
        description="对比两个文本的情节差异，识别新增、删除、修改的情节节点。",
        parameters={
            "text_a": {"type": "string", "description": "文本A"},
            "text_b": {"type": "string", "description": "文本B"},
        },
    )
)
registry.register(
    Tool(
        name="suggest_plot_directions",
        description="生成多个剧情走向选项供用户选择。基于当前章节、大纲和知识库，提出3-4种不同的剧情发展方向，以可视化卡片形式呈现给用户。用户可以选择一个方向、自定义方向或拒绝所有选项。适用于'接下来怎么写''剧情走向''给几个选择'类指令。",
        parameters={
            "instruction": {
                "type": "string",
                "description": "用户关于剧情方向的需求描述（如'主角接下来怎么办''第二幕高潮怎么设计'）",
            },
            "chapter_ref": {
                "type": "string",
                "description": "参考章节序号（如 #5），用于获取当前剧情上下文",
                "required": False,
            },
            "num_options": {"type": "integer", "description": "生成选项数量（默认3，最多5）", "required": False},
        },
    )
)
registry.register(
    Tool(
        name="run_review",
        description="启动评审团评审指定章节。多位评审员（编剧/编辑/各类读者）并发评审，输出汇总报告+每人详细反馈。可指定评审员和执行模式。",
        parameters={
            "chapter": {"type": "string", "description": "章节序号（如 #1、#3）或完整ID，也可直接传入章节文本"},
            "reviewers": {
                "type": "string",
                "description": "指定评审员ID（逗号分隔，如 screenwriter,harsh_critic），留空则使用全部激活的评审员",
                "required": False,
            },
            "mode": {
                "type": "string",
                "description": "执行模式: concurrent(并发,默认) 或 serial(串行，后续评审员可看到前序意见)",
                "required": False,
            },
        },
    )
)
registry.register(
    Tool(
        name="manage_reviewers",
        description="管理评审团成员：查看列表、激活/停用评审员。",
        parameters={
            "action": {"type": "string", "description": "操作: list/activate/deactivate"},
            "reviewer_id": {
                "type": "string",
                "description": "评审员ID（activate/deactivate时必填）",
                "required": False,
            },
        },
    )
)
registry.register(
    Tool(
        name="analyze_voice",
        description="分析指定角色的语言风格指纹：高频用词、句式偏好、口头禅、情感倾向。用于确保角色对话风格一致性。",
        parameters={
            "character_name": {"type": "string", "description": "角色名称"},
        },
    )
)
registry.register(
    Tool(
        name="get_voice_profile",
        description="获取所有角色的语言指纹摘要。写作前调用可了解每个角色的说话风格特征，帮助保持对话一致性。",
        parameters={},
    )
)
registry.register(
    Tool(
        name="semantic_diff",
        description="对比章节两个版本的语义差异（非文本差异）。识别角色情绪变化、场景变更、情节走向调整等。比 diff_chapters 更深入。",
        parameters={
            "chapter_id": {"type": "string", "description": "章节序号或ID"},
            "old_version_id": {"type": "string", "description": "旧版本ID"},
            "new_version_id": {"type": "string", "description": "新版本ID"},
        },
    )
)
registry.register(
    Tool(
        name="analyze_structure",
        description="分析参考书的叙事结构：逐章字数分布、对话占比、段落统计、节奏曲线。纯Python确定性计算，结果缓存可复用。适用于原著续写前的结构深读。",
        parameters={
            "ref_book_id": {
                "type": "string",
                "description": "参考书项目ID。留空则分析当前书的第一本参考书",
                "required": False,
            },
        },
    )
)
registry.register(
    Tool(
        name="quantify_style",
        description="量化分析参考书的文风指纹：句长分布、词汇丰富度(TTR)、标点模式、四字成语密度、段落长度统计。纯Python确定性计算，结果缓存可复用。适用于原著续写前的文风匹配。",
        parameters={
            "ref_book_id": {
                "type": "string",
                "description": "参考书项目ID。留空则分析当前书的第一本参考书",
                "required": False,
            },
        },
    )
)
registry.register(
    Tool(
        name="analyze_deep_style",
        description="深度分析文学文本的风格特征（尤其适用于古典/半文半白小说）。支持四种分析类型：\n- sentence_rhythm：句式韵律（对仗/骈文/文言标记/长短交替/倒装）\n- rhetoric_density：修辞密度（用典/谐音双关/比喻/反讽）\n- prophecy_signature：谶语特征（诗词暗示/对话伏笔/象征行为/梦境叙事）\n- narrative_pov：叙事视角（全知标记/限知段落/视角切换/叙事者干预）\n纯Python确定性计算，结果缓存可复用。",
        parameters={
            "ref_book_id": {"type": "string", "description": "参考书项目ID", "required": False},
            "analysis_type": {
                "type": "string",
                "description": "分析类型: sentence_rhythm / rhetoric_density / prophecy_signature / narrative_pov",
                "required": True,
            },
        },
    )
)
registry.register(
    Tool(
        name="analyze_emotional_curve",
        description="分析全书情感弧线：逐章情感基调检测（喜/怒/哀/乐/惊/思/淡）、情感转换矩阵、乐极生悲转折密度。纯Python确定性计算，结果缓存可复用。适用于续写时的情感节奏对齐。",
        parameters={
            "ref_book_id": {
                "type": "string",
                "description": "参考书项目ID。留空则分析当前书的第一本参考书",
                "required": False,
            },
        },
    )
)
