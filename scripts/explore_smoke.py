# -*- coding: utf-8 -*-
"""
AnySpark v4 — 阶段 3 真实链路冒烟：种子→意图确认→并行探索×4→方向卡→固化。

运行：uv run python scripts/explore_smoke.py
需要：.env 配置 DEEPSEEK_API_KEY（真实 DeepSeek）
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from dotenv import load_dotenv

from anyspark.explore import (
    DirectionCard,
    ExplorationStrategy,
    IntentUnderstander,
    ProjectArchive,
    run_exploration,
)
from anyspark.models.deepseek import DeepSeekModel

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def main() -> None:
    model = DeepSeekModel()
    print(f"模型: {model.model_name}\n")

    seed = "一个雨夜，侦探陈渡抵达陌生的雾城，追查一桩二十年前的悬案"

    print("== 1. 意图理解（种子→概念卡+关键歧义点）==")
    understander = IntentUnderstander(model)
    concept = understander.understand(seed)
    print(understander.build_confirmation(concept))

    print("\n== 2. 并行探索（4 个差异化探索者，asyncio.gather）==")
    archive = ProjectArchive(Path(tempfile.mkdtemp()) / "explore.db")
    try:
        # 已固化约束（模拟：探索不得撞墙）
        archive.add_constraint("陈渡的过去在雾城", "main")
        constraints = archive.constraints()

        strategy = ExplorationStrategy(
            seed=seed,
            intent_confirmed=concept,
            constraints=constraints,
        )
        cards = run_exploration(model, seed, concept, constraints, n_explorers=4)

        for i, c in enumerate(cards):
            tag = {"template": "模板派生", "grow": "作品生长", "user": "用户指导"}[c.source]
            print(f"  卡{i + 1} [{c.dimension} / {tag}]")
            print(f"    「{c.title}」 {('(' + c.term + ')') if c.term else ''}")
            print(f"    {c.summary[:90]}")

        print("\n== 3. 固化选中方向 ==")
        if cards:
            chosen = cards[0]
            archive.archive_direction(chosen)
            dirs = archive.directions()
            print(f"   已固化: {dirs[0]['title']} (来源 {dirs[0]['source']})")
            print(f"   档案现有 {len(dirs)} 个方向, {len(constraints)} 条设定约束")
    finally:
        archive.close()


if __name__ == "__main__":
    main()
