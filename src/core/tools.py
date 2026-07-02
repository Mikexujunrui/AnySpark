# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from .token_counter import _get_encoder, count_tokens
from .tool_meta import (
    TOOL_META,
)

logger = logging.getLogger(__name__)

MAX_TOOL_OUTPUT_CHARS = 200000
MAX_TOOL_OUTPUT_TOKENS = 80000
DOOM_LOOP_THRESHOLD = 3


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict = field(default_factory=dict)
    handler: Callable = None
    dangerous: bool = False
    # Behavioural metadata — single source of truth consulted by the agent loop
    # instead of scattered tool-name sets. Defaults are False; special tools are
    # annotated via TOOL_META at the bottom of this module.
    streaming: bool = False        # reports progress via queue, not a single return
    mutates_kb: bool = False       # irreversible knowledge-graph changes
    touches_chapter: bool = False  # creates/edits/deletes chapters → refresh UI
    context_aware: bool = False     # accepts an _available_tokens hint

    def to_llm(self) -> dict:
        props = {}
        required = []
        for k, v in self.parameters.items():
            if isinstance(v, dict):
                is_required = v.get("required", True)
                prop = {pk: pv for pk, pv in v.items() if pk != "required"}
                props[k] = prop
                if is_required:
                    required.append(k)
            else:
                props[k] = {"type": "string", "description": str(v)}
                required.append(k)
        schema = {
            "type": "object",
            "properties": props,
        }
        if required:
            schema["required"] = required
        return {
            "name": self.name,
            "description": self.description,
            "parameters": schema,
        }


def validate_tool_input(tool: Tool, args: dict) -> tuple[dict, list[str]]:
    errors = []
    validated = {}
    props = tool.parameters

    for key, schema in props.items():
        value = args.get(key)
        if isinstance(schema, dict):
            expected_type = schema.get("type", "string")
            is_required = schema.get("required", True)
            if value is None or (isinstance(value, str) and not value.strip()):
                if is_required and key in (tool.to_llm()["parameters"].get("required", [])):
                    errors.append(f"Missing required parameter: {key}")
                continue
            if expected_type == "string" and not isinstance(value, str):
                validated[key] = str(value)
            elif expected_type == "boolean":
                if isinstance(value, bool):
                    validated[key] = value
                elif isinstance(value, str):
                    if value.lower() in ("true", "1", "yes"):
                        validated[key] = True
                    elif value.lower() in ("false", "0", "no"):
                        validated[key] = False
                    else:
                        errors.append(f"Parameter {key} must be a boolean, got '{value}'")
                elif isinstance(value, (int, float)):
                    validated[key] = bool(value)
                else:
                    errors.append(f"Parameter {key} must be a boolean")
            elif expected_type == "number" and not isinstance(value, (int, float)):
                try:
                    validated[key] = float(value)
                except (ValueError, TypeError):
                    errors.append(f"Parameter {key} must be a number, got {type(value).__name__}")
                    continue
            elif expected_type == "integer" and not isinstance(value, int):
                try:
                    validated[key] = int(value)
                except (ValueError, TypeError):
                    errors.append(f"Parameter {key} must be an integer")
                    continue
            elif expected_type == "array" and not isinstance(value, list):
                if isinstance(value, str):
                    try:
                        validated[key] = json.loads(value)
                    except json.JSONDecodeError:
                        validated[key] = [value]
                else:
                    errors.append(f"Parameter {key} must be an array")
                    continue
            else:
                # Check enum constraint if present
                enum_values = schema.get("enum")
                if enum_values and value not in enum_values:
                    errors.append(f"Parameter {key} must be one of {enum_values}, got '{value}'")
                    continue
                validated[key] = value
        else:
            if value is not None:
                validated[key] = value

    # Reject extras that are not in the schema (prevent injection of internal fields)
    for key in args:
        if key not in props and key.startswith("_"):
            errors.append(f"Unknown parameter with internal prefix: {key}")
            continue
        if key not in validated and key not in props:
            continue
    for key, value in args.items():
        if key not in validated and key in props:
            continue
        if key not in props:
            validated[key] = value

    return validated, errors


