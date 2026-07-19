"""Narrator Agent — 推演中央调度器.

负责：图谱洞察获取 → 选项生成 → CharacterAgent 唤醒 → 叙事综合 → SSE 流式输出。

双模式推演：
    - 角色主视角 (character_pov): 用户选定角色 → CharacterAgent 生成感知+可行动作
      → NarratorAgent 包装叙事+选项 → 用户选择 → 循环
    - 叙事者主视角 (narrator_pov): 用户设定条件 → NarratorAgent 唤醒相关
      CharacterAgent(并行) → 各角色独立响应 → NarratorAgent 综合叙事 → 循环

升级内容：
    - 回合裁定循环 7 步法 prompt
    - 记忆压缩（最近 N 回合完整 + 较早回合摘要）
    - 结构化状态注入
    - HotChoicesAgent 集成
"""

import asyncio
import logging
from collections.abc import AsyncGenerator

from ..graph_store import GraphStore
from ..llm_client import chat as llm_chat
from ..llm_client import chat_stream as llm_chat_stream
from ..styles import manager as style_manager
from ..utils import safe_json_parse
from .character_agent import CharacterAgent, CharacterProfile
from .hot_choices_agent import HotChoicesAgent
from .simulation_store import SimulationStore, TurnEvent

logger = logging.getLogger(__name__)

NARRATOR_SYSTEM_PROMPT = """你是一个小说推演叙事引擎。每回合必须隐式执行以下7步裁定循环：

## 回合裁定循环（隐式执行，不要输出分析过程）
1. 识别用户行动：区分行动/对白/观察/提问，提取目标、手段、风险、涉及对象和隐含意图
2. 判断相关上下文：只调动本轮相关的在场角色、角色状态、关系、规则、未解决线索
3. 裁定后果：行动必须带来具体反馈，至少包含成功/部分成功/失败/代价/发现/阻碍中的一种
4. 推进场景：用小说正文呈现动作、感官、对白、环境反馈和角色主动反应
5. 保留选择权：不要替用户完成重大选择、不可逆决定或长期目标
6. 打开可选择：回合结尾自然露出可继续行动的入口（可询问的人、可探索的物、逼近的危险、可利用的资源等）
7. 一致性自检：确认角色性格、说话方式、世界规则、已记录状态没有被遗忘或矛盾改写

## 叙事原则
- 叙事紧凑有张力，每段200-400字
- 其他角色有主观能动性：他们会依据性格、关系、目标主动反应
- 正文只写场景、动作、对白和后果，不要把下一步行动整理成菜单列表

## 角色主视角模式
- 以第三人称叙述主视角角色的经历和内心世界
- 侧重描写主视角角色的感官体验和心理活动
- 其他角色通过主视角的观察来呈现

## 叙事者主视角模式
- 以全知视角叙述多个角色的行动和互动
- 平衡展示不同角色的反应和冲突
- 展现角色间的冲突、合作和情感张力

## 输出格式
直接输出纯文本叙事内容，不要输出JSON、不要输出选项、不要包裹在代码块中。
叙事结束后自然结束即可。"""

OPTIONS_SYSTEM_PROMPT = """你是一个小说推演选项生成器。根据给定的叙事文本和上下文，生成2-4个选项供用户选择。

## 输出格式（严格JSON）
{
  "prompt": "用一句话描述当前选择情境（如'张三面临追兵，你选择：'）",
  "options": [
    {"text": "选项文本（15字以内）", "description": "此选项可能导致的后果简述"},
    ...
  ]
}

角色主视角模式的选项是角色可采取的行动（如"拔剑迎战"、"转身逃离"）。
叙事者主视角模式的选项是后续可设定的客观条件（如"敌军发起进攻"、"援军到达"）。
prompt字段必须简明扼要地描述用户当前面临的选择情境。"""


