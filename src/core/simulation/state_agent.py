"""State Agent — 推演结构化状态追踪.

每回合叙事完成后异步运行，分析叙事内容并将其转换为结构化状态变化。
状态通过 SimulationStore 的 append_state_delta 持久化。
失败不影响主推演流程。

参照 Nova 的 StateAgent 设计。
"""

import asyncio
import logging

from ..llm_client import chat as llm_chat
from ..utils import safe_json_parse
from .simulation_store import SimulationStore

logger = logging.getLogger(__name__)

STATE_SYSTEM_PROMPT = """你是推演模式的状态记录 Agent。

你只负责把一个已经生成完成的推演回合转换为结构化状态变化 JSON，
不负责续写剧情或生成选项。

## 输出格式
必须只输出 JSON 对象，格式：
{"ops": [{"op": "set", "path": "characters.张三.status", "value": "受伤"}]}

ops 不能为空，每条 op 记录本回合已经发生且确定成立的变化。

## 允许的状态路径
- on_stage: 当前在场角色列表（数组）
- characters.<角色名>.location: 角色位置
- characters.<角色名>.status: 角色状态（如"健康""受伤""昏迷"）
- characters.<角色名>.mood: 角色情绪（如"愤怒""恐惧""平静"）
- characters.<角色名>.goal: 角色当前目标
- characters.<角色名>.relationship.<对方名>: 关系变化描述
- scene: 当前场景描述
- location: 当前位置名称
- time: 时间进度
- pov: 当前主视角角色
- inventory: 物品列表
- resources: 资源列表
- world_flags: 世界规则/标记（对象）
- threads: 未解决线索/危机/倒计时（数组）
- action_space: 可行动入口（数组）

## 要求
- 只记录本回合已经确定的变化，不记录未来计划
- 不复制没有变化的旧状态
- 不要记录下一步行动建议或选项
- 角色名使用推演中使用的名字"""


class StateAgent:
    """结构化状态追踪 — 每回合异步运行."""

    def __init__(self, book_id: str):
        self.book_id = book_id

    async def update_state(
        self,
        sim_id: str,
        narrative: str,
        user_action: str = "",
        previous_state: dict | None = None,
        store: SimulationStore | None = None,
    ) -> list[dict]:
        """分析回合叙事，生成并持久化结构化状态变化.

        Args:
            sim_id: 推演会话ID
            narrative: 当前回合的叙事正文
            user_action: 用户本轮行动
            previous_state: 之前的状态快照（可选）
            store: SimulationStore 实例（提供则以持久化）

        Returns:
            生成的 state ops 列表；失败时返回空列表
        """
        if not narrative or len(narrative) < 50:
            logger.info("StateAgent: narrative too short (%d chars), skipping", len(narrative or ""))
            return []

        # Build prompt
        parts = ["请根据以下推演回合内容，生成本回合的状态变化 JSON。"]

        if previous_state:
            state_preview = self._summarize_previous_state(previous_state)
            if state_preview:
                parts.append(f"\n## 变化前的状态\n{state_preview}")

        if user_action:
            parts.append(f"\n## 用户本轮行动\n{user_action[:300]}")

        parts.append(f"\n## 本回合叙事正文\n{narrative[:2000]}")
        prompt = "\n".join(parts)

        # Call LLM
        loop = asyncio.get_running_loop()
        try:
            content = await loop.run_in_executor(
                None,
                lambda: llm_chat(
                    prompt=prompt,
                    system=STATE_SYSTEM_PROMPT,
                    temperature=0.3,
                    task="general",
                ),
            )
        except Exception as e:
            logger.warning("StateAgent LLM call failed: %s", e)
            return []

        if not content:
            return []

        # Parse JSON
        result = safe_json_parse(content, default=None)
        if not result or not isinstance(result, dict):
            logger.warning("StateAgent parse failed, raw: %s", content[:100])
            return []

        ops = result.get("ops", [])
        if not isinstance(ops, list) or not ops:
            logger.info("StateAgent returned empty ops")
            return []

        # Validate ops
        valid_ops = []
        for op in ops:
            if isinstance(op, dict) and op.get("op") in ("set", "merge", "push", "pull", "inc", "unset"):
                if op.get("path"):
                    valid_ops.append(op)

        if not valid_ops:
            logger.info("StateAgent returned no valid ops")
            return []

        # Persist via store
        if store:
            # Get latest turn for parent_id
            latest = store.get_latest_turn(sim_id)
            parent_id = latest.get("id", sim_id) if latest else sim_id
            store.append_state_delta(sim_id, parent_id, valid_ops)

        logger.info("StateAgent: %d valid ops generated", len(valid_ops))
        return valid_ops

    def _summarize_previous_state(self, state: dict) -> str:
        """Summarize previous state for prompt."""
        summaries = []
        on_stage = state.get("on_stage", [])
        if on_stage:
            summaries.append(f"在场: {', '.join(str(s) for s in on_stage[:5])}")
        scene = state.get("scene", "")
        if scene:
            summaries.append(f"场景: {scene[:80]}")
        location = state.get("location", "")
        if location:
            summaries.append(f"位置: {location[:50]}")
        characters = state.get("characters", {})
        if characters:
            states = []
            for name, info in list(characters.items())[:3]:
                if isinstance(info, dict):
                    summary = name
                    if info.get("status"):
                        summary += f"[{info['status']}]"
                    if info.get("mood"):
                        summary += f"({info['mood']})"
                    states.append(summary)
            if states:
                summaries.append("角色: " + "; ".join(states))
        threads = state.get("threads", [])
        if threads and isinstance(threads, list):
            summaries.append(f"线索({len(threads)}): {'; '.join(str(t)[:25] for t in threads[:3])}")
        return " | ".join(summaries) if summaries else "（空）"
