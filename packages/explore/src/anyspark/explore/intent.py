"""
anyspark.explore.intent — 意图理解者（种子 → 对齐确认）。

设计（DESIGN 机制 7）：意图理解者产出"对齐确认"而非方向——两阶段：
意图确认 → 方向探索。对齐确认先给用户看（摩擦前置最便宜的纠错点）。
"""

from __future__ import annotations

import json
import re
from typing import Any

from anyspark.core.types import Message

INTENT_PROMPT = """你是小说创作协作的意图理解者。用户给出写作种子/意图，请产出**对齐确认**，包含：
1. 概念卡：把用户的话复述成清晰的概念（画面核心/情绪基调/类型直觉/种子位置）
2. 关键歧义点：只问 2-3 个影响方向的问题（AI 提问=不确定性信号，只问关键歧义）

输出格式（严格 JSON，不要其它文字）：
{
  "concept": {
    "core": "画面核心一句话",
    "mood": "情绪基调",
    "genre": "类型直觉",
    "seed_position": "开篇|高潮|结局|未知"
  },
  "questions": ["问题1", "问题2", "问题3"]
}

用户种子：
"""


class IntentUnderstander:
    """意图理解者：真实 LLM 把种子转成概念卡 + 关键歧义点。"""

    def __init__(self, model: object) -> None:
        self._model = model

    def understand(self, seed: str) -> dict[str, Any]:
        prompt = INTENT_PROMPT + seed
        output = self._model.respond(  # type: ignore[attr-defined]
            [Message(role="system", content=prompt)],
            [],
        )
        return _parse_concept(output.text, seed)

    def build_confirmation(self, concept: dict[str, Any]) -> str:
        """把概念卡渲染成用户可见的对齐确认。"""
        c = concept.get("concept", {})
        qs = concept.get("questions", [])
        lines = [
            "## 我对你的理解（请确认或修正）",
            f"- 画面核心：{c.get('core', '')}",
            f"- 情绪基调：{c.get('mood', '')}",
            f"- 类型直觉：{c.get('genre', '')}",
            f"- 种子位置：{c.get('seed_position', '未知')}",
        ]
        if qs:
            lines.append("")
            lines.append("有两个问题想确认：")
            lines.extend(f"- {q}" for q in qs[:3])
        return "\n".join(lines)


def _parse_concept(text: str, fallback_seed: str) -> dict[str, Any]:
    """宽容解析概念卡 JSON。"""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    # 解析失败回退：概念=原始种子
    return {
        "concept": {
            "core": fallback_seed[:100],
            "mood": "",
            "genre": "",
            "seed_position": "未知",
        },
        "questions": [],
    }
