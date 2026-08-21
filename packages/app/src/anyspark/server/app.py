"""
anyspark.server.app — FastAPI 后端（真实 API 层）。

提供：对话→写作→修改闭环的 HTTP 接口 + 章节读写接口。
所有真实组件（DeepSeekModel / SQLite 存储 / 写作工具）在此装配。
"""

from __future__ import annotations

import contextlib
import os
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

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
from anyspark.core import (
    Agent,
    CancellationToken,
    Model,
    RetryingModel,
)
from anyspark.explore import (
    DimensionStore,
    ProjectArchive,
)
from anyspark.graph import GraphExtractor, GraphInjector, GraphStore, GraphVerifier
from anyspark.library import LibraryStore
from anyspark.models.mode import ModeResolver, ModeStore
from anyspark.models.registry import (
    ModelProvider,
    ModelRegistry,
)
from anyspark.play import PlayEngine, PlayStore
from anyspark.review import ReviewPanel
from anyspark.server.context import TokenBudget, make_summarizer
from anyspark.server.deps import AppDeps, BgTask
from anyspark.server.logging import log_path, logger, setup_logging
from anyspark.server.recorder import RunRecorder
from anyspark.server.routes_agency import make_agency_router
from anyspark.server.routes_books import make_books_router
from anyspark.server.routes_chapters import make_chapters_router
from anyspark.server.routes_chat import make_chat_router
from anyspark.server.routes_check import make_check_router
from anyspark.server.routes_conversations import make_conversations_router
from anyspark.server.routes_explore import make_explore_router
from anyspark.server.routes_graph import make_graph_router
from anyspark.server.routes_library import make_library_router
from anyspark.server.routes_mind import make_mind_router
from anyspark.server.routes_mode import make_mode_router
from anyspark.server.routes_play import make_play_router
from anyspark.server.routes_plot import make_plot_router
from anyspark.server.routes_settings import make_settings_router
from anyspark.server.routes_skills import make_skills_router
from anyspark.server.routes_story import make_story_router
from anyspark.server.routes_tools import make_tools_router
from anyspark.server.routes_update import make_update_router
from anyspark.server.routes_workflow import make_workflow_router
from anyspark.server.routes_workspace import make_workspace_router
from anyspark.server.schemas import (
    DEFAULT_SYSTEM as DEFAULT_SYSTEM,  # re-export（test_recorder 兼容）
)
from anyspark.server.seeds import (
    _migrate_templates_to_skills,
    _seed_book_refine_template,
)
from anyspark.server.tasks import start_bg_worker
from anyspark.server.tools_extensions import (
    ExtensionToolStore,
)
from anyspark.server.workspace import Workspace
from anyspark.store import ChapterStore, SqliteConversationStore
from anyspark.template import (
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
)

# 数据根：项目 data/（gitignored，绝不入库）
# S109 打包改造：PyInstaller frozen 下——资源根=_MEIPASS（只读：frontend dist/.env 模板/reviewers），
# 数据根=exe 同目录 /data（用户可写、可整体拷贝）；开发模式保持项目 data/。


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _runtime_root() -> Path:
    """资源根：frozen → PyInstaller 解包目录（只读）；开发 → 项目根。"""
    if _is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[5]


def _data_root() -> Path:
    """数据根：frozen → exe 同目录 /data（可写、可拷贝、可见）；开发 → 项目 data/。"""
    if _is_frozen():
        return Path(sys.executable).resolve().parent / "data"
    return Path(__file__).resolve().parents[5] / "data"


