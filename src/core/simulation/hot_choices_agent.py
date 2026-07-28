"""Hot Choices Agent — 快捷选择生成器.

独立于 NarratorAgent 运行，基于当前推演状态和最新叙事内容，
生成2-5条用户可直接点击的行动建议。

参照 Nova 的 InteractiveHotChoices 设计，使用独立轻量 LLM 调用。
"""

import asyncio
import logging

from ..llm_client import chat as llm_chat
from ..utils import safe_json_parse

logger = logging.getLogger(__name__)

HOT_CHOICES_SYSTEM_PROMPT = """你是推演模式的快捷行动建议生成器。
你只负责基于当前故事上下文生成用户下一轮可直接输入的行动建议，不负责续写剧情。

## 要求
1. 输出 2-5 条中文行动句，从玩家第一人称或明确行动意图出发
2. 每条应覆盖不同的方向：观察、对话、探索、决策、保守应对等
3. 彼此有区分度，不得引入上下文未支撑的新事实
4. 不得重复已展示过的选择
5. 必须只输出 JSON 对象：{"choices": ["...", "..."]}
6. 不要输出思考过程、解释、Markdown 或代码块

## 示例
输入：用户刚刚探索完一个古墓密室，发现了壁画和一扇暗门
输出：{"choices": ["仔细研究壁画上的文字", "尝试推开暗门", "检查周围是否有陷阱", "退回通道重新观察"]}"""


class HotChoicesAgent:
    """快捷选择生成器 — 独立于叙事 Agent 的轻量 LLM 调用."""

    def __init__(self, book_id: str):
        self.book_id = book_id

    async def generate(
        self,
        narrative: str,
        state: dict | None = None,
        user_action: str = "",
        recent_turns: list[dict] | None = None,
        exclude_choices: list[str] | None = None,
    ) -> list[str]:
        """基于当前上下文生成 2-5 条行动建议.

        Args:
            narrative: 最新回合的叙事正文
            state: 当前结构化状态快照
            user_action: 用户本轮已采取的行动
            recent_turns: 最近几回合的完整内容
            exclude_choices: 已展示过的选择（避免重复）

        Returns:
            行动建议列表，最多5条
        """
        # Build context
        parts = ["## 当前叙事\n" + narrative[:1000]]

        if state:
            state_preview = self._summarize_state(state)
            if state_preview:
                parts.append("\n## 当前状态\n" + state_preview)

        if user_action:
            parts.append("\n## 用户本轮行动\n" + user_action[:200])

        if recent_turns:
            recent_summary = self._format_recent_turns(recent_turns)
            parts.append("\n## 近期回合\n" + recent_summary)

        if exclude_choices:
            parts.append("\n## 已展示过的选择（不要重复）\n" + "\n".join(f"- {c}" for c in exclude_choices))

        prompt = "\n".join(parts)

        # Call LLM
        loop = asyncio.get_running_loop()
        try:
            content = await loop.run_in_executor(
                None,
                lambda: llm_chat(
                    prompt=prompt,
                    system=HOT_CHOICES_SYSTEM_PROMPT,
                    temperature=0.7,
                    task="general",
                ),
            )
        except Exception as e:
            logger.warning("HotChoicesAgent LLM call failed: %s", e)
            return []

        if not content:
            return []

        # Parse JSON
        result = safe_json_parse(content, default=None)
        if not result or not isinstance(result, dict):
            logger.warning("HotChoicesAgent parse failed, raw: %s", content[:100])
            return []

        choices = result.get("choices", [])
        if not isinstance(choices, list):
            return []

        # Clean and deduplicate
        seen = set(exclude_choices or [])
        cleaned = []
        for c in choices:
            c = c.strip()
            if c and c not in seen and len(cleaned) < 5:
                cleaned.append(c)
                seen.add(c)

        if not cleaned:
            logger.info("HotChoicesAgent returned empty choices after dedup")
            return []

        logger.info("HotChoicesAgent generated %d choices", len(cleaned))
        return cleaned

    def _summarize_state(self, state: dict) -> str:
        """Summarize structured state for prompt injection."""
        parts = []
        on_stage = state.get("on_stage", [])
        if on_stage:
            parts.append(f"在场角色: {', '.join(str(s) for s in on_stage[:5])}")

        scene = state.get("scene", "")
        if scene:
            parts.append(f"场景: {scene[:100]}")

        location = state.get("location", "")
        if location:
            parts.append(f"位置: {location[:50]}")

        characters = state.get("characters", {})
        if characters:
            char_summary = []
            for name, info in list(characters.items())[:3]:
                if isinstance(info, dict):
                    status = info.get("status", "")
                    mood = info.get("mood", "")
                    s = name
                    if status:
                        s += f"({status})"
                    if mood:
                        s += f"[{mood}]"
                    char_summary.append(s)
            if char_summary:
                parts.append(f"角色状态: {'; '.join(char_summary)}")

        threads = state.get("threads", [])
        if threads and isinstance(threads, list):
            parts.append(f"待处理线索: {'; '.join(str(t)[:30] for t in threads[:3])}")

        return "\n".join(parts) if parts else ""

    def _format_recent_turns(self, turns: list[dict]) -> str:
        """Format recent turns for prompt."""
        parts = []
        for ev in turns[-3:]:
            tn = ev.get("turn_number", "?")
            user = (ev.get("user", "") or "")[:80]
            narrative = (ev.get("narrative", "") or ev.get("content", ""))[:120]
            if user:
                parts.append(f"第{tn}回合用户: {user}")
            parts.append(f"第{tn}回合剧情: {narrative}")
        return "\n".join(parts)