def truncate_tool_output(output: str, max_chars: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    if not output:
        return output
    tokens = count_tokens(output)
    if len(output) <= max_chars and tokens <= MAX_TOOL_OUTPUT_TOKENS:
        return output

    # Truncate by the more restrictive limit
    total_chars = len(output)
    if tokens > MAX_TOOL_OUTPUT_TOKENS:
        # Token-based truncation: encode → slice → decode
        encoder = _get_encoder()
        encoded = encoder.encode(output)
        truncated = encoder.decode(encoded[:MAX_TOOL_OUTPUT_TOKENS])
    else:
        truncated = output[:max_chars]
    return (
        f"{truncated}\n\n"
        f"[输出已截断: 原始 {total_chars} 字符 / {tokens} tokens。"
        f"如需查看完整内容，请使用 read_document 工具指定 offset/limit 分段读取]"
    )


class DoomLoopDetector:
    def __init__(self, threshold: int = DOOM_LOOP_THRESHOLD):
        self._history: list[str] = []
        self._tool_names: list[str] = []
        self._threshold = threshold
        # Same-tool consecutive streak: only flag if the *exact same tool* is
        # called many times in a row WITHOUT interleaving other tools.
        # Legitimate batch operations (e.g. update_entity x10) are allowed
        # as long as args differ, but if the model calls one tool 12+ times
        # straight it's likely stuck even if args vary slightly.
        self._consecutive_same_tool_max = 25  # 提升阈值以支持批量大纲/实体操作

    def record_call(self, tool_name: str, arguments: str) -> bool:
        sig = f"{tool_name}:{arguments}"
        self._history.append(sig)
        self._tool_names.append(tool_name)

        # Pattern 1: exact same call repeated N times in a row
        if len(self._history) >= self._threshold:
            recent = self._history[-self._threshold:]
            if len(set(recent)) == 1:
                logger.warning(f"Doom loop detected: {tool_name} called {self._threshold} times with same args")
                return True

        # Pattern 2: same tool called consecutively without any other tool in between.
        # Only triggers when the model is truly stuck on one tool (12+ straight calls).
        # Legitimate batch ops like update_entity×8 won't trigger (< 12).
        if len(self._tool_names) >= self._consecutive_same_tool_max:
            tail = self._tool_names[-self._consecutive_same_tool_max:]
            if len(set(tail)) == 1:
                logger.warning(
                    f"Doom loop detected: {tool_name} called {self._consecutive_same_tool_max} "
                    f"times consecutively (no other tool interleaved)"
                )
                return True

        return False

    def reset(self):
        self._history.clear()
        self._tool_names.clear()


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def list(self, exclude_dangerous: bool = False) -> list[dict]:
        tools = self._tools.values()
        if exclude_dangerous:
            tools = [t for t in tools if not t.dangerous]
        return [t.to_llm() for t in tools]

    def list_names(self) -> list[str]:
        return list(self._tools.keys())

    def get(self, name: str) -> Tool | None:
        """Look up a tool by name, with fuzzy fallback for casing/separator
        mismatches (e.g. ``Write_Chapter`` → ``write_chapter``,
        ``search-knowledge`` → ``search_knowledge``).

        Strategy: exact → lowercase → normalized (``-``→``_``) → prefix."""
        tool = self._tools.get(name)
        if tool:
            return tool
        # Lowercase fallback
        lower = name.lower()
        for key, t in self._tools.items():
            if key.lower() == lower:
                return t
        # Separator normalization (- → _)
        normalized = lower.replace("-", "_")
        for key, t in self._tools.items():
            if key.lower() == normalized:
                return t
        # Prefix match (first 8 chars, handles truncated names)
        if len(name) >= 8:
            prefix = name[:8].lower()
            for key, t in self._tools.items():
                if key.lower().startswith(prefix):
                    return t
        return None

    def resolve_name(self, name: str) -> str | None:
        """Return the canonical tool name for a possibly-misspelled input,
        or None if no match. Useful for logging/repair feedback."""
        tool = self.get(name)
        return tool.name if tool else None

    def filter_by_names(self, names: set[str], exclude: bool = False) -> list[dict]:
        if exclude:
            return [t.to_llm() for t in self._tools.values() if t.name not in names]
        return [t.to_llm() for t in self._tools.values() if t.name in names]

    def filter_by_permission(self, allowed: set[str] | None = None,
                             denied: set[str] | None = None) -> list[dict]:
        result = []
        for t in self._tools.values():
            if denied and t.name in denied:
                continue
            if allowed and t.name not in allowed:
                continue
            result.append(t.to_llm())
        return result


registry = ToolRegistry()

# Tool-set constants and behavioural metadata are now defined in tool_meta.py
# and imported above. Re-export them for backward compatibility.

registry.register(Tool(
    name="extract_knowledge",
    description="从文本中提取结构化知识（人物、地点、物品、技能/功法、组织、种族、概念、事件、关系、伏笔）。关系类型优选：ALLY/FAMILY/ROMANTIC/LOVES/ANTAGONIST/MENTOR_OF/KILLED/SAVED/OWNS/BELONGS_TO/CAUSES，避免用泛化的 KNOWS。",
    parameters={"text": {"type": "string", "description": "待提取的文本内容"}},
))

registry.register(Tool(
    name="extract_chapter",
    description="提取指定章节中的新知识，自动与已有知识库对比，仅补充新增和变化的内容。无需手动 read_chapter 再传文本——直接传入章节序号即可。适用于：写完一章后补充知识库、验证发现幻觉实体后补充新角色/地点/设定。",
    parameters={"chapter_id": {"type": "string", "description": "章节序号，如 #5 或 #E1（番外）"}},
))

registry.register(Tool(
    name="prepare_writing",
    description="一键写作准备：自动获取大纲、细纲、知识库搜索和图谱洞察，输出结构化报告和建议的 delegate_writing 调用。适用于写新章节前快速了解本章需要什么。",
    parameters={"chapter_index": {"type": "integer", "description": "章节序号（从1开始），如 5"}},
))

registry.register(Tool(
    name="finalize_chapter",
    description="写后一键闭环：自动验证章节（实体漂移/大纲合规/约束/伏笔），验证通过后补充知识库，并检查伏笔状态。适用于写完一章后的收尾操作。",
    parameters={"chapter_id": {"type": "string", "description": "章节序号，如 #5 或 #E1（番外）"}},
))

registry.register(Tool(
    name="store_chapter",
    description="将叙事文本存储为章节内容。适用于小说正文、章节草稿、番外。",
    parameters={
        "title": {"type": "string", "description": "章节标题"},
        "content": {"type": "string", "description": "章节正文"},
        "is_extra": {"type": "boolean", "description": "是否为番外（不计入正常章节序号）", "required": False},
        "chapter_index": {"type": "integer", "description": "章节序号（如第5章写5），用于去重更新已有章节", "required": False},
    },
))

registry.register(Tool(
    name="store_inspiration",
    description="存储灵感碎片/临时想法。⚠️ 仅用于短笔记。工作流→generate_workflow，参考资料→add_material，章节→write_chapter。",
    parameters={
        "content": {"type": "string", "description": "灵感内容"},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "标签", "required": False},
    },
))

registry.register(Tool(
    name="search_knowledge",
    description="检索当前书知识库中的实体和关系。如果搜索结果为空且本书有参考书，应主动用 search_reference 在参考书中查找。",
    parameters={"query": {"type": "string", "description": "搜索关键词"}},
))

registry.register(Tool(
    name="write_chapter",
    description="轻量写作工具：写大纲文本、补写过渡段落、修改小节细节、写番外片段等不需要严格控制上下文的场景。会加载全部知识库实体。⚠️ 正式写章节请用 delegate_writing，此工具仅用于辅助性轻量任务。",
    parameters={
        "instruction": {"type": "string", "description": "写作指令"},
        "mode": {"type": "string", "description": "strict=严格约束 suggest=建议模式", "required": False},
        "is_extra": {"type": "boolean", "description": "是否为番外（不计入正常章节序号）", "required": False},
        "chapter_title": {"type": "string", "description": "章节标题（不指定则自动生成）", "required": False},
        "chapter_index": {"type": "integer", "description": "章节序号（如第5章写5），用于去重更新已有章节", "required": False},
        "ref_chapters": {"type": "array", "items": {"type": "string"}, "description": "参考书章节ID列表（如['#1','#3']或['book_id:#2']），完整注入原著章节原文", "required": False},
    },
))

