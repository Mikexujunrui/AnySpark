"""
anyspark.graph.extract — 实体抽取器（章节/资料 → 实体/关系/事件）。

设计（DESIGN §8.3）：知识图谱是 AI 事实源；章节落盘后自动抽取入库。
真实 LLM 抽取（模型无关：提示词与输出全为自然语言），宽容 JSON 解析。
已有实体清单注入提示，避免重复抽取（抽取器轻量，单次 LLM 调用）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from anyspark.core.types import Message

# 默认实体类型（S50 内容化：GraphExtractor 可注入自定义类型集，提示词动态拼）
VALID_TYPES = ("角色", "地点", "事件", "物件", "设定")


def _types_line(types: list[str]) -> str:
    """类型清单 → 提示词里的约束行（N 选一，随内容集变化）。"""
    if not types:
        types = list(VALID_TYPES)
    return "实体类型只能从以下选一：" + "/".join(types) + "。"


EXTRACT_PROMPT = (
    "你是小说知识图谱抽取器。从给定的章节正文中抽取**新出现或本章关键**的实体、关系和事件。\n"
    "规则：\n"
    "1. 只抽取正文明确提及的，不要臆测、不要推断未写的背景。\n"
    "2. {types_line}\n"
    "3. 关系：两个实体之间明确的关系（如 认识/兄妹/师徒/居住/敌视），类型用自然语言。\n"
    "4. 事件：本章发生的具体事件（time_point=章节号，如'第3章'），involved 列出涉及实体名。\n"
    "5. 已在'已有实体'清单里的不要重复抽取（不出现在 entities），"
    "但若本章该实体状态发生变化，在 states 里单独更新（见下）。\n"
    "输出（严格 JSON，不要其它文字）：\n"
    '{"entities": [{"name": "实体名", "type": "角色", "aliases": ["别名"], '
    '"description": "一句明确无歧义的描述", '
    '"state": "本章该实体发生的变化/新处境（一句话；本章无变化可省略）"}],\n'
    ' "states": [{"name": "已有实体名", "state": "本章该实体状态变化（一句话）"}],\n'
    ' "relations": [{"from": "甲", "to": "乙", "type": "关系类型", '
    '"description": "关系说明"}],\n'
    ' "events": [{"time_point": "第N章", "label": "事件名", "description": "事件说明", '
    '"involved": ["甲", "乙"]}]}\n'
    "\n"
    "已有实体（不要重复抽取）：\n"
)


@dataclass
class EntityDraft:
    """抽取出的实体（入库前草稿）。"""

    name: str
    entity_type: str
    aliases: list[str] = field(default_factory=list)
    description: str = ""
    state: str = ""  # 本章状态变化（S20：增量拼接成角色/地点演化）


@dataclass
class RelationDraft:
    """抽取出的关系（入库前草稿，名字引用）。"""

    from_name: str
    to_name: str
    rel_type: str
    description: str = ""


@dataclass
class EventDraft:
    """抽取出的事件（入库前草稿）。"""

    time_point: str
    label: str
    description: str = ""
    involved: list[str] = field(default_factory=list)


@dataclass
class Extraction:
    """一章的抽取结果。"""

    entities: list[EntityDraft] = field(default_factory=list)
    relations: list[RelationDraft] = field(default_factory=list)
    events: list[EventDraft] = field(default_factory=list)
    states: list[StateUpdate] = field(default_factory=list)  # S20：已有实体状态更新


@dataclass
class StateUpdate:
    """已有实体的状态变化（不出现在 entities，仅更新 state）。"""

    name: str
    state: str


class GraphExtractor:
    """真实 LLM 抽取器（模型无关，适配器注入）。"""

    def __init__(self, model: object, types: list[str] | None = None) -> None:
        # model 实现 core.Model 协议（respond(messages, tools) -> ModelOutput）
        self._model = model
        # S50：类型集内容化——项目级可配置（缺省默认 5 类），提示词动态拼
        self._types = list(types) if types else list(VALID_TYPES)

    def extract(
        self,
        chapter_ref: str,
        text: str,
        existing: list[dict[str, Any]] | None = None,
    ) -> Extraction:
        """抽取一章：新实体 + 关系 + 事件（已有实体不重复）。

        >>> 宽容解析的补强（benchmark 发现）：模型输出偶发截断/非法 JSON，
        解析结果全空时重试一次（不同采样）；仍空则返回空（不阻塞调用方）。
        """
        existing_text = ""
        if existing:
            names = "\n".join(f"- {e['name']}（{e['entity_type']}）" for e in existing[:50])
            existing_text = f"\n{names}\n"
        prompt = EXTRACT_PROMPT.replace("{types_line}", _types_line(self._types)) + (
            existing_text + f"\n章节《{chapter_ref}》正文：\n{text[:6000]}"
        )
        parsed = Extraction()
        for _attempt in range(2):
            output = self._model.respond(  # type: ignore[attr-defined]
                [Message(role="system", content=prompt)],
                [],
            )
            candidate = self._parse(output.text)
            # 实体或状态更新任一非空即接受（S20：states 也是有效产出）
            if candidate.entities or candidate.states:
                parsed = candidate
                break
            parsed = candidate
        return parsed

    def _parse(self, raw: str) -> Extraction:
        """宽容解析模型输出（围栏/前后文字/非法类型容错）。"""
        data = _parse_json_object(raw)
        extraction = Extraction()

        for item in _as_dict_list(data.get("entities")):
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            etype = str(item.get("type", "设定")).strip()
            if etype not in self._types:
                etype = "设定"
            aliases = [str(a).strip() for a in _as_list(item.get("aliases")) if str(a).strip()]
            extraction.entities.append(
                EntityDraft(
                    name=name,
                    entity_type=etype,
                    aliases=aliases,
                    description=str(item.get("description", "")).strip(),
                    state=str(item.get("state", "")).strip(),
                )
            )

        for item in _as_dict_list(data.get("relations")):
            fn = str(item.get("from", "")).strip()
            tn = str(item.get("to", "")).strip()
            rt = str(item.get("type", "")).strip()
            if fn and tn and rt:
                extraction.relations.append(
                    RelationDraft(
                        from_name=fn,
                        to_name=tn,
                        rel_type=rt,
                        description=str(item.get("description", "")).strip(),
                    )
                )

        for item in _as_dict_list(data.get("events")):
            label = str(item.get("label", "")).strip()
            if not label:
                continue
            involved = [str(x).strip() for x in _as_list(item.get("involved")) if str(x).strip()]
            extraction.events.append(
                EventDraft(
                    time_point=str(item.get("time_point", "")).strip(),
                    label=label,
                    description=str(item.get("description", "")).strip(),
                    involved=involved,
                )
            )
        # S20：已有实体状态更新（不建新实体，仅更新 state）
        for item in _as_dict_list(data.get("states")):
            name = str(item.get("name", "")).strip()
            state = str(item.get("state", "")).strip()
            if name and state:
                extraction.states.append(StateUpdate(name=name, state=state))
        return extraction


def _parse_json_object(text: str) -> dict[str, Any]:
    """宽容解析模型输出的 JSON 对象（去除 ``` 围栏与前后文字）。"""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(cleaned[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return {}


def _as_dict_list(value: object) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    return []


def _as_list(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []
