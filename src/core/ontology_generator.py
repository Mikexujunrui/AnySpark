"""LLM-driven ontology generator — dynamically generates domain-specific entity types
and relationship types from book content, replacing the one-size-fits-all fixed schema.
"""

import json
import logging
from dataclasses import dataclass, field

from .llm_client import chat as llm_chat
from .utils import extract_json_from_response

logger = logging.getLogger(__name__)

# ── Default built-in types (used as fallback) ──
DEFAULT_ENTITY_TYPES = [
    {"name": "character", "label": "角色", "description": "小说中的人物角色"},
    {"name": "location", "label": "地点", "description": "故事发生的地点、场景"},
    {"name": "item", "label": "物品", "description": "重要物品、道具、法器"},
    {"name": "skill", "label": "技能/功法", "description": "角色掌握的能力、功法、法术"},
    {"name": "organization", "label": "组织", "description": "宗门、势力、团体"},
    {"name": "race", "label": "种族", "description": "种族、族群"},
    {"name": "concept", "label": "概念", "description": "抽象概念、设定、法则"},
    {"name": "event", "label": "事件", "description": "重大事件、历史节点"},
]

DEFAULT_RELATION_TYPES = [
    "KNOWS",
    "BELONGS_TO",
    "LOCATED_AT",
    "OWNS",
    "ANTAGONIST",
    "ALLY",
    "FAMILY",
    "ROMANTIC",
    "MASTER_OF",
    "MENTOR_OF",
    "KILLED",
    "SAVED",
    "LOVES",
    "CAUSES",
    "BEFORE",
    "AFTER",
    "FORESHADOWS",
    "RESOLVES",
    "PARTICIPATES_IN",
]

