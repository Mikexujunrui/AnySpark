"""单元层任务注册表（顺序 = 依赖顺序：图谱组最先，避免后续任务污染图谱断言）。

说明：
- 任务共享同一个隔离后端实例（--db），因此顺序敏感：
  图谱组（T1/T2/T3/T5）最先——T17 资料消化会 resolve_names 产生占位实体，
  若在图谱组之前跑会污染 F1 断言。
- 每个任务签名：fn(api) -> (passed, metrics, detail)
"""

from __future__ import annotations

from collections.abc import Callable

from benchmarks.unit.tasks import agency, align, chat, check, explore, graph, materials

TaskFn = Callable[[object], tuple[bool, dict, str]]

REGISTRY: list[tuple[str, str, TaskFn]] = [
    ("T1", "图谱抽取准确率 F1（vs gold）", graph.t1_extract_f1),
    ("T2", "图谱幂等落库", graph.t2_idempotent),
    ("T3", "注入块包含已知事实", graph.t3_context_block),
    ("T5", "时序校验（时空倒置检测）", graph.t5_temporal),
    ("T14", "能动性档位载体（五级+CRUD）", agency.t14_agency_crud),
    ("T8", "说明书载体（CRUD/锁定/元数据）", align.t8_manual_crud),
    ("T9", "信号采集（操作→信号）", align.t9_signals),
    ("T7", "规则编译器（自然语言规则）", check.t7_rule_compiler),
    ("T16", "SSE 帧协议", chat.t16_sse_frames),
    ("T13", "能动性档位真实生效（0 vs 4）", agency.t13_agency_levels),
    ("T10", "探索意图确认（概念卡+歧义点）", explore.t10_explore_intent),
    ("T11", "探索方向卡多样性（三来源混合）", explore.t11_explore_diversity),
    ("T12", "方向固化落盘", explore.t12_explore_archive),
    ("T15", "长书记忆保持率（跨章问答）", chat.t15_memory_retention),
    ("T17", "材料摘要卡结构", materials.t17_material_card),
    ("T18", "材料→图谱实体关联", materials.t18_material_graph_link),
    ("T19", "关键点图谱草案", materials.t19_plot_draft),
]
