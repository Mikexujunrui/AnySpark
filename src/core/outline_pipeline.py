# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Outline expansion pipeline — multi-level outline generation from a seed.

Levels:
  Level 1: one-sentence seed → 500-word master outline
  Level 2: master outline → N volume outlines (300 words each)
  Level 3: volume outline → M chapter outlines (200 words each)
  Level 4: chapter outline → 2000-word detailed outline

Each level:
1. Injects the previous level's output + knowledge graph context
2. Calls LLM (Pro model for quality)
3. Yields progress events for SSE streaming
4. Supports pause/resume for human review between levels
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from core.llm_client import chat

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of a single level expansion."""

    level: int = 0
    level_name: str = ""
    input_text: str = ""
    output_text: str = ""
    word_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "level_name": self.level_name,
            "input_preview": self.input_text[:200],
            "output": self.output_text,
            "word_count": self.word_count,
        }


# ── Level prompts ──

_LEVEL1_PROMPT = """你是一位经验丰富的小说策划。请将以下一句话设定扩展为500字左右的总纲。

要求：
1. 确定小说类型、核心冲突、主要角色群
2. 概述故事起因、发展、高潮、结局的总体走向
3. 设定世界观基调（奇幻/科幻/现实/历史等）
4. 不要写正文，只写总纲

一句话设定：{seed}"""

_LEVEL2_PROMPT = """你是一位经验丰富的小说策划。请基于以下总纲，将故事拆分为若干卷（通常3-5卷），每卷给出300字左右的分卷纲。

要求：
1. 每卷有明确的主题和核心冲突
2. 卷与卷之间有递进关系
3. 标注每卷预计章节数

总纲：
{master_outline}"""

_LEVEL3_PROMPT = """你是一位经验丰富的小说策划。请基于以下分卷纲，为本卷拆分出具体章节（每章200字左右的章节纲）。

要求：
1. 每章有明确的情节推进点
2. 标注关键出场角色和场景
3. 标注伏笔埋设点和回收点
4. 章节间有因果逻辑链

分卷纲：
{volume_outline}"""

_LEVEL4_PROMPT = """你是一位经验丰富的小说策划。请基于以下章节纲，扩展为2000字左右的细纲。

要求：
1. 细化场景描写、对话要点、情绪弧线
2. 标注本章需要注入的知识库要素（角色设定、世界观细节）
3. 标注与前后章的衔接点
4. 不要写正文，只写细纲

章节纲：
{chapter_outline}"""


def _count_words(text: str) -> int:
    """Count Chinese characters (excluding whitespace)."""
    return len(text.replace("\n", "").replace(" ", "").replace("\r", ""))


async def expand_single_level(
    level: int,
    input_text: str,
    book_id: str = "",
) -> str:
    """Expand a single level of the pipeline.

    Args:
        level: 1-4, which level to expand.
        input_text: The input text for this level.
        book_id: Optional book ID for knowledge context injection.

    Returns:
        The expanded text output.
    """
    prompts = {
        1: _LEVEL1_PROMPT,
        2: _LEVEL2_PROMPT,
        3: _LEVEL3_PROMPT,
        4: _LEVEL4_PROMPT,
    }

    template = prompts.get(level, prompts[1])
    prompt = template.format(
        seed=input_text,
        master_outline=input_text,
        volume_outline=input_text,
        chapter_outline=input_text,
    )

    # For levels 3-4, try to inject knowledge context
    if book_id and level >= 3:
        try:
            from core.context_manager import context_manager

            ctx = context_manager.buildWritingContext(
                task="outline_expansion",
                book_id=book_id,
            )
            if ctx and ctx.system_prompt:
                prompt = ctx.system_prompt + "\n\n" + prompt
        except Exception:
            pass  # Knowledge context is best-effort

    # Call LLM (sync, wrapped in to_thread)
    response: str = await asyncio.to_thread(
        chat,
        prompt=prompt,
        system="你是一位经验丰富的小说策划，擅长从简短设定扩展为完整大纲体系。",
        temperature=0.7,
        task="general",
    )

    return response.strip()


async def expand_pipeline(
    book_id: str,
    seed: str,
    levels: int = 4,
) -> AsyncGenerator[dict, None]:
    """Run the full multi-level expansion pipeline.

    Yields progress events after each level completes.
    The caller (SSE endpoint or tool) can stream these to the frontend.

    Args:
        book_id: Target book ID.
        seed: One-sentence story seed.
        levels: How many levels to expand (1-4).

    Yields:
        Progress dicts with level info and output text.
    """
    level_names = {1: "总纲", 2: "分卷纲", 3: "章节纲", 4: "细纲"}

    current_text = seed

    for level in range(1, levels + 1):
        level_name = level_names.get(level, f"Level {level}")

        # Yield "started" event
        yield {
            "event": "level_started",
            "level": level,
            "level_name": level_name,
            "input_preview": current_text[:200],
        }

        try:
            output = await expand_single_level(level, current_text, book_id)

            result = PipelineResult(
                level=level,
                level_name=level_name,
                input_text=current_text,
                output_text=output,
                word_count=_count_words(output),
            )

            # Yield "completed" event with full output
            yield {
                "event": "level_completed",
                **result.to_dict(),
            }

            current_text = output

        except Exception as e:
            logger.error("Pipeline level %d failed: %s", level, e)
            yield {
                "event": "level_failed",
                "level": level,
                "level_name": level_name,
                "error": str(e),
            }
            return

    # Final summary
    yield {
        "event": "pipeline_complete",
        "total_levels": levels,
        "final_word_count": _count_words(current_text),
        "final_preview": current_text[:500],
    }


async def expand_pipeline_to_json(
    book_id: str,
    seed: str,
    levels: int = 4,
) -> list[dict]:
    """Run pipeline and collect all results into a list.

    Convenience wrapper for non-streaming callers.
    """
    results: list[dict] = []
    async for event in expand_pipeline(book_id, seed, levels):
        results.append(event)
    return results