registry.register(Tool(
    name="ask_user",
    description="向用户提问。支持多个问题依次展示、单选/多选、自定义输入。仅当指令存在真正歧义且无法从上下文推断时使用。",
    parameters={
        "question": {"type": "string", "description": "向用户提出的问题（简单单问题场景）"},
        "options": {"type": "array", "items": {"type": "string"}, "description": "可选答案列表（简单单问题场景）", "required": False},
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
))

registry.register(Tool(
    name="list_chapters",
    description="列出当前书籍的所有章节（标题+字数+ID）。",
    parameters={},
))

registry.register(Tool(
    name="read_chapter",
    description="读取指定章节的完整内容。支持读取参考书章节。",
    parameters={
        "chapter_id": {"type": "string", "description": "章节序号（如 #1、#3）或完整ID"},
        "ref_book_id": {"type": "string", "description": "参考书ID，指定后从参考书读取章节而非当前书", "required": False},
    },
))

registry.register(Tool(
    name="delete_chapter",
    description="删除指定章节。不可恢复。",
    parameters={"chapter_id": {"type": "string", "description": "章节序号（如 #1）或完整ID"}},
    dangerous=True,
))

registry.register(Tool(
    name="delete_all_chapters",
    description="一次性删除当前书籍的所有章节。用户明确要求全部删除时使用。",
    parameters={},
    dangerous=True,
))

registry.register(Tool(
    name="import_chapters",
    description="读取上传的文档，自动按章节标题切割并创建章节记录。",
    parameters={
        "doc_id": {"type": "string", "description": "文档ID（从系统提示中的已上传文档列表获取）"},
    },
))

registry.register(Tool(
    name="read_document",
    description="读取用户上传的文档内容。可指定偏移量和长度分段读取。",
    parameters={
        "doc_id": {"type": "string", "description": "文档ID（留空列出所有文档）", "required": False},
        "offset": {"type": "integer", "description": "偏移量（字符数）", "required": False},
        "limit": {"type": "integer", "description": "读取长度", "required": False},
    },
))

registry.register(Tool(
    name="decompose_chapter",
    description="将章节拆解为结构化剧情链（场景+节拍+对话+情感弧线）。输出JSON并自动存储，可用于后续 rewrite_by_chain 逐节点复写。支持拆解参考书章节。",
    parameters={
        "chapter_text": {"type": "string", "description": "章节原文（与chapter_id二选一）", "required": False},
        "chapter_id": {"type": "string", "description": "章节序号（如 #1）或完整ID，自动读取章节内容", "required": False},
        "chapter_title": {"type": "string", "description": "章节标题", "required": False},
        "save": {"type": "boolean", "description": "是否存储剧情链（默认true）", "required": False},
        "ref_book_id": {"type": "string", "description": "参考书ID，指定后从参考书读取章节而非当前书", "required": False},
    },
))

registry.register(Tool(
    name="annotate_chain",
    description="修改剧情链中各节点的改写模式(edit_mode)和具体修改指令(edit_instructions)。用于高保真改写场景：将节点标记为 keep(原样保留)/tweak(微调)/rewrite(改写)。无参数时显示当前状态。preview=true时显示带原文摘要的提案摘要，供用户确认。",
    parameters={
        "chain_id": {"type": "string", "description": "剧情链ID，留空则使用最近一条链", "required": False},
        "preview": {"type": "boolean", "description": "预览模式：返回每个节点的原文摘要和改写建议，不修改剧情链。用于提案-确认流程。", "required": False},
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
))

registry.register(Tool(
    name="rewrite_by_chain",
    description="根据剧情链逐场景节点复写章节。每个节点独立生成文本并流式输出，最终拼接存储。需先通过 decompose_chapter 生成剧情链。",
    parameters={
        "chain_id": {"type": "string", "description": "剧情链ID（从 decompose_chapter 结果获取），留空则使用最近一条链", "required": False},
        "style_profile": {"type": "string", "description": "文风约束", "required": False},
        "target_words_per_node": {"type": "number", "description": "每个节点目标字数（默认300）", "required": False},
        "chapter_title": {"type": "string", "description": "输出章节标题", "required": False},
    },
))

registry.register(Tool(
    name="generate_outline",
    description="根据所有章节内容自动生成全书大纲。逐章概括情节要点、关键事件、出场角色，最后生成全书总纲。已有大纲会被覆盖。适用于'生成大纲''概括全文'类指令。",
    parameters={
        "chapters": {"type": "string", "description": "范围：'all' 或 '#1-#5'，默认全部", "required": False},
    },
))

registry.register(Tool(
    name="get_outline",
    description="获取当前书籍的大纲。不指定章节时返回全书总纲+所有章节概要。指定章节序号只返回该章大纲。",
    parameters={
        "chapter_index": {"type": "integer", "description": "章节序号（从1开始），留空返回全部", "required": False},
    },
))

registry.register(Tool(
    name="update_outline",
    description="手动修改大纲中某章的内容（概要、备注等），或修改全书总纲。番外条目用 is_extra=true。",
    parameters={
        "chapter_index": {"type": "integer", "description": "章节序号（从1开始），留空则修改全书总纲", "required": False},
        "synopsis": {"type": "string", "description": "章节概要", "required": False},
        "notes": {"type": "string", "description": "备注/规划", "required": False},
        "summary": {"type": "string", "description": "全书总纲（仅当不指定chapter_index时）", "required": False},
        "is_extra": {"type": "boolean", "description": "设为true则操作番外大纲条目（番外用 #E1 引用）", "required": False},
    },
))

registry.register(Tool(
    name="generate_timeline",
    description="从知识图谱读取已提取的时间线事件（由知识提取 extract_all_chapters 自动创建）。如果知识库中无数据，需先运行知识提取（/s 或 extract_all_chapters）。",
    parameters={},
))

registry.register(Tool(
    name="get_timeline",
    description="获取当前时间线（所有轨道和事件）。",
    parameters={},
))

registry.register(Tool(
    name="add_timeline_event",
    description="手动添加一个时间线事件。可指定所属轨道，不指定则为散点事件。",
    parameters={
        "label": {"type": "string", "description": "事件名称"},
        "description": {"type": "string", "description": "事件描述", "required": False},
        "track_id": {"type": "string", "description": "轨道ID（'main'=主线，留空=散点）", "required": False},
        "order": {"type": "integer", "description": "在轨道中的顺序位置", "required": False},
        "chapter_ref": {"type": "string", "description": "关联章节（如 #3）", "required": False},
        "characters": {"type": "array", "items": {"type": "string"}, "description": "涉及角色", "required": False},
    },
))

registry.register(Tool(
    name="add_entity",
    description="手动向知识图谱添加一个实体（角色、地点、物品、组织、概念、事件等）。如果实体已存在则更新其属性。",
    parameters={
        "name": {"type": "string", "description": "实体名称（如 '哈利·波特'）"},
        "type": {"type": "string", "description": "实体类型: character/location/item/organization/concept/event/skill/race", "required": False},
        "aliases": {"type": "array", "items": {"type": "string"}, "description": "别名列表", "required": False},
        "data": {"type": "object", "description": "属性数据（如 {基本: {name:'...', age:'18'}, 外貌: {appearance:'...'}}）", "required": False},
    },
))

registry.register(Tool(
    name="add_relation",
    description="手动向知识图谱添加一条关系边。from和to可以是实体名或实体ID，支持所有关系类型。",
    parameters={
        "from": {"type": "string", "description": "起始实体名或ID"},
        "to": {"type": "string", "description": "目标实体名或ID"},
        "type": {"type": "string", "description": "关系类型: knows/ally/antagonist/family/romantic/master_of/mentor_of/killed/saved/loves/owns/located_at/belongs_to/causes/participates_in"},
    },
))

registry.register(Tool(
    name="generate_worldbuilding",
    description="分析已有章节和知识库，自动识别该小说的世界观维度（如魔法体系、势力分布、社会规则等），生成分类和条目。每个条目以人类可读的段落形式呈现，注重设定的影响和作用而非角色性格。支持嵌套分类和@交叉引用。",
    parameters={},
))

registry.register(Tool(
    name="get_worldbuilding",
    description="查看当前小说的世界观设定（所有分类和条目）。",
    parameters={},
))

registry.register(Tool(
    name="add_worldbuilding_entry",
    description="向世界观的指定分类下添加一个条目。内容中可用 @条目名 交叉引用其他条目。",
    parameters={
        "category": {"type": "string", "description": "分类名称（如已存在则添加到该分类，不存在则自动创建）"},
        "title": {"type": "string", "description": "条目标题"},
        "content": {"type": "string", "description": "条目正文（人类可读的段落描述，可用@引用其他条目）"},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "标签", "required": False},
        "chapter_refs": {"type": "array", "items": {"type": "string"}, "description": "相关章节如#1,#3", "required": False},
    },
))

registry.register(Tool(
    name="delete_entity",
    description="删除知识库中的一个实体（角色/地点/物品/组织/概念/事件）。不可恢复。",
    parameters={
        "entity_id": {"type": "string", "description": "实体ID（从 search_knowledge 获取）或实体名称"},
    },
    dangerous=True,
))

registry.register(Tool(
    name="update_entity",
    description="修改知识库中某个实体的属性和描述。传入 entity_id 和要修改的字段即可。",
    parameters={
        "entity_id": {"type": "string", "description": "实体ID或名称"},
        "data": {"type": "object", "description": "要更新/新增的字段键值对，如 {\"年龄\": \"25岁\", \"能力\": \"控火\"}"},
    },
))

registry.register(Tool(
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
        "is_current": {"type": "boolean", "description": "是否为当前写作阶段(自动取消同角色其他阶段的 is_current)。新建下一阶段时建议设为 true。默认 true", "required": False},
        "data": {
            "type": "object",
            "description": (
                "该阶段的角色完整属性(与 entity.data 同字段,但是该阶段的状态)。"
                "建议包含:appearance(外貌变化), personality(性格状态), "
                "abilities(能力), status(当前状态), motivation(本阶段驱动力), "
                "relationships(关系状态摘要), growth_note(从上一阶段到本阶段的变化说明)"
            ),
        },
        "description": {"type": "string", "description": "阶段叙事描述:一句话概括角色在本阶段的状态", "required": False},
    },
    mutates_kb=True,
))

