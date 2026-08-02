# -*- coding: utf-8 -*-
"""
AnySpark v4 — 阶段 2 真实链路冒烟：操作→信号→提炼→说明书→注入→写作生效。

运行：uv run python scripts/align_smoke.py
需要：.env 配置 DEEPSEEK_API_KEY（真实 DeepSeek）
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from dotenv import load_dotenv

from anyspark.align import (
    ManualEntry,
    ManualInjector,
    ManualStore,
    PreferenceExtractor,
    SignalCollector,
    SignalStore,
)
from anyspark.core.types import Message
from anyspark.models.deepseek import DeepSeekModel

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def main() -> None:
    model = DeepSeekModel()

    db = Path(tempfile.mkdtemp()) / "align.db"
    manual = ManualStore(db)
    sigs = SignalStore(db)
    collector = SignalCollector(sigs)
    extractor = PreferenceExtractor(model)

    print("== 1. 用户操作（信号采集）==")
    collector.deleted("窗外下着血雨，尸体躺在路边", context="稿纸")
    collector.modified("他愤怒地砸门", "他沉默地放下钥匙", context="稿纸")
    collector.accepted("对话要克制", context="稿纸")
    print(f"   已记录 {len(sigs.recent())} 条信号")

    print("\n== 2. 真实 DeepSeek 提炼偏好 ==")
    dialogue = [
        Message(role="user", content="这段血腥描写删掉，我这本书不要暴力场面"),
        Message(role="assistant", content="好的，已删除血腥描写"),
    ]
    entries = extractor.extract(dialogue, sigs.recent())
    for e in entries:
        print(f"   → {e.content} (置信度 {e.confidence}, {e.activity})")

    print("\n== 3. 写入说明书（含用户手写条目）==")
    manual.add(
        ManualEntry(content="本书禁止血腥暴力描写", source="user", confidence=0.95, locked=True)
    )
    for e in entries:
        manual.add(e)
    project_entries = manual.list("project", "main")
    print(f"   项目说明书现有 {len(project_entries)} 条")

    print("\n== 4. 注入器生成对齐块 ==")
    injector = ManualInjector(manual)
    block = injector.build_system_block("main")
    print("   --- 注入内容 ---")
    print(block[:400])

    print("\n== 5. 说明书生效验证：带偏好写作 ==")
    from anyspark.core import Agent, ToolRegistry, ToolResult, ToolSpec
    from anyspark.core.protocol import ParamSpec
    from anyspark.core.types import ToolCall

    reg = ToolRegistry()

    def _save(spec: ToolSpec, arguments: dict) -> ToolResult:
        return ToolResult(
            call=ToolCall(name=spec.name, arguments=arguments),
            ok=True,
            content=f"已保存《{arguments.get('title')}》",
        )

    reg.register(
        ToolSpec(
            name="write_chapter",
            description="保存章节正文",
            params=[
                ParamSpec(name="title", type="string", required=True),
                ParamSpec(name="content", type="string", required=True),
            ],
        ),
        _save,
    )

    agent = Agent(
        model=model,
        registry=reg,
        system_prompt=(
            "你是小说写作智能体。写作时必须遵守下面的写作说明书。\n\n"
            + block
            + "\n\n用 write_chapter 保存正文。"
        ),
    )
    turn = agent.run("写一章开头：小城发生了一起离奇失踪案，侦探陈渡介入调查。约150字。")
    print("   --- AI 写的正文 ---")
    print(turn.text[:300])


if __name__ == "__main__":
    main()
