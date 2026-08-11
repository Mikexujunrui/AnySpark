"""
anyspark.server.agent_factory — Agent 构造工厂（S80 拆分，从 app.py 搬移）。

make_agent(deps, ...) 原为 build_app 内的 _make_agent 闭包（224 行）：
组装工具注册表 + 注入块装配（心智/图谱/设定/技巧渐进式披露）+ 能动性档位。
搬移后闭包引用全部改为 deps.xxx，行为零变化。
"""

from __future__ import annotations

from anyspark.align.agency import build_agency_block
from anyspark.align.plan import render_plan
from anyspark.align.skills import render_skill_index
from anyspark.align.worldsettings import (
    render_constraints_block,
    render_settings_adaptive,
)
from anyspark.core import Agent, Model, RetryingModel, ToolRegistry
from anyspark.models.deepseek import DeepSeekModel
from anyspark.models.registry import ModelProvider
from anyspark.server.deps import AppDeps
from anyspark.server.toolkit import ToolContext, build_toolkit
from anyspark.server.tools_writing import UNCENSORED_PROMPT

_skill_cache: dict[str, str] = {}  # 签名 → 索引块（S60：只存索引，内容靠 skill_lookup 按需）


def make_agent(
    deps: AppDeps,
    system_prompt: str,
    temperature: float,
    book_id: str = "main",
    agency_level: int | None = None,
    enable_search: bool = False,
    enable_extras: bool = False,
    enable_domain: bool = True,
    enable_codex: bool = False,
    enable_workflow: bool = False,
    enable_play: bool = False,
    skip_inject: set[str] | None = None,
    context_mode: str = "auto",
    model_id: str | None = None,
    thinking: str | None = None,
    context: str = "",
) -> Agent:
    # 心智规划提前（S56 C 架构）：style_prefs 供写作工具意图模式选文笔 skill
    # S61：context=本轮用户意图，心智块渐进式披露按相关动态选取
    if agency_level is None:
        session_plan = deps.mind_planner.plan(
            book_id, base_agency=deps.agency.get_current(book_id).order, context=context
        )
    else:
        session_plan = deps.mind_planner.plan(book_id, context=context)
    # 工具装配（S52 抽出为独立模块 toolkit.build_toolkit——组合根接口化，
    # 与 HTTP 编排解耦；S62：依赖收敛为 ToolContext 单对象，签名稳定）
    registry = build_toolkit(
        ToolRegistry(),
        ToolContext(
            chapters=deps.chapters,
            workspace=deps.workspace,
            model=deps.model,
            graph=deps.graph,
            plots=deps.plots,
            plans=deps.plans,
            settings=deps.settings,
            materials=deps.materials,
            ext_tools=deps.ext_tools,
            dim_store=deps.dim_store,
            manual=deps.manual,
            skills_store=deps.skills,
            style_prefs=session_plan.style_prefs,
            workflow_store=deps.workflow_store,
            workflow_engine=deps.workflow_engine,
            workflow_generator=deps.workflow_generator,
            play_engine=deps.play_engine,
            review_panel=deps.review_panel,
            skill_generator=deps.skill_generator,
            # S68：探索注入真实模板库（L2+L3 合并，agent 的 explore_direction 消费）
            templates=[f"{t.name}：{t.description}" for t in deps.templates_external.all()[:12]],
        ),
        enable_domain=enable_domain,
        enable_codex=enable_codex,
        enable_extras=enable_extras,
        enable_search=enable_search,
        # S59：工作流 agent 工具（默认关，enable_workflow 点亮）
        enable_workflow=enable_workflow,
        # S65：互动推演 agent 工具（默认关，enable_play 点亮）
        enable_play=enable_play,
    )
    # 能动级别：显式传入 > 心智规划建议 > 已存档位（S35：档位记录，温度入档）
    # S50：心智模型=会话规划器——S62 修正：启发式档位推断**不自动应用**
    # （对齐 S61"建议不自动应用，用户主权"；启发式关键词猜意图会误判，
    # 见 S61 实测"不要反复确认"的"确认"抵消"直接写"）。用户未显式指定时
    # 一律用已存档位；推断结果只经 /api/mind/deps.agency-suggest 呈现供用户采纳。
    if agency_level is None:
        current = deps.agency.get_current(book_id)
    else:
        levels = deps.agency.list_levels()
        current = next(
            (lv for lv in levels if lv.order == int(agency_level)),
            deps.agency.get_level(f"default-{int(agency_level)}")
            or deps.agency.get_current(book_id),
        )
    eff_temp = current.temperature if temperature == 0.7 else temperature
    # S21 流式核心：不再构造 stream 模型——Agent 循环内部检测 respond_stream 流式；
    # 温度映射时重建模型（档位低=精确执行温度低）；测试 fake 走共享 deps.model
    base_model = getattr(deps.model, "inner", deps.model)
    m: Model
    if model_id:
        # S47 请求级指定模型：按该配置构造（显式指定 > 当前激活）
        cfg = deps.models.get(model_id)
        if cfg is None:
            raise ValueError(f"模型配置不存在: {model_id}")
        m = RetryingModel(
            DeepSeekModel(
                base_url=cfg.base_url,
                api_key=cfg.resolved_api_key(),
                model=cfg.model,
                temperature=eff_temp,
                max_tokens=cfg.max_tokens,
                context_window=cfg.context_window,
                thinking=cfg.thinking if thinking is None else thinking,
            )
        )
    elif isinstance(base_model, ModelProvider):
        # S47 运行时模型：按当前激活配置 + 档位温度 + 思考强度覆盖构造
        m = RetryingModel(base_model.build(temperature=eff_temp, thinking=thinking))
    elif isinstance(base_model, DeepSeekModel) and eff_temp != 0.7:
        # 真实模型 + 能动性温度映射（档位低=精确执行温度低）
        m = RetryingModel(DeepSeekModel(temperature=eff_temp))
    else:
        m = deps.model  # 共享 deps.model（测试注入或默认真实）；温度由构造决定
    # 注入块装配：核心注入默认全开，skip_inject 可细粒度关闭（S15 增强按需）
    skip = skip_inject or set()
    # S58b context_mode（主人偏好：默认不继承场景记忆）：
    # - auto/fresh（默认干净）：不注入场景记忆/剧情计划——新任务/探索不被上次对话绑架
    # - continue（显式继承）：注入场景记忆 + 剧情计划——跨会话续写时显式打开
    # 心智习惯/世界事实（简介/设定档）始终保留（行为底线，非进程状态）。
    if context_mode != "continue":
        skip = skip | {"memory", "plan"}
    # 注入块装配（S62：表驱动重构——块定义收敛为 (key, 位置, 内容)，
    # 顺序/去留/优先级从 90 行 if 链变成可读数据；语义不变：
    # prepend 块（brief/collab 协作约定）置顶，其余按声明顺序追加）
    prepend_blocks: list[str] = []
    append_blocks: list[str] = []

    # 置顶块：项目简介（定调）→ 协作约定（怎么配合我）
    if "brief" not in skip:
        brief_block = deps.workspace.read_brief(book_id)
        if brief_block:
            prepend_blocks.append(f"# 项目简介\n{brief_block}")
    if "manual" not in skip:
        collab_block = session_plan.collab_block()
        if collab_block:
            prepend_blocks.append(collab_block)

    # 追加块（按声明顺序 = 优先级）
    if "story" not in skip:
        tree_block = deps.story_tree.render_tree(book_id)
        thread_block = deps.story_threads.render_threads(book_id)
        nav = "\n\n".join(x for x in (tree_block, thread_block) if x)
        if nav:
            append_blocks.append(nav)
    # 能动性注入：当前档位（机制 2；职责边界：档位只管能动性，心智模型独立系统）
    if "agency" not in skip:
        agency_block = build_agency_block(current)
        if agency_block:
            append_blocks.append(agency_block)
    # AI 倾向档案注入（双向黑盒解法）
    if "bias" not in skip:
        bias_block = deps.bias.render()
        if bias_block:
            append_blocks.append(bias_block)
    # 关键点图谱注入（T2 阶段 3：当前推进状态——哪些伏笔还开着/刚回收）
    # S31：注入时传当前章节数（老龄化：must 钩子标"已开放 N 章"，中性事实）
    if "plot" not in skip:
        plot_block = deps.plots.render(
            book_id, current_order=len(deps.chapters.list_by_book(book_id))
        )
        if plot_block:
            append_blocks.append(plot_block)
    # 设定档注入（S41 作者正典：人物卡/能力体系/世界观规则——与图谱互补）
    if "settings" not in skip:
        settings_block = render_settings_adaptive(deps.settings.list())
        if settings_block:
            append_blocks.append(settings_block)
    # S83 约束注入（作品规则：全局 + 当前时空点实体相关——与已固化事实同源选取）
    if "constraints" not in skip:
        constraint_entries = deps.settings.list_constraints(book_id)
        if constraint_entries:
            # 当前情景实体 = 当前时空点已知实体（复用图谱 known_facts 选取）
            ctx_entities: set[str] = set()
            try:
                facts = deps.graph.known_facts(
                    book_id, up_to_order=None, max_entities=15, max_relations=0, max_events=0
                )
                ctx_entities = {e.name for e in facts["entities"]}
            except Exception:  # 图谱读取失败不阻断约束注入（仅全局）
                ctx_entities = set()
            constraints_block = render_constraints_block(constraint_entries, ctx_entities)
            if constraints_block:
                append_blocks.append(constraints_block)
    # S53 心智指导块：文风偏好 + 习惯（渐进式披露：只列关键条目，指导性保留）
    if "manual" not in skip:
        mind_block = session_plan.mind_block()
        if mind_block:
            append_blocks.append(mind_block)
    # S74c 心智变更通知（未读）：agent 读到应告知用户（知情），用户可要求改回（指导权）
    if "manual" not in skip:
        notices = deps.manual.unread_notices(book_id)
        if notices:
            nlines = ["# 心智变更通知（请在本轮回复中告知用户；用户可要求改回/纠正）"]
            for n in notices:
                if n["action"] == "update":
                    nlines.append(f"- 修改了偏好：「{n['old_content']}」→「{n['new_content']}」")
                elif n["action"] == "delete":
                    nlines.append(f"- 删除了偏好：「{n['old_content']}」")
                else:
                    nlines.append(f"- 新增偏好：「{n['new_content']}」")
            append_blocks.append("\n".join(nlines))
            deps.manual.mark_notices_read(book_id)
    # S53c ④ 下轮展示学到：上次会话的场景记忆（跨会话延续性，归档过才注入）
    if "memory" not in skip:
        last_memory = deps.memory_store.latest(book_id)
        if last_memory is not None:
            append_blocks.append("# 上次会话的延续（场景记忆）\n" + last_memory.content)
    # 叙事技巧注入（S50：索引常驻+内容按需；S55 #3 按 deps.skills 内容签名缓存）
    # S60：主循环只注入全部技巧索引（target 不限——决策者需要看到全部可用
    # 技巧才能点名给写作调用）；完整内容靠 skill_lookup 按需 / write_chapter
    # 的 deps.skills 参数点名（对齐图谱：内容按需查）。
    if "skills" not in skip:
        skill_sig = deps.skills.revision()
        cached = _skill_cache.get(skill_sig)
        if cached is not None:
            skill_block = cached
        else:
            skill_block = render_skill_index(deps.skills.list_skills(), target="")
            _skill_cache[skill_sig] = skill_block
            # 缓存防膨胀：超过 16 个签名清理最旧（长会话/多书场景安全阀）
            if len(_skill_cache) > 16:
                oldest = next(iter(_skill_cache))
                _skill_cache.pop(oldest, None)
        if skill_block:
            append_blocks.append(skill_block)
    # 剧情计划注入（S46：当前章+后续计划——AI 知道接下来写什么）
    if "plan" not in skip:
        plan_block = render_plan(deps.plans.list())
        if plan_block:
            append_blocks.append(plan_block)

    # S70：破限模式（书籍级开关）——写作自由度：黑暗/暴力/敏感题材不设禁区。
    # 注入 agent 主循环（对话/写作全路径）+ write_chapter 干净调用（工具侧另注）。
    if deps.workspace.is_uncensored(book_id):
        append_blocks.append(UNCENSORED_PROMPT)

    full_prompt = system_prompt
    if prepend_blocks:
        full_prompt = "\n\n".join(prepend_blocks) + "\n\n" + full_prompt
    if append_blocks:
        full_prompt = full_prompt + "\n\n" + "\n\n".join(append_blocks)
    return Agent(
        model=m,
        registry=registry,
        store=deps.store,
        system_prompt=full_prompt,
        context_compressor=deps.budget.compress,  # token 预算两阶段压缩（S8）
        persist_compression=True,  # S26：压缩结果回写 deps.store（pi compaction entry 语义）
    )
