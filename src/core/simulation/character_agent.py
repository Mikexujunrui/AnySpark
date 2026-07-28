"""Character Agent — 轻量级角色智能体.

基于图谱角色画像（Entity:Character + Snapshot阶段 + 关系网络）构建
角色约束 prompt，通过轻量 LLM 调用生成角色对情境的独立响应。

不走完整 agent_loop，直接 llm_chat 调用，快速返回。
"""

import asyncio
import logging
from dataclasses import dataclass, field

from ..graph_store import GraphStore
from ..llm_client import chat as llm_chat
from ..utils import safe_json_parse

logger = logging.getLogger(__name__)

# ── Relationship type labels for prompt ──
REL_TYPE_LABELS = {
    "KNOWS": "认识",
    "ALLY": "盟友",
    "ANTAGONIST": "敌对",
    "FAMILY": "家族",
    "ROMANTIC": "情感关系",
    "LOVES": "爱慕",
    "MENTOR_OF": "师徒",
    "MASTER_OF": "从属",
    "KILLED": "杀死了",
    "SAVED": "救过",
    "OWNS": "拥有",
    "BELONGS_TO": "属于",
    "FRIEND": "朋友",
}

CHARACTER_SYSTEM_TEMPLATE = """你是「{name}」。

## 角色性格
{personality}

## 当前阶段
{phase_description}

## 人际关系（决定你对其他角色的态度）
{relationships_list}

## 能力与技能
{skills_list}

## 行为约束
1. 用户的指令代表你已决定采取的行动，你必须执行它，不能拒绝或否定
2. 你的性格体现在你执行行动时的内心想法、感受和台词风格中，而非拒绝执行
3. 对其他角色的态度由关系类型决定（如敌对关系 → 敌意/警惕，盟友关系 → 信任/合作）
4. 保持角色语言风格的一致性

## 输出格式（严格JSON）
{{
  "perception": "角色对当前情境的感知和理解",
  "thoughts": "角色的内心独白和思考过程（可以体现性格，但不要否定用户指令）",
  "action": "角色执行用户指令的具体行动",
  "dialogue": "角色可能说出的台词（可选，如不说话则留空字符串）"
}}"""

NARRATOR_POV_SUFFIX = """

## 特别说明
你正在被叙事者召唤，以第三人称视角描述你在给定情境下会怎么做。
请基于你的性格和关系，给出真实合理的反应。"""


@dataclass
class CharacterProfile:
    """从图谱实体生成的角色画像.

    Attributes:
        character_id: Entity:Character 的 ID
        name: 角色名
        entity_type: 实体类型（通常为 "character"）
        personality: 性格描述（来自 entity.data["description"] 或 Snapshot）
        current_phase: 最新阶段快照（来自 HAS_PHASE → Snapshot）
        relationships: 关系列表 [{target_name, rel_type, direction}]
        skills: 技能列表
        system_prompt: 组装好的约束 prompt
    """

    character_id: str
    name: str
    entity_type: str = "character"
    personality: str = ""
    current_phase: dict | None = None
    relationships: list[dict] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    system_prompt: str = ""

    def to_dict(self) -> dict:
        return {
            "character_id": self.character_id,
            "name": self.name,
            "entity_type": self.entity_type,
            "personality": self.personality,
            "current_phase": self.current_phase,
            "relationships": self.relationships,
            "skills": self.skills,
        }


