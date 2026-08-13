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

from dataclasses import dataclass
from typing import Any

from anyspark.core import ToolRegistry
from anyspark.server.tools_writing import register_writing_tools


@dataclass
class ToolContext:
    """工具装配上下文：全部 store/model 依赖收敛为单对象（S62 解耦修正）。

    - 此前 build_toolkit 15 个 Any 命名参数（耦合隐形、新增工具组要改签名）；
      收敛后签名稳定（registry + ctx + enable_* 开关），依赖关系可读。
    - 仍保持"依赖全部由组合根注入"（不在此处创建任何 store/model）——单向依赖，
      工具不"认识"装配逻辑。模型无关（全部自然语言承载）。
    """

    chapters: Any
    workspace: Any
    model: Any
    graph: Any
    plots: Any
    plans: Any
    settings: Any
    materials: Any
    ext_tools: Any
    dim_store: Any = None  # S50 探索维度内容载体（explore_direction 用，缺省默认种子）
    manual: Any = None
    skills_store: Any = None
    style_prefs: list[str] | None = None
    workflow_store: Any = None  # S59 工作流 agent 工具（默认关：可选增强，需要时点亮）
    workflow_engine: Any = None
    workflow_generator: Any = None
    play_engine: Any = None  # S65 互动推演 agent 工具（默认关：玩法/灵感，需要时点亮）
    review_panel: Any = None  # S64 拟人化评审团面板（panel_review 工具用）
    skill_generator: Any = None  # S72 文风参考 → skill 提炼工具（skill_refine）
    templates: list[str] = None  # type: ignore[assignment]  # S68 模板描述列表（explore_direction 注入）
    library: Any = None  # S86 参考书库（reference_lookup 工具：不注入，按需检索）
    book_id: str = "main"  # S74：当前项目 id——工具层多书隔离（此前各 implementer 硬编码 main）


