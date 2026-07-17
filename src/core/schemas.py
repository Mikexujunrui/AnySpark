# 实体分层结构模板
# 每个实体类型分为多个区块 (block)，每区块含多个字段 (field)
# 字段值可为 string / string[] / embedded object

CHARACTER_SCHEMA = {
    "基本": {
        "label": "基本信息",
        "fields": {
            "name": "姓名", "aliases": "别名",
            "age": "年龄", "gender": "性别", "species": "种族",
        },
    },
    "外貌": {
        "label": "外貌特征",
        "fields": {
            "appearance": "整体描述",
            "hair": "发色/发型", "eyes": "瞳色/特征",
            "height": "身高", "build": "体型",
            "clothing": "惯常衣着", "distinctive_marks": "显著特征（疤痕/胎记等）",
        },
    },
    "性格": {
        "label": "性格",
        "fields": {
            "personality": "性格概括",
            "temperament": "气质（外向/内向/暴戾/温润等）",
            "inner_conflict": "内心矛盾", "motivation": "核心动机",
            "fears": "恐惧", "quirks": "癖好/小习惯",
            "likes": "喜好", "dislikes": "厌恶",
        },
    },
    "能力": {
        "label": "能力/功法",
        "fields": {
            "cultivation_level": "修为等级", "cultivation_method": "修炼功法",
            "techniques": "掌握招式/技巧", "powers": "特殊能力",
            "special_items": "特殊装备", "combat_style": "战斗风格",
        },
    },
    "背景": {
        "label": "背景经历",
        "fields": {
            "origin": "出身", "background": "背景概述",
            "key_experiences": "关键经历", "secrets": "隐藏秘密",
            "traumas": "心理创伤", "goals": "当前目标",
            "regrets": "遗憾", "identity": "隐藏身份",
        },
    },
    "状态": {
        "label": "当前状态",
        "fields": {
            "current_location": "当前位置", "current_condition": "当前处境",
            "social_standing": "社会地位", "reputation": "名声",
        },
    },
    "对话": {
        "label": "对话风格",
        "fields": {
            "speaking_style": "说话风格概述（如：市井泼皮、豪门千金、冷傲剑客等）",
            "tone": "语气特征（冷峻/温柔/粗鲁/文雅/戏谑/庄严/油滑/简洁等）",
            "self_address": "自称（我/老子/本座/朕/在下/奴家/妾身/小生/咱等）",
            "catchphrases": "口头禅/高频用语（如：'找死'、'有意思'、'无聊'）",
            "address_superiors": "对上级/长辈的称呼方式",
            "address_peers": "对平辈的称呼方式",
            "address_juniors": "对下级/晚辈的称呼方式",
            "sentence_style": "句式特点（短促/冗长/反问多/语气词多/爱用典/大白话等）",
            "dialogue_sample": "典型对话示例（1-2句体现该角色说话风格的原句）",
        },
    },
}

LOCATION_SCHEMA = {
    "基本": {
        "label": "基本信息",
        "fields": {
            "name": "名称", "aliases": "别名",
            "location_type": "类型（大陆/国度/城池/村镇/秘境/建筑等）",
        },
    },
    "地理": {
        "label": "地理环境",
        "fields": {
            "region": "所属区域", "parent_location": "上级地点",
            "climate": "气候", "terrain": "地形",
            "landmarks": "地标/重要场所", "resources": "资源特产",
        },
    },
    "社会": {
        "label": "社会人文",
        "fields": {
            "population": "人口规模", "ruler": "统治者",
            "economy": "经济特色", "culture": "文化特征",
            "factions": "势力分布", "atmosphere": "氛围",
        },
    },
    "叙事": {
        "label": "叙事信息",
        "fields": {
            "description": "场景描写",
            "first_appearance": "首次出现",
            "significance": "剧情重要性",
            "current_status": "当前状态",
        },
    },
}