ONTOLOGY_SYSTEM_PROMPT = """你是一位专业的小说世界观设定专家。你的任务是分析小说的内容，为知识图谱设计最合适的实体类型和关系类型。

## 核心原则

1. **实体类型必须覆盖小说中所有重要的"可命名事物"**——除角色、地点外，还要深入挖掘该小说世界观独有的类型
2. **关系类型绝不能过度简化**——不要把"同一个学院"简单标为ALLY，不要把"同一个球队"简单标为ALLY
3. **类型名称用英文 snake_case**（如 spell, potion, quidditch_team, hogwarts_house）
4. **中文标签用于展示**（如 咒语、魔药、魁地奇球队、霍格沃茨学院）

## 实体类型设计指南

你必须根据小说世界观，主动发现以下类别的专属类型：

### 魔法/异能体系
- 如果小说有魔法 → spell（咒语）、potion（魔药）、magical_creature（魔法生物）、magical_artifact（魔法道具）
- 如果小说有修仙 → cultivation_method（功法）、elixir（丹药）、spirit_beast（灵兽）、secret_realm（秘境）
- 如果小说有超能力 → superpower（超能力）、mutant（变种人）

### 社会组织体系
- 学校 → school_house（学院）、school_club（社团）、school_year（年级）
- 运动 → sports_team（球队）、league（联赛）
- 宗门 → sect（宗门）、clan（家族）、alliance（联盟）
- 政治 → faction（派系）、government_agency（政府机构）、rebel_group（反抗组织）

### 物品/科技体系
- 魔法世界 → wand（魔杖）、broomstick（飞天扫帚）、horcrux（魂器）
- 科幻 → spaceship（飞船）、weapon（兵器）、ai_system（AI系统）
- 武侠 → weapon（兵器）、martial_art_manual（武功秘籍）

### 种族/生物体系
- 不是简单标为"race"，而是细分：elf（精灵）、dwarf（矮人）、goblin（哥布林）、giant（巨人）、werewolf（狼人）

## 关系类型设计指南（极其重要）

**千万不要把"同属一个组织"的人全部标为ALLY！**

错误示例：哈利和罗恩都在格兰芬多 → ALLY（错！）
正确做法：
- 哈利和罗恩是朋友 → FRIEND（或 KNOWS）
- 哈利和马尔福是敌对 → ANTAGONIST
- 哈利 → 格兰芬多 → BELONGS_TO_HOUSE（组织归属）
- 罗恩 → 格兰芬多 → BELONGS_TO_HOUSE（组织归属）
- 伍德 → 格兰芬多魁地奇队 → TEAM_CAPTAIN（队长）
- 哈利 → 格兰芬多魁地奇队 → TEAM_MEMBER（队员）

关系类型必须包含：
- **组织归属关系**：BELONGS_TO_HOUSE, BELONGS_TO_SECT, BELONGS_TO_TEAM, BELONGS_TO_FACTION
- **组织内角色关系**：TEAM_CAPTAIN, TEAM_MEMBER, CLASS_TEACHER, PREFECT（级长）, HEADMASTER（校长）
- **基础人际关系**：KNOWS, ALLY, ANTAGONIST, FAMILY, ROMANTIC, MENTOR_OF, FRIEND
- **层级关系**：MASTER_OF（师徒/主仆）, LOVES, KILLED, SAVED
- **归属/位置关系**：BELONGS_TO（物品归属）, LOCATED_AT, OWNS
- **因果/时序**：CAUSES, BEFORE, AFTER, PARTICIPATES_IN

## 输出格式

严格输出JSON：
```json
{
  "entity_types": [
    {
      "name": "类型英文名（snake_case）",
      "label": "中文标签",
      "description": "简短描述（中文）",
      "examples": ["示例1", "示例2"]
    }
  ],
  "relation_types": [
    {
      "name": "关系英文名（UPPER_SNAKE_CASE）",
      "label": "中文标签",
      "description": "简短描述（中文）",
      "examples": ["A→B", "C→D"]
    }
  ],
  "genre_analysis": "小说类型分析（1-2句话）"
}
```

## 特殊要求

- 必须包含 character（角色）和 location（地点）两种基础实体类型
- 实体类型总数 8-15 个（比通用版更丰富），关系类型 15-25 个
- 关系类型必须包含 KNOWS, ALLY, ANTAGONIST 三个基础人际关系
- 必须包含至少 2 个"组织归属"类关系（如 BELONGS_TO_HOUSE, BELONGS_TO_TEAM）
- 必须包含至少 1 个"组织内角色"关系（如 TEAM_CAPTAIN, PREFECT）
- 不要包含过于抽象的类型（如"情感"、"主题"）
- 每个实体类型给出 2-3 个代表性示例，示例必须来自该小说的世界观
"""


@dataclass
class Ontology:
    """Generated ontology for a specific book."""

    entity_types: list[dict] = field(default_factory=list)
    relation_types: list[dict] = field(default_factory=list)
    genre_analysis: str = ""
    source: str = "default"  # "generated" or "default"

    def to_dict(self) -> dict:
        return {
            "entity_types": self.entity_types,
            "relation_types": self.relation_types,
            "genre_analysis": self.genre_analysis,
            "source": self.source,
        }

    @staticmethod
    def default() -> "Ontology":
        return Ontology(
            entity_types=DEFAULT_ENTITY_TYPES,
            relation_types=[{"name": r, "label": r, "description": ""} for r in DEFAULT_RELATION_TYPES],
            genre_analysis="默认通用本体",
            source="default",
        )

    def get_entity_type_names(self) -> list[str]:
        return [e["name"] for e in self.entity_types]

    def get_relation_type_names(self) -> list[str]:
        return [r["name"] for r in self.relation_types]

    def get_entity_labels(self) -> dict[str, str]:
        return {e["name"]: e.get("label", e["name"]) for e in self.entity_types}

    def get_relation_labels(self) -> dict[str, str]:
        return {r["name"]: r.get("label", r["name"]) for r in self.relation_types}


