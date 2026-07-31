"""Knowledge graph, foreshadow, constraints and extraction tools.

Part of the ``core.tool_defs`` package (split from ``core/tools.py``).
"""

from __future__ import annotations

from ..tool_registry import Tool, registry

registry.register(
    Tool(
        name="extract_knowledge",
        description="从文本中提取结构化知识（人物、地点、物品、技能/功法、组织、种族、概念、事件、关系、伏笔）。关系类型优选：ALLY/FAMILY/ROMANTIC/LOVES/ANTAGONIST/MENTOR_OF/KILLED/SAVED/OWNS/BELONGS_TO/CAUSES，避免用泛化的 KNOWS。",
        parameters={"text": {"type": "string", "description": "待提取的文本内容"}},
    )
)
registry.register(
    Tool(
        name="extract_chapter",
        description="仅提取知识：从指定章节中提取新实体/关系/伏笔，与已有知识库对比后补充。不验证、不扫描AI味、不生成连续性卡片。用于草稿阶段的增量知识补充。写完定稿请用 finalize_chapter。",
        parameters={
            "chapter_id": {"type": "string", "description": "章节序号，如 #5 或 #E1（番外）"},
            "force": {
                "type": "boolean",
                "description": "忽略内容指纹缓存并重新提取，默认 false",
                "required": False,
            },
        },
    )
)
registry.register(
    Tool(
        name="prepare_writing",
        description="一键写作准备：自动获取大纲、细纲、知识库搜索和图谱洞察，输出结构化报告和建议的 delegate_writing 调用。适用于写新章节前快速了解本章需要什么。",
        parameters={"chapter_index": {"type": "integer", "description": "章节序号（从1开始），如 5"}},
    )
)
registry.register(
    Tool(
        name="finalize_chapter",
        description="【定稿收尾】按安全顺序执行：验证 → AI味扫描（纯规则零token）→ 有原文证据的增量知识提取 → 伏笔检查 → 连续性卡片 → 标记final。hard叙事约束冲突会保持draft并阻止知识入库。仅当章节最终定稿时使用。",
        parameters={"chapter_id": {"type": "string", "description": "章节序号，如 #5 或 #E1（番外）"}},
    )
)
registry.register(
    Tool(
        name="search_knowledge",
        description="检索当前书知识库中的实体和关系。如果搜索结果为空且本书有参考书，应主动用 search_reference 在参考书中查找。",
        parameters={"query": {"type": "string", "description": "搜索关键词"}},
    )
)
registry.register(
    Tool(
        name="add_entity",
        description="手动向知识图谱添加一个实体（角色、地点、物品、组织、概念、事件等）。如果实体已存在则更新其属性。",
        parameters={
            "name": {"type": "string", "description": "实体名称（如 '哈利·波特'）"},
            "type": {
                "type": "string",
                "description": "实体类型: character/location/item/organization/concept/event/skill/race",
                "required": False,
            },
            "aliases": {"type": "array", "items": {"type": "string"}, "description": "别名列表", "required": False},
            "data": {
                "type": "object",
                "description": "属性数据（如 {基本: {name:'...', age:'18'}, 外貌: {appearance:'...'}}）",
                "required": False,
            },
        },
    )
)
registry.register(
    Tool(
        name="add_relation",
        description="手动向知识图谱添加一条关系边。from和to可以是实体名或实体ID，支持所有关系类型。",
        parameters={
            "from": {"type": "string", "description": "起始实体名或ID"},
            "to": {"type": "string", "description": "目标实体名或ID"},
            "type": {
                "type": "string",
                "description": "关系类型: knows/ally/antagonist/family/romantic/master_of/mentor_of/killed/saved/loves/owns/located_at/belongs_to/causes/participates_in",
            },
        },
    )
)
registry.register(
    Tool(
        name="delete_entity",
        description="删除知识库中的一个实体（角色/地点/物品/组织/概念/事件）。不可恢复。",
        parameters={
            "entity_id": {"type": "string", "description": "实体ID（从 search_knowledge 获取）或实体名称"},
        },
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="update_entity",
        description="修改知识库中某个实体的属性和描述。传入 entity_id 和要修改的字段即可。",
        parameters={
            "entity_id": {"type": "string", "description": "实体ID或名称"},
            "data": {"type": "object", "description": '要更新/新增的字段键值对，如 {"年龄": "25岁", "能力": "控火"}'},
        },
    )
)
registry.register(
    Tool(
        name="set_character_phase",
        description=(
            "为角色创建或切换到一个「阶段」(角色弧光阶段卡片)。一个角色可以随剧情推进拥有"
            "多个阶段卡片(如 第一部·觉醒 / 第二部·暗流 / 第三部·救赎)。每个阶段"
            "是一张半独立的完整角色卡,包括该阶段的 personality/abilities/motivation/"
            "relationships/status/growth_note 等。\n\n"
            "⚠️ 阶段系统不绑定具体章节或分卷——阶段点是角色状态的切片,你可以在角色"
            "经历重大转变(背叛、觉醒、死亡、成长、黑化等)时直接设计并填入新阶段,"
            "不需要预先有章节。写作时系统自动注入该角色「当前阶段」(is_current)的卡片。\n\n"
            "调用场景:1) 写作中发现角色经历了重大转变时新建下一阶段并标记为当前;"
            "2) 规划时预先为角色建立后续阶段;3) 切换当前写作阶段(对已有阶段设 is_current=true)。"
        ),
        parameters={
            "character_id": {"type": "string", "description": "角色实体ID或名称"},
            "phase": {"type": "string", "description": "阶段名,如'第一部·觉醒'、'复仇期'、'救赎期'"},
            "phase_key": {"type": "string", "description": "稳定标识,如 arc1/arc2,留空则自动生成", "required": False},
            "is_current": {
                "type": "boolean",
                "description": "是否为当前写作阶段(自动取消同角色其他阶段的 is_current)。新建下一阶段时建议设为 true。默认 true",
                "required": False,
            },
            "data": {
                "type": "object",
                "description": (
                    "该阶段的角色完整属性(与 entity.data 同字段,但是该阶段的状态)。"
                    "建议包含:appearance(外貌变化), personality(性格状态), "
                    "abilities(能力), status(当前状态), motivation(本阶段驱动力), "
                    "relationships(关系状态摘要), growth_note(从上一阶段到本阶段的变化说明)"
                ),
            },
            "description": {
                "type": "string",
                "description": "阶段叙事描述:一句话概括角色在本阶段的状态",
                "required": False,
            },
        },
        mutates_kb=True,
    )
)
registry.register(
    Tool(
        name="delete_foreshadow",
        description="删除一个伏笔。",
        parameters={
            "foreshadow_id": {"type": "string", "description": "伏笔ID，从 search_knowledge 查询获得"},
        },
        dangerous=True,
    )
)
registry.register(
    Tool(
        name="plan_foreshadow",
        description="为伏笔规划回收弧。用户决定某个伏笔应该在哪个叙事弧（如'真相揭露'、'最终决战'）中回收。系统会在进入该弧时提醒用户确认。",
        parameters={
            "foreshadow_id": {"type": "string", "description": "伏笔ID，从 search_knowledge 查询获得"},
            "planned_arc": {"type": "string", "description": "规划回收弧名称，如'真相揭露'、'学院篇'、'最终决战'"},
        },
    )
)
registry.register(
    Tool(
        name="schedule_foreshadow",
        description="将伏笔排入指定章节回收。用户确认后，该伏笔会在写作该章时作为主动回收任务注入。",
        parameters={
            "foreshadow_id": {"type": "string", "description": "伏笔ID，从 search_knowledge 查询获得"},
            "chapter": {"type": "string", "description": "回收章节，如'#15'"},
        },
    )
)
registry.register(
    Tool(
        name="postpone_foreshadow",
        description="推迟伏笔回收。将'到期'的伏笔退回'已规划'状态，下次不再提醒。",
        parameters={
            "foreshadow_id": {"type": "string", "description": "伏笔ID，从 search_knowledge 查询获得"},
        },
    )
)
registry.register(
    Tool(
        name="list_pending_foreshadows",
        description="列出所有待处理的伏笔：包括已规划回收弧的（planned）和已到期等待确认的（due）。",
        parameters={},
    )
)
registry.register(
    Tool(
        name="resolve_foreshadow",
        description="手动标记一个伏笔为已回收。当伏笔已在章节正文中被实际处理后调用此工具确认回收。需提供 foreshadow_id（从 search_knowledge 或 list_pending_foreshadows 获取）和回收说明。",
        parameters={
            "foreshadow_id": {
                "type": "string",
                "description": "伏笔ID，从 search_knowledge 或 list_pending_foreshadows 获取",
            },
            "resolution_text": {
                "type": "string",
                "description": "回收说明，描述伏笔如何被回收、在哪个章节的什么情节中实现",
            },
        },
    )
)
registry.register(
    Tool(
        name="extract_all_chapters",
        description="逐章渐进式提取知识（人物卡/地点/关系/伏笔）。自动跳过内容未变化且已成功提取的章节，避免重复消耗 token；新实体和关系必须能在章节原文中找到证据。这是一个完整操作，调用后直接汇报结果即可。",
        parameters={
            "force": {
                "type": "boolean",
                "description": "忽略内容指纹缓存并重新提取全部章节，默认 false",
                "required": False,
            }
        },
        streaming=True,
    )
)
registry.register(
    Tool(
        name="define_constraint",
        description="设定叙事约束规则。如'主角获得神器后不能丢失'、'反派在第10章前不能知道主角身份'。系统将用LLM自动生成检测查询，在 check_constraints 时执行。",
        parameters={
            "description": {"type": "string", "description": "用自然语言描述约束规则"},
            "severity": {
                "type": "string",
                "description": "hard=必须遵守(违反报红), soft=仅警告(报黄)",
                "required": False,
            },
        },
    )
)
registry.register(
    Tool(
        name="check_constraints",
        description="检查当前所有叙事约束是否被遵守。返回违反列表，无违反时报告全部通过。修改章节后可调用此工具验证一致性。",
        parameters={},
    )
)
registry.register(
    Tool(
        name="delete_constraint",
        description="删除一条叙事约束。传入约束ID（从 check_constraints 或 define_constraint 的返回中获取）。",
        parameters={
            "constraint_id": {"type": "string", "description": "要删除的约束ID，如 C0a1b2c3"},
        },
    )
)
registry.register(
    Tool(
        name="analyze_impact",
        description="分析某个改动的影响范围（爆炸半径）。修改章节/设定/事件/伏笔前先调用，预览哪些后续内容会受影响。避免改一处忘一处。",
        parameters={
            "source_type": {"type": "string", "description": "被修改元素类型: entity / timeline_event / foreshadow"},
            "source_id": {"type": "string", "description": "被修改元素的ID"},
            "change_description": {"type": "string", "description": "改了什么（自然语言描述）", "required": False},
        },
    )
)
registry.register(
    Tool(
        name="score_confidence",
        description="评估知识库设定的可信度。每个设定卡片获得0-1分，反映引用密度、关系丰富度和一致性。低分设定建议补充。不传 entity_id 则评分全部实体。",
        parameters={
            "entity_id": {"type": "string", "description": "单个实体ID（可选，不填则评分全部）", "required": False},
        },
    )
)
registry.register(
    Tool(
        name="verify_chapter",
        description="写后验证：检查章节的实体漂移、大纲合规、约束违反、伏笔状态、可信度。delegate_writing 写完后自动调用。也可手动调用验证任意章节。",
        parameters={
            "chapter_id": {"type": "string", "description": "章节序号（如 #5）或完整ID"},
            "scope_entities": {
                "type": "string",
                "description": "本章scope内的实体名列表（逗号分隔），用于实体漂移检测。留空则用全部实体",
                "required": False,
            },
        },
    )
)
registry.register(
    Tool(
        name="search_graph",
        description="用自然语言搜索知识图谱（GraphRAG）。自动分解问题、生成Cypher查询、综合结果。适合复杂关系查询，如'叶凡和谁有师徒关系''哪些伏笔涉及青云宗'。",
        parameters={
            "question": {"type": "string", "description": "自然语言问题"},
        },
    )
)
registry.register(
    Tool(
        name="get_graph_insights",
        description="获取图谱洞察：遗忘角色、未回收伏笔、桥接角色、设定薄弱实体、约束违反、写作建议。写作前调用可了解全局状态。",
        parameters={},
    )
)
registry.register(
    Tool(
        name="memory_write",
        description="写入记忆系统：记录项目架构决策、已知问题、功能状态，或用户偏好（XP、套路、雷点等）。"
        "当用户说了需要记住的内容时调用此工具。如果记忆系统已全局关闭，操作会静默忽略。",
        parameters={
            "target": {
                "type": "string",
                "description": "目标类别: 'decision'(架构决策) | 'issue'(已知问题) | 'feature'(功能状态) | 'preference'(用户偏好)",
                "enum": ["decision", "issue", "feature", "preference"],
            },
            "title": {"type": "string", "description": "标题/摘要"},
            "content": {"type": "string", "description": "详细内容"},
            "keywords": {
                "type": "string",
                "description": "偏好条目的关键词（仅 target=preference 时使用），逗号分隔",
                "required": False,
            },
            "confidence": {
                "type": "string",
                "description": "偏好条目的置信度（仅 target=preference 时使用）: confirmed(已确认) | pending(待确认)",
                "enum": ["confirmed", "pending"],
                "required": False,
            },
        },
    )
)
