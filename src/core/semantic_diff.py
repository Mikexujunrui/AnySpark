# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Semantic diff — LLM-powered structured change comparison between chapter versions.

Unlike text-level diff (difflib), this module asks the LLM to identify
*semantic* changes: character emotion shifts, scene location changes,
plot direction changes, new/deleted foreshadows, relationship changes.

Uses the Flash model for cost efficiency.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from core.llm_client import chat
from core.utils import extract_json_from_response

# chat() is sync (blocking) — we wrap in asyncio.to_thread for the async API.

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """你是一位文学编辑，专门对比小说章节的两个版本，识别语义层面的变更。

请对比「旧版本」和「新版本」文本，输出 JSON 格式的语义变更报告。

变更分类（category）：
- character_emotion：角色情绪/态度变化（如"愤怒→悲伤"）
- scene_location：场景地点变化
- plot_direction：情节走向变化（如"和解→冲突升级"）
- new_foreshadow：新增伏笔/暗示
- deleted_content：删除的重要内容
- relationship_change：人物关系变化
- style_change：文风/叙述方式变化
- pacing_change：节奏变化（加速/减速）

严重程度（severity）：
- minor：微调（措辞、细节润色）
- moderate：中等修改（段落替换、情绪调整）
- major：重大变更（情节走向改变、角色弧线调整）

影响力层级（impact_level）：
- cosmetic：表面修饰，不影响剧情
- moderate：局部调整，影响单章体验
- structural：结构性变更，影响后续章节

输出格式（严格 JSON）：
{
  "changes": [
    {
      "category": "character_emotion",
      "description": "角色张三的情绪从愤怒变为悲伤",
      "old_text": "张三怒不可遏，一拳砸在桌上",
      "new_text": "张三的眼眶泛红，默默低下了头",
      "severity": "moderate"
    }
  ],
  "summary": "本次修改主要调整了第3章的角色情绪走向，从对抗转为内敛，情节未变。",
  "impact_level": "moderate"
}

只输出 JSON，不要附加其他文字。"""


@dataclass
class SemanticChange:
    """A single semantic change between two versions."""

    category: str = ""
    description: str = ""
    old_text: str = ""
    new_text: str = ""
    severity: str = "minor"

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "description": self.description,
            "old_text": self.old_text,
            "new_text": self.new_text,
            "severity": self.severity,
        }


@dataclass
class SemanticDiff:
    """Full semantic diff result between two chapter versions."""

    changes: list[SemanticChange] = field(default_factory=list)
    summary: str = ""
    impact_level: str = "cosmetic"

    def to_dict(self) -> dict[str, Any]:
        return {
            "changes": [c.to_dict() for c in self.changes],
            "summary": self.summary,
            "impact_level": self.impact_level,
            "change_count": len(self.changes),
        }


def _parse_diff_response(response: str) -> SemanticDiff:
    """Parse the LLM JSON response into a SemanticDiff object."""
    try:
        cleaned = extract_json_from_response(response)
        data = json.loads(cleaned)
        if not data or not isinstance(data, dict):
            return SemanticDiff(summary="无法解析语义差异结果")

        changes: list[SemanticChange] = []
        for item in data.get("changes", []):
            if not isinstance(item, dict):
                continue
            changes.append(SemanticChange(
                category=item.get("category", "unknown"),
                description=item.get("description", ""),
                old_text=item.get("old_text", ""),
                new_text=item.get("new_text", ""),
                severity=item.get("severity", "minor"),
            ))

        return SemanticDiff(
            changes=changes,
            summary=data.get("summary", ""),
            impact_level=data.get("impact_level", "cosmetic"),
        )
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning("Failed to parse semantic diff response: %s", e)
        return SemanticDiff(summary=f"解析失败: {e}")


async def compute_semantic_diff(
    old_content: str,
    new_content: str,
    chapter_title: str = "",
) -> SemanticDiff:
    """Compute semantic diff between two chapter versions using LLM.

    Args:
        old_content: The original chapter text.
        new_content: The modified chapter text.
        chapter_title: Optional chapter title for context.

    Returns:
        SemanticDiff with structured changes.
    """
    if not old_content.strip() and not new_content.strip():
        return SemanticDiff(summary="两个版本均为空")
    if old_content.strip() == new_content.strip():
        return SemanticDiff(summary="两个版本完全相同，无变更")

    # Truncate to avoid token overflow (keep first and last portions)
    max_len = 8000
    old_trunc = _truncate_content(old_content, max_len)
    new_trunc = _truncate_content(new_content, max_len)

    user_prompt = (
        f"章节标题：{chapter_title}\n\n"
        f"=== 旧版本 ===\n{old_trunc}\n\n"
        f"=== 新版本 ===\n{new_trunc}\n\n"
        f"请输出语义变更 JSON 报告。"
    )

    try:
        import asyncio
        response = await asyncio.to_thread(
            chat,
            prompt=user_prompt,
            system=_SYSTEM_PROMPT,
            temperature=0.3,
            task="general",  # uses Flash model in split mode
        )
        return _parse_diff_response(response)
    except Exception as e:
        logger.error("Semantic diff LLM call failed: %s", e)
        return SemanticDiff(summary=f"LLM 调用失败: {e}")


def _truncate_content(content: str, max_len: int) -> str:
    """Truncate content to fit within token limits.

    Keeps the first 60% and last 40% to preserve both opening and ending.
    """
    if len(content) <= max_len:
        return content
    first_part = int(max_len * 0.6)
    last_part = max_len - first_part
    return (
        content[:first_part]
        + "\n...[中间部分省略]...\n"
        + content[-last_part:]
    )