PROJECT_ROOT = _runtime_root()
DATA_DIR = _data_root()
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
    # S109：.env 位置——frozen 下放数据根（exe 同目录，用户可填 key）；缺失时从模板生成
    if _is_frozen():
        env_path = DATA_DIR / ".env"
        if not env_path.exists():
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            template = PROJECT_ROOT / ".env.example"
            if template.exists():
                with contextlib.suppress(Exception):
                    env_path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
            logger.warning("已生成 .env 模板（请填入 DeepSeek API Key 后重启）：%s", env_path)
    else:
        env_path = PROJECT_ROOT / ".env"
    load_dotenv(env_path)
    setup_logging()

    real_db = db_path or DB_PATH
    store = SqliteConversationStore(real_db)
    # S200：启动时自动修复历史悬挂 tool_calls 声明（幂等；旧版遗留数据一次性落库清干净，
    # 用户升级后无需任何操作，首次启动即完成——否则旧会话历史可能触发 OpenAI 400）
    try:
        _repaired = store.repair_dangling_decls()
        if _repaired:
            logger.info("启动修复: 清理 %d 条消息的历史悬挂 tool_calls 声明", _repaired)
    except Exception:
        logger.warning("启动修复跳过: 历史悬挂清理失败（不影响服务启动）", exc_info=True)
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

    mind_planner = MindPlanner(manual)  # S50 心智模型=会话规划器（不从写作循环注入）
    signal_collector = SignalCollector(signals)
    # S47 运行时模型：注册表（持久化多配置）+ 动态 Provider——
    # 默认装配 RetryingModel(ModelProvider(registry))，所有组件跟随当前激活配置；
    # 测试可注入 fake model（实现 core Model 协议），走共享分支不受影响。
    # 注意：必须在任何依赖 model 的组件（summarizer/plot/提炼器等）之前初始化。
    models = ModelRegistry(real_db)
    # S98 快速模式切换：模式/槽位/任务映射存储 + 解析器；provider 按任务分流（未配回退激活）
    mode_store = ModeStore(real_db)
    mode_resolver = ModeResolver(mode_store, models)
    provider = ModelProvider(models, mode=mode_resolver)
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
    # S128（PLAN-SKILL-UNIFY 阶段 2）：templates（ExternalLibrary）并入 skill 表。
    # 物理并入：L2 默认模板 + L3 外部模板迁移为 type=plot 条目（四要素+layer 存 ext），
    # 探索消费方改读 skills.plot_skills()；幂等同名跳过（可重复启动/迁移不重复）。
    _migrate_templates_to_skills(skills, real_db)
    plans = StoryPlanStore(real_db)  # S46 剧情计划（计划→执行）

    # S59 工作流扩展包（可选增强，默认关）：结构化流程（顺序/分支/循环）+
    # 断点恢复 + AI 生成（草稿→人工确认转正）。runner 由组合根注入：
    # agent 节点=干净单次 LLM 调用；script 节点=确定性函数（read/review）；
    # approval=等待人工。
    workflow_store = WorkflowStore(real_db)
    # S129（WORKFLOW 第 1 批）：预置拆书模板——把 skill_refine(mode=book) 的多步 LLM 管道
    # 声明化为 workflow（确定性步骤=script 节点，LLM 步骤=agent 节点，可断点/可编辑）。
    # prompt 文本在种子时从 skillgen 常量内联（模板=数据，用户可改拆解指令不碰代码）。
    _seed_book_refine_template(workflow_store)
    workflow_generator = WorkflowGenerator(model)
    # S65 互动推演（独立扩展包 anyspark-play）：扮演角色多轮选择推进的推演树
    # S65：拟人化评审团面板（系统评审员随包分发 + 用户自定义覆盖 data/reviewers/）
    # S109：frozen 下系统评审员在 _MEIPASS/reviewers（默认 parents 计算失效）
    review_panel = (
        ReviewPanel(system_dir=PROJECT_ROOT / "reviewers") if _is_frozen() else ReviewPanel()
    )
    try:
        review_panel.add_dir(DATA_DIR / "reviewers")
    except Exception as _rpe:  # 用户目录损坏不影响服务启动
        logger.warning("加载用户评审员失败: %s", _rpe)
    play_store = PlayStore(real_db)
    # S86 参考书库（全局文件区 data/library/ + 关联表）
    library = LibraryStore(real_db)
    # S195：用户自定义骨架检测项存储（DESIGN 机制 9 第③层持久化）
    from anyspark.server.check_store import UserSkeletonStore

    user_skeleton = UserSkeletonStore(real_db)

    # S187：工作流脚本函数提取到 wf_scripts.py（闭包→模块级，依赖通过 WfScriptDeps 传入）
    from anyspark.server.wf_scripts import WfScriptDeps, wf_judge, wf_runner

    wfd = WfScriptDeps()
    wfd.model = model
    wfd.chapters = chapters
    wfd.graph = graph
    wfd.settings = settings
    wfd.library = library
    wfd.workspace = workspace
    wfd.skills = skills
    # deps 在下方 AppDeps 创建后回填（wf_run_subagent/tasks 脚本需要）

    def _wf_runner(ctx: RunContext, node: Any) -> NodeResult:
        return wf_runner(wfd, ctx, node)

    def _wf_judge_wrapper(prompt: str, ctx: RunContext) -> bool:
        return wf_judge(wfd, prompt, ctx)

    workflow_engine = WorkflowEngine(workflow_store, _wf_runner, model_judge=_wf_judge_wrapper)
    # S65：play 引擎（树存储 + LLM 生成；角色卡加载复用 explore load_role_card）
    play_engine = PlayEngine(play_store, model, workspace, graph)

    app = FastAPI(title="AnySpark v4 API", version="0.0.1")
    # S116 安全收紧：CORS 从 "*" 改为 localhost 开发白名单（原 * 允许任意网页
    # 跨域调本地 API——配合无鉴权可被恶意网页触发 codex RCE）。
    # 前端 dev 走 Vite proxy（5173→8000，浏览器同源无需 CORS）；生产后端 serve
    # dist（同源）。第三方前端可用 ANYSPARK_CORS_ORIGINS（逗号分隔）显式扩展。
    _cors_origins = [
        o.strip() for o in os.environ.get("ANYSPARK_CORS_ORIGINS", "").split(",") if o.strip()
    ] or ["http://127.0.0.1:5173", "http://localhost:5173"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> Response:
        """全局兜底：未捕获异常打 ERROR 日志（含 traceback）再返回 500——
        此前 _make_agent 等 try 块外的异常静默 500 零日志，排查无据。"""
        logger.exception("未捕获异常: %s %s", request.method, request.url.path, exc_info=exc)
        return Response(status_code=500, content="Internal Server Error")

    @app.middleware("http")
    async def _access_log(request: Request, call_next: Any) -> Response:
        """S104：请求级访问日志——写操作 + 非 2xx + 慢读请求（防刷屏）。

        bug 定位用：前端报错时后端能查到这个端点/耗时/状态码；异常堆栈
        由 _unhandled 兜底（此处只记访问行，不重复记异常）。
        """
        started = time.monotonic()
        try:
            response: Response = await call_next(request)
        except Exception:
            raise  # 交给 _unhandled 记堆栈
        ms = int((time.monotonic() - started) * 1000)
        is_write = request.method in ("POST", "PUT", "PATCH", "DELETE")
        is_bad = response.status_code >= 400
        if is_write or is_bad or ms >= 2000:
            logger.info(
                "请求 %s %s → %d（%dms）%s",
                request.method,
                request.url.path,
                response.status_code,
                ms,
                f"?{request.url.query}" if request.url.query else "",
            )
        return response

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
        plots=plots,
        models=models,
        mode_store=mode_store,
        mode_resolver=mode_resolver,
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
        library=library,
        user_skeleton=user_skeleton,
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
        workspace=workspace,
        recorder=recorder,
    )

    # S187：回填 wfd.deps（wf_run_subagent/tasks 脚本需要 AppDeps）
    wfd.deps = deps

    # S81：shutdown 时统一 close 各 store 连接（WAL 优雅收尾；防连接泄漏）
    @app.on_event("shutdown")
    def _close_stores() -> None:
        for name in deps.__dataclass_fields__:
            obj = getattr(deps, name)
            close = getattr(obj, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:  # 单个失败不阻断其余
                    logger.warning("关闭 %s 失败: %s", name, exc)

    # S80d：router 拆分后薄包装已移除——端点直接调 make_agent(deps, ...) / extract_chapter(deps, ...)
    start_bg_worker(deps)
    app.include_router(make_conversations_router(deps))
    app.include_router(make_books_router(deps))
    app.include_router(make_agency_router(deps))
    app.include_router(make_chapters_router(deps))
    app.include_router(make_check_router(deps))
    app.include_router(make_chat_router(deps))
    app.include_router(make_explore_router(deps))
    app.include_router(make_graph_router(deps))
    app.include_router(make_mind_router(deps))
    app.include_router(make_mode_router(deps))
    app.include_router(make_library_router(deps))
    app.include_router(make_play_router(deps))
    app.include_router(make_plot_router(deps))
    app.include_router(make_settings_router(deps))
    app.include_router(make_skills_router(deps))
    app.include_router(make_story_router(deps))
    app.include_router(make_tools_router(deps))
    app.include_router(make_update_router(deps))
    app.include_router(make_workflow_router(deps))
    app.include_router(make_workspace_router(deps))

    @app.get("/api/health")
    def health() -> dict[str, str]:
        name = getattr(model, "model_name", "unknown")
        return {"status": "ok", "model": str(name), "log": log_path()}

    # S88：生产模式——frontend/dist 存在时由后端同端口 serve（单端口全包）。
    # /api/* 路由优先（FastAPI 先匹配路由后匹配 mount），静态资源走 dist。
    frontend_dist = PROJECT_ROOT / "frontend" / "dist"
    if (frontend_dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

    # S135：暴露组合根（测试/工具收编验证用——可直接取 workflow 依赖做单元验证）
    app.state.deps = deps
    return app


app = build_app()