class NarratorAgent:
    """推演中央调度器 — 双模式 + SSE流式 + 裁定循环 + 记忆压缩."""

    def __init__(self, book_id: str):
        self.book_id = book_id
        self.graph = GraphStore(project_id=book_id)
        self.store = SimulationStore(book_id)
        self.char_agent = CharacterAgent(book_id)
        self.choices_agent = HotChoicesAgent(book_id)

    # ── 启动推演 ──

    async def start(
        self,
        sim_id: str,
        mode: str,
        setting: str,
        character_ids: list[str],
        pov_character_id: str | None = None,
        style_name: str | None = None,
        reference_book_ids: list[str] | None = None,
        timeline_event_id: str | None = None,
        user_supplement: str = "",
    ) -> AsyncGenerator[dict, None]:
        """启动推演，生成开场叙事。SSE事件流.

        Yields SSE events: config_preview → narrator_synthesizing → narrative_chunk
                          → choices_ready → hot_choices → done
        """
        session = self.store.get_session(sim_id)
        if not session:
            yield {"type": "error", "message": "推演会话不存在"}
            return

        # Build character profiles
        profiles = self.char_agent.build_profiles_batch(character_ids)
        if not profiles:
            yield {"type": "error", "message": "无法构建角色画像，请检查知识库中是否有角色数据"}
            return

        # Graph insights — only for config preview, skip on timeout
        insights = {}
        try:
            loop = asyncio.get_running_loop()
            insights = await asyncio.wait_for(
                loop.run_in_executor(None, self.graph.get_graph_insights),
                timeout=10.0,
            )
        except TimeoutError:
            logger.info("Graph insights timed out (10s), skipping for推演 start")
        except Exception:
            insights = {}

        # Get open foreshadows
        foreshadows = self._get_open_foreshadows()

        # Load timeline event context if specified
        timeline_event = None
        if timeline_event_id:
            timeline_event = self._load_timeline_event(timeline_event_id)
            if not timeline_event:
                yield {"type": "error", "message": f"时间线事件 {timeline_event_id} 不存在"}
                return

        # ── Emit config preview ──
        config_preview = {
            "characters": [
                {
                    "id": p.character_id,
                    "name": p.name,
                    "personality": p.personality[:120] if p.personality else "",
                    "phase": (p.current_phase or {}).get("phase", "未分阶段"),
                    "relationships_count": len(p.relationships),
                    "skills": p.skills[:5],
                    "is_pov": p.character_id == pov_character_id,
                }
                for p in profiles.values()
            ],
            "graph_insights": {
                "forgotten_characters": [
                    c.get("name", "") for c in insights.get("forgotten_characters", [])[:5]
                ],
                "unresolved_foreshadows": len(insights.get("unresolved_foreshadows", [])),
            },
            "timeline_event": timeline_event,
            "user_supplement": user_supplement,
            "setting": setting,
        }
        yield {"type": "config_preview", "data": config_preview}

        # Build context
        context = self._build_initial_context(
            setting=setting, mode=mode, profiles=profiles,
            pov_character_id=pov_character_id, foreshadows=foreshadows,
            insights=insights, timeline_event=timeline_event,
            user_supplement=user_supplement, style_name=style_name,
            reference_book_ids=reference_book_ids,
        )

        # Generate via streaming
        yield {"type": "narrator_synthesizing"}

        full_text = ""
        async for chunk in self._stream_llm(context, NARRATOR_SYSTEM_PROMPT, 0.8):
            full_text += chunk
            yield {"type": "narrative_chunk", "text": chunk}

        narrative = full_text.strip()

        # Generate options separately
        yield {"type": "generating_options"}
        options, choice_prompt = await self._generate_options(narrative, mode, sim_id, setting)

        # Store as TurnEvent
        turn = TurnEvent(
            id=sim_id,
            branch_id=sim_id,
            narrative=narrative,
            turn_number=0,
            user=setting,
        )
        self.store.append_turn(sim_id, turn)

        # Store choices
        choice_type = "action" if mode == "character_pov" else "condition"
        stored_choices = []
        for opt in options[:4]:
            choice = self.store.add_choice(
                event_id=turn.id, sim_id=sim_id,
                text=opt.get("text", str(opt)) if isinstance(opt, dict) else str(opt),
                description=opt.get("description", "") if isinstance(opt, dict) else "",
                choice_type=choice_type,
            )
            if choice:
                stored_choices.append(choice)

        # Persist choices to JSONL for session reload
        self.store.append_choices(sim_id, turn.id, stored_choices)

        # Generate hot choices
        yield {"type": "generating_hot_choices"}
        state = self.store.get_latest_state(sim_id)
        hot_choices = await self.choices_agent.generate(
            narrative=narrative,
            state=state,
            user_action=setting,
        )
        if hot_choices:
            self.store.append_hot_choices(sim_id, turn.id, hot_choices)

        self.store.update_session(sim_id, turn_count=1)

        yield {"type": "choices_ready", "choices": stored_choices, "choice_prompt": choice_prompt, "event_id": turn.id}
        if hot_choices:
            yield {"type": "hot_choices", "choices": hot_choices}
        yield {"type": "done", "turn": 0, "event_id": turn.id}

    # ── 处理回合 ──

    async def process_turn(
        self,
        sim_id: str,
        choice_text: str = "",
        choice_id: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """处理用户选择，生成下一回合。SSE事件流."""
        session = self.store.get_session(sim_id)
        if not session:
            yield {"type": "error", "message": "推演会话不存在"}
            return

        mode = session.get("mode", "character_pov")
        history = self.store.get_turns(sim_id)

        # Dispatch to mode-specific handler
        if mode == "character_pov":
            async for event in self._character_pov_turn(sim_id, session, choice_text, history):
                yield event
        else:
            async for event in self._narrator_pov_turn(sim_id, session, choice_text, history):
                yield event

    # ── 角色主视角模式 ──

    async def _character_pov_turn(
        self,
        sim_id: str,
        session: dict,
        choice_text: str,
        history: list[dict],
    ) -> AsyncGenerator[dict, None]:
        """角色主视角模式回合处理."""
        pov_char_id = session.get("pov_character_id")
        if not pov_char_id:
            yield {"type": "error", "message": "角色主视角模式需要主视角角色ID"}
            return

        pov_profile = self.char_agent.build_profile(pov_char_id)
        if not pov_profile:
            yield {"type": "error", "message": "无法构建主视角角色画像"}
            return

        turn_number = session.get("turn_count", 0)

        # 1. Character thinks
        yield {"type": "character_thinking", "character": pov_profile.name}

        # 2. Get character response
        char_response = await self.char_agent.respond(
            profile=pov_profile,
            situation=choice_text or session.get("setting", "推演开始"),
            history=history,
            mode="character_pov",
        )

        yield {"type": "character_response", "data": char_response, "character": pov_profile.name}

        # 3. Narrator synthesizes
        yield {"type": "narrator_synthesizing"}

        # Build synthesis prompt with memory compaction + state
        prompt = self._build_synthesis_prompt(
            mode="character_pov",
            sim_id=sim_id,
            pov_profile=pov_profile,
            char_responses=[{**char_response, "character_name": pov_profile.name}],
            history=history,
            user_action=choice_text,
            setting=session.get("setting", ""),
            style_name=session.get("style_name"),
        )

        full_text = ""
        async for chunk in self._stream_llm(prompt, NARRATOR_SYSTEM_PROMPT, 0.8):
            full_text += chunk
            yield {"type": "narrative_chunk", "text": chunk}

        narrative = full_text.strip()

        # Generate options
        yield {"type": "generating_options"}
        options, choice_prompt = await self._generate_options(narrative, "character_pov", sim_id, choice_text)

        # 4. Store turn event
        turn = TurnEvent(
            branch_id=session.get("current_branch", sim_id),
            narrative=narrative,
            turn_number=turn_number,
            user=choice_text,
        )
        self.store.append_turn(sim_id, turn)

        # 5. Store choices
        stored_choices = []
        for opt in options[:4]:
            choice = self.store.add_choice(
                event_id=turn.id, sim_id=sim_id,
                text=opt.get("text", str(opt)) if isinstance(opt, dict) else str(opt),
                description=opt.get("description", "") if isinstance(opt, dict) else "",
                choice_type="action",
            )
            if choice:
                stored_choices.append(choice)

        # Persist choices to JSONL for session reload
        self.store.append_choices(sim_id, turn.id, stored_choices)

        # 6. Generate hot choices
        yield {"type": "generating_hot_choices"}
        state = self.store.get_latest_state(sim_id)
        hot_choices = await self.choices_agent.generate(
            narrative=narrative,
            state=state,
            user_action=choice_text,
            recent_turns=history,
        )
        if hot_choices:
            self.store.append_hot_choices(sim_id, turn.id, hot_choices)

        self.store.update_session(sim_id, turn_count=turn_number + 1)

        yield {"type": "choices_ready", "choices": stored_choices, "choice_prompt": choice_prompt, "event_id": turn.id}
        if hot_choices:
            yield {"type": "hot_choices", "choices": hot_choices}
        yield {"type": "done", "turn": turn_number, "event_id": turn.id}

    # ── 叙事者主视角模式 ──

    async def _narrator_pov_turn(
        self,
        sim_id: str,
        session: dict,
        choice_text: str,
        history: list[dict],
    ) -> AsyncGenerator[dict, None]:
        """叙事者主视角模式回合处理."""
        involved_ids = session.get("involved_character_ids", [])
        if not involved_ids:
            yield {"type": "error", "message": "叙事者模式需要至少一个参与角色"}
            return

        turn_number = session.get("turn_count", 0)
        condition = choice_text or session.get("condition") or session.get("setting", "推演开始")

        # 1. Build profiles
        profiles = self.char_agent.build_profiles_batch(involved_ids)
        if not profiles:
            yield {"type": "error", "message": "无法构建角色画像"}
            return

        # 2. Wake all characters in parallel
        yield {"type": "analyzing_condition", "condition": condition}

        for pid, profile in profiles.items():
            yield {"type": "character_thinking", "character": profile.name}

        tasks = []
        for pid, profile in profiles.items():
            tasks.append(
                self.char_agent.respond(
                    profile=profile,
                    situation=condition,
                    history=history,
                    mode="narrator_pov",
                )
            )

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        char_responses = []
        for i, (pid, profile) in enumerate(profiles.items()):
            resp = responses[i]
            if isinstance(resp, Exception):
                resp = {
                    "perception": "（角色响应失败）",
                    "thoughts": str(resp)[:100],
                    "action": "无",
                    "dialogue": "",
                }
            resp_with_name = {**resp, "character_name": profile.name, "character_id": pid}
            char_responses.append(resp_with_name)
            yield {"type": "character_response", "data": resp, "character": profile.name}

        # 3. Narrator synthesizes with memory compaction + state
        yield {"type": "narrator_synthesizing"}

        prompt = self._build_synthesis_prompt(
            mode="narrator_pov",
            sim_id=sim_id,
            char_responses=char_responses,
            history=history,
            user_action=condition,
            setting=session.get("setting", ""),
            style_name=session.get("style_name"),
        )

        full_text = ""
        async for chunk in self._stream_llm(prompt, NARRATOR_SYSTEM_PROMPT, 0.8):
            full_text += chunk
            yield {"type": "narrative_chunk", "text": chunk}

        narrative = full_text.strip()

        # Generate options
        yield {"type": "generating_options"}
        options, choice_prompt = await self._generate_options(narrative, "narrator_pov", sim_id, condition)

        # 4. Store turn event
        turn = TurnEvent(
            branch_id=session.get("current_branch", sim_id),
            narrative=narrative,
            turn_number=turn_number,
            user=condition,
        )
        self.store.append_turn(sim_id, turn)

        # 5. Store choices
        stored_choices = []
        for opt in options[:4]:
            choice = self.store.add_choice(
                event_id=turn.id, sim_id=sim_id,
                text=opt.get("text", str(opt)) if isinstance(opt, dict) else str(opt),
                description=opt.get("description", "") if isinstance(opt, dict) else "",
                choice_type="condition",
            )
            if choice:
                stored_choices.append(choice)

        # Persist choices to JSONL for session reload
        self.store.append_choices(sim_id, turn.id, stored_choices)

        # 6. Generate hot choices
        yield {"type": "generating_hot_choices"}
        state = self.store.get_latest_state(sim_id)
        hot_choices = await self.choices_agent.generate(
            narrative=narrative,
            state=state,
            user_action=condition,
            recent_turns=history,
        )
        if hot_choices:
            self.store.append_hot_choices(sim_id, turn.id, hot_choices)

        self.store.update_session(sim_id, turn_count=turn_number + 1)

        yield {"type": "choices_ready", "choices": stored_choices, "choice_prompt": choice_prompt, "event_id": turn.id}
        if hot_choices:
            yield {"type": "hot_choices", "choices": hot_choices}
        yield {"type": "done", "turn": turn_number, "event_id": turn.id}

    # ── 选项生成 ──

    async def _generate_options(
        self, narrative: str, mode: str, sim_id: str, context: str = ""
    ) -> tuple[list[dict], str]:
        """Generate options and a choice prompt based on the narrative."""
        mode_label = "角色主视角-生成行动选项" if mode == "character_pov" else "叙事者主视角-生成条件选项"
        prompt = (
            f"## 叙事文本\n{narrative[:800]}\n\n"
            f"## 模式\n{mode_label}\n\n"
            f"## 上下文\n{context[:200]}\n\n"
            f"请生成2-4个选项和选择情境描述。"
        )

        loop = asyncio.get_running_loop()
        try:
            content = await loop.run_in_executor(
                None,
                lambda: llm_chat(
                    prompt=prompt, system=OPTIONS_SYSTEM_PROMPT,
                    temperature=0.5, task="general",
                ),
            )
            result = safe_json_parse(content, default=None)
            if result and isinstance(result, dict):
                opts = result.get("options", [])[:4]
                choice_prompt = result.get("prompt", "")
                if opts:
                    return opts, choice_prompt
        except Exception as e:
            logger.warning("Options generation failed: %s, using graph insights", e)

        fallback_opts = self._generate_graph_insight_options(sim_id, context)
        fallback_prompt = (
            f"{('角色面临抉择，你选择：' if mode == 'character_pov' else '剧情将如何发展？选择一个条件：')}"
        )
        return fallback_opts, fallback_prompt

    def _generate_graph_insight_options(self, sim_id: str, context: str) -> list[dict]:
        """利用图谱洞察生成有意义的选项作为兜底."""
        options = []
        try:
            insights = self.graph.get_graph_insights()
        except Exception:
            insights = {}

        forgotten = insights.get("forgotten_characters", [])
        for char in forgotten[:2]:
            options.append({
                "text": f"想起{char.get('name', '某人')}",
                "description": "已多章未出场的角色，可以安排重新登场",
                "type": "action",
            })

        unresolved = insights.get("unresolved_foreshadows", [])
        for f in unresolved[:2]:
            text = f.get("text", "")[:20]
            options.append({
                "text": f"推进伏笔：{text}",
                "description": "尝试回收或推进一条未解决的伏笔",
                "type": "action",
            })

        if len(options) < 2:
            options.extend([
                {"text": "继续推进当前剧情", "description": "沿着当前方向发展", "type": "action"},
                {"text": "引入意外变数", "description": "制造新的冲突或转折", "type": "action"},
            ])

        return options[:4]

    # ── 初始上下文构建 ──

    def _build_initial_context(
        self,
        setting: str,
        mode: str,
        profiles: dict[str, CharacterProfile],
        pov_character_id: str | None = None,
        foreshadows: list | None = None,
        insights: dict | None = None,
        timeline_event: dict | None = None,
        user_supplement: str = "",
        style_name: str | None = None,
        reference_book_ids: list[str] | None = None,
    ) -> str:
        """构建推演开局上下文."""
        parts = ["## 推演开局"]

        if setting:
            parts.append(f"开局设定: {setting}")

        # Timeline event context
        if timeline_event:
            parts.append("\n## 正文事件起点")
            parts.append(f"事件: {timeline_event.get('label', '未知事件')}")
            if timeline_event.get('description'):
                parts.append(f"描述: {timeline_event['description'][:300]}")
            if timeline_event.get('time_label'):
                parts.append(f"时间: {timeline_event['time_label']}")
            if timeline_event.get('chapter_ref'):
                parts.append(f"章节: {timeline_event['chapter_ref']}")
            involved_chars = timeline_event.get('characters', [])
            if involved_chars:
                parts.append(f"涉及角色: {', '.join(involved_chars[:5])}")

        # User supplement
        if user_supplement:
            parts.append(f"\n## 用户补充说明\n{user_supplement}")

        # Character profiles
        parts.append("\n## 参与角色")
        for pid, profile in profiles.items():
            parts.append(f"- {profile.name}: {profile.personality[:100]}")

        if mode == "character_pov" and pov_character_id:
            pov_profile = profiles.get(pov_character_id)
            if pov_profile:
                parts.append(f"\n## 主视角角色: {pov_profile.name}")

        # Foreshadows
        if foreshadows:
            parts.append("\n## 开放伏笔")
            for f in foreshadows[:5]:
                parts.append(f"- {f.get('text', '')[:100]}")

        # Graph insights
        if insights:
            forgotten = insights.get("forgotten_characters", [])
            if forgotten:
                parts.append(f"\n## 图谱提示: 遗忘角色: {', '.join(c.get('name','') for c in forgotten[:3])}")

        # Style
        if style_name:
            style_ctx = style_manager.build_style_context(style_name)
            if style_ctx:
                parts.append(f"\n## 写作风格约束（{style_name}）\n{style_ctx}")

        strategy_prompt = style_manager.get_narrative_strategy_prompt(self.book_id, style_name or "")
        if strategy_prompt:
            parts.append(f"\n{strategy_prompt}")

        # Reference books
        if reference_book_ids:
            ref_ctx = self._load_reference_book_context(reference_book_ids)
            if ref_ctx:
                parts.append(f"\n## 参考书设定约束\n{ref_ctx}")

        return "\n".join(parts)

    # ── 叙事综合上下文构建（含记忆压缩 + 状态注入） ──

    def _build_synthesis_prompt(
        self,
        mode: str,
        sim_id: str,
        char_responses: list[dict] | None = None,
        history: list[dict] | None = None,
        user_action: str = "",
        setting: str = "",
        style_name: str | None = None,
        pov_profile: CharacterProfile | None = None,
    ) -> str:
        """构建叙事综合的 LLM prompt.

        特性：
        - 记忆压缩：最近N回合完整 + 较早回合摘要
        - 结构化状态注入
        """
        parts = []

        # User action context
        if user_action:
            parts.append(f"## 用户本轮行动\n{user_action[:300]}")

        # POV character
        if mode == "character_pov" and pov_profile:
            parts.append(f"## 主视角角色: {pov_profile.name}")
            parts.append(f"性格: {pov_profile.personality[:100]}")

        # Character responses
        if char_responses:
            parts.append("\n## 角色行动与反应")
            for resp in char_responses:
                name = resp.get("character_name", "未知角色")
                parts.append(f"\n### {name}")
                if resp.get("perception"):
                    parts.append(f"感知: {resp['perception']}")
                if resp.get("thoughts"):
                    parts.append(f"内心: {resp['thoughts']}")
                if resp.get("action"):
                    parts.append(f"行动: {resp['action']}")
                if resp.get("dialogue"):
                    parts.append(f"台词: 「{resp['dialogue']}」")

        # Memory compaction
        if history:
            summary, recent = self.store.build_memory_context(sim_id, recent_limit=6)
            if summary:
                parts.append(f"\n## 较早剧情记忆\n{summary}")

            if recent:
                parts.append("\n## 最近剧情（请自然延续，不要重复）")
                for ev in recent[-3:]:
                    tn = ev.get("turn_number", "?")
                    user = (ev.get("user", "") or "")[:100]
                    nar = (ev.get("narrative", "") or ev.get("content", ""))[:200]
                    if user:
                        parts.append(f"[回合{tn}用户]: {user}")
                    parts.append(f"[回合{tn}剧情]: {nar}")

        # Structured state injection
        try:
            state = self.store.get_latest_state(sim_id)
            if state:
                state_preview = self._summarize_state_for_prompt(state)
                if state_preview:
                    parts.append(f"\n## 当前推演状态\n{state_preview}")
        except Exception:
            pass

        if setting:
            parts.append(f"\n## 开局设定: {setting}")

        # Style
        if style_name:
            style_ctx = style_manager.build_style_context(style_name)
            if style_ctx:
                parts.append(f"\n## 写作风格约束\n{style_ctx}")

        strategy_prompt = style_manager.get_narrative_strategy_prompt(self.book_id, style_name or "")
        if strategy_prompt:
            parts.append(f"\n{strategy_prompt}")

        mode_instruction = (
            "\n\n请以角色主视角模式综合以上信息，继续推进剧情。"
            "将角色的感知、内心活动和台词自然融入叙事中。"
            "剧情必须向前推进，不要重复已发生的内容。"
            if mode == "character_pov"
            else "\n\n请以叙事者全知视角模式综合以上角色反应，继续推进剧情。"
            "展现角色间的互动和冲突发展，不要重复已发生的内容。"
        )

        return NARRATOR_SYSTEM_PROMPT + "\n\n" + "\n".join(parts) + mode_instruction

    def _summarize_state_for_prompt(self, state: dict) -> str:
        """Summarize structured state for prompt injection."""
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
        time_str = state.get("time", "")
        if time_str:
            summaries.append(f"时间: {time_str[:30]}")
        characters = state.get("characters", {})
        if characters:
            char_states = []
            for name, info in list(characters.items())[:3]:
                if isinstance(info, dict):
                    parts = [name]
                    if info.get("status"):
                        parts.append(f"状态={info['status']}")
                    if info.get("mood"):
                        parts.append(f"情绪={info['mood']}")
                    char_states.append("(" + " ".join(parts) + ")")
            if char_states:
                summaries.append("角色: " + "; ".join(char_states))
        threads = state.get("threads", [])
        if threads and isinstance(threads, list):
            summaries.append(f"线索: {'; '.join(str(t)[:25] for t in threads[:3])}")
        return " | ".join(summaries)

    # ── 流式 LLM 调用 ──

    async def _stream_llm(
        self, prompt: str, system: str, temperature: float = 0.8
    ) -> AsyncGenerator[str, None]:
        """异步包装同步 chat_stream 生成器."""
        loop = asyncio.get_running_loop()
        stream_failed = False
        connection_error = False
        queue: asyncio.Queue = asyncio.Queue()

        async def _producer():
            nonlocal stream_failed, connection_error
            def _run_sync():
                try:
                    for chunk in llm_chat_stream(
                        prompt=prompt, system=system,
                        temperature=temperature, task="writing",
                    ):
                        asyncio.run_coroutine_threadsafe(queue.put(chunk), loop)
                    asyncio.run_coroutine_threadsafe(
                        queue.put(None), loop
                    )
                except Exception as e:
                    error_msg = str(e).lower()
                    if "connection" in error_msg:
                        logger.error("LLM connection error: %s", e)
                    elif "timeout" in error_msg or "timed out" in error_msg:
                        logger.warning("Stream LLM timed out, will fall back to non-streaming: %s", e)
                    else:
                        logger.error("Stream LLM error: %s", e)
                    asyncio.run_coroutine_threadsafe(
                        queue.put(None), loop
                    )

            await loop.run_in_executor(None, _run_sync)

        producer_task = asyncio.create_task(_producer())
        collected = ""
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                collected += chunk
                yield chunk
        finally:
            if not producer_task.done():
                producer_task.cancel()

        if connection_error and not collected:
            yield "[LLM API连接失败，请检查API配置（密钥、地址、网络）后重试]"
            return

        if stream_failed and not collected:
            logger.info("Falling back to non-streaming LLM call")
            try:
                content = await loop.run_in_executor(
                    None,
                    lambda: llm_chat(
                        prompt=prompt, system=system,
                        temperature=temperature, task="writing",
                    ),
                )
                if content:
                    yield content
                else:
                    yield "[叙事生成失败，请重试]"
            except Exception as e2:
                logger.error("Non-streaming fallback also failed: %s", e2)
                yield f"[生成失败: {str(e2)[:100]}，请检查API配置后重试]"

    # ── 辅助方法 ──

    def _get_open_foreshadows(self) -> list[dict]:
        """获取未解决的伏笔."""
        try:
            results = self.graph._run(
                """
                MATCH (f:Fore)
                WHERE f.resolved = false OR f.resolved IS NULL
                RETURN f ORDER BY f.created_at DESC LIMIT 10
                """,
                {},
            )
            return [dict(r["f"]) for r in results]
        except Exception:
            return []

    def _load_reference_book_context(self, ref_book_ids: list[str]) -> str:
        """加载参考书设定上下文."""
        try:
            from data.json_store import json_store
            parts = []
            for ref_id in ref_book_ids[:3]:
                try:
                    ref_book = json_store.get_book(ref_id)
                    title = ref_book.get("title", ref_id)
                    parts.append(f"### {title}")
                    outline = json_store.load_outline(ref_id)
                    if outline:
                        parts.append(f"大纲: {str(outline)[:300]}")
                    wb = json_store.load_worldbuilding(ref_id)
                    if wb and isinstance(wb, dict):
                        entries = wb.get("entries", wb) if isinstance(wb, dict) else {}
                        if isinstance(entries, list) and entries:
                            parts.append(
                                f"核心设定({len(entries)}条): "
                                + "; ".join(
                                    str(e.get("name", e))[:80]
                                    for e in entries[:5]
                                    if isinstance(e, dict)
                                )
                            )
                except Exception:
                    continue
            return "\n".join(parts) if parts else ""
        except Exception:
            return ""

    def _load_timeline_event(self, event_id: str) -> dict | None:
        """加载正文时间线事件详情，用于从事件点启动推演."""
        try:
            rows = self.graph._run(
                """
                MATCH (t:Timeline {id: $eid, project_id: $pid})
                OPTIONAL MATCH (t)-[:INVOLVES|TIMELINE_INVOLVES]->(c:Entity:Character {project_id: $pid})
                RETURN t.id AS id, t.label AS label, t.description AS desc,
                       t.time_label AS time_label, t.chapter_ref AS cr,
                       t.time_order AS tord,
                       collect(c.name) AS characters
                """,
                {"eid": event_id, "pid": self.book_id},
            )
            if not rows:
                return None
            r = rows[0]
            return {
                "id": r.get("id", event_id),
                "label": r.get("label", ""),
                "description": r.get("desc", ""),
                "time_label": r.get("time_label", ""),
                "chapter_ref": r.get("cr", ""),
                "time_order": r.get("tord", 0),
                "characters": [c for c in r.get("characters", []) if c],
            }
        except Exception as e:
            logger.debug("Failed to load timeline event %s: %s", event_id, e)
            return None