def _validate_ontology(data: dict) -> Ontology | None:
    """Validate and normalize LLM-generated ontology JSON."""
    entity_types = data.get("entity_types", [])
    relation_types = data.get("relation_types", [])

    if not entity_types:
        logger.warning("Ontology generation returned empty entity_types")
        return None

    # Ensure required base types exist
    has_character = any(e.get("name") == "character" for e in entity_types)
    has_location = any(e.get("name") == "location" for e in entity_types)
    if not has_character:
        entity_types.append({"name": "character", "label": "角色", "description": "人物角色"})
    if not has_location:
        entity_types.append({"name": "location", "label": "地点", "description": "地点/场景"})

    # Ensure required relation types exist
    rel_names = {r.get("name", "").upper() for r in relation_types}
    for required in ["KNOWS", "ALLY", "ANTAGONIST"]:
        if required not in rel_names:
            relation_types.append({"name": required, "label": required, "description": ""})

    # Normalize: ensure each entry has all required fields
    for e in entity_types:
        e.setdefault("label", e.get("name", ""))
        e.setdefault("description", "")
        e.setdefault("examples", [])
    for r in relation_types:
        r.setdefault("label", r.get("name", ""))
        r.setdefault("description", "")
        r.setdefault("examples", [])

    return Ontology(
        entity_types=entity_types,
        relation_types=relation_types,
        genre_analysis=data.get("genre_analysis", ""),
        source="generated",
    )


def generate_ontology(
    book_title: str = "",
    book_description: str = "",
    sample_text: str = "",
    existing_entity_names: list[str] | None = None,
) -> Ontology:
    """Generate domain-specific ontology for a book using LLM.

    Args:
        book_title: The book's title for context.
        book_description: A brief description of the book's genre/world.
        sample_text: A sample of the book's content (first chapter or outline).
        existing_entity_names: Already-extracted entity names to help LLM understand the domain.

    Returns:
        An Ontology object with entity_types and relation_types.
    """
    context_parts = []
    if book_title:
        context_parts.append(f"书名: {book_title}")
    if book_description:
        context_parts.append(f"简介: {book_description}")
    if existing_entity_names:
        context_parts.append(f"已提取实体: {', '.join(existing_entity_names[:30])}")

    context = "\n".join(context_parts)

    prompt = f"## 小说信息\n{context}\n\n"
    if sample_text:
        prompt += f"## 内容样本（前4000字）\n{sample_text[:4000]}\n\n"
    prompt += "请为这部小说设计最合适的实体类型和关系类型。输出JSON:"

    try:
        response = llm_chat(prompt, system=ONTOLOGY_SYSTEM_PROMPT, temperature=0.2, task="extraction")
        if not response:
            logger.warning("Ontology generation returned empty response, using default")
            return Ontology.default()

        j = extract_json_from_response(response)
        data = json.loads(j.strip())
        ontology = _validate_ontology(data)
        if ontology:
            logger.info(
                "Ontology generated: %d entity types, %d relation types. Genre: %s",
                len(ontology.entity_types),
                len(ontology.relation_types),
                ontology.genre_analysis[:50],
            )
            return ontology
        return Ontology.default()
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning("Ontology generation failed (%s), using default", e)
        return Ontology.default()
    except Exception as e:
        logger.error("Unexpected error in ontology generation: %s", e)
        return Ontology.default()


def _to_pascal_case(name: str) -> str:
    """Convert snake_case to PascalCase for Neo4j labels."""
    parts = name.split("_")
    return "".join(p.capitalize() for p in parts if p)


def apply_ontology_to_schema(ontology: Ontology) -> dict:
    """Convert an Ontology to graph_schema-compatible dictionaries.

    Returns:
        dict with keys: entity_labels, relationship_types, entity_type_names
    """
    entity_labels = {}
    for e in ontology.entity_types:
        name = e["name"]
        label = _to_pascal_case(name)
        entity_labels[name] = label

    relationship_types = [r["name"].upper() for r in ontology.relation_types]

    return {
        "entity_labels": entity_labels,
        "relationship_types": relationship_types,
        "entity_type_names": [e["name"] for e in ontology.entity_types],
    }