registry.register(Tool(
    name="delete_worldbuilding_entry",
    description="删除世界观中的某个条目。",
    parameters={
        "entry_id": {"type": "string", "description": "条目ID，从 get_worldbuilding 获取"},
    },
    dangerous=True,
))

registry.register(Tool(
    name="delete_timeline_event",
    description="删除时间线上的一个事件。",
    parameters={
        "event_id": {"type": "string", "description": "事件ID，从 get_timeline 获取"},
    },
    dangerous=True,
))

registry.register(Tool(
    name="delete_foreshadow",
    description="删除一个伏笔。",
    parameters={
        "foreshadow_id": {"type": "string", "description": "伏笔ID，从 search_knowledge 查询获得"},
    },
    dangerous=True,
))

registry.register(Tool(
    name="generate_location_map",
    description="从知识图谱读取已提取的地点实体和关系（由知识提取 extract_all_chapters 自动创建）。如果知识库中无数据，需先运行知识提取（/s 或 extract_all_chapters）。",
    parameters={},
))

registry.register(Tool(
    name="generate_detailed_outline",
    description="生成细纲：逐章提取纯剧情骨架，去掉所有描写、对话、心理活动，只保留'谁做了什么→导致什么结果'的事件链。适用于'生成细纲''提取剧情线''去水分大纲'类指令。",
    parameters={
        "chapters": {"type": "string", "description": "范围：'all' 或 '#1-#5'，默认全部", "required": False},
    },
))

registry.register(Tool(
    name="get_detailed_outline",
    description="查看已生成的细纲（纯剧情骨架）。",
    parameters={},
))

registry.register(Tool(
    name="update_detailed_outline",
    description="直接写入或修改某章的细纲（剧情事件链和叙事功能）。番外用 is_extra=true。可用于手动规划剧情，不要求已有章节正文。",
    parameters={
        "chapter_index": {"type": "integer", "description": "章节序号（从1开始）", "required": True},
        "title": {"type": "string", "description": "章节标题", "required": False},
        "plot_chain": {"type": "array", "description": "事件链数组，如 ['事件1: 谁→做了什么→结果', ...]", "required": False},
        "chapter_function": {"type": "string", "description": "本章叙事功能（如'引入反派'、'主角成长转折'）", "required": False},
        "is_extra": {"type": "boolean", "description": "设为true则操作番外细纲条目", "required": False},
    },
))

registry.register(Tool(
    name="extract_all_chapters",
    description="逐章渐进式提取知识（人物卡/地点/关系/伏笔）。按章节顺序处理：新角色建卡，已有角色对比更新，最后通读验证一致性。这是一个完整操作，调用后直接汇报结果即可，不需要额外调用 task 或 read_chapter。",
    parameters={},
    streaming=True,
))

registry.register(Tool(
    name="edit_chapter",
    description="修改指定章节内容，自动创建新版本。旧版本保留可回退。⚠️ 必须调用此工具才能修改，仅文字描述无效。适用于完整重写整章。若只需修改某段落或句子，请优先使用 patch_chapter。",
    parameters={
        "chapter_id": {"type": "string", "description": "章节序号（如 #1）或完整ID"},
        "content": {"type": "string", "description": "新的章节内容"},
        "message": {"type": "string", "description": "版本说明（类似 commit message）", "required": False},
        "title": {"type": "string", "description": "新标题（可选，不传则保持原标题）", "required": False},
    },
    dangerous=True,
))

registry.register(Tool(
    name="patch_chapter",
    description=(
        "局部编辑章节——精确替换/插入/删除指定段落或句子，无需重写整章。自动创建新版本，旧版本保留可回退。"
        "⚠️ 必须调用此工具才能修改，仅文字描述无效。"
        "适用场景：修改某段对话、替换角色名、删除某句、在某段后插入新段落等小改动。"
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
                "{\"op\": \"replace\", \"segment_id\": 2, \"confirm\": \"段内片段\", \"replace\": \"替换为\"} 或 "
                "{\"op\": \"replace\", \"find\": \"原文片段\", \"replace\": \"替换为\"} 或 "
                "{\"op\": \"insert_after\", \"segment_id\": 3, \"confirm\": \"段内片段\", \"text\": \"插入内容\"} 或 "
                "{\"op\": \"delete\", \"segment_id\": 1, \"confirm\": \"要删除的文本\"} 或 "
                "{\"op\": \"append\", \"text\": \"追加内容\"}"
            ),
        },
        "message": {"type": "string", "description": "版本说明（如 '修改第3段对话'）", "required": False},
    },
    dangerous=True,
))

registry.register(Tool(
    name="chapter_history",
    description="查看章节的版本历史。返回所有版本的时间、说明、字数，标注当前版本。类似 git log。",
    parameters={
        "chapter_id": {"type": "string", "description": "章节序号（如 #1）或完整ID"},
    },
))

registry.register(Tool(
    name="revert_chapter",
    description="将章节回退到指定历史版本。类似 git checkout。不会删除其他版本。",
    parameters={
        "chapter_id": {"type": "string", "description": "章节序号（如 #1）或完整ID"},
        "version_id": {"type": "string", "description": "目标版本ID（从 chapter_history 获取）"},
    },
    dangerous=True,
))

registry.register(Tool(
    name="diff_chapters",
    description="对比章节的两个版本之间的差异。输出新增/删除/修改的段落摘要。",
    parameters={
        "chapter_id": {"type": "string", "description": "章节序号（如 #1）或完整ID"},
        "version_a": {"type": "string", "description": "版本A的ID（较旧版本）"},
        "version_b": {"type": "string", "description": "版本B的ID（较新版本，留空则用当前版本）", "required": False},
    },
))