ITEM_SCHEMA = {
    "基本": {
        "label": "基本信息",
        "fields": {
            "name": "名称", "aliases": "别名",
            "item_type": "类型（武器/法宝/丹药/典籍/信物/神秘物品等）",
            "rarity": "稀有度",
        },
    },
    "属性": {
        "label": "物品属性",
        "fields": {
            "appearance": "外观描述", "material": "材质",
            "origin": "来历/锻造者", "special_ability": "特殊能力",
            "limitation": "使用限制/代价", "current_state": "当前状态（完整/破损/封印等）",
        },
    },
    "归属": {
        "label": "归属信息",
        "fields": {
            "owner": "当前持有者", "previous_owners": "历任持有者",
            "acquisition_method": "获得方式",
        },
    },
    "叙事": {
        "label": "叙事信息",
        "fields": {
            "description": "详细描述",
            "first_appearance": "首次出现",
            "significance": "剧情重要性",
        },
    },
}

ORGANIZATION_SCHEMA = {
    "基本": {
        "label": "基本信息",
        "fields": {
            "name": "名称", "aliases": "别名",
            "org_type": "类型（宗门/世家/王朝/教派/帮会/商会等）",
            "alignment": "立场（正/邪/中立）",
        },
    },
    "结构": {
        "label": "组织结构",
        "fields": {
            "leader": "领袖", "key_members": "核心成员",
            "hierarchy": "等级制度", "headquarters": "总部所在地",
            "sub_orgs": "下属分支",
        },
    },
    "属性": {
        "label": "组织属性",
        "fields": {
            "purpose": "宗旨", "influence": "势力范围",
            "history": "历史渊源", "strength": "整体实力",
            "secrets": "内部秘密",
        },
    },
    "叙事": {
        "label": "叙事信息",
        "fields": {
            "description": "描述",
            "first_appearance": "首次出现",
            "significance": "剧情重要性",
            "current_status": "当前状态",
        },
    },
}

CONCEPT_SCHEMA = {
    "基本": {
        "label": "基本信息",
        "fields": {
            "name": "名称", "aliases": "别名",
            "concept_type": "类型（修炼体系/世界规则/功法理论/法术体系/特殊法则等）",
        },
    },
    "规则": {
        "label": "规则说明",
        "fields": {
            "mechanism": "运作机制",
            "rules": "具体规则",
            "levels_or_stages": "等级/阶段划分",
            "limitations": "限制条件",
            "exceptions": "例外情况",
        },
    },
    "范围": {
        "label": "作用范围",
        "fields": {
            "affected_by": "适用对象",
            "region": "区域范围",
            "requirements": "前置条件",
        },
    },
    "叙事": {
        "label": "叙事信息",
        "fields": {
            "description": "描述",
            "source": "出处/创造者",
            "significance": "剧情重要性",
        },
    },
}

EVENT_SCHEMA = {
    "基本": {
        "label": "基本信息",
        "fields": {
            "name": "名称", "aliases": "别名",
            "event_type": "类型（战斗/转折/揭秘/相遇/背叛/灾难等）",
        },
    },
    "时间": {
        "label": "时间信息",
        "fields": {
            "time_point": "发生时间/章节",
            "duration": "持续时长",
            "chronology_order": "时间顺序",
        },
    },
    "参与者": {
        "label": "参与方",
        "fields": {
            "characters": "涉及人物", "organizations": "涉及势力",
            "locations": "发生地点",
        },
    },
    "叙事": {
        "label": "叙事信息",
        "fields": {
            "description": "事件描述",
            "cause": "起因", "consequence": "后果",
            "significance": "剧情重要性",
            "is_foreshadow": "是否伏笔",
        },
    },
}

# 供 LLM 使用的类型→Schema 映射
SCHEMAS = {
    "character": CHARACTER_SCHEMA,
    "location": LOCATION_SCHEMA,
    "item": ITEM_SCHEMA,
    "organization": ORGANIZATION_SCHEMA,
    "concept": CONCEPT_SCHEMA,
    "event": EVENT_SCHEMA,
}

# 用于构建提取 Prompt 的 Schema 摘要
def build_schema_prompt() -> str:
    lines = []
    for etype, blocks in SCHEMAS.items():
        lines.append(f"\n### {etype} 实体")
        for _block_key, block in blocks.items():
            fields_desc = []
            for fk, fv in block["fields"].items():
                desc = f"  \"{fk}\": \"{fv}\""
                fields_desc.append(desc)
            lines.append(f"// {block['label']}")
            lines.append("{")
            lines.extend(fields_desc)
            lines.append("}")
    return "\n".join(lines)

ALL_SCHEMAS = SCHEMAS
