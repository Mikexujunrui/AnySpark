"""
anyspark.server.app — FastAPI 后端（真实 API 层）。

提供：对话→写作→修改闭环的 HTTP 接口 + 章节读写接口。
所有真实组件（DeepSeekModel / SQLite 存储 / 写作工具）在此装配。
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from anyspark.align import (
    AgencyStore,
    BiasStore,
    ManualStore,
    MemoryStore,
    MindPlanner,
    PreferenceExtractor,
    SessionSummarizer,
    SignalCollector,
    SignalStore,
    SkillGenerator,
    StoryPlanStore,
    StoryThreadStore,
    StoryTreeStore,
    WorldSettingStore,
    WritingSkillStore,
)
from anyspark.check import run_review
from anyspark.core import (
    Agent,
    CancellationToken,
    Message,
    Model,
    RetryingModel,
)
from anyspark.explore import (
    DimensionStore,
    ProjectArchive,
)
from anyspark.graph import GraphExtractor, GraphInjector, GraphStore, GraphVerifier
from anyspark.models.registry import (
    ModelProvider,
    ModelRegistry,
)
from anyspark.play import PlayEngine, PlayStore
from anyspark.review import ReviewPanel
from anyspark.server.agent_factory import make_agent
from anyspark.server.context import TokenBudget, make_summarizer
from anyspark.server.deps import AppDeps, BgTask
from anyspark.server.logging import log_path, logger, setup_logging
from anyspark.server.recorder import RunRecorder
from anyspark.server.routes_agency import make_agency_router
from anyspark.server.routes_books import make_books_router
from anyspark.server.routes_chapters import make_chapters_router
from anyspark.server.routes_chat import make_chat_router
from anyspark.server.routes_conversations import make_conversations_router
from anyspark.server.routes_explore import make_explore_router
from anyspark.server.routes_graph import make_graph_router
from anyspark.server.routes_mind import make_mind_router
from anyspark.server.routes_play import make_play_router
from anyspark.server.routes_plot import make_plot_router
from anyspark.server.routes_settings import make_settings_router
from anyspark.server.routes_skills import make_skills_router
from anyspark.server.routes_story import make_story_router
from anyspark.server.routes_tools import make_tools_router
from anyspark.server.routes_workflow import make_workflow_router
from anyspark.server.routes_workspace import make_workspace_router
from anyspark.server.schemas import (
    DEFAULT_SYSTEM as DEFAULT_SYSTEM,  # re-export（test_recorder 兼容）
)
from anyspark.server.tasks import extract_chapter, review_for_learning, start_bg_worker
from anyspark.server.tools_extensions import (
    ExtensionToolStore,
)
from anyspark.server.workspace import Workspace
from anyspark.store import ChapterStore, SqliteConversationStore
from anyspark.template import (
    ExternalLibrary,
    MaterialStore,
    PlotGenerator,
    PlotResolver,
    PlotStore,
)
from anyspark.workflow import (
    NodeResult,
    RunContext,
    WorkflowEngine,
    WorkflowGenerator,
    WorkflowStore,
    wait_approval,
)

# 数据根：项目 data/（gitignored，绝不入库）
PROJECT_ROOT = Path(__file__).resolve().parents[5]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "anyspark.db"

# S55 #3 注入块分层缓存：stable 块（跨请求不变）按签名缓存，volatile 块每次组装。
# 签名=底层数据内容（任何增删改 → 签名变 → 缓存失效），避免长会话重复渲染。


# 应用装配
# ---------------------------------------------------------------------------
def build_app(
    model: Model | None = None,
    db_path: str | Path | None = None,
    workspace: Workspace | None = None,
) -> FastAPI:
    """装配后端应用。

    - model: 真实 DeepSeekModel（默认）；测试可注入 fake model（实现 core.Model 协议）
    - db_path: 默认 data/anyspark.db；测试可注入临时路径
    - workspace: S48 工作区（默认 data/workspace）；测试可注入临时路径隔离
    """
    load_dotenv(PROJECT_ROOT / ".env")
    setup_logging()

    real_db = db_path or DB_PATH
    store = SqliteConversationStore(real_db)
    # S48 工作区化：每项目一路径（上传/章节/卡片），章节 md 文件为权威
    # 默认与 db 配对隔离（防测试污染全局）：未显式注入时——
    #   默认 db → data/workspace；临时 db → db 同目录 workspace；:memory: → 临时目录
    if workspace is None:
        if real_db == ":memory:":
            import tempfile

            workspace = Workspace(root=Path(tempfile.mkdtemp()))
        elif db_path is None:
            workspace = Workspace()
        else:
            workspace = Workspace(root=Path(real_db).parent / "workspace")
    chapters = ChapterStore(real_db)
    ext_tools = ExtensionToolStore(real_db)  # S48-P4/B：扩展工具注册表（人工批准生效）
    # S49 会话运行记录：与 db 配对隔离（同 workspace 逻辑——防测试污染全局 records）
    if real_db == ":memory:":
        import tempfile as _tf

        recorder = RunRecorder(root=Path(_tf.mkdtemp()))
    elif db_path is None:
        recorder = RunRecorder()
    else:
        recorder = RunRecorder(root=Path(real_db).parent / "records")
    manual = ManualStore(real_db)
    signals = SignalStore(real_db)
    archive = ProjectArchive(real_db)
    dim_store = DimensionStore(real_db)  # S50 探索维度内容化（可增删改）
    materials = MaterialStore(real_db)
    templates_external = ExternalLibrary(real_db)
    plots = PlotStore(real_db)
    # 活跃会话的取消令牌（S21：/api/chat/cancel 可中断正在跑的 Agent）
    _active_tokens: dict[str, CancellationToken] = {}
    # 活跃会话的 Agent 实例（S25：/api/chat/steer 运行中插话用）——chat/chat_stream
    # 启动时注册、结束时注销；steer 端点据此把插话消息投入 steer_queue。
    _active_agents: dict[str, Agent] = {}
    _active_lock: threading.Lock = threading.Lock()

    # 后台任务队列 + 独立 worker（S21 修 BackgroundTasks 共享线程池排队缺陷）：
    # 图谱抽取/伏笔回收/信号提炼不占请求线程池，请求立即返回、后台串行处理。
    # 任务负载类型（S28 扩展）：("chapter", title, content, order) 图谱抽取/伏笔回收；
    # ("refine",) 信号→说明书提炼；("batch_rewrite", batch_id, ids, instruction) 批量改写；
    # ("batch_review", batch_id, ids) 批量审读（S40）。

    _bg_queue: queue.Queue[BgTask] = queue.Queue()  # 后台任务队列（S28/S40）
    # S40 批量任务状态（内存会话级）：id → {status, done, total, results}
    _batches: dict[str, dict[str, Any]] = {}
    _batch_lock: threading.Lock = threading.Lock()

    mind_planner = MindPlanner(manual)  # S50 心智模型=会话规划器（不从写作循环注入）
    signal_collector = SignalCollector(signals)
    # S47 运行时模型：注册表（持久化多配置）+ 动态 Provider——
    # 默认装配 RetryingModel(ModelProvider(registry))，所有组件跟随当前激活配置；
    # 测试可注入 fake model（实现 core Model 协议），走共享分支不受影响。
    # 注意：必须在任何依赖 model 的组件（summarizer/plot/提炼器等）之前初始化。
    models = ModelRegistry(real_db)
    provider = ModelProvider(models)
    model = model or RetryingModel(provider)
    memory_store = MemoryStore(real_db)  # S53c ② 场景记忆（项目档案延续性层）
    story_tree = StoryTreeStore(real_db)  # S59 叙事树（分叉路径模型）
    story_threads = StoryThreadStore(real_db)  # S59 线进度（映射锚）
    summarizer = SessionSummarizer(model, memory_store)  # ② 归档摘要器（真实 LLM）
    plot_generator = PlotGenerator(model)  # 依赖 model，须在其初始化之后
    plot_resolver = PlotResolver(model)  # 伏笔自动回收（S17：章节落盘后台识别揭开）
    preference_extractor = PreferenceExtractor(model)  # S28：信号→说明书提炼（后台）
    skill_generator = SkillGenerator(model)  # S54：文风提炼→skill 候选（人工确认生效）
    # 知识图谱（S7：AI 事实源）
    graph = GraphStore(real_db)
    graph_extractor = GraphExtractor(model, types=graph.types_for("main"))  # S50：类型集内容化
    graph_injector = GraphInjector(graph)
    graph_verifier = GraphVerifier(graph)
    # token 预算 + 两阶段压缩（S8：长书上下文刚需；S26：预算按模型窗口配置——
    # 窗口 64K 时预算 ~45K，不再 12K 硬编码导致长书频繁压缩）
    _window = getattr(getattr(model, "inner", model), "context_window", 65536)
    budget = TokenBudget(
        budget=int(_window * 0.7),
        summarize=make_summarizer(model),
    )
    # 能动性协议（机制 2）+ AI 倾向档案（S9）
    agency = AgencyStore(real_db)
    bias = BiasStore(real_db)
    settings = WorldSettingStore(real_db)  # S41 设定档（作者正典）
    skills = WritingSkillStore(real_db)  # S50 叙事技巧（skill 式内容载体）
    plans = StoryPlanStore(real_db)  # S46 剧情计划（计划→执行）

    # S59 工作流扩展包（可选增强，默认关）：结构化流程（顺序/分支/循环）+
    # 断点恢复 + AI 生成（草稿→人工确认转正）。runner 由组合根注入：
    # agent 节点=干净单次 LLM 调用；script 节点=确定性函数（read/review）；
    # approval=等待人工。
    workflow_store = WorkflowStore(real_db)
    workflow_generator = WorkflowGenerator(model)
    # S65 互动推演（独立扩展包 anyspark-play）：扮演角色多轮选择推进的推演树
    # S65：拟人化评审团面板（系统评审员随包分发 + 用户自定义覆盖 data/reviewers/）
    review_panel = ReviewPanel()
    try:
        review_panel.add_dir(DATA_DIR / "reviewers")
    except Exception as _rpe:  # 用户目录损坏不影响服务启动
        logger.warning("加载用户评审员失败: %s", _rpe)
    play_store = PlayStore(real_db)

    def _wf_run_agent(ctx: RunContext, node: Any) -> NodeResult:
        """agent 节点：干净单次 LLM 调用（无对话历史/工具记录——对齐 S56 干净写作）。

        变量插值：instruction/system_prompt 中的 {{var}} 从上游节点输出解析
        （如 {{chapter_text}} = 前序 read_chapter 脚本的产出）——真实链路暴露的
        接缝：AI 生成的流程若不插值，agent 拿不到章节内容。
        """
        instruction = _wf_resolve(str(node.params.get("instruction") or ""), ctx)
        system = _wf_resolve(str(node.params.get("system_prompt") or ""), ctx)
        # 便捷注入：params.chapter_title 指定章节时自动附带正文
        chapter_title = str(node.params.get("chapter_title") or "")
        if chapter_title:
            ch = next(
                (c for c in chapters.list_by_book(ctx.book_id) if c.title == chapter_title),
                None,
            )
            if ch is not None:
                instruction = f"【章节正文】\n{ch.content[:8000]}\n\n{instruction}"
        messages: list[Any] = []
        if system:
            messages.append(Message(role="system", content=system))
        messages.append(Message(role="user", content=instruction))
        out = model.respond(messages, [])
        text = (out.text or "").strip()
        if not text:
            return NodeResult(error="agent 节点空输出")
        usage = getattr(out, "usage", None)
        tokens = int(getattr(usage, "total_tokens", 0) or 0)
        return NodeResult(output=text, token_usage=tokens)

    def _wf_resolve(text: str, ctx: RunContext) -> str:
        """把 {{var}} 占位符替换为上游节点输出（缺失保留原样）。"""
        import re

        def _repl(m: re.Match[str]) -> str:
            key = m.group(1)
            val = ctx.results.get(key, "")
            return str(val) if val else f"{{{{{key}}}}}"

        return re.sub(r"\{\{\s*([A-Za-z0-9_.\-]+)\s*\}\}", _repl, text)

    def _wf_run_script(ctx: RunContext, node: Any) -> NodeResult:
        """script 节点：确定性函数（内置白名单）。"""
        fn = str(node.params.get("function") or "")
        if fn == "noop":
            # 无操作（AI 生成流程常用来做循环体出口占位）
            return NodeResult(output=str(node.params.get("output_key") or "done"))
        if fn == "read_chapter":
            title = str(node.params.get("chapter_title") or "")
            chs = chapters.list_by_book(ctx.book_id)
            ch = next((c for c in chs if c.title == title), None)
            if ch is None:
                # 模糊匹配（AI 生成标题可能不精确——真实链路暴露）：
                # ① 双向包含 ② 提取双方"第X章"片段做章号匹配
                def _chapter_no(t: str) -> str:
                    import re as _re

                    m = _re.search(r"第\s*([0-9一二三四五六七八九十百]+)\s*章", t)
                    return m.group(1) if m else ""

                t_no = _chapter_no(title)
                for c in chs:
                    if title and (title in c.title or c.title in title):
                        ch = c
                        break
                    if t_no and _chapter_no(c.title) == t_no:
                        ch = c
                        break
            if ch is None:
                return NodeResult(
                    error=f"章节不存在: {title}（可用章节: "
                    + ", ".join(c.title for c in chs[:8])
                    + "）"
                )
            return NodeResult(output=ch.content)
        if fn == "review_chapter":
            title = str(node.params.get("chapter_title") or "")
            ch = next((c for c in chapters.list_by_book(ctx.book_id) if c.title == title), None)
            if ch is None:
                return NodeResult(error=f"章节不存在: {title}")
            report = run_review(model, ch.title, ch.content[:20000])
            return NodeResult(output=f"硬伤数: {report.hard_count}\n" + report.render())
        if fn == "list_chapters":
            chs = chapters.list_by_book(ctx.book_id)
            if not chs:
                return NodeResult(output="（无章节）")
            return NodeResult(output="\n".join(f"{c.order_index}. {c.title}" for c in chs))
        if fn == "write_chapter":
            """写回章节：参数 chapter_title + content（或 {{var}} 引用上游改写结果）。

            content 缺失时取 params.text_key（缺省 'rewritten'）对应的上游输出——
            AI 生成的流程常用：改写 agent 输出 rewritten → write_chapter 脚本落盘。
            """
            title = str(node.params.get("chapter_title") or "")
            content = str(node.params.get("content") or "")
            if not content:
                text_key = str(node.params.get("text_key") or "rewritten")
                content = str(ctx.results.get(text_key, ""))
            if not title:
                return NodeResult(error="write_chapter 缺 chapter_title")
            if not content.strip():
                return NodeResult(error="write_chapter 无内容（检查 text_key 上游输出）")
            try:
                chs = chapters.list_by_book(ctx.book_id)
                ch = next((c for c in chs if c.title == title), None)
                if ch is None:
                    order = len(chs) + 1
                    chapters.upsert(ctx.book_id, title, content, order)
                else:
                    chapters.upsert(ctx.book_id, title, content, ch.order_index)
                # 双写落盘（工作区 md 权威，与 write_chapter 工具一致）
                try:
                    order = ch.order_index if ch else (len(chs) + 1)
                    workspace.write_chapter(ctx.book_id, order, title, content)
                except Exception:
                    pass  # 库镜像已更新，落盘失败不阻断
                return NodeResult(output=f"已写回章节: {title}")
            except Exception as exc:
                return NodeResult(error=f"写回失败: {exc}")
        return NodeResult(error=f"未注册的 script 函数: {fn}")

    def _wf_run_approval(ctx: RunContext, node: Any) -> NodeResult:
        """approval 节点：抛等待信号（任务置 waiting_approval，人工 approve 后续跑）。"""
        wait_approval()
        return NodeResult(output="approved")

    def _wf_runner(ctx: RunContext, node: Any) -> NodeResult:
        if node.kind == "agent":
            return _wf_run_agent(ctx, node)
        if node.kind == "script":
            return _wf_run_script(ctx, node)
        if node.kind == "approval":
            return _wf_run_approval(ctx, node)
        return NodeResult(error=f"未知节点类型: {node.kind}")

    def _wf_judge(prompt: str, ctx: RunContext) -> bool:
        """model 型条件：自然语言问题 → 模型判断 yes/no。

        真实链路暴露：模型答"否/不通过"时旧逻辑误判。强制输出 是/否 首字判定，
        明确否定词优先级（避免"没有硬伤"被"有"字误判）。
        """
        out = model.respond(
            [
                Message(
                    role="system",
                    content="你只判断一个条件是否成立。必须严格以单个字'是'或'否'开头回答，不要解释。",
                ),
                Message(role="user", content=prompt),
            ],
            [],
        )
        text = (out.text or "").strip()
        if not text:
            return False
        first = text[0]
        # 否定词优先（'不'/'没'/'无'/'否' 开头 → False；'是'/'通' 开头 → True）
        if first in ("不", "没", "无", "否", "非"):
            return False
        if first in ("是", "通", "可", "同", "y", "Y", "t", "T"):
            return True
        # 兜底：整句包含强肯定词且无否定词
        lower = text.lower()
        has_pos = any(w in lower for w in ("yes", "true", "通过", "可以", "同意"))
        has_neg = any(w in lower for w in ("no", "false", "不是", "不通过", "没有", "无法"))
        return has_pos and not has_neg

    workflow_engine = WorkflowEngine(workflow_store, _wf_runner, model_judge=_wf_judge)
    # S65：play 引擎（树存储 + LLM 生成；角色卡加载复用 explore load_role_card）
    play_engine = PlayEngine(play_store, model, workspace, graph)

    app = FastAPI(title="AnySpark v4 API", version="0.0.1")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 开发期；前端 Vite dev server 在此端口
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> Response:
        """全局兜底：未捕获异常打 ERROR 日志（含 traceback）再返回 500——
        此前 _make_agent 等 try 块外的异常静默 500 零日志，排查无据。"""
        logger.exception("未捕获异常: %s %s", request.method, request.url.path, exc_info=exc)
        return Response(status_code=500, content="Internal Server Error")

    # S80b：组合根依赖契约（AppDeps 单例；router 拆分后各 make_xxx_router(deps) 注入）
    deps = AppDeps(
        store=store,
        chapters=chapters,
        ext_tools=ext_tools,
        manual=manual,
        signals=signals,
        archive=archive,
        dim_store=dim_store,
        materials=materials,
        templates_external=templates_external,
        plots=plots,
        models=models,
        memory_store=memory_store,
        story_tree=story_tree,
        story_threads=story_threads,
        graph=graph,
        agency=agency,
        bias=bias,
        settings=settings,
        skills=skills,
        plans=plans,
        workflow_store=workflow_store,
        play_store=play_store,
        mind_planner=mind_planner,
        signal_collector=signal_collector,
        provider=provider,
        model=model,
        summarizer=summarizer,
        plot_generator=plot_generator,
        plot_resolver=plot_resolver,
        preference_extractor=preference_extractor,
        skill_generator=skill_generator,
        graph_extractor=graph_extractor,
        graph_injector=graph_injector,
        graph_verifier=graph_verifier,
        budget=budget,
        window=_window,
        db_path=str(real_db),
        workflow_generator=workflow_generator,
        workflow_engine=workflow_engine,
        play_engine=play_engine,
        review_panel=review_panel,
        active_tokens=_active_tokens,
        active_agents=_active_agents,
        active_lock=_active_lock,
        bg_queue=_bg_queue,
        batches=_batches,
        batch_lock=_batch_lock,
        workspace=workspace,
        recorder=recorder,
    )

    # 兼容薄包装：端点仍按原闭包名调用（router 拆分后移除）
    def _make_agent(*args: Any, **kwargs: Any) -> Agent:
        return make_agent(deps, *args, **kwargs)

    def _extract_chapter(*args: Any, **kwargs: Any) -> None:
        return extract_chapter(deps, *args, **kwargs)

    def _review_for_learning(*args: Any, **kwargs: Any) -> None:
        return review_for_learning(deps, *args, **kwargs)

    start_bg_worker(deps)
    app.include_router(make_conversations_router(deps))
    app.include_router(make_books_router(deps))
    app.include_router(make_agency_router(deps))
    app.include_router(make_chapters_router(deps))
    app.include_router(make_chat_router(deps))
    app.include_router(make_explore_router(deps))
    app.include_router(make_graph_router(deps))
    app.include_router(make_mind_router(deps))
    app.include_router(make_play_router(deps))
    app.include_router(make_plot_router(deps))
    app.include_router(make_settings_router(deps))
    app.include_router(make_skills_router(deps))
    app.include_router(make_story_router(deps))
    app.include_router(make_tools_router(deps))
    app.include_router(make_workflow_router(deps))
    app.include_router(make_workspace_router(deps))

    @app.get("/api/health")
    def health() -> dict[str, str]:
        name = getattr(model, "model_name", "unknown")
        return {"status": "ok", "model": str(name), "log": log_path()}

    return app


app = build_app()