registry.register(Tool(
    name="transform_book",
    description=(
        "统一全书变换工具：用自然语言指令对全书（或指定范围章节）执行批量变换。"
        "每章生成新版本可回滚。支持三种模式：\n"
        "  patch（默认）：局部修改，保持大部分内容不变，只调整指令涉及的部分；\n"
        "  rewrite：根据原文情节完全重写本章，保持故事走向但用全新文字表达；\n"
        "  restyle：将指定文风应用到章节，保持情节不变只调整遣词造句。\n"
        "自动判断串行/并行执行模式（如'改名'→并行，'前后呼应'→串行）。"
    ),
    parameters={
        "instruction": {"type": "string", "description": "自然语言修改指令，如'把所有小姐改成姑娘'、'战争场面描写更详细'、'第一人称改为第三人称'"},
        "scope": {"type": "string", "description": "章节范围：'all' 或 '#1-#5' 或 '#1,#3,#7'，默认 'all'", "required": False},
        "mode": {"type": "string", "description": "变换模式：'patch'(局部修改) | 'rewrite'(完全重写) | 'restyle'(文风调整)。默认 patch", "required": False},
        "style_id": {"type": "string", "description": "文风ID/名称（mode=restyle时必填，从 list_styles 或 /api/styles 获取）", "required": False},
        "execution_mode": {"type": "string", "description": "执行模式：'auto'(自动判断) | 'serial'(串行) | 'parallel'(并行)。默认 auto", "required": False},
        "dry_run": {"type": "boolean", "description": "是否预览模式（不实际修改，只报告匹配数）。默认 false", "required": False},
    },
    dangerous=True,
))

registry.register(Tool(
    name="find_replace_book",
    description="全书查找替换：对全部（或指定范围）章节执行字面或正则查找替换。每章生成新版本可回滚。适用于改名、统一术语等精确替换场景。",
    parameters={
        "pattern": {"type": "string", "description": "要查找的文本或正则表达式"},
        "replacement": {"type": "string", "description": "替换文本（正则模式支持 $1 等反向引用）"},
        "scope": {"type": "string", "description": "章节范围：'all' 或 '#1-#5' 或 '#1,#3,#7'，默认 'all'", "required": False},
        "regex": {"type": "boolean", "description": "是否使用正则模式。默认 false（字面替换）", "required": False},
        "dry_run": {"type": "boolean", "description": "是否预览模式（只统计匹配数不修改）。默认 false", "required": False},
        "message": {"type": "string", "description": "版本说明", "required": False},
    },
    dangerous=True,
))

registry.register(Tool(
    name="apply_directive_globally",
    description="按指令对全书章节执行批量修改（插入/替换/删除）。自动判断串行或并行执行。适用于大规模修改场景，如'统一主角名称''调整所有章节的对话风格'等。",
    parameters={
        "directive": {"type": "string", "description": "修改指令（自然语言描述要做什么）"},
        "scope": {"type": "string", "description": "章节范围：'all'（默认）或 '#1-#5' 或 '#1,#3,#7'", "required": False},
        "execution_mode": {"type": "string", "description": "执行模式：'auto'(自动判断) | 'serial'(串行) | 'parallel'(并行)。默认 auto", "required": False},
        "dry_run": {"type": "boolean", "description": "是否预览模式（不实际修改，只报告匹配数）。默认 false", "required": False},
    },
    dangerous=True,
))

registry.register(Tool(
    name="transform_chapters_batch",
    description="批量重写指定章节：对选中的章节执行结构化重写，支持修改模式（rewrite）或补写模式（supplement）。",
    parameters={
        "chapter_ids": {"type": "string", "description": "章节范围：'all' 或 '#1-#5' 或 '#1,#3,#7'"},
        "instruction": {"type": "string", "description": "重写指令（自然语言描述）"},
        "mode": {"type": "string", "description": "模式：'rewrite'(重写) | 'supplement'(补写)。默认 rewrite", "required": False},
        "dry_run": {"type": "boolean", "description": "是否预览模式。默认 false", "required": False},
    },
    dangerous=True,
))

registry.register(Tool(
    name="restyle_book",
    description="调整全书文风：对指定范围章节按目标文风进行改写。",
    parameters={
        "style_id": {"type": "string", "description": "目标文风ID/名称（从 list_styles 或 /api/styles 获取）"},
        "scope": {"type": "string", "description": "章节范围：'all'（默认）或 '#1-#5'", "required": False},
        "dry_run": {"type": "boolean", "description": "是否预览模式。默认 false", "required": False},
    },
    dangerous=True,
))

registry.register(Tool(
    name="summarize_book",
    description="生成或刷新全书摘要：读取所有章节，生成结构化摘要（核心设定、主线剧情、角色列表、关键事件、未解伏笔），存入书籍元数据。长篇小说的摘要会注入 system prompt 作为长程上下文。建议每写完若干章调用一次。",
    parameters={},
))

registry.register(Tool(
    name="delete_version",
    description="删除章节的指定历史版本。不能删除当前版本（需先 revert 到其他版本）。至少保留一个版本。",
    parameters={
        "chapter_id": {"type": "string", "description": "章节序号（如 #1）或完整ID"},
        "version_id": {"type": "string", "description": "要删除的版本ID（从 chapter_history 获取）"},
    },
    dangerous=True,
))

registry.register(Tool(
    name="purge_chapter_history",
    description="清除章节的所有旧版本，只保留当前版本并重编为 v1。用于确认最终稿后清理历史。可指定单章或全部章节。",
    parameters={
        "chapter_id": {"type": "string", "description": "章节序号（如 #1）或 'all' 表示全部章节", "required": True},
    },
    dangerous=True,
))

registry.register(Tool(
    name="manage_volumes",
    description=(
        "分卷管理统一入口。action 参数:\n"
        "  list: 列出所有分卷、每卷的章节和故事主线\n"
        "  create: 创建新分卷\n"
        "  update: 修改分卷标题/故事主线/顺序\n"
        "  delete: 删除分卷（章节不删，仅解除分组）\n"
        "  move: 将章节移入指定分卷"
    ),
    parameters={
        "action": {"type": "string", "description": "操作: list/create/update/delete/move"},
        "volume_id": {"type": "string", "description": "分卷ID（update/delete/move时必填）", "required": False},
        "title": {"type": "string", "description": "分卷标题（create/update时可选）", "required": False},
        "story_line": {"type": "string", "description": "故事主线/大纲（create/update时可选）", "required": False},
        "order": {"type": "integer", "description": "排序号（update时可选）", "required": False},
        "chapter_id": {"type": "string", "description": "章节序号或ID（action=move时必填）", "required": False},
    },
    dangerous=True,
))

registry.register(Tool(
    name="list_volumes",
    description="列出当前书籍的所有分卷（名称、章节数、故事线）。",
    parameters={},
))

registry.register(Tool(
    name="count_words",
    description="统计字数：指定章节或全书的字数。",
    parameters={
        "chapter_id": {"type": "string", "description": "章节序号（如 #1），留空则统计全书", "required": False},
    },
))

registry.register(Tool(
    name="generate_volume_outlines",
    description="根据全书大纲自动划分分卷结构并填写每卷故事主线。无需参数，自动读取大纲分析并创建分卷。已有分卷会被保留并补充缺失的 storyLine。",
    parameters={},
))

registry.register(Tool(
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
        "action": {"type": "string", "description": "操作: generate/list/browse/subscribe/unsubscribe/delete/update"},
        "description": {"type": "string", "description": "需求描述（action=generate时必填）", "required": False},
        "workflow_id": {"type": "string", "description": "工作流ID（subscribe/unsubscribe/delete/update时必填）", "required": False},
        "name": {"type": "string", "description": "新名称（action=update时可选）", "required": False},
        "steps": {"type": "array", "items": {"type": "object"}, "description": "新步骤列表（action=update时可选）", "required": False},
    },
    dangerous=True,
))