class CharacterAgent:
    """轻量角色智能体 — 基于图谱角色画像的独立决策生成.

    工作流程：
        1. build_profile(): 从图谱拉取角色实体+阶段+关系 → 生成约束 prompt
        2. respond(): 用约束 prompt + 情境 → LLM → 角色响应（感知/内心/行动/台词）
    """

    def __init__(self, book_id: str):
        self.book_id = book_id
        self.graph = GraphStore(project_id=book_id)

    # ── 角色画像构建 ──

    def build_profile(self, character_id: str) -> CharacterProfile | None:
        """从图谱构建角色画像.

        整合以下图谱数据：
        - Entity:Character 节点 → 名称、类型、基本数据
        - HAS_PHASE → Snapshot → 角色当前阶段（性格、外貌、能力、动机等）
        - 关系边 → 关系态度矩阵
        """
        entity = self.graph.get_entity(character_id)
        if not entity:
            logger.warning("Character entity not found: %s", character_id)
            return None

        # 1. 获取最新阶段快照
        phase = self._get_current_phase(character_id)

        # 2. 获取关系
        relationships = self._get_relationships(character_id)

        # 3. 提取性格和技能
        if phase and phase.get("data"):
            phase_data = phase["data"]
            personality = (
                phase_data.get("personality", "")
                or phase_data.get("description", "")
                or (entity.data or {}).get("description", "")
            )
            skills = phase_data.get("abilities", [])
            if isinstance(skills, str):
                skills = [skills]
        else:
            personality = (entity.data or {}).get("description", "")
            skills = (entity.data or {}).get("skills", [])
            if isinstance(skills, str):
                skills = [skills]

        # 4. 组装 system prompt
        system_prompt = self._build_system_prompt(
            name=entity.name,
            personality=personality,
            phase=phase,
            relationships=relationships,
            skills=skills,
        )

        return CharacterProfile(
            character_id=character_id,
            name=entity.name,
            entity_type=entity.type,
            personality=personality,
            current_phase=phase,
            relationships=relationships,
            skills=skills,
            system_prompt=system_prompt,
        )

    def _get_current_phase(self, character_id: str) -> dict | None:
        """获取角色当前阶段快照（is_current=true 或 time_order 最大）."""
        try:
            rows = self.graph._run(
                """
                MATCH (e:Entity {id: $cid, project_id: $pid})-[:HAS_PHASE]->(s:Snapshot)
                RETURN s
                ORDER BY
                    CASE WHEN s.is_current = true THEN 0 ELSE 1 END,
                    s.time_order DESC
                LIMIT 1
                """,
                {"cid": character_id, "pid": self.book_id},
            )
            if rows:
                snap = dict(rows[0]["s"])
                return snap
        except Exception as e:
            logger.debug("Failed to get phase for %s: %s", character_id, e)
        return None

    def _get_relationships(self, character_id: str) -> list[dict]:
        """获取角色的所有关系（双向）."""
        rels = []
        try:
            # Outgoing relationships
            rows = self.graph._run(
                """
                MATCH (c:Entity {id: $cid, project_id: $pid})-[r]->(other:Entity {project_id: $pid})
                WHERE other:Character
                RETURN other.name AS name, type(r) AS rel_type, 'outgoing' AS direction,
                       other.id AS target_id
                """,
                {"cid": character_id, "pid": self.book_id},
            )
            for row in rows:
                rels.append(
                    {
                        "target_name": row.get("name", ""),
                        "target_id": row.get("target_id", ""),
                        "rel_type": row.get("rel_type", ""),
                        "direction": "outgoing",
                    }
                )

            # Incoming relationships
            rows = self.graph._run(
                """
                MATCH (other:Entity:Character {project_id: $pid})-[r]->(c:Entity {id: $cid, project_id: $pid})
                RETURN other.name AS name, type(r) AS rel_type, 'incoming' AS direction,
                       other.id AS target_id
                """,
                {"cid": character_id, "pid": self.book_id},
            )
            for row in rows:
                rels.append(
                    {
                        "target_name": row.get("name", ""),
                        "target_id": row.get("target_id", ""),
                        "rel_type": row.get("rel_type", ""),
                        "direction": "incoming",
                    }
                )
        except Exception as e:
            logger.debug("Failed to get relationships for %s: %s", character_id, e)

        return rels

    def _build_system_prompt(
        self,
        name: str,
        personality: str,
        phase: dict | None,
        relationships: list[dict],
        skills: list[str],
    ) -> str:
        """组装角色约束 system prompt."""
        # Phase description
        if phase:
            phase_label = phase.get("phase") or phase.get("label") or "当前阶段"
            phase_data = phase.get("data", {})
            parts = [f"阶段：{phase_label}"]
            if phase_data.get("appearance"):
                parts.append(f"外貌：{phase_data['appearance'][:100]}")
            if phase_data.get("motivation"):
                parts.append(f"动机：{phase_data['motivation'][:100]}")
            if phase_data.get("growth_note"):
                parts.append(f"成长：{phase_data['growth_note'][:100]}")
            phase_desc = "\n".join(parts)
        else:
            phase_desc = "未设定阶段"

        # Relationships list
        if relationships:
            rel_lines = []
            for rel in relationships[:15]:  # cap at 15 to control prompt length
                label = REL_TYPE_LABELS.get(rel["rel_type"], rel["rel_type"])
                direction = "→" if rel["direction"] == "outgoing" else "←"
                rel_lines.append(f"- {direction} {rel['target_name']}：{label}")
            rel_str = "\n".join(rel_lines)
        else:
            rel_str = "暂无已知关系"

        # Skills
        skills_str = "、".join(skills[:8]) if skills else "暂无特殊技能"

        return CHARACTER_SYSTEM_TEMPLATE.format(
            name=name,
            personality=personality or "暂无详细性格描述",
            phase_description=phase_desc,
            relationships_list=rel_str,
            skills_list=skills_str,
        )

    # ── 角色响应生成 ──

    async def respond(
        self,
        profile: CharacterProfile,
        situation: str,
        history: list[dict] | None = None,
        mode: str = "character_pov",
    ) -> dict:
        """让角色对情境做出响应.

        Args:
            profile: 角色画像（含 system_prompt 约束）
            situation: 当前情境描述（用户选择 / 叙事者设定的条件）
            history: 近期推演历史 [{content, turn_number}]
            mode: ``"character_pov"`` 或 ``"narrator_pov"``

        Returns:
            ``{perception, thoughts, action, dialogue}``
        """
        system = profile.system_prompt
        if mode == "narrator_pov":
            system += NARRATOR_POV_SUFFIX

        # Build user prompt
        parts = [f"## 当前情境\n{situation}"]
        if history:
            recent = history[-3:]  # last 3 events for context
            parts.append("\n## 近期发生的事")
            for ev in recent:
                content_preview = (ev.get("content") or "")[:150]
                parts.append(f"[回合{ev.get('turn_number', '?')}] {content_preview}")

        if mode == "character_pov":
            parts.append("\n以上情境中描述的行动是你决定采取的，请执行它并描述你的内心反应。输出严格JSON。")
        else:
            parts.append("\n请基于你的角色设定，对当前情境做出反应。输出严格JSON。")
        prompt = "\n".join(parts)

        # LLM call (async via executor)
        loop = asyncio.get_running_loop()
        try:
            content = await loop.run_in_executor(
                None,
                lambda: llm_chat(
                    prompt=prompt,
                    system=system,
                    temperature=0.7,
                    task="writing",
                ),
            )
        except Exception as e:
            logger.error("CharacterAgent LLM call failed for %s: %s", profile.name, e)
            return {
                "perception": "（角色思考失败）",
                "thoughts": f"错误: {str(e)[:100]}",
                "action": "无",
                "dialogue": "",
            }

        if not content:
            return {
                "perception": "（角色无响应）",
                "thoughts": "",
                "action": "无",
                "dialogue": "",
            }

        # Parse JSON response
        result = safe_json_parse(content, default=None)
        if result and isinstance(result, dict):
            return {
                "perception": result.get("perception", ""),
                "thoughts": result.get("thoughts", ""),
                "action": result.get("action", ""),
                "dialogue": result.get("dialogue", ""),
            }

        # Fallback: if JSON parse fails, use raw content as action
        logger.warning("CharacterAgent JSON parse failed for %s, using raw text", profile.name)
        return {
            "perception": "",
            "thoughts": "",
            "action": content[:500],
            "dialogue": "",
        }

    # ── 批量画像构建 ──

    def build_profiles_batch(self, character_ids: list[str]) -> dict[str, CharacterProfile]:
        """批量构建角色画像（用于叙事者模式多角色推演）.

        Returns:
            ``{character_id: CharacterProfile}`` dict
        """
        profiles = {}
        for cid in character_ids:
            profile = self.build_profile(cid)
            if profile:
                profiles[cid] = profile
            else:
                logger.warning("Failed to build profile for character %s", cid)
        return profiles
