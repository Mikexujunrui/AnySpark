"""Interactive Scenario Agent — generates narrative segments with choices and foreshadow tracking.

Uses the LLM client for generation, with system prompts tailored for plot simulation.
Integrates with the knowledge graph for character, setting, foreshadow, style, and reference book context.
"""

import json
import logging

from .graph_store import GraphStore
from .llm_client import chat as llm_chat
from .styles import manager as style_manager

logger = logging.getLogger(__name__)

INTERACTIVE_SYSTEM_PROMPT = """你是一个剧情推演引擎。根据设定和历史，生成一段引人入胜的叙事，并在结尾提供2-4个选项。

## 核心规则
1. 每段叙事200-500字，保持紧凑有张力
2. 叙事必须以第二人称"你"来描述主角的视角和行动
3. 必须严格遵循已有的世界观设定和角色性格
4. 选项应导向不同的剧情发展方向
5. 选项要简短（15字以内），但指向明确
6. 每段叙事末尾，自然引出选择点

## 伏笔规则
- 注意已有的开放伏笔，在合适的时机推动或回收
- 不要一次性回收所有伏笔，保持叙事张力
- 新引入的伏笔需要在输出中标注

## 输出格式（严格JSON）
{
  "narrative": "叙事内容...",
  "choices": [
    {"text": "选项文本", "description": "此选项可能的后果简述"},
    ...
  ],
  "foreshadow_updates": [
    {"fore_id": "伏笔ID", "action": "triggers|advances|resolves", "detail": "具体更新说明"},
    ...
  ]
}

如果当前回合没有伏笔变化，foreshadow_updates 可以是空数组。"""


