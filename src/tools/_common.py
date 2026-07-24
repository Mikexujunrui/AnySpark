import json
import re
from concurrent.futures import ThreadPoolExecutor

from core.config import config
from core.knowledge import Entity
from core.llm_client import chat as llm_chat
from core.thread_pools import llm_pool as ai_executor
from core.utils import extract_json_from_response
from data.json_store import json_store  # noqa: F401 (re-exported for chapter_tools)


def _coerce_to_dict(v) -> dict:
    """Coerce an LLM-supplied value into a dict.

    LLMs occasionally emit a JSON string where the schema expects an object.
    This helper handles both cases safely and returns {} on anything that
    can't be meaningfully converted — downstream callers can then apply the
    default/fallback without crashing on a TypeError.
    """
    if v is None:
        return {}
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return {}
        try:
            parsed = json.loads(s)
        except (json.JSONDecodeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def get_executor() -> ThreadPoolExecutor:
    return ai_executor


PROGRESSIVE_EXTRACT_SYSTEM = """你是小说知识提取专家。你正在逐章阅读一部小说，当前阅读到新的一章。

# 任务
根据本章内容，对比已有人物/实体卡片，输出以下三类操作：

1. **new** — 本章首次出现的全新角色/地点/物品/组织/事件
2. **update** — 已有角色在本章中展现了新信息（需要补充到卡片的）
3. **unchanged** — 已有角色出现但无新信息（不输出）

# 对于 update 类型的判断规则
- 角色展现了之前不知道的属性（如新技能、真实身份、背景信息）→ 补充
- 角色的状态发生了变化（如位置变动、关系变化、心理转变）→ 更新状态
- 角色的描述与已有卡片矛盾 → 在 conflicts 字段标注

# 关系提取规则（极其重要）
- **同一对实体可以有多条不同维度的关系！** 不要只输出一条。
  例如哈利和罗恩：既输出 knows（个人关系），也输出 belongs_to_house（同属格兰芬多），还可能输出 team_member（同属魁地奇队）。
- 必须从以下三个维度分别检查并提取关系：
  1. **个人关系**：角色之间的直接人际互动（knows, ally, antagonist, family, romantic, friend 等）
  2. **组织归属**：角色→组织/学院/球队的归属关系（belongs_to, belongs_to_house, team_member 等）
  3. **空间关系**：角色/事件→地点的定位关系（located_at, located_in）
- 特别注意提取角色→组织/地点的归属关系，这不同于角色间的个人关系。

# 空间关系提取规则
- 对于本章出现的地点，分析它们之间的空间包含和相邻关系。
- 包含关系：如果一个地点位于另一个地点内部（如“格兰芬多休息室”位于“格兰芬多塔楼”内部，“格兰芬多塔楼”属于“霍格沃兹城堡”），使用 located_in。
- 相邻关系：两个地点物理上毗邻但没有包含关系，使用 adjacent_to。
- 每个地点至少应有一个上级包含关系或相邻关系。

# 时间线提取规则
- 一章内可以有多个关键时间点，只提取有剧情转折意义的事件。
- time_order 使用小数：整数部分=章节号，小数部分=章内序号（如第15章有3个事件：15.1, 15.2, 15.3）。
- 如果本章只有一个关键时间点，time_order 用整数（如 15.0）。
- 每个时间线事件可包含 location 字段（事件发生地点）。

# 伏笔提取规则（极其重要）
- 伏笔是指作者有意埋下的、在后续章节中会回收/揭晓的暗示或线索。
- 提取伏笔时必须输出以下字段：
  1. text: 伏笔原文（引用埋设段落的原文或精确概括）
  2. hint: 暗示了什么（伏笔隐含的信息）
  3. expected_resolution: 可能的揭晓方式
  4. plant_chapter: 伏笔埋设的章节号，如 "#3"
  5. confidence: 伏笔确信度 "high"（明确伏笔，有埋设语言）/ "medium"（疑似伏笔，异常强调的细节）/ "low"（可能是闲笔）
  6. resolve_keywords: 用于后续回收匹配的关键词列表（如 ["伤疤", "疼痛", "伏地魔"]），这些词应出现在伏笔被回收的段落中
- 如果本章同时回收了之前埋下的伏笔，在 foreshadows 中输出该伏笔并设置 resolve_chapter 为本章号。
- 不要把普通的场景描写或角色对话当作伏笔。伏笔必须是有意埋设、等待后续揭晓的内容。

# 输出格式（严格JSON）
{
  "new_entities": [
    {"type": "character/location/item/organization/event（如不匹配可用自定义类型如 clan/spell/faction 等）", "name": "名称", "aliases": ["别名"],
     "data": {"字段名": "值", ...}}
  ],
  "updates": [
    {"name": "已有角色名", "add": {"新字段": "新值"}, "modify": {"已有字段": "新值"},
     "conflicts": ["矛盾描述（可选）"], "reason": "更新理由"}
  ],
  "relations": [
    {"from": "实体名", "to": "实体名", "type": "关系类型"}
  ],
  "spatial_relations": [
    {"from": "内部地点名", "to": "外部地点名", "type": "located_in", "label": "位于...内"}
  ],
  "foreshadows": [
    {"text": "伏笔原文", "hint": "暗示内容", "expected_resolution": "可能的揭晓方式", "plant_chapter": "#3", "confidence": "high", "resolve_keywords": ["关键词1", "关键词2"], "resolve_chapter": ""}
  ],
  "timeline_events": [
    {"time_order": 15.1, "label": "事件名称", "chapter_ref": "#15", "characters": ["角色名"], "location": "地点名"}
  ]
}

关系类型限定: ally, antagonist, family, romantic, master_of, owns, located_at, located_in, adjacent_to, belongs_to, causes, participates_in, knows, occurred_at
如果本章没有新信息可提取，输出 {"new_entities":[],"updates":[],"relations":[],"spatial_relations":[],"foreshadows":[],"timeline_events":[]}"""


def get_extraction_system_prompt() -> str:
    """Generate the extraction system prompt with the currently active dynamic ontology.

    Reads the active entity types and relationship types from graph_schema
    (which may have been updated by ontology_generator) and generates a
    prompt that tells the LLM to use those specific types.

    Falls back to PROGRESSIVE_EXTRACT_SYSTEM if no dynamic ontology is active.
    """
    try:
        from core.graph_schema import get_active_entity_labels, get_active_relationship_types

        entity_labels = get_active_entity_labels()
        rel_types = get_active_relationship_types()

        # Check if dynamic ontology is meaningfully different from defaults
        default_entity_count = 9  # built-in ENTITY_LABELS count
        default_rel_names = {
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
            "INVOLVES",
            "HAS_PHASE",
            "DEPENDS_ON",
            "GOVERNS",
            "LOCATED_IN",
            "ADJACENT_TO",
            "OCCURRED_AT",
        }
        dynamic_rels = [r for r in rel_types if r not in default_rel_names]

        has_dynamic = len(entity_labels) > default_entity_count or len(dynamic_rels) > 0
        if not has_dynamic:
            return PROGRESSIVE_EXTRACT_SYSTEM

        # Build entity type list for the prompt
        entity_type_lines = []
        for name, label in entity_labels.items():
            if name == "constraint":
                continue
            entity_type_lines.append(f"  - {name}（{label}）")

        # Build relationship type list for the prompt
        # Filter out P0 structural edges (INVOLVES, HAS_PHASE, DEPENDS_ON, GOVERNS)
        extract_rel_types = [r for r in rel_types if r not in ("INVOLVES", "HAS_PHASE", "DEPENDS_ON", "GOVERNS")]
        rel_type_str = ", ".join(r.lower() for r in extract_rel_types)

        return f"""你是小说知识提取专家。你正在逐章阅读一部小说，当前阅读到新的一章。

# 任务
根据本章内容，对比已有人物/实体卡片，输出以下三类操作：

1. **new** — 本章首次出现的全新角色/地点/物品/组织/事件
2. **update** — 已有角色在本章中展现了新信息（需要补充到卡片的）
3. **unchanged** — 已有角色出现但无新信息（不输出）

# 可用实体类型（必须使用以下类型之一）
{chr(10).join(entity_type_lines)}

# 对于 update 类型的判断规则
- 角色展现了之前不知道的属性（如新技能、真实身份、背景信息）→ 补充
- 角色的状态发生了变化（如位置变动、关系变化、心理转变）→ 更新状态
- 角色的描述与已有卡片矛盾 → 在 conflicts 字段标注

# 关系提取规则（极其重要）
- **同一对实体可以有多条不同维度的关系！** 不要只输出一条。
  例如哈利和罗恩：既输出 knows（个人关系），也输出 belongs_to_house（同属格兰芬多），还可能输出 team_member（同属魁地奇队）。
- 必须从以下三个维度分别检查并提取关系：
  1. **个人关系**：角色之间的直接人际互动（knows, ally, antagonist, family, romantic, friend 等）
  2. **组织归属**：角色→组织/学院/球队的归属关系（belongs_to, belongs_to_house, team_member 等）
  3. **空间关系**：角色/事件→地点的定位关系（located_at, located_in）
- 特别注意提取角色→组织/地点的归属关系，这不同于角色间的个人关系。

# 空间关系提取规则
- 对于本章出现的地点，分析它们之间的空间包含和相邻关系。
- 包含关系：如果一个地点位于另一个地点内部（如“格兰芬多休息室”位于“格兰芬多塔楼”内部，“格兰芬多塔楼”属于“霍格沃兹城堡”），使用 located_in。
- 相邻关系：两个地点物理上毗邻但没有包含关系，使用 adjacent_to。
- 每个地点至少应有一个上级包含关系或相邻关系。

# 时间线提取规则
- 一章内可以有多个关键时间点，只提取有剧情转折意义的事件。
- time_order 使用小数：整数部分=章节号，小数部分=章内序号（如第15章有3个事件：15.1, 15.2, 15.3）。
- 如果本章只有一个关键时间点，time_order 用整数（如 15.0）。
- 每个时间线事件可包含 location 字段（事件发生地点）。

# 伏笔提取规则（极其重要）
- 伏笔是指作者有意埋下的、在后续章节中会回收/揭晓的暗示或线索。
- 提取伏笔时必须输出以下字段：
  1. text: 伏笔原文（引用埋设段落的原文或精确概括）
  2. hint: 暗示了什么（伏笔隐含的信息）
  3. expected_resolution: 可能的揭晓方式
  4. plant_chapter: 伏笔埋设的章节号，如 "#3"
  5. confidence: 伏笔确信度 "high"/"medium"/"low"
  6. resolve_keywords: 用于后续回收匹配的关键词列表
- 如果本章同时回收了之前埋下的伏笔，设置 resolve_chapter 为本章号。
- 不要把普通的场景描写或角色对话当作伏笔。

# 输出格式（严格JSON）
{{
  "new_entities": [
    {{"type": "实体类型（必须从上面的可用类型中选择）", "name": "名称", "aliases": ["别名"],
     "data": {{"字段名": "值", ...}}}}
  ],
  "updates": [
    {{"name": "已有角色名", "add": {{"新字段": "新值"}}, "modify": {{"已有字段": "新值"}},
     "conflicts": ["矛盾描述（可选）"], "reason": "更新理由"}}
  ],
  "relations": [
    {{"from": "实体名", "to": "实体名", "type": "关系类型"}}
  ],
  "spatial_relations": [
    {{"from": "内部地点名", "to": "外部地点名", "type": "located_in", "label": "位于...内"}}
  ],
  "foreshadows": [
    {{"text": "伏笔原文", "hint": "暗示内容", "expected_resolution": "可能的揭晓方式", "plant_chapter": "#3", "confidence": "high", "resolve_keywords": ["关键词1", "关键词2"], "resolve_chapter": ""}}
  ],
  "timeline_events": [
    {{"time_order": 15.1, "label": "事件名称", "chapter_ref": "#15", "characters": ["角色名"], "location": "地点名"}}
  ]
}}

关系类型限定: {rel_type_str}
如果本章没有新信息可提取，输出 {{"new_entities":[],"updates":[],"relations":[],"spatial_relations":[],"foreshadows":[],"timeline_events":[]}}"""

    except Exception:
        return PROGRESSIVE_EXTRACT_SYSTEM


VALIDATION_SYSTEM = """你是小说设定一致性审核员。以下是从一部小说中逐章提取出的全部人物/设定卡片。

请通读审核，检查以下问题：
1. 同一角色是否存在矛盾描述（如前后外貌不一致、能力冲突）
2. 关系是否自洽（A是B的师父，B是否也标注了A为师父）
3. 是否有遗漏的重要角色/关系
4. 设定是否有逻辑漏洞

输出JSON:
{
  "issues": [
    {"entity": "角色名", "type": "contradiction/missing/logic_error", "description": "问题描述", "suggestion": "建议修正"}
  ],
  "summary": "整体评价（1-2句话）"
}
如果没有问题，issues 为空数组。"""

SKIP_CHECK_SYSTEM = """你是小说章节快速扫描器。判断本章是否包含需要更新角色卡的新信息。

回答 YES 的条件（满足任一）：
- 出现了全新的角色（已有卡片中不存在的人物）
- 已有角色展现了之前未知的重要属性（新能力、真实身份、重要背景）
- 已有角色的状态发生了显著变化（修为突破、关系转变、立场改变）
- 出现了与已有设定矛盾的描述
- 出现了重要的新地点/组织/物品

回答 NO 的条件：
- 本章只是已知角色的日常互动，无新信息
- 角色言行符合已有设定，无突破性表现
- 只是推进情节但不涉及设定变化

只输出一个词: YES 或 NO"""


class _EntityCache:
    def __init__(self, kb):
        self._kb = kb
        self._entities: list = kb.list_entities()
        self._cards: str = self._format_cards()
        self._known_names: set = self._build_known_names()

    def get_cards(self) -> str:
        return self._cards

    def get_known_names(self) -> set:
        return self._known_names

    def get_entities(self) -> list:
        return self._entities

    def refresh(self):
        self._entities = self._kb.list_entities()
        self._cards = self._format_cards()
        self._known_names = self._build_known_names()

    def _build_known_names(self) -> set:
        names = set()
        for e in self._entities:
            names.add(e.name)
            for a in e.aliases:
                names.add(a)
        return names

    def _format_cards(self) -> str:
        if not self._entities:
            return ""
        # Try GraphStore's to_llm_context for richer formatting
        if hasattr(self._kb, "to_llm_context"):
            return self._kb.to_llm_context()
        # Fallback: basic entity-only format
        lines = []
        for e in self._entities:
            aliases = f"（{', '.join(e.aliases)}）" if e.aliases else ""
            lines.append(f"### [{e.type}] {e.name}{aliases}")
            for k, v in e.data.items():
                if v:
                    lines.append(f"  - {k}: {v}")
        return "\n".join(lines)


def _local_skip_check(content: str, known_names: set) -> bool:
    names_in_text = set(re.findall(r"[\u4e00-\u9fff]{2,4}(?=[说道想笑叹看问答喊叫])", content[:5000]))
    new_names = names_in_text - known_names
    setting_keywords = {
        "世界",
        "魔法",
        "功法",
        "境界",
        "种族",
        "国度",
        "势力",
        "宗门",
        "秘境",
        "血脉",
        "神器",
        "阵法",
        "丹药",
        "灵石",
        "大陆",
        "帝国",
    }
    has_new_setting = any(k in content for k in setting_keywords)
    if len(new_names) >= 2 or has_new_setting:
        return False
    return len(new_names) == 0


def _build_existing_cards(kb) -> str:
    """Build LLM-friendly knowledge cards including entities, relations, and foreshadows.

    Uses GraphStore.to_llm_context() when available for richer formatting,
    falls back to basic entity-only format otherwise.
    """
    # Try the richer to_llm_context() first (includes relations + foreshadows)
    if hasattr(kb, "to_llm_context"):
        ctx = kb.to_llm_context()
        header = (
            "(以下实体列表是该项目的唯一权威名单。列表中的实体（含别名）已存在于知识库，"
            "禁止作为 new_entities 重复添加；如需修改，请放到 updates 列表。同一批次内也禁止用"
            "多个略有差别的名字创建同一个角色——必须用同一个名字。)\n"
        )
        return header + ctx

    # Fallback: basic entity-only format
    entities = kb.list_entities()
    if not entities:
        return ""
    lines = []
    for e in entities:
        aliases = f"（{', '.join(e.aliases)}）" if e.aliases else ""
        lines.append(f"### [{e.type}] {e.name}{aliases}")
        for k, v in e.data.items():
            if v:
                lines.append(f"  - {k}: {v}")
    header = (
        "(以下实体列表是该项目的唯一权威名单。列表中的实体（含别名）已存在于知识库，"
        "禁止作为 new_entities 重复添加；如需修改，请放到 updates 列表。同一批次内也禁止用"
        "多个略有差别的名字创建同一个角色——必须用同一个名字。)\n"
    )
    return header + "\n".join(lines)


def _parse_progressive_result(response: str) -> dict:
    j = extract_json_from_response(response)
    try:
        return json.loads(j.strip())
    except json.JSONDecodeError:
        return {
            "new_entities": [],
            "updates": [],
            "relations": [],
            "spatial_relations": [],
            "foreshadows": [],
            "timeline_events": [],
        }


def _apply_progressive_result_batch(result: dict, kb, book_id: str) -> tuple[int, int, int, int]:
    import uuid

    from core.knowledge import Foreshadow, Relation, RelationType

    new_count = 0
    update_count = 0
    operations = []

    # ── Batch-internal dedupe pools ──
    # Within one LLM response, the model may emit the same entity twice (under
    # slightly different names, or both as new_entity and as updates entry).
    # Track what we've already scheduled so we merge instead of creating dupes
    # at the database layer (which is what makes the agent "see" phantom dupes
    # on the NEXT extraction).
    pending_by_name: dict[str, dict] = {}  # lower(name/alias) -> {"op_idx": int, "name": str}
    pending_id_to_idx: dict[str, int] = {}  # entity.id -> operations index (for updates)

    def _register_pending(names: list[str], op_idx: int, primary: str):
        """Mark an already-scheduled entity so later same-batch hits merge into it."""
        pending_by_name[primary.lower()] = {"op_idx": op_idx, "name": primary}
        for n in names:
            if not n:
                continue
            pending_by_name[n.lower()] = {"op_idx": op_idx, "name": n}

    def _lookup_pending(name: str):
        hit = pending_by_name.get(name.lower())
        if not hit:
            return None, None
        return hit["op_idx"], hit["name"]

    def _merge_into_operation(op_idx: int, extra_data: dict, extra_aliases: list[str] | None = None):
        op = operations[op_idx]
        if op["type"] == "update_entity":
            for k, v in extra_data.items():
                if v:
                    op["data"][k] = v
        elif op["type"] == "add_entity":
            entity = op["entity"]
            entity.data = {**entity.data, **{k: v for k, v in extra_data.items() if v}}
            if extra_aliases:
                existing = set(entity.aliases)
                for a in extra_aliases:
                    if a and a != entity.name and a not in existing:
                        entity.aliases.append(a)
                        existing.add(a)

    # ── Process new_entities ──
    for e in result.get("new_entities", []):
        etype_str = e.get("type", "character")
        name = e.get("name", "")
        aliases = e.get("aliases", []) if isinstance(e.get("aliases", []), list) else []
        data = _coerce_to_dict(e.get("data", {}))
        if not name:
            continue

        # 1. Same-batch hit → merge (avoid creating two "Neil"s in one extraction)
        pending_idx, _ = _lookup_pending(name)
        if pending_idx is None:
            for a in aliases:
                pending_idx, _ = _lookup_pending(a)
                if pending_idx is not None:
                    break

        if pending_idx is not None:
            _merge_into_operation(pending_idx, data, aliases)
            # Re-register every name/alias from this entity as pointing to the
            # same batch entry, so any further duplicates (by alias or by name)
            # in later iterations still merge cleanly.
            primary = pending_by_name.get(name.lower(), {}).get("name")
            if not primary:
                for k, v in pending_by_name.items():
                    if v["op_idx"] == pending_idx:
                        primary = v["name"]
                        break
            primary = primary or name
            for a in [name] + aliases:
                if a:
                    pending_by_name[a.lower()] = {"op_idx": pending_idx, "name": primary}
            # If the pending entry is an "add_entity", fold the new aliases in
            # so the merged record has a unified alias set by the time we flush.
            if operations[pending_idx]["type"] == "add_entity":
                ent = operations[pending_idx]["entity"]
                for a in aliases:
                    if a and a != ent.name and a not in ent.aliases:
                        ent.aliases.append(a)
            update_count += 1
            continue

        # 2. Database hit → convert to update
        existing = kb.get_entity_by_name(name)
        if existing:
            merged = {**existing.data, **data}
            op_idx = len(operations)
            operations.append({"type": "update_entity", "id": existing.id, "data": merged})
            _register_pending([name] + aliases, op_idx, name)
            pending_id_to_idx[existing.id] = op_idx
            update_count += 1
            continue

        # 3. Truly new
        entity = Entity(
            id=str(uuid.uuid4())[:8],
            type=etype_str,
            name=name,
            aliases=[a for a in aliases if a and a != name],
            data=data,
        )
        op_idx = len(operations)
        operations.append({"type": "add_entity", "entity": entity})
        _register_pending([name] + aliases, op_idx, name)
        new_count += 1

    # ── Process updates (LLM says "update existing entity X") ──
    for u in result.get("updates", []):
        name = u.get("name", "")
        add_data = _coerce_to_dict(u.get("add", {}))
        mod_data = _coerce_to_dict(u.get("modify", {}))
        if not name:
            continue
        combined = {}
        for k, v in {**add_data, **mod_data}.items():
            if v:
                combined[k] = v

        # Same-batch merge first
        pending_idx, _ = _lookup_pending(name)
        if pending_idx is not None:
            _merge_into_operation(pending_idx, combined)
            update_count += 1
            continue

        existing = kb.get_entity_by_name(name)
        if not existing:
            continue

        # Dedupe if we already have an update operation for this id in this batch
        if existing.id in pending_id_to_idx:
            _merge_into_operation(pending_id_to_idx[existing.id], combined)
            update_count += 1
            continue

        merged = dict(existing.data)
        for k, v in combined.items():
            merged[k] = v
        conflicts = u.get("conflicts", [])
        if conflicts:
            old_conflicts = merged.get("_conflicts", [])
            if isinstance(old_conflicts, str):
                old_conflicts = [old_conflicts]
            merged["_conflicts"] = old_conflicts + conflicts

        op_idx = len(operations)
        operations.append({"type": "update_entity", "id": existing.id, "data": merged})
        pending_id_to_idx[existing.id] = op_idx
        _register_pending([name], op_idx, name)
        update_count += 1

    if operations:
        kb.batch_write(operations)

    all_entities = kb.list_entities()
    name_to_id = {}
    for e in all_entities:
        name_to_id[e.name] = e.id
        name_to_id[e.name.lower()] = e.id
        for alias in e.aliases:
            name_to_id[alias] = e.id
            name_to_id[alias.lower()] = e.id

    relations_to_add = []
    for r in result.get("relations", []):
        raw_type = r.get("type", "")
        try:
            rtype = RelationType(raw_type.lower())
        except (ValueError, KeyError):
            continue
        from_name = r.get("from", "")
        to_name = r.get("to", "")
        from_id = name_to_id.get(from_name) or name_to_id.get(from_name.lower()) or from_name
        to_id = name_to_id.get(to_name) or name_to_id.get(to_name.lower()) or to_name
        relations_to_add.append(
            Relation(
                id=str(uuid.uuid4())[:8],
                from_entity=from_id,
                to_entity=to_id,
                type=rtype,
                data={},
            )
        )

    if relations_to_add:
        kb.batch_add_relations(relations_to_add)

    # ── Process spatial_relations (location → location) ──
    spatial_added = 0
    for sr in result.get("spatial_relations", []):
        raw_type = sr.get("type", "located_in")
        try:
            srtype = RelationType(raw_type.lower())
        except (ValueError, KeyError):
            srtype = RelationType.LOCATED_IN
        from_name = sr.get("from", "")
        to_name = sr.get("to", "")
        from_id = name_to_id.get(from_name) or name_to_id.get(from_name.lower())
        to_id = name_to_id.get(to_name) or name_to_id.get(to_name.lower())
        if from_id and to_id and from_id != to_id:
            kb.add_relation(
                Relation(
                    id=str(uuid.uuid4())[:8],
                    from_entity=from_id,
                    to_entity=to_id,
                    type=srtype,
                    data={"label": sr.get("label", "")},
                )
            )
            spatial_added += 1

    # ── Auto-complete transitive spatial containment ──
    # If A LOCATED_IN B, B LOCATED_IN C → add A LOCATED_IN C
    if spatial_added > 0 and hasattr(kb, "_run"):
        try:
            # First: fix LOCATED_IN direction errors by removing cycles
            # If A LOCATED_IN B and B LOCATED_IN A, keep only the correct direction.
            # Heuristic: the entity with the longer name is likely the child (more specific).
            # Also check parent_location data field for authoritative direction.
            kb._run(
                """
                MATCH (a:Entity:Location {project_id: $pid})-[r1:LOCATED_IN]->(b:Entity:Location {project_id: $pid})-[r2:LOCATED_IN]->(a)
                WHERE a.id < b.id
                WITH a, b, r1, r2,
                    CASE
                        WHEN a.data CONTAINS b.name THEN 'a_is_child'
                        WHEN b.data CONTAINS a.name THEN 'b_is_child'
                        WHEN size(a.name) > size(b.name) THEN 'a_is_child'
                        ELSE 'b_is_child'
                    END AS correct_direction
                FOREACH (_ IN CASE WHEN correct_direction = 'a_is_child' THEN [1] ELSE [] END |
                    DELETE r2
                )
                FOREACH (_ IN CASE WHEN correct_direction = 'b_is_child' THEN [1] ELSE [] END |
                    DELETE r1
                )
            """,
                {"pid": kb.project_id},
            )
            # Then: transitive closure
            kb._run(
                """
                MATCH (a:Entity:Location {project_id: $pid})-[:LOCATED_IN]->(b:Entity:Location {project_id: $pid})-[:LOCATED_IN]->(c:Entity:Location {project_id: $pid})
                WHERE a.id <> c.id AND NOT (a)-[:LOCATED_IN]->(c)
                MERGE (a)-[:LOCATED_IN]->(c)
            """,
                {"pid": kb.project_id},
            )
        except Exception:
            pass

    foreshadows_to_add = []
    for f in result.get("foreshadows", []):
        resolve_ch = f.get("resolve_chapter", "")
        fs = Foreshadow(
            id=str(uuid.uuid4())[:8],
            text=f.get("text", ""),
            hint=f.get("hint", ""),
            expected_resolution=f.get("expected_resolution", ""),
            plant_chapter=f.get("plant_chapter", ""),
            confidence=f.get("confidence", "high"),
            resolve_keywords=f.get("resolve_keywords", []) if isinstance(f.get("resolve_keywords", []), list) else [],
        )
        if resolve_ch:
            fs.resolve_chapter = resolve_ch
            fs.status = "resolved"
            fs.resolved = True
            fs.resolution_text = f.get("resolution_text", f.get("expected_resolution", ""))
        foreshadows_to_add.append(fs)

    if foreshadows_to_add:
        kb.batch_add_foreshadows(foreshadows_to_add)

    return new_count, update_count, len(relations_to_add), len(foreshadows_to_add)


async def _should_skip_chapter(loop, content: str, existing_cards: str, title: str) -> bool:
    from core.llm_client import MODELS, get_client

    cards_brief = existing_cards[:3000]
    text_brief = content[:4000]

    prompt = f"## 已有角色卡（摘要）\n{cards_brief}\n\n## 本章内容: {title}\n{text_brief}\n\n本章是否有需要更新卡片的新信息？只回答 YES 或 NO:"

    def _call():
        client = get_client()
        r = client.chat.completions.create(
            model=MODELS["flash"],
            messages=[
                {"role": "system", "content": SKIP_CHECK_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=5,
        )
        return r.choices[0].message.content or ""

    response = await loop.run_in_executor(ai_executor, _call)
    answer = response.strip().upper()
    return "NO" in answer and "YES" not in answer


async def _validate_consistency(loop, kb, book_id: str) -> str:

    # Phase 1: Cypher deterministic checks
    cypher_result = kb.check_consistency()
    lines = []
    contradictions = cypher_result.get("contradictions", [])

    if contradictions:
        lines.append(f"🔍 图规则检测到 {len(contradictions)} 个确定性矛盾:")
        for c in contradictions:
            sev = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(c.get("severity", "low"), "⚪")
            lines.append(f"  {sev} [{c['type']}] {c['description']}")
    else:
        lines.append("✅ 图规则检查未发现矛盾。")

    # Phase 2: LLM semantic check (only for unresolved issues)
    cards = _build_existing_cards(kb)
    if cards and len(cards) >= 100:
        llm_prompt = (
            f"## 全部角色/设定卡片\n{cards[: config.storage.max_extraction_chars]}\n\n"
            f"## 图规则已检测到 {len(contradictions)} 个矛盾（已列出，忽略即可）\n"
            f"请额外审核卡片之间的语义矛盾，如性格与行为不一致、设定逻辑漏洞等。输出JSON:"
        )
        try:
            response = await loop.run_in_executor(
                ai_executor, llm_chat, llm_prompt, VALIDATION_SYSTEM, 0.1, "extraction"
            )
            j = response.strip()
            if j.startswith("```json"):
                j = j[7:]
            if j.startswith("```"):
                j = j[3:]
            if j.endswith("```"):
                j = j[:-3]
            data = json.loads(j.strip())
            semantic_issues = data.get("issues", [])
            semantic_summary = data.get("summary", "")
            if semantic_issues:
                lines.append(f"\n🔎 LLM语义检查发现 {len(semantic_issues)} 个问题:")
                for iss in semantic_issues[:8]:
                    entity = iss.get("entity", "")
                    typ = iss.get("type", "")
                    desc = iss.get("description", "")
                    lines.append(f"  ⚠ [{entity}] {typ}: {desc}")
                    if iss.get("suggestion"):
                        lines.append(f"    → {iss['suggestion']}")
            if semantic_summary:
                lines.append(f"\n总评: {semantic_summary}")
        except Exception as e:
            lines.append(f"\n（LLM语义检查跳过: {str(e)[:40]}）")

    return "\n".join(lines)


def _call_edit_llm(llm_chat, prompt, system):
    from openai import APIError

    try:
        result = llm_chat(prompt, system=system, temperature=0.3, task="writing")
    except APIError as e:
        body = str(e.body or "").lower()
        if "content" in body or "filter" in body or "sensitive" in body or "policy" in body:
            return {"blocked_reason": f"API审查: {str(e.body)[:60]}", "content": ""}
        raise
    except Exception as e:
        err = str(e).lower()
        if "content" in err and ("filter" in err or "policy" in err):
            return {"blocked_reason": f"审查拦截: {str(e)[:60]}", "content": ""}
        raise

    if not result:
        return {"blocked_reason": "空响应", "content": ""}

    refusal_patterns = ["我无法", "我不能", "抱歉，我无法", "作为AI", "违反", "不适合"]
    first_line = result.strip()[:50]
    if any(p in first_line for p in refusal_patterns):
        return {"blocked_reason": f"模型拒绝: {first_line[:40]}", "content": ""}

    return result


def _parse_chapter_range(range_str: str, total: int) -> list[int]:
    s = range_str.strip().lower()
    if s == "all" or s == "全部":
        return list(range(total))

    s = s.replace("#", "").replace("（", "(").replace("）", ")")

    if "-" in s and "," not in s:
        parts = s.split("-")
        try:
            start = int(parts[0].strip()) - 1
            end = int(parts[1].strip()) - 1
            return [i for i in range(start, end + 1) if 0 <= i < total]
        except (ValueError, IndexError):
            return []

    if "," in s:
        indices = []
        for part in s.split(","):
            try:
                idx = int(part.strip()) - 1
                if 0 <= idx < total:
                    indices.append(idx)
            except ValueError:
                pass
        return indices

    try:
        idx = int(s) - 1
        if 0 <= idx < total:
            return [idx]
    except ValueError:
        pass

    return []
