"""Chapter management and editing tools.

Part of the ``core.tool_defs`` package (split from ``core/tools.py``).
"""

from __future__ import annotations

from ..tool_registry import Tool, registry

registry.register(
    Tool(
        name="store_chapter",
        description="将用户提供的文本存储为章节。⚠️ Agent 自己写的章节用 delegate_writing 或 edit_chapter，不要用此工具——它会创建额外新章节。仅用于用户手动粘贴/导入文本时。",
        parameters={
            "title": {"type": "string", "description": "章节标题"},
            "content": {"type": "string", "description": "章节正文"},
            "is_extra": {"type": "boolean", "description": "是否为番外（不计入正常章节序号）", "required": False},
            "chapter_index": {
                "type": "integer",
                "description": "章节序号（如第5章写5）；若该序号已存在会拒绝覆盖",
                "required": False,
            },
        },
    )
)
registry.register(
    Tool(
        name="write_chapter",
        description="轻量写作工具：写大纲文本、补写过渡段落、写番外片段等辅助性轻量任务。会加载全部知识库实体。⚠️ 正式写章节请用 delegate_writing。⚠️ 修改已有章节请用 patch_chapter（局部编辑）或 edit_chapter（完整重写），不要用此工具。\n\n💡 推荐工作流：write_chapter 写初稿草稿 → 定稿后用 finalize_chapter（提取知识到知识库）。定稿前不会更新知识库，请放心反复试写。",
        parameters={
            "instruction": {"type": "string", "description": "写作指令"},
            "mode": {"type": "string", "description": "strict=严格约束 suggest=建议模式", "required": False},
            "is_extra": {"type": "boolean", "description": "是否为番外（不计入正常章节序号）", "required": False},
            "chapter_title": {"type": "string", "description": "章节标题（不指定则自动生成）", "required": False},
            "chapter_index": {
                "type": "integer",
                "description": "章节序号（如第5章写5）；若该序号已存在会拒绝覆盖",
                "required": False,
            },
            "ref_chapters": {
                "type": "array",
                "items": {"type": "string"},
                "description": "参考书章节ID列表（如['#1','#3']或['book_id:#2']），完整注入原著章节原文",
                "required": False,
            },
        },
    )
)
registry.register(
    Tool(
        name="list_chapters",
        description="列出当前书籍的所有章节（标题+字数+ID）。",
        parameters={},
    )
)
registry.register(
    Tool(
        name="read_chapter",
        description="读取指定章节内容。支持 offset/limit 分段读取（当输出被截断时使用）。也支持读取参考书章节。",
        parameters={
            "chapter_id": {"type": "string", "description": "章节序号（如 #1、#3）或完整ID"},
            "ref_book_id": {
                "type": "string",
                "description": "参考书ID，指定后从参考书读取章节而非当前书",
                "required": False,
            },
            "offset": {"type": "integer", "description": "起始字符偏移（0开始），用于分段读取", "required": False},
            "limit": {"type": "integer", "description": "最大读取字符数，用于分段读取", "required": False},
        },
    )
)
registry.register(
    Tool(
        name="delete_chapter",
        description="删除指定章节。不可恢复。",
        parameters={"chapter_id": {"type": "string", "description": "章节序号（如 #1）或完整ID"}},
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="delete_all_chapters",
        description="一次性删除当前书籍的所有章节。用户明确要求全部删除时使用。",
        parameters={},
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="import_chapters",
        description="读取上传的文档，自动按章节标题切割并创建章节记录。",
        parameters={
            "doc_id": {"type": "string", "description": "文档ID（从系统提示中的已上传文档列表获取）"},
        },
    )
)
registry.register(
    Tool(
        name="read_document",
        description="读取用户上传的文档内容。可指定偏移量和长度分段读取。",
        parameters={
            "doc_id": {"type": "string", "description": "文档ID（留空列出所有文档）", "required": False},
            "offset": {"type": "integer", "description": "偏移量（字符数）", "required": False},
            "limit": {"type": "integer", "description": "读取长度", "required": False},
        },
    )
)
registry.register(
    Tool(
        name="decompose_chapter",
        description="将章节拆解为结构化剧情链（场景+节拍+对话+情感弧线）。输出JSON并自动存储，可用于后续 rewrite_by_chain 逐节点复写。支持拆解参考书章节。",
        parameters={
            "chapter_text": {"type": "string", "description": "章节原文（与chapter_id二选一）", "required": False},
            "chapter_id": {
                "type": "string",
                "description": "章节序号（如 #1）或完整ID，自动读取章节内容",
                "required": False,
            },
            "chapter_title": {"type": "string", "description": "章节标题", "required": False},
            "save": {"type": "boolean", "description": "是否存储剧情链（默认true）", "required": False},
            "ref_book_id": {
                "type": "string",
                "description": "参考书ID，指定后从参考书读取章节而非当前书",
                "required": False,
            },
        },
    )
)
registry.register(
    Tool(
        name="annotate_chain",
        description="修改剧情链中各节点的改写模式(edit_mode)和具体修改指令(edit_instructions)。用于高保真改写场景：将节点标记为 keep(原样保留)/tweak(微调)/rewrite(改写)。无参数时显示当前状态。preview=true时显示带原文摘要的提案摘要，供用户确认。",
        parameters={
            "chain_id": {"type": "string", "description": "剧情链ID，留空则使用最近一条链", "required": False},
            "preview": {
                "type": "boolean",
                "description": "预览模式：返回每个节点的原文摘要和改写建议，不修改剧情链。用于提案-确认流程。",
                "required": False,
            },
            "annotations": {
                "type": "array",
                "description": "标注列表，每项包含 index(节点序号)、edit_mode(keep/tweak/rewrite)、edit_instructions(具体修改指令)",
                "required": False,
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer", "description": "节点序号"},
                        "edit_mode": {"type": "string", "description": "keep=原样保留 tweak=微调 rewrite=改写"},
                        "edit_instructions": {"type": "string", "description": "具体修改指令（tweak/rewrite模式需要）"},
                    },
                },
            },
        },
    )
)
registry.register(
    Tool(
        name="rewrite_by_chain",
        description="根据剧情链逐场景节点复写章节。每个节点独立生成文本并流式输出，最终拼接存储。需先通过 decompose_chapter 生成剧情链。",
        parameters={
            "chain_id": {
                "type": "string",
                "description": "剧情链ID（从 decompose_chapter 结果获取），留空则使用最近一条链",
                "required": False,
            },
            "style_profile": {"type": "string", "description": "文风约束", "required": False},
            "target_words_per_node": {
                "type": "number",
                "description": "每个节点目标字数（默认300）",
                "required": False,
            },
            "chapter_title": {"type": "string", "description": "输出章节标题", "required": False},
        },
    )
)
registry.register(
    Tool(
        name="edit_chapter",
        description="覆盖式修改章节：用新内容完整替换章节全文，自动创建新版本（旧版本保留可回退）。⚠️ 这是完整重写工具，会替换整章。若只需修改某段话、某句话、某个词，请优先使用 patch_chapter（局部精确编辑，不重写全章）。⚠️ 必须调用此工具才能修改，仅文字描述无效。",
        parameters={
            "chapter_id": {"type": "string", "description": "章节序号（如 #1）或完整ID"},
            "content": {"type": "string", "description": "新的章节内容"},
            "message": {"type": "string", "description": "版本说明（类似 commit message）", "required": False},
            "title": {"type": "string", "description": "新标题（可选，不传则保持原标题）", "required": False},
        },
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="patch_chapter",
        description=(
            "修改章节的局部内容——精确替换/插入/删除指定段落或句子，无需重写整章。自动创建新版本，旧版本保留可回退。"
            "这是精修/润色/局部修改的首选工具。⚠️ 必须调用此工具才能修改，仅文字描述无效。"
            "适用场景：修改某段对话、替换角色名、删除某句、在某段后插入新段落、润色某段描写等小改动。"
            "patch 操作类型："
            "  replace: 将 find/confirm 精确替换为 replace（只替换第一次出现）；"
            "  insert_after: 在锚点文本之后插入 text；"
            "  insert_before: 在锚点文本之前插入 text；"
            "  delete: 删除锚点文本（只删第一次出现）；"
            "  append: 追加 text 到章节末尾；"
            "  prepend: 在章节开头插入 text。"
            "📌 定位策略（推荐）：提供 segment_id（段落序号，从 0 开始）+ confirm（段落内 10-30 字片段），"
            "程序先在指定段落内搜索 confirm，找不到再尝试全章搜索。多次 patch 时每次操作后段落会重新编号。"
            "备选：仅提供 find（原文中精确存在的字符串，建议 20 字以上唯一片段）。"
        ),
        parameters={
            "chapter_id": {"type": "string", "description": "章节序号（如 #1）或完整ID"},
            "patches": {
                "type": "array",
                "description": (
                    "patch 操作列表，按顺序依次应用。每项格式："
                    '{"op": "replace", "segment_id": 2, "confirm": "段内片段", "replace": "替换为"} 或 '
                    '{"op": "replace", "find": "原文片段", "replace": "替换为"} 或 '
                    '{"op": "insert_after", "segment_id": 3, "confirm": "段内片段", "text": "插入内容"} 或 '
                    '{"op": "delete", "segment_id": 1, "confirm": "要删除的文本"} 或 '
                    '{"op": "append", "text": "追加内容"}'
                ),
            },
            "message": {"type": "string", "description": "版本说明（如 '修改第3段对话'）", "required": False},
        },
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="reorder_chapters",
        description="重新排列章节顺序。传入章节 ID 列表（按期望的新顺序），不在列表中的章节排到最后。适用场景：调换章节顺序、批量分卷组织、调整叙事节奏。先调用 list_chapters 查看当前顺序，再构造新顺序。",
        parameters={
            "order": {
                "type": "array",
                "items": {"type": "string"},
                "description": "章节 ID 列表，按新顺序排列（如 ['id1','id3','id2']）",
            },
        },
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="chapter_history",
        description="查看章节的版本历史。返回所有版本的时间、说明、字数，标注当前版本。类似 git log。",
        parameters={
            "chapter_id": {"type": "string", "description": "章节序号（如 #1）或完整ID"},
        },
    )
)
registry.register(
    Tool(
        name="revert_chapter",
        description="将章节回退到指定历史版本。类似 git checkout。不会删除其他版本。",
        parameters={
            "chapter_id": {"type": "string", "description": "章节序号（如 #1）或完整ID"},
            "version_id": {"type": "string", "description": "目标版本ID（从 chapter_history 获取）"},
        },
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="diff_chapters",
        description="对比章节的两个版本之间的差异。输出新增/删除/修改的段落摘要。",
        parameters={
            "chapter_id": {"type": "string", "description": "章节序号（如 #1）或完整ID"},
            "version_a": {"type": "string", "description": "版本A的ID（较旧版本）"},
            "version_b": {
                "type": "string",
                "description": "版本B的ID（较新版本，留空则用当前版本）",
                "required": False,
            },
        },
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="delete_version",
        description="删除章节的指定历史版本。不能删除当前版本（需先 revert 到其他版本）。至少保留一个版本。",
        parameters={
            "chapter_id": {"type": "string", "description": "章节序号（如 #1）或完整ID"},
            "version_id": {"type": "string", "description": "要删除的版本ID（从 chapter_history 获取）"},
        },
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="purge_chapter_history",
        description="清除章节的所有旧版本，只保留当前版本并重编为 v1。用于确认最终稿后清理历史。可指定单章或全部章节。",
        parameters={
            "chapter_id": {"type": "string", "description": "章节序号（如 #1）或 'all' 表示全部章节", "required": True},
        },
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="count_words",
        description="统计字数：指定章节或全书的字数。",
        parameters={
            "chapter_id": {"type": "string", "description": "章节序号（如 #1），留空则统计全书", "required": False},
        },
    )
)
registry.register(
    Tool(
        name="reconstruct_chapter",
        description="根据剧情链和风格配置重新构建章节。先分解后重组，保留核心情节但优化表达。",
        parameters={
            "chapter_id": {"type": "string", "description": "章节序号（如 #1）或完整ID"},
            "style_profile": {"type": "string", "description": "文风约束（可选）", "required": False},
        },
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="delegate_writing",
        description="正式写作工具。划定知识范围后生成并保存章节。先调用 prepare_writing；有细纲时按剧情合同分段写作，长章默认单段不超过2000字并阻止提前消耗后续剧情，写完后自动验证。",
        doc=(
            "主力写作工具。写作前必须调用 prepare_writing 获取本章需要的大纲/细纲/知识搜索/图谱洞察。"
            "prepare_writing 会自动输出建议的 delegate_writing 调用，直接复制使用。"
        ),
        parameters={
            "instruction": {"type": "string", "description": "写作指令（如'写第5章关于叶凡入魔的部分'）"},
            "characters": {
                "type": "string",
                "description": "本章出场角色名，逗号分隔（如'叶凡,林婉'）。留空则AI自动推断",
                "required": False,
            },
            "locations": {
                "type": "string",
                "description": "本章涉及地点，逗号分隔（如'青云宗,古魔洞'）。留空则AI自动推断",
                "required": False,
            },
            "concepts": {
                "type": "string",
                "description": "本章需要的世界观概念，逗号分隔（如'古魔血脉,灵气运转'）",
                "required": False,
            },
            "forbidden": {
                "type": "string",
                "description": "禁止出场的角色，逗号分隔（如'苏晴,慕容白'）。防止悬疑/节奏被破坏",
                "required": False,
            },
            "writing_rules": {
                "type": "string",
                "description": "特殊写作规则（如'本章结尾必须有悬念钩子''用叶凡视角'）",
                "required": False,
            },
            "target_words": {"type": "integer", "description": "目标总字数（默认2500）", "required": False},
            "target_words_per_node": {
                "type": "integer",
                "description": "分段写作时每段目标字数。留空则按总字数和分段数自动计算",
                "required": False,
            },
            "max_segment_words": {
                "type": "integer",
                "description": "单次正文生成硬上限（默认2000字）。长章会自动拆成多个剧情合同",
                "required": False,
            },
            "enforce_segment_boundaries": {
                "type": "boolean",
                "description": "是否启用剧情预算边界检查。总字数超过单段上限时默认开启",
                "required": False,
            },
            "segment_plan": {
                "type": "array",
                "items": {"type": "object"},
                "description": "可选的显式分段合同列表，每项可含 beat/must_cover/end_state/open_threads",
                "required": False,
            },
            "mode": {"type": "string", "description": "strict=严格模式 suggest=宽松模式", "required": False},
            "chapter_title": {"type": "string", "description": "章节标题（可选）", "required": False},
            "is_extra": {"type": "boolean", "description": "是否为番外（不计入正常章节序号）", "required": False},
            "ref_chapters": {
                "type": "array",
                "items": {"type": "string"},
                "description": "参考书章节ID列表（如['#1','#3']或['book_id:#2']），完整注入原著章节原文",
                "required": False,
            },
        },
    )
)