registry.register(Tool(
    name="list_workflows",
    description="列出当前项目已订阅的工作流（名称、ID、步骤数、创建时间）。",
    parameters={},
))

registry.register(Tool(
    name="browse_workflows",
    description="浏览全局工作流池（包括未订阅的），用于发现可复用的工作流模板。",
    parameters={},
))

registry.register(Tool(
    name="execute_workflow",
    description="在会话内执行一个已订阅的工作流。按顺序执行每个步骤并返回结果。可通过 params 传入动态参数覆盖步骤静态配置。",
    parameters={
        "workflow_id": {"type": "string", "description": "工作流ID（从 list_workflows 获取）"},
        "params": {
            "type": "object",
            "description": "动态参数，合并到每个步骤的执行上下文中，优先级高于步骤静态 config",
            "required": False,
            "properties": {
                "ref_chapters": {"type": "array", "items": {"type": "string"}, "description": "参考书章节列表，如 ['#1','#3']，注入原著章节原文"},
                "chapter_title": {"type": "string", "description": "目标章节标题"},
                "instruction": {"type": "string", "description": "覆盖步骤的 writing instruction"},
            },
        },
    },
))

registry.register(Tool(
    name="manage_workflow_steps",
    description="工作流步骤管理：列出步骤配置或修改某个步骤的参数。action=list 查看所有步骤详情，action=update 修改指定步骤的配置。",
    parameters={
        "action": {"type": "string", "description": "操作: list(列出步骤) / update(修改步骤配置)"},
        "workflow_id": {"type": "string", "description": "工作流ID"},
        "step_index": {"type": "integer", "description": "步骤编号（从0开始，action=update时必填）", "required": False},
        "config": {"type": "object", "description": "新的配置参数，会与现有 config 合并（action=update时必填）", "required": False},
    },
))

registry.register(Tool(
    name="list_skills",
    description="列出所有可用技能（系统预设+用户自定义），支持按来源筛选。",
    parameters={
        "source": {"type": "string", "description": "过滤来源：'system'（系统预设）或 'user'（自定义），留空列出全部", "required": False},
    },
))

registry.register(Tool(
    name="manage_skills",
    description=(
        "技能管理统一入口。技能是预定义的工具调用序列，可通过触发器自动推荐。\n"
        "action 参数: list(列出) / create(创建) / update(修改) / delete(删除)"
    ),
    parameters={
        "action": {"type": "string", "description": "操作: list/create/update/delete"},
        "name": {"type": "string", "description": "技能名称（create/update/delete时必填）", "required": False},
        "description": {"type": "string", "description": "技能描述（create/update时可选）", "required": False},
        "triggers": {"type": "array", "items": {"type": "string"}, "description": "触发器列表（create/update时可选）", "required": False},
        "steps": {"type": "array", "items": {"type": "object"}, "description": "步骤列表 [{tool, label, params}]（create/update时可选）", "required": False},
        "source": {"type": "string", "description": "过滤来源: system/user（action=list时可选）", "required": False},
    },
    dangerous=True,
))

registry.register(Tool(
    name="set_style",
    description="设置当前写作风格，切换后 write_chapter/delegate_writing 将自动遵循新风格。不传 name 时根据 content 自动推荐并设置。查看当前风格用 manage_styles action=get。",
    parameters={
        "name": {"type": "string", "description": "风格名（从 manage_styles action=list 获取）。不传则根据 content 自动推荐", "required": False},
        "content": {"type": "string", "description": "场景描述或章节关键词（如'战斗''回忆''悬疑'），用于自动推荐风格。仅当不传 name 时使用", "required": False},
    },
))

registry.register(Tool(
    name="get_style",
    description="获取当前激活的写作风格详情。",
    parameters={},
))

registry.register(Tool(
    name="list_styles",
    description="列出所有可用的写作风格（系统预设+自定义），支持按来源筛选。",
    parameters={
        "source": {"type": "string", "description": "过滤来源：'system'（系统预设）或 'user'（自定义），留空列出全部", "required": False},
    },
))

registry.register(Tool(
    name="manage_styles",
    description="管理自定义写作风格：查看详情、添加、修改、删除。系统预设风格只读不可修改。",
    parameters={
        "action": {"type": "string", "description": "操作: list(列出所有) / get(查看详情) / add(添加自定义) / update(修改自定义) / delete(删除自定义)"},
        "name": {"type": "string", "description": "风格名称（get/add/update/delete时必填）", "required": False},
        "description": {"type": "string", "description": "风格描述（add/update时可选）", "required": False},
        "priority": {"type": "string", "description": "优先级: suggest/apply/strict（add/update时可选）", "required": False},
        "applies_to": {"type": "array", "items": {"type": "string"}, "description": "适用场景标签列表", "required": False},
        "slots": {"type": "array", "items": {"type": "object"}, "description": "提示槽列表 [{target, content}]", "required": False},
    },
))

registry.register(Tool(
    name="extract_style",
    description="从章节文本中提取并分析写作风格特征（句式、修辞、节奏、用词习惯等）。",
    parameters={
        "chapter_id": {"type": "string", "description": "章节序号（如 #1）或完整ID"},
    },
))

registry.register(Tool(
    name="reconstruct_chapter",
    description="根据剧情链和风格配置重新构建章节。先分解后重组，保留核心情节但优化表达。",
    parameters={
        "chapter_id": {"type": "string", "description": "章节序号（如 #1）或完整ID"},
        "style_profile": {"type": "string", "description": "文风约束（可选）", "required": False},
    },
    dangerous=True,
))

registry.register(Tool(
    name="compare_plot",
    description="对比两个文本的情节差异，识别新增、删除、修改的情节节点。",
    parameters={
        "text_a": {"type": "string", "description": "文本A"},
        "text_b": {"type": "string", "description": "文本B"},
    },
))

registry.register(Tool(
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
            "enum": ["research", "plan", "consistency", "reviewer",
                     "extract", "write", "edit", "general"],
            "description": "子 Agent 类型（只读型所有模式可用，读写型仅 Write 模式）",
        },
        "task_id": {"type": "string", "description": "恢复已有子任务会话的 ID（可选）", "required": False},
    },
))

registry.register(Tool(
    name="suggest_plot_directions",
    description="生成多个剧情走向选项供用户选择。基于当前章节、大纲和知识库，提出3-4种不同的剧情发展方向，以可视化卡片形式呈现给用户。用户可以选择一个方向、自定义方向或拒绝所有选项。适用于'接下来怎么写''剧情走向''给几个选择'类指令。",
    parameters={
        "instruction": {"type": "string", "description": "用户关于剧情方向的需求描述（如'主角接下来怎么办''第二幕高潮怎么设计'）"},
        "chapter_ref": {"type": "string", "description": "参考章节序号（如 #5），用于获取当前剧情上下文", "required": False},
        "num_options": {"type": "integer", "description": "生成选项数量（默认3，最多5）", "required": False},
    },
))

