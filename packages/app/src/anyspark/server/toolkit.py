"""anyspark.server.toolkit — 工具装配（组合根接口化）。

把"工具注册"从 app.py 的 _make_agent 抽出为独立可复用模块（S52 架构轻重构）：
- 所有 make_*_implementer 依赖注入 + enable_* 按需点亮 + 扩展工具表装配，集中于此。
- 收益：app.py 组合根减负（工具装配与 HTTP 编排解耦）；任何入口（HTTP/CLI/桌面）
  都能复用同一套装配逻辑；后续新增工具分组（如 MRAgent 主动检索独立 group）
  只需在此加一个 make_* 调用 + 对应开关。
- 哲学保持：机制（注册顺序/开关/闭包依赖注入）硬编码；工具描述（ToolSpec）自然语言。
- 与原 _make_agent 内联块**逐字对应**（纯搬移，不改任何行为）：
  写作工具常驻 → 探索工具常驻 → 领域工具(enable_domain) → 扩展工具表 → run_code(enable_codex)
  → 扩展(enable_extras) → 网络搜索(enable_search)。
"""

from __future__ import annotations

from typing import Any

from anyspark.core import ToolRegistry
from anyspark.server.tools_writing import register_writing_tools


def build_toolkit(
    registry: ToolRegistry,
    *,
    chapters: Any,
    workspace: Any,
    model: Any,
    graph: Any,
    plots: Any,
    plans: Any,
    settings: Any,
    materials: Any,
    ext_tools: Any,
    manual: Any = None,
    skills_store: Any = None,
    style_prefs: list[str] | None = None,
    enable_domain: bool = True,
    enable_codex: bool = False,
    enable_extras: bool = False,
    enable_search: bool = False,
) -> ToolRegistry:
    """把全部工具装配进 registry（按 enable_* 开关分组点亮），返回同一注册表。

    依赖全部作为命名参数闭包注入（不在此处创建任何 store/model）——保持单向依赖，
    工具不"认识"装配逻辑，装配逻辑只认识工具工厂。模型无关（全部自然语言承载）。

    S56（C 架构）：skills_store + style_prefs 传给写作工具——write_chapter 意图模式
    的干净写作调用用文笔 skill 素材（按文风偏好匹配），与主循环解耦。
    """
    # 写作核心工具：无条件常驻（主链路必需）
    register_writing_tools(
        registry,
        chapters,
        workspace=workspace,
        model=model,
        skills_store=skills_store,
        style_prefs=style_prefs,
    )

    # S32：探索工具无条件注册（修复核心——方向模糊时 Agent 可自觉探索；
    # 仅此工具常驻，其余扩展按 enable_extras 点亮，防无关调用干扰主链路）。
    from anyspark.server.tools_extras import make_explore_implementer

    explore_spec, explore_impl = make_explore_implementer(model)
    registry.register(explore_spec, explore_impl)

    # S48-P2 领域工具：图谱查证/伏笔登记/伏笔列表/计划列表/计划推进/设定查证
    # 默认开（小说写作必需能力）；skip_inject 无关（工具注册非注入）。
    if enable_domain:
        from anyspark.server.tools_domain import (
            make_graph_query_implementer,
            make_ingest_implementer,
            make_mind_register_implementer,
            make_plan_implementer,
            make_plot_implementer,
            make_read_context_implementer,
            make_register_tool_implementer,
            make_roleplay_implementer,
            make_search_chapters_implementer,
            make_setting_implementer,
        )

        gq_spec, gq_impl = make_graph_query_implementer(graph)
        registry.register(gq_spec, gq_impl)
        ig_spec, ig_impl = make_ingest_implementer(workspace, chapters, materials, model)
        registry.register(ig_spec, ig_impl)
        plot_specs, plot_impls = make_plot_implementer(plots)
        for s, i in zip(plot_specs, plot_impls, strict=True):
            registry.register(s, i)
        plan_specs, plan_impls = make_plan_implementer(plans)
        for s, i in zip(plan_specs, plan_impls, strict=True):
            registry.register(s, i)
        st_spec, st_impl = make_setting_implementer(settings)
        registry.register(st_spec, st_impl)
        rp_spec, rp_impl = make_roleplay_implementer(workspace, graph, model)
        registry.register(rp_spec, rp_impl)
        sc_spec, sc_impl = make_search_chapters_implementer(chapters)
        registry.register(sc_spec, sc_impl)
        rc_spec, rc_impl = make_read_context_implementer(chapters)
        registry.register(rc_spec, rc_impl)
        rt_spec, rt_impl = make_register_tool_implementer(ext_tools)
        registry.register(rt_spec, rt_impl)
        # S53c ① 心智登记工具：对话中"记一下"→ 即时落心智条目（user 来源高置信度）
        if manual is not None:
            md_spec, md_impl = make_mind_register_implementer(manual)
            registry.register(md_spec, md_impl)

    # S48-P4/B 扩展工具注册表：已批准（active）的扩展注入工具集（无需重启生效）
    from anyspark.server.codex import make_data_env
    from anyspark.server.tools_extensions import execute_extension, tool_spec_from_ext

    _ext_data_env = make_data_env(workspace, chapters, graph)

    def _make_ext_impl(e: Any, env: dict[str, Any]) -> Any:
        def impl(spec_: Any, arguments: dict[str, Any]) -> Any:
            return execute_extension(e, arguments, env)

        return impl

    for _ext in ext_tools.active_tools():
        registry.register(tool_spec_from_ext(_ext), _make_ext_impl(_ext, _ext_data_env))

    # S48-P5 代码扩展（沙箱 run_code）：默认关，按需点亮（固定工具做不了的自定义处理）
    if enable_codex:
        from anyspark.server.tools_domain import make_codex_implementer

        cx_spec, cx_impl = make_codex_implementer(workspace, chapters, graph)
        registry.register(cx_spec, cx_impl)

    # S32 扩展：read_material / check_text，按 enable_extras 点亮（默认关，
    # 防无关工具调用干扰主链路——S15 哲学延续）。
    if enable_extras:
        from anyspark.server.tools_extras import (
            make_check_implementer,
            make_read_material_implementer,
        )

        material_spec, material_impl = make_read_material_implementer(materials)
        registry.register(material_spec, material_impl)
        check_spec, check_impl = make_check_implementer(model)
        registry.register(check_spec, check_impl)

    # 网络搜索工具：按需注册（S15 起默认关——写作主链路不背考据能力，需要时点亮）
    if enable_search:
        from anyspark.server.tools_web import make_search_implementer

        search_spec, search_impl = make_search_implementer()
        registry.register(search_spec, search_impl)

    return registry