def build_toolkit(
    registry: ToolRegistry,
    ctx: ToolContext,
    *,
    enable_domain: bool = True,
    enable_codex: bool = True,
    enable_extras: bool = True,
    enable_search: bool = True,
    enable_workflow: bool = True,
    enable_play: bool = True,
) -> ToolRegistry:
    """把全部工具装配进 registry（S114：能力默认可用、按需选用；enable_* 可显式禁用）。

    ctx：ToolContext（全部 store/model 依赖，组合根构造注入）；enable_*：功能开关
    （增强默认关，点亮才挂——S15"你要什么再装什么"）。

    S56（C 架构）：ctx.skills_store + ctx.style_prefs 传给写作工具——write_chapter
    意图模式用文笔 skill 素材（按文风偏好匹配），与主循环解耦。
    """
    # 写作核心工具：无条件常驻（主链路必需）
    register_writing_tools(
        registry,
        ctx.chapters,
        book_id=ctx.book_id,
        workspace=ctx.workspace,
        model=ctx.model,
        skills_store=ctx.skills_store,
        style_prefs=ctx.style_prefs,
    )

    # S32：探索工具无条件注册（修复核心——方向模糊时 Agent 可自觉探索；
    # 仅此工具常驻，其余扩展按 enable_extras 点亮，防无关调用干扰主链路）。
    from anyspark.server.tools_extras import make_explore_implementer

    explore_spec, explore_impl = make_explore_implementer(
        ctx.model,
        dim_names=ctx.dim_store.list_names() if ctx.dim_store else None,
        templates=ctx.templates,
    )
    registry.register(explore_spec, explore_impl)

    # S48-P2 领域工具：图谱查证/伏笔登记/伏笔列表/计划列表/计划推进/设定查证
    # 默认开（小说写作必需能力）；skip_inject 无关（工具注册非注入）。
    if enable_domain:
        from anyspark.server.tools_domain import (
            make_batch_implementer,
            make_graph_query_implementer,
            make_graph_register_implementer,
            make_ingest_implementer,
            make_material_register_implementer,
            make_mind_manage_implementer,
            make_mind_register_implementer,
            make_path_explore_implementer,
            make_plan_implementer,
            make_plot_implementer,
            make_read_context_implementer,
            make_reference_lookup_implementer,
            make_register_tool_implementer,
            make_roleplay_implementer,
            make_search_chapters_implementer,
            make_setting_implementer,
            make_skill_lookup_implementer,
            make_skill_refine_implementer,
        )

        # S102：批量改写/批量审读**提议工具**（agent 自主发起，前端弹窗批准后执行）
        b_specs, b_impls = make_batch_implementer(ctx.chapters, book_id=ctx.book_id)
        for _s, _i in zip(b_specs, b_impls, strict=True):
            registry.register(_s, _i)

        # S104：检测工具（智能体自查硬伤/自然语言规则，替代人用 /api/check）
        from anyspark.server.tools_check import make_check_implementer

        ck_spec, ck_impl = make_check_implementer(ctx.model)
        registry.register(ck_spec, ck_impl)

        gq_spec, gq_impl = make_graph_query_implementer(ctx.graph, book_id=ctx.book_id)
        registry.register(gq_spec, gq_impl)
        # S60：技巧查证工具（与索引常驻配套：索引轻量注入，内容按需细看）
        if ctx.skills_store is not None:
            sl_spec, sl_impl = make_skill_lookup_implementer(ctx.skills_store)
            registry.register(sl_spec, sl_impl)
        # S72：图谱登记工具（对话"把XX记进图谱"→ 即时落库；对齐 mind_register）
        gr_spec, gr_impl = make_graph_register_implementer(ctx.graph, book_id=ctx.book_id)
        registry.register(gr_spec, gr_impl)
        # S72：文风参考书 → skill 提炼（方法论通道；生成候选，人工确认生效）
        # S103：+library（书库取原文）+ skills（候选存草稿，对话链路可确认）
        if ctx.skill_generator is not None and ctx.materials is not None:
            sr_spec, sr_impl = make_skill_refine_implementer(
                ctx.skill_generator, ctx.materials, library=ctx.library, skills=ctx.skills_store
            )
            registry.register(sr_spec, sr_impl)
        # S80：灵感登记（资料库 = 灵感冷藏库；AI 可写 inspiration，copy 仅人工/导入）
        if ctx.materials is not None:
            mr_spec, mr_impl = make_material_register_implementer(
                ctx.materials, book_id=ctx.book_id
            )
            registry.register(mr_spec, mr_impl)
        ig_spec, ig_impl = make_ingest_implementer(
            ctx.workspace, ctx.chapters, ctx.materials, ctx.model, book_id=ctx.book_id
        )
        registry.register(ig_spec, ig_impl)
        plot_specs, plot_impls = make_plot_implementer(ctx.plots, book_id=ctx.book_id)
        for s, i in zip(plot_specs, plot_impls, strict=True):
            registry.register(s, i)
        plan_specs, plan_impls = make_plan_implementer(ctx.plans, book_id=ctx.book_id)
        for s, i in zip(plan_specs, plan_impls, strict=True):
            registry.register(s, i)
        st_spec, st_impl = make_setting_implementer(ctx.settings, book_id=ctx.book_id)
        registry.register(st_spec, st_impl)
        rp_spec, rp_impl = make_roleplay_implementer(
            ctx.workspace, ctx.graph, ctx.model, book_id=ctx.book_id
        )
        registry.register(rp_spec, rp_impl)
        # S67：叙事路径探索（起点 A → 终点 B 串联候选，章节间过渡/情节点连接）
        px_spec, px_impl = make_path_explore_implementer(ctx.model)
        registry.register(px_spec, px_impl)
        sc_spec, sc_impl = make_search_chapters_implementer(ctx.chapters, book_id=ctx.book_id)
        registry.register(sc_spec, sc_impl)
        # S86：参考书检索（不注入，按需翻书——只读参考书库/其他项目）
        # 分级：书库的书=低级（原文检索）；项目=高级（额外可检索图谱/设定，只读）
        if ctx.library is not None:
            rl_spec, rl_impl = make_reference_lookup_implementer(
                ctx.library,
                ctx.chapters,
                book_id=ctx.book_id,
                graph=ctx.graph,
                settings=ctx.settings,
            )
            registry.register(rl_spec, rl_impl)
        rc_spec, rc_impl = make_read_context_implementer(ctx.chapters, book_id=ctx.book_id)
        registry.register(rc_spec, rc_impl)
        # S108：资料库查询（原 enable_extras 默认关→挪到 domain 默认开：AI 应能查看资料库）
        if ctx.materials is not None:
            from anyspark.server.tools_extras import make_read_material_implementer

            material_spec, material_impl = make_read_material_implementer(
                ctx.materials, book_id=ctx.book_id
            )
            registry.register(material_spec, material_impl)
        rt_spec, rt_impl = make_register_tool_implementer(ctx.ext_tools)
        registry.register(rt_spec, rt_impl)
        # S53c ① 心智登记工具：对话中"记一下"→ 即时落心智条目（user 来源高置信度）
        if ctx.manual is not None:
            md_spec, md_impl = make_mind_register_implementer(ctx.manual)
            registry.register(md_spec, md_impl)
            # S73d 心智纠正工具：用户明确要求改/删时 agent 代执行（内容裁决权在用户）
            mm_specs, mm_impls = make_mind_manage_implementer(ctx.manual)
            for _s, _i in zip(mm_specs, mm_impls, strict=True):
                registry.register(_s, _i)

    # S48-P4/B 扩展工具注册表：已批准（active）的扩展注入工具集（无需重启生效）
    from anyspark.server.codex import make_data_env
    from anyspark.server.tools_extensions import execute_extension, tool_spec_from_ext

    _ext_data_env = make_data_env(ctx.workspace, ctx.chapters, ctx.graph)

    def _make_ext_impl(e: Any, env: dict[str, Any]) -> Any:
        def impl(spec_: Any, arguments: dict[str, Any]) -> Any:
            return execute_extension(e, arguments, env)

        return impl

    for _ext in ctx.ext_tools.active_tools():
        registry.register(tool_spec_from_ext(_ext), _make_ext_impl(_ext, _ext_data_env))

    # S48-P5 代码扩展（沙箱 run_code）：默认可用（S114 哲学：安全靠沙箱兜底不靠隐藏；
    # 工具描述已写明"不可读写文件/访问网络"，显式 False 可禁用）
    if enable_codex:
        from anyspark.server.tools_domain import make_codex_implementer

        cx_spec, cx_impl = make_codex_implementer(
            ctx.workspace, ctx.chapters, ctx.graph, book_id=ctx.book_id
        )
        registry.register(cx_spec, cx_impl)

    # S63 曾退役 check_text（被 review_chapter 取代）；S104 重建为智能体自查工具
    # （自然语言规则检测 + 硬伤检测，无需自传全文），默认可用（enable_domain 名下）。
    # S108：read_material 已挪到 enable_domain 默认开（AI 查看资料库是写作必需能力）。

    # 网络搜索工具：默认可用（S114 翻转——S15 曾默认关，S64 教训：默认关的工具=没人用的残废通道）
    # S111：enable_search 名下同时注册 search_web（搜索）+ fetch_page（抓正文）——搜索闭环
    if enable_search:
        from anyspark.server.tools_fetch import make_fetch_implementer
        from anyspark.server.tools_web import make_search_implementer

        search_spec, search_impl = make_search_implementer()
        registry.register(search_spec, search_impl)
        fetch_spec, fetch_impl = make_fetch_implementer()
        registry.register(fetch_spec, fetch_impl)

    # S59 工作流 agent 工具：默认可用，enable_workflow 可显式禁用（Agent 可列/生成/运行/查进度）
    if enable_workflow and ctx.workflow_store is not None:
        from anyspark.server.tools_workflow import make_workflow_tools

        for _spec, _impl in make_workflow_tools(
            ctx.workflow_store, ctx.workflow_engine, ctx.workflow_generator
        ):
            registry.register(_spec, _impl)

    # S65 互动推演 agent 工具：默认可用，enable_play 可显式禁用（玩法/灵感：启动/选择/查看/导出）
    if enable_play and ctx.play_engine is not None:
        from anyspark.server.tools_domain import make_play_implementer

        # S114：make_play_implementer 返回 (specs[], impls[]) 两个列表——
        # 此前 enable_play 默认关从未触发，潜伏的解包 bug（S65 遗留）在此修复
        _play_specs, _play_impls = make_play_implementer(ctx.play_engine)
        for _spec, _impl in zip(_play_specs, _play_impls, strict=True):
            registry.register(_spec, _impl)

    # S64：拟人化评审团 agent 工具（无条件注册——用户喊"帮我看看这章"时 agent
    # 自主调用；对齐 explore_direction，S63 教训：默认关的工具=没人用的残废通道）
    if ctx.review_panel is not None:
        from anyspark.server.tools_review import make_review_tools

        for _rspec, _rimpl in make_review_tools(
            ctx.review_panel, ctx.chapters, ctx.model, book_id=ctx.book_id
        ):
            registry.register(_rspec, _rimpl)

    return registry