registry.register(Tool(
    name="delegate_writing",
    description="划定知识范围后委托写作。先分析本章需要哪些角色/地点/世界观条目，然后仅将这些知识提供给写作引擎，避免无关知识干扰。适用于'正式写作''写第X章''按大纲写作'等场景。如果有参考书，可指定原著章节注入。",
    parameters={
        "instruction": {"type": "string", "description": "写作指令（如'写第5章关于叶凡入魔的部分'）"},
        "characters": {"type": "string", "description": "本章出场角色名，逗号分隔（如'叶凡,林婉'）。留空则AI自动推断", "required": False},
        "locations": {"type": "string", "description": "本章涉及地点，逗号分隔（如'青云宗,古魔洞'）。留空则AI自动推断", "required": False},
        "concepts": {"type": "string", "description": "本章需要的世界观概念，逗号分隔（如'古魔血脉,灵气运转'）", "required": False},
        "forbidden": {"type": "string", "description": "禁止出场的角色，逗号分隔（如'苏晴,慕容白'）。防止悬疑/节奏被破坏", "required": False},
        "writing_rules": {"type": "string", "description": "特殊写作规则（如'本章结尾必须有悬念钩子''用叶凡视角'）", "required": False},
        "target_words": {"type": "integer", "description": "目标总字数（默认2500）", "required": False},
        "target_words_per_node": {"type": "integer", "description": "逐节点写作时每节点目标字数（默认350）。有细纲时自动生效，控制每段篇幅", "required": False},
        "mode": {"type": "string", "description": "strict=严格模式 suggest=宽松模式", "required": False},
        "chapter_title": {"type": "string", "description": "章节标题（可选）", "required": False},
        "is_extra": {"type": "boolean", "description": "是否为番外（不计入正常章节序号）", "required": False},
        "ref_chapters": {"type": "array", "items": {"type": "string"}, "description": "参考书章节ID列表（如['#1','#3']或['book_id:#2']），完整注入原著章节原文", "required": False},
    },
))

registry.register(Tool(
    name="run_review",
    description="启动评审团评审指定章节。多位评审员（编剧/编辑/各类读者）并发评审，输出汇总报告+每人详细反馈。可指定评审员和执行模式。",
    parameters={
        "chapter": {"type": "string", "description": "章节序号（如 #1、#3）或完整ID，也可直接传入章节文本"},
        "reviewers": {"type": "string", "description": "指定评审员ID（逗号分隔，如 screenwriter,harsh_critic），留空则使用全部激活的评审员", "required": False},
        "mode": {"type": "string", "description": "执行模式: concurrent(并发,默认) 或 serial(串行，后续评审员可看到前序意见)", "required": False},
    },
))

registry.register(Tool(
    name="manage_reviewers",
    description="管理评审团成员：查看列表、激活/停用评审员。",
    parameters={
        "action": {"type": "string", "description": "操作: list/activate/deactivate"},
        "reviewer_id": {"type": "string", "description": "评审员ID（activate/deactivate时必填）", "required": False},
    },
))

registry.register(Tool(
    name="manage_permissions",
    description="管理 Agent 权限模式。status(查看当前状态) / enable(启用自主模式，Agent 执行删除等危险操作无需确认) / disable(关闭自主模式，恢复确认机制)。⚠️ 启用后 Agent 可直接删除章节/实体/世界观条目等。",
    parameters={
        "action": {"type": "string", "description": "操作: status(查看状态) / enable(开启自主模式) / disable(关闭自主模式)"},
    },
))

registry.register(Tool(
    name="web_search",
    description="联网搜索。通过 Exa/Parallel 搜索引擎查找实时信息。用于查找历史典故、地理知识、文化风俗、科学原理、时事新闻等写作素材。当知识库中没有相关信息、或问题涉及真实世界且超出 AI 知识截止日期时使用。",
    parameters={
        "query": {"type": "string", "description": "搜索关键词（建议用精确短语）"},
        "num_results": {"type": "integer", "description": "结果数量（默认8，最多20）", "required": False},
    },
))

registry.register(Tool(
    name="web_fetch",
    description="抓取指定网页的文本内容。用于深入阅读 web_search 搜索结果中的链接，或访问用户提供的参考资料 URL。返回页面的纯文本提取结果。",
    parameters={
        "url": {"type": "string", "description": "网页 URL（http/https）"},
        "format": {"type": "string", "description": "输出格式: text（默认）", "required": False},
        "timeout": {"type": "integer", "description": "超时秒数（默认30，最大120）", "required": False},
    },
))

registry.register(Tool(
    name="add_material",
    description="添加研究资料到共享资料库（所有项目可订阅引用）。可手动输入或从网页搜索结果收藏。",
    parameters={
        "title": {"type": "string", "description": "资料标题"},
        "content": {"type": "string", "description": "资料正文/摘要内容"},
        "tags": {"type": "array", "description": "标签列表，如['历史','服饰','唐代']", "required": False},
        "source": {"type": "string", "description": "来源说明，如'web_search'或书名", "required": False},
        "source_url": {"type": "string", "description": "来源URL（可选）", "required": False},
    },
))

registry.register(Tool(
    name="search_materials",
    description="全文搜索共享资料库。仅返回当前项目已订阅的资料条目。未订阅的资料可通过 browse_materials 发现。",
    parameters={
        "query": {"type": "string", "description": "搜索关键词"},
    },
))

registry.register(Tool(
    name="browse_materials",
    description="浏览全局资料池（包括未订阅的），用于发现新资料。搜索结果不受项目订阅限制。",
    parameters={
        "query": {"type": "string", "description": "搜索关键词（留空则为全部列表）", "required": False},
        "tags": {"type": "array", "description": "按标签筛选", "required": False},
    },
))

registry.register(Tool(
    name="subscribe_material",
    description="将资料库中的条目订阅到当前项目，使其可在 search_materials 和写作上下文中使用。",
    parameters={
        "material_id": {"type": "string", "description": "资料ID（从 browse_materials 获取）"},
    },
))

registry.register(Tool(
    name="unsubscribe_material",
    description="从当前项目取消订阅某条资料（不删除资料本身）。",
    parameters={
        "material_id": {"type": "string", "description": "资料ID"},
    },
))

registry.register(Tool(
    name="delete_material",
    description="从全局资料库永久删除一条资料。影响所有订阅该项目。",
    parameters={
        "material_id": {"type": "string", "description": "资料ID"},
    },
    dangerous=True,
))

registry.register(Tool(
    name="set_reference_books",
    description="设置当前小说项目的参考书（如同人小说可指定原著为参考书）。参考书的知识图谱（角色/设定/关系）会以只读方式注入写作上下文。先用 list_books 查看可用的项目ID。",
    parameters={
        "book_ids": {"type": "array", "description": "参考书的项目ID数组，如['1781356752676']。传入空数组取消所有参考书"},
    },
))

registry.register(Tool(
    name="list_books",
    description="列出系统中所有项目/书籍（包括书名、ID、实体数、章节数）。用于查找参考书的ID。",
    parameters={},
))

registry.register(Tool(
    name="list_references",
    description="列出当前项目已设置的参考书摘要（书名、实体数、章节数、核心角色）。",
    parameters={},
))

registry.register(Tool(
    name="list_reference_chapters",
    description="列出参考书的所有章节（标题、字数、章节ID）。用于在写作前选择原著章节注入上下文。",
    parameters={
        "ref_book_id": {"type": "string", "description": "参考书项目ID（留空则列出所有参考书的章节）", "required": False},
    },
))

registry.register(Tool(
    name="import_reference_chapters",
    description="从参考书导入一个或多个章节到当前书籍。可用于复制原著章节作为参考资料或学习素材。",
    parameters={
        "ref_book_id": {
            "type": "string",
            "description": "参考书的 book_id（从 list_reference_books 获取）"
        },
        "chapter_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "要导入的章节 ID 列表（从 list_reference_chapters 获取）"
        }
    }
))

