"""
anyspark.explore.explorers — 探索者（并行，轻量上下文）。

设计（DESIGN 机制 7）：
- 并行：asyncio.gather，轻量上下文；并行调用时间≈单次
- 轻量优先：探索者多数是单次 LLM 调用，不需要完整 while-true 循环+工具
- 上下文隔离 → 真多样性（multi-prompt sampling / ensemble）
"""

from __future__ import annotations

import asyncio
from typing import Any

from anyspark.core import Message

from .direction import DEFAULT_DIMENSIONS, DirectionCard
from .strategy import ExplorationStrategy


class ExplorationEngine:
    """多智能体探索引擎：并行跑 N 个差异化探索者。"""

    def __init__(self, model: object, n_explorers: int = 4) -> None:
        self._model = model
        self._n = n_explorers

    def explore(self, strategy: ExplorationStrategy) -> list[DirectionCard]:
        """并行探索（同步入口，内部 asyncio.run 包装）。"""
        return asyncio.run(self._parallel(strategy))

    async def _parallel(self, strategy: ExplorationStrategy) -> list[DirectionCard]:
        results = await asyncio.gather(*[self._call_one(strategy, i) for i in range(self._n)])
        return list(results)

    async def _call_one(self, strategy: ExplorationStrategy, index: int) -> DirectionCard:
        prompt = strategy.explorer_prompt(index)
        # 探索者：单次 LLM 调用（轻量上下文，无工具）
        output = await asyncio.to_thread(
            self._model.respond,  # type: ignore[attr-defined]
            [Message(role="system", content=prompt)],
            [],
        )
        return strategy.card_from_response(index, output.text)


def run_exploration(
    model: object,
    seed: str,
    intent_confirmed: dict[str, Any],
    constraints: list[str] | None = None,
    n_explorers: int = 4,
    dimensions: list[str] | None = None,
    templates: list[str] | None = None,
) -> list[DirectionCard]:
    """便捷入口：一次完整探索（dimensions：S50 内容化维度集，缺省默认种子）。

    templates（S68）：真实模板描述列表（template 来源探索者注入；缺省无注入）。
    """
    strategy = ExplorationStrategy(
        seed=seed,
        intent_confirmed=intent_confirmed,
        constraints=constraints or [],
        dimensions=dimensions or list(DEFAULT_DIMENSIONS),
        templates=templates or [],
    )
    return ExplorationEngine(model, n_explorers).explore(strategy)