class InteractiveAgent:
    """Handles LLM-based interactive story generation."""

    def __init__(self, book_id: str):
        self.book_id = book_id
        self.graph = GraphStore(project_id=book_id)

    def _build_context(self, branch_name: str, history: list[dict], turn_number: int) -> str:
        """Build the context string for the LLM prompt."""
        parts = [f"当前分支: {branch_name}"]
        parts.append(f"回合: {turn_number + 1}")

        # Recent history (last 5 events for context)
        if history:
            recent = history[-5:]
            parts.append("\n## 近期叙事")
            for ev in recent:
                content_preview = ev.get("content", "")[:200]
                parts.append(f"[回合{ev.get('turn_number', '?')}] {content_preview}...")

        return "\n".join(parts)

    async def start(
        self,
        branch_id: str,
        chapter_id: str | None = None,
        setting: str | None = None,
        character_ids: list[str] = None,
        style_name: str | None = None,
        reference_book_ids: list[str] = None,
    ) -> dict:
        """Generate the opening narrative for a new plot simulation."""
        context_parts = ["## 剧情推演开端"]

        if chapter_id:
            # Load chapter content for context
            chapters = self._load_chapters()
            chapter = next((c for c in chapters if c.get("id") == chapter_id), None)
            if chapter:
                preview = chapter.get("content", "")[:800]
                context_parts.append(f"基于以下章节开始剧情推演:\n{preview}")

        if setting:
            context_parts.append(f"开局设定: {setting}")

        if character_ids:
            chars = self._load_characters(character_ids)
            if chars:
                context_parts.append("\n## 主要角色")
                for c in chars:
                    desc = (c.get('data') or {}).get('description', '')
                    context_parts.append(f"- {c.get('name', '未知')}: {desc[:100]}")

        # Get open foreshadows
        foreshadows = self._get_open_foreshadows()
        if foreshadows:
            context_parts.append("\n## 开放伏笔（需要在故事中关注）")
            for f in foreshadows[:5]:
                context_parts.append(f"- [{f.get('id', '')[:8]}] {f.get('text', '')[:120]}")

        # Inject style context
        if style_name:
            style_context = style_manager.build_style_context(style_name)
            if style_context:
                context_parts.append(f"\n## 写作风格约束（{style_name}）\n{style_context}")

        # Inject reference book content
        if reference_book_ids:
            ref_context = self._load_reference_book_context(reference_book_ids)
            if ref_context:
                context_parts.append(f"\n## 参考书设定约束\n{ref_context}")

        context = "\n".join(context_parts)
        prompt = f"{INTERACTIVE_SYSTEM_PROMPT}\n\n{context}\n\n请生成剧情推演的开始叙事和初始选项。"

        result = await self._generate(prompt)
        return result

    async def continue_story(
        self,
        branch_id: str,
        branch_name: str,
        user_choice: str,
        history: list[dict],
        turn_number: int,
    ) -> dict:
        """Generate the next narrative segment after a user choice."""
        context = self._build_context(branch_name, history, turn_number)

        # Get relevant characters and foreshadows
        chars = self._load_characters()
        if chars:
            active_chars = chars[:5]
            context += "\n\n## 当前活跃角色（参考，勿超出）"
            for c in active_chars:
                name = c.get('name') or '未知'
                context += f"\n- {name}"

        foreshadows = self._get_open_foreshadows()
        if foreshadows:
            context += "\n\n## 开放伏笔"
            for f in foreshadows[:3]:
                context += f"\n- {f.get('text', '')[:120]}"

        context += f"\n\n## 玩家的选择\n{user_choice}"
        context += "\n\n请根据玩家的选择，继续生成下一段叙事。"

        prompt = f"{INTERACTIVE_SYSTEM_PROMPT}\n\n{context}"
        result = await self._generate(prompt)
        return result

    async def _generate(self, prompt: str) -> dict:
        """Call LLM and parse JSON response."""
        import asyncio
        content = ""
        try:
            loop = asyncio.get_running_loop()
            content = await loop.run_in_executor(
                None,
                lambda: llm_chat(prompt=prompt, system=INTERACTIVE_SYSTEM_PROMPT, temperature=0.9, task="writing"),
            )
            if not content:
                return {"narrative": "（生成失败，请重试）", "choices": [], "foreshadow_updates": []}

            # Extract JSON from response
            json_str = content
            # Find first { and last }
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                json_str = content[start:end + 1]

            result = json.loads(json_str)
            return {
                "narrative": result.get("narrative", content),
                "choices": result.get("choices", []),
                "foreshadow_updates": result.get("foreshadow_updates", []),
            }
        except json.JSONDecodeError:
            logger.warning("Failed to parse interactive agent JSON response")
            return {
                "narrative": content if content else "（生成失败）",
                "choices": [{"text": "继续", "description": ""}],
                "foreshadow_updates": [],
            }
        except Exception as e:
            logger.error("Interactive agent generation failed: %s", e, exc_info=True)
            return {
                "narrative": f"（生成出错: {str(e)[:200]}）",
                "choices": [{"text": "重试", "description": ""}],
                "foreshadow_updates": [],
            }

    def _load_chapters(self) -> list[dict]:
        """Load chapters for this book."""
        try:
            from data.json_store import json_store
            return json_store.load_chapters(self.book_id)
        except Exception:
            return []

    def _load_characters(self, character_ids: list[str] = None) -> list[dict]:
        """Load character entities from graph. Returns dicts for safe usage."""
        try:
            entities = self.graph.list_entities(entity_type="character")
            # Convert Entity dataclass objects to dicts for .get() compatibility
            result = []
            for e in entities:
                d = {"id": e.id, "name": e.name, "type": e.type, "data": e.data}
                if character_ids is None or e.id in character_ids:
                    result.append(d)
            return result
        except Exception:
            return []

    def _load_reference_book_context(self, ref_book_ids: list[str]) -> str:
        """Load summary/outline from reference books for context injection."""
        try:
            from data.json_store import json_store
            parts = []
            for ref_id in ref_book_ids[:3]:  # max 3 reference books
                try:
                    ref_book = json_store.get_book(ref_id)
                    title = ref_book.get("title", ref_id)
                    parts.append(f"### {title}")
                    # Load outline summary
                    outline = json_store.load_outline(ref_id)
                    if outline:
                        parts.append(f"大纲: {str(outline)[:300]}")
                    # Load worldbuilding summary
                    wb = json_store.load_worldbuilding(ref_id)
                    if wb and isinstance(wb, dict):
                        entries = wb.get("entries", wb) if isinstance(wb, dict) else {}
                        if isinstance(entries, list) and entries:
                            parts.append(f"核心设定({len(entries)}条): " + "; ".join(
                                str(e.get("name", e))[:80] for e in entries[:5] if isinstance(e, dict)
                            ))
                except Exception:
                    continue
            return "\n".join(parts) if parts else ""
        except Exception:
            return ""

    def _get_open_foreshadows(self) -> list[dict]:
        """Get unresolved foreshadows from graph."""
        try:
            query = """
            MATCH (f:Fore)
            WHERE f.resolved = false OR f.resolved IS NULL
            RETURN f ORDER BY f.created_at DESC LIMIT 10
            """
            results = self.graph._run(query, {})
            return [dict(r["f"]) for r in results]
        except Exception:
            return []