registry.register(Tool(
    name="search_reference",
    description="在参考书中搜索角色、设定或章节内容。不自动加载参考书，按需查询。如同人写作需查原著设定时使用。",
    parameters={
        "query": {"type": "string", "description": "搜索关键词（角色名、术语、事件等）"},
    },
))

registry.register(Tool(
    name="migrate_reference_knowledge",
    description="将参考书中的实体迁移到当前书的知识库。当本书缺少某个角色/地点/设定的知识点、但参考书中存在时使用。可复制原样迁移，也可修改后再迁移（参考书的知识点不会被修改）。",
    parameters={
        "ref_book_id": {"type": "string", "description": "参考书项目ID"},
        "entity_name": {"type": "string", "description": "参考书中要迁移的实体名称（精确匹配）"},
        "new_name": {"type": "string", "description": "迁移后新实体的名称（留空则保持原名）", "required": False},
        "new_data": {"type": "object", "description": "迁移后修改的数据字段（留空则完全复制参考书数据）。可修改 personality/appearance/description/abilities 等字段以适应本书", "required": False},
    },
))

registry.register(Tool(
    name="agent_tasks",
    description="Agent任务清单：规划、追踪多步操作。支持创建清单、查看进度、更新任务状态。",
    parameters={
        "action": {"type": "string", "description": "操作: create(创建新清单) / get(查看清单) / update(更新任务状态) / add(追加任务) / list(列出所有清单) / clear(清除已完成清单)"},
        "task_list_id": {"type": "string", "description": "清单ID（get/update/add时必填，留空则操作最近清单）", "required": False},
        "title": {"type": "string", "description": "清单标题（create时必填）", "required": False},
        "items": {"type": "array", "items": {"type": "object"}, "description": "任务项列表 [{label, tool?}]（create/add时可选）", "required": False},
        "item_index": {"type": "number", "description": "任务项序号（update时必填，从0开始）", "required": False},
        "status": {"type": "string", "description": "新状态: pending/in_progress/done/skipped/failed（update时必填）", "required": False},
        "result_summary": {"type": "string", "description": "执行结果摘要（update时可选）", "required": False},
    },
))


registry.register(Tool(
    name="start_autopilot",
    description="启动 Autopilot 自主写作引擎，让 Agent 自主写完整本书或指定范围。此工具会先展示执行计划，等待用户确认后才开始执行。后台运行不阻塞聊天，断开连接也继续。⚠️ 调用前必须先读取大纲确定需要写哪些章节。",
    parameters={
        "instruction": {"type": "string", "description": "写作指令，如'按大纲写完剩余章节'、'续写后5章'"},
        "max_chapters": {"type": "integer", "description": "最多写几章，默认10", "required": False},
        "audit_mode": {"type": "string", "description": "审核模式：'soft'(质量低时暂停) | 'hard'(每章需确认) | 'autonomous'(全自动)。默认 soft", "required": False},
        "auto_review": {"type": "boolean", "description": "是否每章写完自动评审，默认 true", "required": False},
        "auto_extract": {"type": "boolean", "description": "是否每章写完自动提取知识，默认 true", "required": False},
    },
    dangerous=True,
))

# ──────────────────────────────────────────────────────────────────────────
# Narrative logic tools — constraint engine, impact propagation, confidence
# ──────────────────────────────────────────────────────────────────────────

registry.register(Tool(
    name="define_constraint",
    description="设定叙事约束规则。如'主角获得神器后不能丢失'、'反派在第10章前不能知道主角身份'。系统将用LLM自动生成检测查询，在 check_constraints 时执行。",
    parameters={
        "description": {"type": "string", "description": "用自然语言描述约束规则"},
        "severity": {"type": "string", "description": "hard=必须遵守(违反报红), soft=仅警告(报黄)", "required": False},
    },
))

registry.register(Tool(
    name="check_constraints",
    description="检查当前所有叙事约束是否被遵守。返回违反列表，无违反时报告全部通过。修改章节后可调用此工具验证一致性。",
    parameters={},
))

registry.register(Tool(
    name="delete_constraint",
    description="删除一条叙事约束。传入约束ID（从 check_constraints 或 define_constraint 的返回中获取）。",
    parameters={
        "constraint_id": {"type": "string", "description": "要删除的约束ID，如 C0a1b2c3"},
    },
))

registry.register(Tool(
    name="analyze_impact",
    description="分析某个改动的影响范围（爆炸半径）。修改章节/设定/事件/伏笔前先调用，预览哪些后续内容会受影响。避免改一处忘一处。",
    parameters={
        "source_type": {"type": "string", "description": "被修改元素类型: entity / timeline_event / foreshadow"},
        "source_id": {"type": "string", "description": "被修改元素的ID"},
        "change_description": {"type": "string", "description": "改了什么（自然语言描述）", "required": False},
    },
))

registry.register(Tool(
    name="score_confidence",
    description="评估知识库设定的可信度。每个设定卡片获得0-1分，反映引用密度、关系丰富度和一致性。低分设定建议补充。不传 entity_id 则评分全部实体。",
    parameters={
        "entity_id": {"type": "string", "description": "单个实体ID（可选，不填则评分全部）", "required": False},
    },
))

registry.register(Tool(
    name="verify_chapter",
    description="写后验证：检查章节的实体漂移、大纲合规、约束违反、伏笔状态、可信度。delegate_writing 写完后自动调用。也可手动调用验证任意章节。",
    parameters={
        "chapter_id": {"type": "string", "description": "章节序号（如 #5）或完整ID"},
        "scope_entities": {"type": "string", "description": "本章scope内的实体名列表（逗号分隔），用于实体漂移检测。留空则用全部实体", "required": False},
    },
))

# ──────────────────────────────────────────────────────────────────────────
# Graph tools — GraphRAG search and graph insights
# ──────────────────────────────────────────────────────────────────────────

registry.register(Tool(
    name="search_graph",
    description="用自然语言搜索知识图谱（GraphRAG）。自动分解问题、生成Cypher查询、综合结果。适合复杂关系查询，如'叶凡和谁有师徒关系''哪些伏笔涉及青云宗'。",
    parameters={
        "question": {"type": "string", "description": "自然语言问题"},
    },
))

registry.register(Tool(
    name="get_graph_insights",
    description="获取图谱洞察：遗忘角色、未回收伏笔、桥接角色、设定薄弱实体、约束违反、写作建议。写作前调用可了解全局状态。",
    parameters={},
))

# ──────────────────────────────────────────────────────────────────────────
# Apply TOOL_META to registered tools
# ──────────────────────────────────────────────────────────────────────────
def _apply_tool_meta() -> None:
    for _name, _meta in TOOL_META.items():
        _t = registry._tools.get(_name)
        if _t is None:
            logger.warning("TOOL_META references unknown tool: %s", _name)
            continue
        for _k, _v in _meta.items():
            setattr(_t, _k, _v)


_apply_tool_meta()


def tools_with(flag: str) -> set[str]:
    """Return the set of tool names that have ``flag`` set True. Convenience for
    code paths that still want a set (e.g. logging)."""
    return {t.name for t in registry._tools.values() if getattr(t, flag, False)}
