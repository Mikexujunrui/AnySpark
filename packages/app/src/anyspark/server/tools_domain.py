"""
anyspark.server.tools_domain — 领域工具集（兼容性 re-export 层，S188 拆分后）。

S188 将本文件按功能域拆分到：
- tools_graph.py：图谱查证/登记
- tools_plot.py：伏笔/计划/设定查证
- tools_search.py：正文检索/锚点阅读
- tools_align.py：心智登记/管理 + 技巧提炼
- tools_reference.py：参考书检索/批量任务
- tools_explore.py：角色推演/路径探索/推演/代码沙箱/资料消化/扩展工具注册

本文件保留所有 make_* 工厂的 re-export，兼容现有 import（toolkit.py 等）。
新代码应直接从对应功能域模块 import。
"""

from __future__ import annotations

from anyspark.server.tools_align import (
    make_mind_manage_implementer,
    make_mind_reconcile_implementer,
    make_mind_register_implementer,
    make_skill_lookup_implementer,
    make_skill_refine_implementer,
)
from anyspark.server.tools_explore import (
    make_codex_implementer,
    make_ingest_implementer,
    make_material_register_implementer,
    make_path_explore_implementer,
    make_play_implementer,
    make_register_tool_implementer,
    make_roleplay_implementer,
)

# 查询返回上限（防 token 爆炸：Agent 是裁剪消费者，需要细节再查）
from anyspark.server.tools_graph import (
    _QUERY_LIMIT,
    _RELATION_LIMIT,
    make_graph_query_implementer,
    make_graph_register_implementer,
)
from anyspark.server.tools_plot import (
    make_plan_implementer,
    make_plot_implementer,
    make_setting_implementer,
)
from anyspark.server.tools_reference import (
    make_batch_implementer,
    make_reference_lookup_implementer,
    render_reference_knowledge,
)
from anyspark.server.tools_search import (
    make_read_context_implementer,
    make_search_chapters_implementer,
)

__all__ = [
    "_QUERY_LIMIT",
    "_RELATION_LIMIT",
    "make_batch_implementer",
    "make_codex_implementer",
    "make_graph_query_implementer",
    "make_graph_register_implementer",
    "make_ingest_implementer",
    "make_material_register_implementer",
    "make_mind_manage_implementer",
    "make_mind_reconcile_implementer",
    "make_mind_register_implementer",
    "make_path_explore_implementer",
    "make_plan_implementer",
    "make_play_implementer",
    "make_plot_implementer",
    "make_read_context_implementer",
    "make_reference_lookup_implementer",
    "make_register_tool_implementer",
    "make_roleplay_implementer",
    "make_search_chapters_implementer",
    "make_setting_implementer",
    "make_skill_lookup_implementer",
    "make_skill_refine_implementer",
    "render_reference_knowledge",
]
