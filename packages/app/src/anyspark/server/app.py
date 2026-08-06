"""
anyspark.server.app — FastAPI 后端（真实 API 层）。

提供：对话→写作→修改闭环的 HTTP 接口 + 章节读写接口。
所有真实组件（DeepSeekModel / SQLite 存储 / 写作工具）在此装配。
"""

from __future__ import annotations

import json
import queue
import threading
import uuid
from pathlib import Path
from typing import Annotated, Any, Literal, cast

from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from anyspark.align import (
    AgencyStore,
    BiasStore,
    ManualEntry,
    ManualStore,
    MindPlanner,
    MoodDimStore,
    PreferenceExtractor,
    SignalCollector,
    SignalStore,
    StoryPlanStore,
    WorldSettingStore,
    WritingSkillStore,
    build_agency_block,
    build_mood_block,
    parse_agency_declaration,
    render_plan,
    render_settings,
    render_skill_index,
    render_skills_content,
)
from anyspark.check import compile_rule, run_review
from anyspark.core import (
    Agent,
    CancellationToken,
    Message,
    Model,
    RetryingModel,
    ToolRegistry,
)
from anyspark.explore import (
    DimensionStore,
    DirectionCard,
    IntentUnderstander,
    ProjectArchive,
    run_exploration,
)
from anyspark.graph import GraphExtractor, GraphInjector, GraphStore, GraphVerifier
from anyspark.models.deepseek import DEFAULT_BASE_URL, DeepSeekModel
from anyspark.models.registry import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    ModelConfig,
    ModelProvider,
    ModelRegistry,
    slugify,
)
from anyspark.server.context import TokenBudget, make_summarizer
from anyspark.server.logging import log_path, logger, setup_logging
from anyspark.server.recorder import RunRecorder
from anyspark.server.stats import compute_stats
from anyspark.server.toolkit import build_toolkit
from anyspark.server.tools_extensions import (
    ExtensionToolStore,
)
from anyspark.server.workspace import Workspace
from anyspark.store import ChapterStore, SqliteConversationStore
from anyspark.template import (
    ExternalLibrary,
    MaterialDigestor,
    MaterialStore,
    PlotGenerator,
    PlotResolver,
    PlotStore,
)

# 数据根：项目 data/（gitignored，绝不入库）
PROJECT_ROOT = Path(__file__).resolve().parents[5]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "anyspark.db"

# 默认写作系统提示（真实写作指令）
DEFAULT_SYSTEM = (
    "你是 AnySpark 小说写作智能体。你要直接写故事正文。"
    "写正文前用 list_chapters 查看章节列表；如需保持连贯，"
    "只需 read 最近的 1-2 章，不要读取全部历史章节"
    "（更早的内容由【已固化事实】注入提供）。"
    "若章节内容已在本轮对话历史或【已固化事实】注入中，直接基于它们，不要重复读取。"
    "写正文可用 write_chapter 保存。"
    "正文要具体、有画面感，杜绝空泛总结。"
    # S43：DEFAULT_SYSTEM 回归极简（只留行为底线）——写作技巧类规则已抽为内容载体
    # （WritingSkill：镜头感/对白机锋/节奏控制等叙事技巧，见【叙事技巧】注入块），不再堆行为守则
    "首要目标是把正文写出来并落盘，不要为了准备而反复调用与当前任务无关的工具。"
    "仅当用户给的任务方向不明确（种子含糊、无明确脉络、不知往哪个方向写）时，"
    "先调用 explore_direction 生成方向建议并在回复中列出询问用户选择；方向明确时直接写。"
)


def _sse_frame(event: str, data: dict[str, Any]) -> str:
    """SSE 帧：event: <type>\ndata: <json>\n\n（core 事件协议 → 传输层）。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# 氛围注入（机制 4）已由 align.mood 提供（S15 从组合根挪入 align，与 agency/bias 同归属）


# ---------------------------------------------------------------------------
# Pydantic 请求/响应模型
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户输入")
    conversation_id: str | None = None
    system_prompt: str | None = None
    temperature: float = 0.7
    agency_level: int | None = None  # 能动级别 0-4（覆盖当前档位；缺省用已存档位）
    mood: dict[str, float] | None = None  # 氛围滑块：维度→强度 0-100（如 tension: 80）
    # 增强按需装配（S15："你要什么再装什么"——默认关的增强，点亮才挂）
    enable_search: bool = False  # 网络搜索工具按需注册（默认关：写作主链路不背考据能力）
    enable_extras: bool = False  # S32 扩展工具（read_material/check_text）按需点亮
    enable_domain: bool = True  # S48-P2 领域工具（图谱查证/伏笔登记/计划推进/设定查证）默认开
    enable_codex: bool = False  # S48-P5 代码扩展 run_code（沙箱，默认关：安全按需点亮）
    extract_graph: bool = True  # 章节落盘后图谱抽取（默认开保持现状；可关省 token）
    skip_inject: list[str] = []  # 细粒度跳过注入：manual/graph/agency/bias/mood/plot 子集
    # S47 运行时模型选择：缺省用注册表当前激活模型；thinking 覆盖该模型默认思考强度
    model_id: str | None = None  # 指定用哪个已配置模型（未配置/不存在 → 400）
    thinking: str | None = None  # 思考强度覆盖：off/low/medium/high/xhigh/max（None=用模型配置）


class ModelIn(BaseModel):
    """S47 模型配置写入（新增或更新；id 缺省由 name 生成 slug）。"""

    id: str | None = None
    name: str
    base_url: str | None = None  # 缺省用 env 默认端点（DEEPSEEK_BASE_URL）
    model: str  # 模型名（如 deepseek-v4-flash / deepseek-v4-pro）
    api_key: str | None = None  # 缺省用 env DEEPSEEK_API_KEY
    context_window: int | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    thinking: str | None = None  # off/low/medium/high/xhigh/max（None=交模型默认）


class RoleCardIn(BaseModel):
    """S48-P4 角色卡（卡片/角色卡-{name}.md）。"""

    name: str
    content: str


class ToolUpdateIn(BaseModel):
    """S49 扩展工具更新（改后自动回 draft 重新批准）。"""

    name: str | None = None
    description: str | None = None
    params_json: str | None = None
    code: str | None = None


class ToolRegisterIn(BaseModel):
    """S48-P4/B 扩展工具登记（Agent 或用户提交，人工批准后生效）。"""

    name: str  # 工具名（唯一，agent 可见）
    description: str  # 工具描述（agent 判断何时调用用）
    params_json: str = "[]"  # 参数定义 JSON 数组
    code: str  # Python 代码：def run(args: dict) -> str


class RolePlayIn(BaseModel):
    """S48-P4 角色推演请求。"""

    role: str  # 角色名（角色卡文件名 + 图谱实体）
    scenario: str  # 推演场景（自然语言）
    n: int = 4  # 推演路数（2-6）


class CodexIn(BaseModel):
    """S48-P5 代码执行请求（沙箱安全）。"""

    code: str
    timeout: float = 10.0


class IngestIn(BaseModel):
    """S48-P3 消化上传区文件。mode：auto（自动判别）/ chapters（强制拆章）/ card（强制摘要卡）。"""

    filename: str
    mode: str = "auto"


class UploadIn(BaseModel):
    """S48 上传存档（base64 JSON，零新依赖）。"""

    filename: str
    data_b64: str  # base64 编码的文件内容


class ToolEvent(BaseModel):
    type: str
    payload: dict[str, Any]


class ChatResponse(BaseModel):
    conversation_id: str
    text: str
    turns: list[dict[str, Any]]
    events: list[ToolEvent]
    agency_declared: int | None = None  # AI 声明的档位（用户点选确认）


class ChapterOut(BaseModel):
    id: str
    book_id: str
    title: str
    content: str
    order_index: int
    updated_at: str


class ManualEntryIn(BaseModel):
    content: str
    confidence: float = 0.5
    scope: str = "project"
    category: str = "style"  # S50：collab(协作)/style(文风)/habit(习惯)


class ManualEntryPatch(BaseModel):
    content: str | None = None
    locked: bool | None = None
    category: str | None = None


class SignalIn(BaseModel):
    kind: str  # accepted|modified|deleted|rejected|custom
    content: str
    new_content: str | None = None
    context: str = ""


class ExploreIntentIn(BaseModel):
    seed: str


class ExploreCardsIn(BaseModel):
    seed: str
    intent_confirmed: dict[str, object]


class ExploreArchiveIn(BaseModel):
    card: dict[str, object]


class ExploreDimIn(BaseModel):
    """S50：探索维度（内容化，可增删改）。"""

    name: str


class ExploreDimPatch(BaseModel):
    enabled: bool


class CheckRequest(BaseModel):
    text: str
    target: str = "当前章节"
    chapter_order: int | None = None  # 时序校验：当前章节序号（校验时空倒置）
    line: str = "main"  # S29 多线叙事：当前写作的叙事线（时序校验按线比较）


class RuleRequest(BaseModel):
    rule: str
    text: str


class GraphTypeIn(BaseModel):
    """S50：实体类型（内容化，可增删改）。"""

    name: str


class GraphTypePatch(BaseModel):
    enabled: bool


class MaterialIn(BaseModel):
    text: str
    title: str = ""
    purpose: str = "fact"  # style|fact|both


class GraphExtractIn(BaseModel):
    chapter_ref: str
    text: str


class AgencyIn(BaseModel):
    level: int | None = None  # 兼容旧调用：排序位数字（0 起）
    level_id: str | None = None  # S35：档位记录 id（优先）


class AgencyLevelIn(BaseModel):
    """S35：新增/修改自定义档位。"""

    name: str
    description: str = ""
    temperature: float = 0.7


class BatchRewriteIn(BaseModel):
    """S40：批量改写（全书变换）——多章统一指令改写。"""

    chapter_ids: list[str]
    instruction: str


class BatchReviewIn(BaseModel):
    """S40：批量审读——多章检测网审读。"""

    chapter_ids: list[str]


class WorldSettingIn(BaseModel):
    """S41：设定档条目。"""

    content: str
    category: str = "世界观"
    name: str = ""


class WorldSettingPatch(BaseModel):
    content: str | None = None
    category: str | None = None
    name: str | None = None


class WorldSettingExtractIn(BaseModel):
    """S42：从图谱提炼设定草案（LLM 生成候选，作者逐条确认）。"""

    book_id: str = "main"


class SettingCategoryIn(BaseModel):
    """S50：设定档类别（内容化，可增删改）。"""

    name: str


class SettingCategoryPatch(BaseModel):
    enabled: bool


class WritingSkillIn(BaseModel):
    """S50：叙事技巧（skill 式内容载体）。"""

    name: str
    description: str = ""
    content: str
    example: str = ""  # 具体情形案例（提升文笔：样例比抽象指令有效）
    tags: str = ""  # 场景标签（逗号分隔，支撑按需选取）
    enabled: bool = True


class WritingSkillPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    content: str | None = None
    example: str | None = None
    tags: str | None = None
    enabled: bool | None = None


class MoodDimIn(BaseModel):
    """S50：氛围维度（内容化，可增删改）。"""

    key: str
    label: str
    description: str = ""
    example: str = ""


class MoodDimPatch(BaseModel):
    label: str | None = None
    description: str | None = None
    example: str | None = None
    enabled: bool | None = None


class ChapterPatchIn(BaseModel):
    """S44：定点编辑操作列表。"""

    operations: list[dict[str, Any]]


class ImpactIn(BaseModel):
    """S45：影响分析（连锁修改）——改某章（涉及实体）→ 受影响下游章节。"""

    chapter_order: int
    entities: list[str] | None = None


class ChapterPlanIn(BaseModel):
    """S46：剧情计划条目。"""

    chapter_order: int
    title: str = ""
    content: str = ""


class ChapterPlanPatch(BaseModel):
    title: str | None = None
    content: str | None = None
    status: str | None = None


class BiasIn(BaseModel):
    content: str
    source: str = "ai"


class DirectionIn(BaseModel):
    prompt: str
    context: str = ""  # 可选：章节摘要/设定约束


class CandidatesIn(BaseModel):
    prompt: str
    context: str = ""
    n: int = 3


class RewriteIn(BaseModel):
    text: str
    mode: str = "balanced"  # subtle|balanced|bold


class WrapupIn(BaseModel):
    chapter_id: str


class TemplateIn(BaseModel):
    name: str
    description: str
    granularity: str = "章"
    position: str = "发展"
    function: str = "主线"
    params: list[str] = []


class PlotIn(BaseModel):
    settings: str = ""  # 作品设定/种子（可选，缺省用已写章节）


class PlotPatchIn(BaseModel):
    status: str | None = None  # open|resolved
    attention: str | None = None  # care|ignore（用户标注在意/不需要）
    priority: str | None = None  # S31: must（剧情钩子，必须回收）| soft（细节线索）
    resolved_chapter: str | None = None  # S31: 回收章节


class PlotItemIn(BaseModel):
    """S31：主动登记一个关键点/伏笔（作者/AI 声明，非 LLM 生成）。"""

    content: str = Field(..., min_length=1)
    category: str = "伏笔"
    chapter_ref: str = ""
    priority: str = "soft"  # must=剧情钩子（作者承诺必须回收）/ soft=细节线索
    planted_order: int = 0  # S31 老龄化：登记时的章节序号（开放时长 = 当前章 - planted_order）


class CancelIn(BaseModel):
    conversation_id: str | None = None  # 空=取消最近活跃会话（新会话 id 客户端未知）


class SteerIn(BaseModel):
    conversation_id: str  # 目标会话（必须正在运行才能插话）
    message: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# 应用装配
# ---------------------------------------------------------------------------
def _now_iso_rec() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


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
    _bg_queue: queue.Queue[Any] = queue.Queue()  # 任务负载类型见 _bg_worker（S28/S40）
    # S40 批量任务状态（内存会话级）：id → {status, done, total, results}
    _batches: dict[str, dict[str, Any]] = {}
    _batch_lock: threading.Lock = threading.Lock()

    def _run_batch_rewrite(batch_id: str, chapter_ids: list[str], instruction: str) -> None:
        """批量改写：逐章 LLM 按指令改写 → upsert（覆盖前旧版进版本历史）。"""
        batch = _batches.get(batch_id)
        if not batch:
            return
        for cid in chapter_ids:
            try:
                assert model is not None  # 真实装配必有模型
                ch = chapters.get(cid)
                if ch is None:
                    batch["results"].append({"id": cid, "ok": False, "error": "章节不存在"})
                else:
                    prompt = (
                        "按用户指令改写以下章节。保持剧情走向/人物/设定/时间线一致，"
                        "只按指令调整（风格/情节/表达）。直接输出改写后的完整正文。\n"
                        f"【指令】{instruction}\n【原章】\n{ch.content}\n【改写后正文】"
                    )
                    from anyspark.core.types import Message

                    out = model.respond([Message(role="user", content=prompt)], [])
                    new_text = (out.text or "").strip()
                    if new_text:
                        chapters.upsert(
                            "main", ch.title, new_text, ch.order_index, ch.narrative_line
                        )
                        batch["results"].append(
                            {"id": cid, "title": ch.title, "ok": True, "chars": len(new_text)}
                        )
                    else:
                        batch["results"].append(
                            {"id": cid, "title": ch.title, "ok": False, "error": "空输出"}
                        )
            except Exception as exc:
                batch["results"].append({"id": cid, "ok": False, "error": str(exc)[:150]})
            batch["done"] += 1
        batch["status"] = "done"

    def _run_batch_review(batch_id: str, chapter_ids: list[str]) -> None:
        """批量审读：逐章检测网审读，汇总报告。"""
        batch = _batches.get(batch_id)
        if not batch:
            return
        for cid in chapter_ids:
            try:
                ch = chapters.get(cid)
                if ch is None:
                    batch["results"].append({"id": cid, "ok": False, "error": "章节不存在"})
                else:
                    report = run_review(model, ch.title, ch.content[:20000])
                    batch["results"].append(
                        {
                            "id": cid,
                            "title": ch.title,
                            "ok": True,
                            "hard": report.hard_count,
                            "report": report.render(),
                        }
                    )
            except Exception as exc:
                batch["results"].append({"id": cid, "ok": False, "error": str(exc)[:150]})
            batch["done"] += 1
        batch["status"] = "done"

    def _bg_worker() -> None:
        while True:
            try:
                task = _bg_queue.get()
                if task and task[0] == "chapter" and len(task) == 5:
                    _, title, content, order, line = task
                    _extract_chapter("main", title, content, order, line)
                elif task and task[0] == "refine":
                    _refine_from_signals()
                elif task and task[0] == "batch_rewrite" and len(task) == 4:
                    _, bid, ids, inst = task
                    _run_batch_rewrite(bid, ids, inst)
                elif task and task[0] == "batch_review" and len(task) == 3:
                    _, bid, ids = task
                    _run_batch_review(bid, ids)
            except Exception as exc:
                logger.warning("后台任务异常: %s", exc)
            finally:
                _bg_queue.task_done()

    threading.Thread(target=_bg_worker, daemon=True).start()

    def _refine_from_signals() -> None:
        """S28：信号 → 偏好提炼 → 说明书（后台异步，不阻塞用户操作）。

        修复对齐闭环缺口：此前 /api/signals 只记录信号，说明书永不自动更新
        （PreferenceExtractor 存在但从未在 API 层接线）——用户操作无法变成
        写作约束，T7"修改率↓/说明书累积"的机制前提缺失。
        """
        try:
            recent = signals.recent(limit=20)
            if not recent:
                return
            # 最近对话（任意会话，取最近 10 条）作为提炼上下文
            dialogue = store.recent_messages(10)
            entries = preference_extractor.extract(dialogue, recent, max_items=3)
            existing = {e.content for e in manual.list("project", "main")}
            added = 0
            for e in entries:
                if e.content in existing:
                    continue
                manual.add(e)
                added += 1
            if added:
                logger.info("信号提炼: +%d 条说明书条目", added)
        except Exception as exc:
            logger.warning("信号提炼失败(不影响主链路): %s", exc)

    mind_planner = MindPlanner(manual)  # S50 心智模型=会话规划器（不从写作循环注入）
    signal_collector = SignalCollector(signals)
    # S47 运行时模型：注册表（持久化多配置）+ 动态 Provider——
    # 默认装配 RetryingModel(ModelProvider(registry))，所有组件跟随当前激活配置；
    # 测试可注入 fake model（实现 core Model 协议），走共享分支不受影响。
    models = ModelRegistry(real_db)
    provider = ModelProvider(models)
    model = model or RetryingModel(provider)
    plot_generator = PlotGenerator(model)  # 依赖 model，须在其初始化之后
    plot_resolver = PlotResolver(model)  # 伏笔自动回收（S17：章节落盘后台识别揭开）
    preference_extractor = PreferenceExtractor(model)  # S28：信号→说明书提炼（后台）
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
    mood_dims = MoodDimStore(real_db)  # S50 氛围维度内容化（滑块形状硬编码，维度可增删改）
    plans = StoryPlanStore(real_db)  # S46 剧情计划（计划→执行）

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

    def _make_agent(
        system_prompt: str,
        temperature: float,
        book_id: str = "main",
        agency_level: int | None = None,
        mood: dict[str, float] | None = None,
        enable_search: bool = False,
        enable_extras: bool = False,
        enable_domain: bool = True,
        enable_codex: bool = False,
        skip_inject: set[str] | None = None,
        model_id: str | None = None,
        thinking: str | None = None,
    ) -> Agent:
        # 工具装配（S52 抽出为独立模块 toolkit.build_toolkit——组合根接口化，
        # 与 HTTP 编排解耦；写作/探索常驻 + domain/codex/extras/search 按开关点亮）
        registry = build_toolkit(
            ToolRegistry(),
            chapters=chapters,
            workspace=workspace,
            model=model,
            graph=graph,
            plots=plots,
            plans=plans,
            settings=settings,
            materials=materials,
            ext_tools=ext_tools,
            enable_domain=enable_domain,
            enable_codex=enable_codex,
            enable_extras=enable_extras,
            enable_search=enable_search,
        )
        # 能动级别：显式传入 > 心智规划建议 > 已存档位（S35：档位记录，温度入档）
        # S50：心智模型=会话规划器——未显式指定时，MindPlanner 按 collab 条目建议档位
        if agency_level is None:
            session_plan = mind_planner.plan(book_id, base_agency=agency.get_current(book_id).order)
            if session_plan.agency_level is not None:
                agency_level = session_plan.agency_level
            current = agency.get_current(book_id)
            if agency_level is not None:
                levels = agency.list_levels()
                current = next(
                    (lv for lv in levels if lv.order == agency_level),
                    agency.get_level(f"default-{agency_level}") or current,
                )
        else:
            session_plan = mind_planner.plan(book_id)  # 仍取协作约定（档位用显式）
            levels = agency.list_levels()
            current = next(
                (lv for lv in levels if lv.order == int(agency_level)),
                agency.get_level(f"default-{int(agency_level)}") or agency.get_current(book_id),
            )
        eff_temp = current.temperature if temperature == 0.7 else temperature
        # S21 流式核心：不再构造 stream 模型——Agent 循环内部检测 respond_stream 流式；
        # 温度映射时重建模型（档位低=精确执行温度低）；测试 fake 走共享 model
        base_model = getattr(model, "inner", model)
        m: Model
        if model_id:
            # S47 请求级指定模型：按该配置构造（显式指定 > 当前激活）
            cfg = models.get(model_id)
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
            m = model  # 共享 model（测试注入或默认真实）；温度由构造决定
        # 注入块装配：核心注入默认全开，skip_inject 可细粒度关闭（S15 增强按需）
        skip = skip_inject or set()
        full_prompt = system_prompt
        # S53 心智模型=会话规划器：协作约定注入系统提示顶部（怎么配合我）
        collab_block = session_plan.collab_block()
        if "manual" not in skip and collab_block:
            full_prompt = collab_block + "\n\n" + full_prompt
        # 图谱注入：当前时空点已知事实（AI 事实源，模型局限弥补）
        graph_block = graph_injector.build_block(book_id)
        if "graph" not in skip and graph_block:
            full_prompt = full_prompt + "\n\n" + graph_block
        # 能动性注入：当前档位（机制 2；职责边界：档位只管能动性，心智模型独立系统）
        agency_block = build_agency_block(current)
        if "agency" not in skip and agency_block:
            full_prompt = full_prompt + "\n\n" + agency_block
        # AI 倾向档案注入（双向黑盒解法）
        bias_block = bias.render()
        if "bias" not in skip and bias_block:
            full_prompt = full_prompt + "\n\n" + bias_block
        # 关键点图谱注入（T2 阶段 3：当前推进状态——哪些伏笔还开着/刚回收）
        # S31：注入时传当前章节数（老龄化：must 钩子标"已开放 N 章"，中性事实）
        plot_block = plots.render("main", current_order=len(chapters.list_by_book(book_id)))
        if "plot" not in skip and plot_block:
            full_prompt = full_prompt + "\n\n" + plot_block
        # 设定档注入（S41 作者正典：人物卡/能力体系/世界观规则——与图谱互补）
        settings_block = render_settings(settings.list())
        if "settings" not in skip and settings_block:
            full_prompt = full_prompt + "\n\n" + settings_block
        # S53 心智指导块：文风偏好 + 习惯（渐进式披露：只列关键条目，指导性保留）
        mind_block = session_plan.mind_block()
        if "manual" not in skip and mind_block:
            full_prompt = full_prompt + "\n\n" + mind_block
        # 叙事技巧注入（S50：skill 重构——名+技法+情形案例；索引常驻+内容按需）
        skill_list = skills.list_skills()
        skill_block = render_skill_index(skill_list)
        if "skills" not in skip and skill_block:
            full_prompt = full_prompt + "\n\n" + skill_block
        # 内容按需：S53 心智联动——用户文风偏好优先匹配 skill，其次会话意图 tags
        skill_content = render_skills_content(skill_list, prefs=session_plan.style_prefs)
        if "skills" not in skip and skill_content:
            full_prompt = full_prompt + "\n\n" + skill_content
        # 剧情计划注入（S46：当前章+后续计划——AI 知道接下来写什么）
        plan_block = render_plan(plans.list())
        if "plan" not in skip and plan_block:
            full_prompt = full_prompt + "\n\n" + plan_block
        # 氛围滑块注入（机制 4：本段氛围要求）
        mood_block = build_mood_block(mood, mood_dims.list_dims())
        if "mood" not in skip and mood_block:
            full_prompt = full_prompt + "\n\n" + mood_block
        return Agent(
            model=m,
            registry=registry,
            store=store,
            system_prompt=full_prompt,
            context_compressor=budget.compress,  # token 预算两阶段压缩（S8）
            persist_compression=True,  # S26：压缩结果回写 store（pi compaction entry 语义）
        )

    def _extract_chapter(
        book_id: str, title: str, content: str, order: int, line: str = "main"
    ) -> None:
        """章节落盘后自动：图谱抽取 + 伏笔自动回收（后台任务）。失败只记日志，绝不阻断写作。"""
        try:
            existing = [e.to_dict() for e in graph.list_entities(book_id)]
            ext = graph_extractor.extract(title, content, existing)
            graph.ingest_chapter(book_id, title, order, ext, line)
            logger.info(
                "图谱抽取完成: 《%s》 实体%d 关系%d 事件%d",
                title,
                len(ext.entities),
                len(ext.relations),
                len(ext.events),
            )
        except Exception as exc:  # 抽取失败不影响写作主链路
            logger.warning("图谱抽取失败(不影响写作): %s", exc)
        # 伏笔自动回收：本章揭开了哪些进行中的关键点（S17，独立 try 互不影响）
        try:
            resolved = plot_resolver.resolve(book_id, title, content, plots)
            if resolved:
                logger.info("伏笔自动回收: 《%s》 %s", title, "、".join(resolved))
        except Exception as exc:
            logger.warning("伏笔回收失败(不影响写作): %s", exc)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        name = getattr(model, "model_name", "unknown")
        return {"status": "ok", "model": str(name), "log": log_path()}

    # -----------------------------------------------------------------------
    # S47 运行时模型配置：注册表 CRUD + 激活切换（换供应商/换模型/选思考强度）
    # -----------------------------------------------------------------------
    @app.get("/api/models", response_model=dict[str, Any])
    def list_models() -> dict[str, Any]:
        cfgs = models.list()
        active_id = next((c.id for c in cfgs if c.is_active), cfgs[0].id if cfgs else None)
        return {"active_id": active_id, "models": [c.to_dict() for c in cfgs]}

    @app.post("/api/models", response_model=dict[str, Any])
    def upsert_model(req: ModelIn) -> dict[str, Any]:
        """新增或更新模型配置（同 id 覆盖；id 缺省由 name 生成 slug）。"""
        from anyspark.models.deepseek import _validate_thinking

        try:
            _validate_thinking(req.thinking)  # 非法思考强度 → 400（尽早暴露配置错误）
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        cfg = ModelConfig(
            id=req.id or slugify(req.name),
            name=req.name,
            base_url=req.base_url or DEFAULT_BASE_URL,
            model=req.model,
            api_key=req.api_key,
            context_window=req.context_window or DEFAULT_CONTEXT_WINDOW,
            max_tokens=req.max_tokens or DEFAULT_MAX_TOKENS,
            temperature=req.temperature or DEFAULT_TEMPERATURE,
            thinking=req.thinking,
        )
        saved = models.upsert(cfg)
        return {"ok": True, "model": saved.to_dict(), "active": saved.is_active}

    @app.delete("/api/models/{model_id}", response_model=dict[str, Any])
    def delete_model(model_id: str) -> dict[str, Any]:
        if not models.delete(model_id):
            raise HTTPException(status_code=400, detail="无法删除：至少保留一条配置，或配置不存在")
        return {"ok": True}

    @app.post("/api/models/{model_id}/activate", response_model=dict[str, Any])
    def activate_model(model_id: str) -> dict[str, Any]:
        """切换当前激活模型——所有组件（Agent/抽取/检测/探索/后台）即时跟随。"""
        cfg = models.activate(model_id)
        if cfg is None:
            raise HTTPException(status_code=404, detail=f"模型配置不存在: {model_id}")
        if cfg.context_window != _window:
            logger.warning(
                "模型窗口 %d != token 预算窗口 %d——重启后预算按新窗口生效（S26）",
                cfg.context_window,
                _window,
            )
        return {"ok": True, "active": cfg.to_dict()}

    @app.post("/api/chat/cancel")
    def cancel_chat(
        req: Annotated[CancelIn, Body()],
    ) -> dict[str, bool | str]:
        """协作式取消（S21）：中断正在跑的 Agent 循环（下个检查点生效）。

        conversation_id 为空时取消最近活跃的会话（新会话 id 由服务端生成，客户端未知）。
        """
        token = None
        if req.conversation_id:
            token = _active_tokens.get(req.conversation_id)
        elif _active_tokens:
            token = next(reversed(_active_tokens.values()), None)
        if token is not None:
            token.cancel()
            return {"ok": True}
        return {"ok": False, "reason": "会话未在运行"}

    @app.post("/api/chat/steer")
    def steer_chat(req: Annotated[SteerIn, Body()]) -> dict[str, bool | str]:
        """S25：运行中插话（对齐 pi Agent.steer）——消息在当前轮工具结果后、
        下一轮 LLM 前注入，写作时可中途说"别写太血腥"而不用取消重来。
        conversation_id 为空时取最近活跃会话（新会话 id 客户端可先于 turn_start 帧获得）。"""
        with _active_lock:
            if req.conversation_id:
                agent = _active_agents.get(req.conversation_id)
            elif _active_agents:
                agent = next(reversed(_active_agents.values()), None)
            else:
                agent = None
        if agent is None:
            return {"ok": False, "reason": "会话未在运行"}
        agent.steer(req.message)
        logger.info("steer 注入: msg=%s", req.message[:40])
        return {"ok": True}

    @app.get("/api/stats")
    def stats() -> dict[str, Any]:
        """T7 验证指标（代理指标，纯 SQL 统计现有表，零新表）：修改率/提问率/完成率。"""
        return compute_stats(real_db)

    @app.post("/api/chat", response_model=ChatResponse)
    def chat(req: ChatRequest) -> ChatResponse:
        # S47 请求级指定模型：不存在 → 400（不是 500）
        if req.model_id and models.get(req.model_id) is None:
            raise HTTPException(status_code=400, detail=f"模型配置不存在: {req.model_id}")
        # steering 防护（S21）：会话正在处理中时拒绝并发新消息，提示等待/取消
        if req.conversation_id and req.conversation_id in _active_tokens:
            raise HTTPException(
                status_code=409,
                detail="该会话正在处理中（可 POST /api/chat/cancel 中断后再发）",
            )
        logger.info("chat 请求: conv=%s len=%d", req.conversation_id or "(新)", len(req.message))
        events: list[ToolEvent] = []
        agent = _make_agent(
            req.system_prompt or DEFAULT_SYSTEM,
            req.temperature,
            agency_level=req.agency_level,
            mood=req.mood,
            enable_search=req.enable_search,
            enable_extras=req.enable_extras,
            enable_domain=req.enable_domain,
            enable_codex=req.enable_codex,
            skip_inject=set(req.skip_inject),
            model_id=req.model_id,
            thinking=req.thinking,
        )
        agent.events.on(
            "tool_call", lambda e: events.append(ToolEvent(type=e.type, payload=e.payload))
        )
        agent.events.on(
            "tool_result", lambda e: events.append(ToolEvent(type=e.type, payload=e.payload))
        )
        # 工具调用/结果写日志（排查用）
        agent.events.on("tool_call", lambda e: logger.info("工具调用: %s", e.payload.get("name")))
        agent.events.on(
            "tool_result",
            lambda e: logger.info("工具结果: %s ok=%s", e.payload.get("name"), e.payload.get("ok")),
        )

        # 无会话时显式创建，保证 conversation_id 可回传（多轮续写）
        conv_id = req.conversation_id
        if not conv_id:
            conv = agent.store.create()
            conv_id = conv.id

        # S49 运行记录：完整上下文+思维链落 data/records/<conv>/（修 bug/训练素材）
        recorder.attach(
            agent,
            conv_id,
            {
                "ts": _now_iso_rec(),
                "endpoint": "chat",
                "model": getattr(model, "model_name", "?"),
                "temperature": req.temperature,
                "agency_level": req.agency_level,
                "mood": req.mood,
                "enable_domain": req.enable_domain,
                "enable_codex": req.enable_codex,
                "thinking": req.thinking,
                "model_id": req.model_id,
            },
        )
        # 协作式取消（S21 移植 pi 的 AbortSignal）：注册 token，/api/chat/cancel 可中断
        token = CancellationToken()
        _active_tokens[conv_id] = token
        with _active_lock:
            _active_agents[conv_id] = agent  # S25：steer 端点可运行中插话
        try:
            turn = agent.run(req.message, conv_id, token)
        except Exception as exc:  # 记录并返回 500
            logger.exception("chat 执行异常: %s", exc)
            raise HTTPException(status_code=500, detail=f"执行失败: {exc}") from exc
        finally:
            _active_tokens.pop(conv_id, None)
            with _active_lock:
                _active_agents.pop(conv_id, None)
        if turn.error is not None:  # S22：模型调用失败/迭代上限（不再字符串匹配）
            logger.warning("chat 非正常结束: conv=%s error=%s", conv_id, turn.error)
            raise HTTPException(status_code=500, detail=turn.error)

        logger.info(
            "chat 完成: conv=%s 输出%d字 工具%d次", conv_id, len(turn.text), len(turn.tool_calls)
        )
        # 图谱抽取：写入章节后自动抽取入库（后台任务，不阻塞响应；失败不影响写作）
        # extract_graph 开关（S15）：默认开保持现状，可关省 token（手动 /api/graph/extract 兜底）
        if req.extract_graph:
            for wc in turn.tool_calls:
                if wc.name == "write_chapter":
                    title = str(wc.arguments.get("title", "")).strip()
                    content = str(wc.arguments.get("content", ""))
                    if title and content:
                        chs = chapters.list_by_book("main")
                        order = next((c.order_index for c in chs if c.title == title), len(chs))
                        logger.info("后台图谱抽取挂载: 《%s》", title)
                        line = str(wc.arguments.get("line", "main")).strip() or "main"
                        _bg_queue.put(("chapter", title, content, order, line))
        turns_payload = [{"text": turn.text, "tool_calls": [c.name for c in turn.tool_calls]}]
        # AI 档位声明解析（机制 2：AI 可声明，用户点选确认）
        declared = parse_agency_declaration(turn.text)
        return ChatResponse(
            conversation_id=conv_id,
            text=turn.text,
            turns=turns_payload,
            events=events,
            agency_declared=declared,
        )

    @app.post("/api/chat/stream")
    def chat_stream(req: ChatRequest) -> StreamingResponse:
        """SSE 流式：turn_start / text_delta / tool_call / tool_result / done / error。

        S8（模型局限弥补 + A 类硬编码 SSE 传输）：长文生成逐字流式，用户不等全量。
        事件帧格式：event: <type>\ndata: <json>\n\n（core 事件协议 → 传输层）。
        """
        events_queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()

        def run_agent(agent: Agent, msg: str, conv_id: str) -> None:
            try:
                token = CancellationToken()
                _active_tokens[conv_id] = token
                with _active_lock:
                    _active_agents[conv_id] = agent  # S25：steer 端点可运行中插话
                try:
                    turn = agent.run(msg, conv_id, token)
                finally:
                    _active_tokens.pop(conv_id, None)
                    with _active_lock:
                        _active_agents.pop(conv_id, None)
                # 图谱抽取：与 /api/chat 行为一致（write_chapter 落盘后自动抽取）
                # extract_graph 开关（S15）：默认开保持现状，可关省 token
                if req.extract_graph:
                    for wc in turn.tool_calls:
                        if wc.name == "write_chapter":
                            title = str(wc.arguments.get("title", "")).strip()
                            content = str(wc.arguments.get("content", ""))
                            if title and content:
                                chs = chapters.list_by_book("main")
                                order = next(
                                    (c.order_index for c in chs if c.title == title),
                                    len(chs),
                                )
                                # 后台队列处理（不阻塞 SSE 的 done 帧）
                                line = str(wc.arguments.get("line", "main")).strip() or "main"
                        _bg_queue.put(("chapter", title, content, order, line))
            except Exception as exc:  # 异常转 error 帧（不中断连接）
                logger.exception("chat/stream 执行异常: %s", exc)
                events_queue.put(("error", {"message": f"执行失败: {exc}"}))

        def gen() -> Any:
            # S47 请求级指定模型：不存在 → 400（SSE 里转 error 帧）
            if req.model_id and models.get(req.model_id) is None:
                events_queue.put(("error", {"message": f"模型配置不存在: {req.model_id}"}))
                yield (
                    "event: error\n"
                    + f"data: {json.dumps({'message': f'模型配置不存在: {req.model_id}'})}\n\n"
                )
                return
            agent = _make_agent(
                req.system_prompt or DEFAULT_SYSTEM,
                req.temperature,
                agency_level=req.agency_level,
                mood=req.mood,
                enable_search=req.enable_search,
                enable_extras=req.enable_extras,
                enable_domain=req.enable_domain,
                enable_codex=req.enable_codex,
                skip_inject=set(req.skip_inject),
                model_id=req.model_id,
                thinking=req.thinking,
            )
            conv_id = req.conversation_id
            if not conv_id:
                conv = agent.store.create()
                conv_id = conv.id

            # S49 运行记录（流式）
            recorder.attach(
                agent,
                conv_id,
                {
                    "ts": _now_iso_rec(),
                    "endpoint": "chat_stream",
                    "model": getattr(model, "model_name", "?"),
                    "temperature": req.temperature,
                    "agency_level": req.agency_level,
                    "mood": req.mood,
                    "enable_domain": req.enable_domain,
                    "enable_codex": req.enable_codex,
                    "thinking": req.thinking,
                    "model_id": req.model_id,
                },
            )

            def on_event(e: Any) -> None:
                payload = e.payload
                # S25：turn_start 帧带 conversation_id——客户端尽早知道会话 id，运行中可 steer
                if e.type == "turn_start":
                    payload = {**payload, "conversation_id": conv_id}
                events_queue.put((e.type, payload))

            # S21 流式核心：Agent 内部流式（model.respond_stream），text_delta 事件转 SSE 帧
            agent.events.on("text_delta", lambda e: events_queue.put(("text_delta", e.payload)))
            for t in (
                "turn_start",
                "text",
                "tool_call",
                "tool_execution_start",  # S25：前端显示"正在执行…"
                "tool_execution_end",  # S25：前端显示耗时/结果
                "tool_result",
                "done",
                "error",
            ):
                agent.events.on(t, on_event)
            # Agent 循环在线程跑，事件经 queue 转 SSE 帧（同步生成器流式输出）
            threading.Thread(
                target=run_agent, args=(agent, req.message, conv_id), daemon=True
            ).start()
            while True:
                try:
                    etype, payload = events_queue.get(timeout=120)
                except queue.Empty:
                    yield _sse_frame("error", {"message": "流式超时（120s 无事件）"})
                    break
                if etype == "done":
                    yield _sse_frame("done", {"conversation_id": conv_id})
                    break
                if etype == "error":
                    yield _sse_frame("error", payload)
                    break
                yield _sse_frame(etype, payload)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/manual", response_model=list[dict[str, Any]])
    def list_manual(scope: str = "project") -> list[dict[str, Any]]:
        """说明书条目（scope=project|global）。"""
        entries = manual.list(scope, "main")  # type: ignore[arg-type]
        return [e.to_dict() for e in entries]

    @app.post("/api/manual", response_model=dict[str, Any])
    def add_manual(req: ManualEntryIn) -> dict[str, Any]:
        """新增说明书条目（用户手写）。"""
        scope = cast(Literal["project", "global"], req.scope)
        entry = ManualEntry(
            content=req.content,
            source="user",
            confidence=req.confidence,
            scope=scope,
            book_id="main",
            category=cast(
                Literal["collab", "style", "habit"],
                req.category if req.category in ("collab", "style", "habit") else "style",
            ),
        )
        manual.add(entry)
        return entry.to_dict()

    @app.patch("/api/manual/{entry_id}", response_model=dict[str, Any])
    def update_manual(entry_id: str, req: ManualEntryPatch) -> dict[str, Any]:
        """修改条目内容（锁定条目拒绝，用户主权）。"""
        entry = manual.update(entry_id, content=req.content, category=req.category)
        if entry is None:
            raise HTTPException(status_code=404, detail="条目不存在")
        if req.locked is not None:
            entry = manual.set_locked(entry_id, req.locked) or entry
        return entry.to_dict()

    @app.delete("/api/manual/{entry_id}")
    def delete_manual(entry_id: str) -> dict[str, bool]:
        manual.delete(entry_id)
        return {"ok": True}

    @app.post("/api/signals")
    def record_signal(req: SignalIn) -> dict[str, Any]:
        """采集用户操作信号（接受/修改/删除/自定义等）；同时驱动能动性反馈调节。"""
        if req.kind == "accepted":
            sig = signal_collector.accepted(req.content, req.context)
            agency.adjust(+1)  # 接受=升级（档位上限 4）
        elif req.kind == "deleted":
            sig = signal_collector.deleted(req.content, req.context)
            agency.adjust(-1)  # 删除=降级（档位下限 0）
        elif req.kind == "rejected":
            sig = signal_collector.rejected(req.content, req.context)
            agency.adjust(-1)  # 拒绝=降级
        elif req.kind == "custom":
            sig = signal_collector.custom(req.content, req.context)
        else:  # modified
            sig = signal_collector.modified(req.content, req.new_content or "", req.context)
        # S28：信号 → 后台提炼 → 说明书（异步，不阻塞操作；修复对齐闭环缺口）
        _bg_queue.put(("refine",))
        return sig.to_dict()

    @app.post("/api/explore/intent", response_model=dict[str, object])
    def explore_intent(req: ExploreIntentIn) -> dict[str, object]:
        """种子 → 概念卡 + 关键歧义点（意图理解）。"""
        understander = IntentUnderstander(model)
        return understander.understand(req.seed)

    @app.post("/api/explore/cards", response_model=list[dict[str, object]])
    def explore_cards(req: ExploreCardsIn) -> list[dict[str, object]]:
        """确认后的意图 → 方向卡 ×4（并行探索，三来源混合）。"""
        constraints = archive.constraints("main")
        cards = run_exploration(
            model,
            req.seed,
            req.intent_confirmed,
            constraints,
            n_explorers=4,
            dimensions=dim_store.list_names(),  # S50：维度来自内容载体（可增删改）
        )
        return [c.to_dict() for c in cards]

    @app.get("/api/explore/dims", response_model=list[dict[str, object]])
    def list_explore_dims() -> list[dict[str, object]]:
        """探索维度（内容化：可增删改/开关）。"""
        return dim_store.list_all()

    @app.post("/api/explore/dims", response_model=dict[str, object])
    def add_explore_dim(req: ExploreDimIn) -> dict[str, object]:
        d = dim_store.add(req.name)
        if d is None:
            raise HTTPException(status_code=409, detail=f"维度已存在: {req.name}")
        return d

    @app.patch("/api/explore/dims/{dim_id}", response_model=dict[str, object])
    def patch_explore_dim(dim_id: str, req: ExploreDimPatch) -> dict[str, object]:
        d = dim_store.set_enabled(dim_id, req.enabled)
        if d is None:
            raise HTTPException(status_code=404, detail="维度不存在")
        return d

    @app.delete("/api/explore/dims/{dim_id}", response_model=dict[str, bool])
    def delete_explore_dim(dim_id: str) -> dict[str, bool]:
        ok = dim_store.delete(dim_id)
        if not ok:
            raise HTTPException(status_code=404, detail="维度不存在")
        return {"ok": True}

    @app.post("/api/explore/archive", response_model=dict[str, object])
    def explore_archive(req: ExploreArchiveIn) -> dict[str, object]:
        """固化选中方向进项目档案。"""
        c = req.card
        src: Literal["template", "grow", "user"]
        if c.get("source") == "grow":
            src = "grow"
        elif c.get("source") == "user":
            src = "user"
        else:
            src = "template"
        card = DirectionCard(
            title=str(c.get("title", "未命名方向")),
            summary=str(c.get("summary", "")),
            dimension=str(c.get("dimension", "情节驱动")),
            source=src,
            term=str(c.get("term", "")),
        )
        return archive.archive_direction(card)

    @app.get("/api/explore/archive", response_model=list[dict[str, object]])
    def explore_archive_list() -> list[dict[str, object]]:
        return archive.directions()

    @app.post("/api/check", response_model=dict[str, object])
    def check_text_route(req: CheckRequest) -> dict[str, object]:
        """多检测者审读正文（骨架检测项，并行）+ 图谱事实证据 + 时序校验（确定性规则）。"""
        report = run_review(model, req.target, req.text)
        # S7：图谱事实证据——文本涉及的已知实体/关系（检测网/用户比对设定冲突）
        evidence = graph_verifier.render_evidence("main", req.text)
        # S13：时序校验——截止当前章节时空点，提及未来才首现的实体=时空倒置
        # S29：按叙事线比较（跨线首现不误报，多线并行时间差正常）
        temporal = (
            graph_verifier.check_temporal("main", req.text, req.chapter_order, req.line)
            if req.chapter_order is not None
            else []
        )
        return {
            "target": report.target,
            "hard_count": report.hard_count,
            "graph_evidence": evidence,
            "temporal_warnings": temporal,
            "findings": [
                {
                    "category": f.category,
                    "severity": f.severity,
                    "message": f.message,
                    "evidence": f.evidence,
                    "suggestion": f.suggestion,
                    "source": f.source,
                }
                for f in report.findings
            ],
        }

    @app.post("/api/check/rule", response_model=dict[str, object])
    def check_rule_route(req: RuleRequest) -> dict[str, object]:
        """轻量规则编译器：用户自然语言规则 → 检测命中。"""
        compiled = compile_rule(req.rule)
        if compiled is None:
            return {"ok": False, "description": "未能识别的规则", "hits": []}
        hits = compiled.checker(req.text)
        return {"ok": True, "description": compiled.description, "hits": hits}

    @app.get("/api/templates", response_model=list[dict[str, object]])
    def list_templates() -> list[dict[str, object]]:
        """模式库 L2+L3 合并（探索方向生成器）。"""
        return [t.to_dict() for t in templates_external.all()]

    @app.post("/api/templates/import", response_model=dict[str, object])
    def import_template(req: TemplateIn) -> dict[str, object]:
        """L3 外部模式库：导入自定义模板（自然语言+四要素，合并进探索库）。"""
        t = templates_external.import_template(
            req.name, req.description, req.granularity, req.position, req.function, req.params
        )
        return t.to_dict()

    @app.delete("/api/templates/{name}")
    def delete_template(name: str) -> dict[str, bool]:
        templates_external.delete(name)
        return {"ok": True}

    class PlotIn(BaseModel):
        settings: str = ""  # 作品设定/种子（可选，缺省用已写章节）

    @app.post("/api/plot", response_model=list[dict[str, object]])
    def generate_plot(req: PlotIn) -> list[dict[str, object]]:
        """关键点图谱（T2 阶段 3 可选深入）：LLM 生成草案入库。"""
        points = plot_generator.generate("main", plots, req.settings)
        return [p.to_dict() for p in points]

    @app.get("/api/plot", response_model=list[dict[str, object]])
    def list_plot() -> list[dict[str, object]]:
        return [p.to_dict() for p in plots.list_points()]

    @app.patch("/api/plot/{plot_id}", response_model=dict[str, object])
    def update_plot_status(plot_id: str, req: PlotPatchIn) -> dict[str, object]:
        """更新关键点：状态/关注度/优先级/回收章节——操作即对齐信号。"""
        p = plots.update(
            plot_id,
            status=req.status,
            attention=req.attention,
            priority=req.priority,
            resolved_chapter=req.resolved_chapter,
        )
        if p is None:
            raise HTTPException(status_code=404, detail="关键点不存在")
        return p.to_dict()

    @app.post("/api/plot/item", response_model=dict[str, object])
    def add_plot_item(req: PlotItemIn) -> dict[str, object]:
        """S31：主动登记伏笔/关键点（作者或 AI 声明）——
        priority=must 表示这是作者对读者的主线承诺（剧情钩子，必须回收）；
        planted_order 记录登记时的章节序号（老龄化计算用）。"""
        p = plots.add(
            "main",
            req.category,
            req.content,
            req.chapter_ref,
            priority=req.priority,
            planted_order=req.planted_order,
        )
        return p.to_dict()

    @app.post("/api/plot/import-resolve")
    def resolve_all_plots() -> dict[str, int]:
        """S31：完整书导入归档——所有 open 伏笔标 resolved（书已写完，线索已揭开）。
        只报告归档数量，不输出回收率（伏笔管理烂不影响作品伟大性，不做质量评分）。"""
        n = plots.resolve_all("main")
        return {"resolved": n}

    @app.delete("/api/plot/{plot_id}")
    def delete_plot(plot_id: str) -> dict[str, bool]:
        plots.delete(plot_id)
        return {"ok": True}

    @app.post("/api/materials", response_model=dict[str, object])
    def add_material(req: MaterialIn) -> dict[str, object]:
        """上传材料 → 真实 LLM 消化成摘要卡 → 图谱关联 → 入库（原文保留）。"""
        purpose: Any = req.purpose if req.purpose in ("style", "fact", "both") else "fact"
        digestor = MaterialDigestor(model)
        card = digestor.digest(req.text, purpose=purpose)
        if req.title:
            card.title = req.title
        # 图谱关联（机制 10 补齐）：摘要卡角色/设定/术语 → 图谱实体
        names = [*card.characters, *card.key_settings, *card.terms]
        linked = graph.resolve_names("main", names)
        card.graph_entities = [e.id for e in linked]
        materials.save(card)
        return card.to_dict()

    @app.get("/api/materials", response_model=list[dict[str, object]])
    def list_materials() -> list[dict[str, object]]:
        return [m.to_dict() for m in materials.list()]

    @app.get("/api/materials/{material_id}", response_model=dict[str, object])
    def get_material(material_id: str) -> dict[str, object]:
        card = materials.get(material_id)
        if card is None:
            raise HTTPException(status_code=404, detail="材料不存在")
        return card.to_dict()

    @app.get("/api/agency", response_model=dict[str, object])
    def get_agency() -> dict[str, object]:
        """能动档位（机制 2 + S35 记录集）：当前档位 + 全部档位（含自定义）。"""
        return {
            "current": agency.get_current().to_dict(),
            "levels": [lv.to_dict() for lv in agency.list_levels()],
        }

    @app.post("/api/agency", response_model=dict[str, object])
    def set_agency(req: AgencyIn) -> dict[str, object]:
        """用户点选档位（level_id 优先；兼容旧 level 数字=排序位）。"""
        if req.level_id:
            lv = agency.set_current(req.level_id)
        elif req.level is not None:
            levels = agency.list_levels()
            target = next((x for x in levels if x.order == req.level), None)
            lv = agency.set_current(target.id) if target else None
        else:
            lv = None
        if lv is None:
            raise HTTPException(status_code=404, detail="档位不存在")
        return {"current": lv.to_dict(), "levels": [x.to_dict() for x in agency.list_levels()]}

    @app.post("/api/agency/add", response_model=dict[str, object])
    def add_agency_level(req: AgencyLevelIn) -> dict[str, object]:
        """S35：新增自定义档位（全局，追加到末尾）。"""
        lv = agency.add_level(req.name, req.description, req.temperature)
        return {"level": lv.to_dict(), "levels": [x.to_dict() for x in agency.list_levels()]}

    @app.patch("/api/agency/{level_id}", response_model=dict[str, object])
    def patch_agency_level(level_id: str, req: AgencyLevelIn) -> dict[str, object]:
        """S35：修改档位名称/描述/温度。"""
        lv = agency.update_level(level_id, req.name, req.description, req.temperature)
        if lv is None:
            raise HTTPException(status_code=404, detail="档位不存在")
        return {"level": lv.to_dict(), "levels": [x.to_dict() for x in agency.list_levels()]}

    @app.delete("/api/agency/{level_id}", response_model=dict[str, object])
    def delete_agency_level(level_id: str) -> dict[str, object]:
        """S35：删除档位（至少保留一条；删当前则回落默认）。"""
        ok = agency.delete_level(level_id)
        if not ok:
            raise HTTPException(status_code=400, detail="无法删除（至少保留一条或不存在）")
        return {"levels": [x.to_dict() for x in agency.list_levels()]}

    @app.post("/api/agency/reset", response_model=dict[str, object])
    def reset_agency() -> dict[str, object]:
        """S35：恢复默认五级档位（不重置心智模型——manual 在不同表，天然保留）。"""
        levels = agency.reset_defaults()
        return {
            "current": agency.get_current().to_dict(),
            "levels": [lv.to_dict() for lv in levels],
        }

    # ------------------------------------------------------------------
    # S40 批量任务（场景 4 全书变换核心）：批量改写 / 批量审读
    # 后台队列执行（不阻塞请求），GET /api/batch/{id} 查进度；状态内存级（会话内）
    # ------------------------------------------------------------------
    @app.post("/api/batch/rewrite", response_model=dict[str, object])
    def batch_rewrite(req: BatchRewriteIn) -> dict[str, object]:
        """批量改写：多章统一指令改写（改文风/改情节），覆盖前旧版进版本历史。"""
        if not req.chapter_ids:
            raise HTTPException(status_code=400, detail="chapter_ids 不能为空")
        if not req.instruction.strip():
            raise HTTPException(status_code=400, detail="instruction 不能为空")
        bid = uuid.uuid4().hex
        with _batch_lock:
            _batches[bid] = {
                "status": "queued",
                "done": 0,
                "total": len(req.chapter_ids),
                "results": [],
                "kind": "rewrite",
                "instruction": req.instruction,
            }
        _bg_queue.put(("batch_rewrite", bid, req.chapter_ids, req.instruction))
        return {"batch_id": bid, "total": len(req.chapter_ids)}

    @app.post("/api/batch/review", response_model=dict[str, object])
    def batch_review(req: BatchReviewIn) -> dict[str, object]:
        """批量审读：多章检测网审读（一致性/动机因果/情感连贯等 7 类）。"""
        if not req.chapter_ids:
            raise HTTPException(status_code=400, detail="chapter_ids 不能为空")
        bid = uuid.uuid4().hex
        with _batch_lock:
            _batches[bid] = {
                "status": "queued",
                "done": 0,
                "total": len(req.chapter_ids),
                "results": [],
                "kind": "review",
            }
        _bg_queue.put(("batch_review", bid, req.chapter_ids))
        return {"batch_id": bid, "total": len(req.chapter_ids)}

    @app.get("/api/batch/{batch_id}", response_model=dict[str, object])
    def batch_status(batch_id: str) -> dict[str, object]:
        """批量任务状态/进度/结果。"""
        with _batch_lock:
            batch = _batches.get(batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail="批量任务不存在")
        return {
            "batch_id": batch_id,
            "status": batch["status"],
            "done": batch["done"],
            "total": batch["total"],
            "results": batch["results"],
        }

    # ------------------------------------------------------------------
    # S41 设定档（作者正典：人物卡/能力体系/世界观规则）
    # ------------------------------------------------------------------
    @app.get("/api/settings/categories", response_model=list[dict[str, Any]])
    def list_setting_categories() -> list[dict[str, Any]]:
        """设定档类别（S50 内容化：可增删改/开关）。"""
        return settings.list_categories()

    @app.post("/api/settings/categories", response_model=dict[str, Any])
    def add_setting_category(req: SettingCategoryIn) -> dict[str, Any]:
        c = settings.add_category(req.name)
        if c is None:
            raise HTTPException(status_code=409, detail=f"类别已存在: {req.name}")
        return c

    @app.patch("/api/settings/categories/{cat_id}", response_model=dict[str, Any])
    def patch_setting_category(cat_id: str, req: SettingCategoryPatch) -> dict[str, Any]:
        c = settings.set_category_enabled(cat_id, req.enabled)
        if c is None:
            raise HTTPException(status_code=404, detail="类别不存在")
        return c

    @app.delete("/api/settings/categories/{cat_id}", response_model=dict[str, bool])
    def delete_setting_category(cat_id: str) -> dict[str, bool]:
        ok = settings.delete_category(cat_id)
        if not ok:
            raise HTTPException(status_code=404, detail="类别不存在")
        return {"ok": True}

    @app.get("/api/settings", response_model=list[dict[str, Any]])
    def list_settings() -> list[dict[str, Any]]:
        """设定档全部条目。"""
        return [s.to_dict() for s in settings.list()]

    @app.post("/api/settings", response_model=dict[str, Any])
    def add_setting(req: WorldSettingIn) -> dict[str, Any]:
        """新增设定条目（作者手写）。"""
        s = settings.add(req.content, req.category, req.name, source="manual")
        return s.to_dict()

    @app.patch("/api/settings/{setting_id}", response_model=dict[str, Any])
    def patch_setting(setting_id: str, req: WorldSettingPatch) -> dict[str, Any]:
        s = settings.update(setting_id, req.content, req.category, req.name)
        if s is None:
            raise HTTPException(status_code=404, detail="设定条目不存在")
        return s.to_dict()

    @app.delete("/api/settings/{setting_id}", response_model=dict[str, bool])
    def delete_setting(setting_id: str) -> dict[str, bool]:
        ok = settings.delete(setting_id)
        if not ok:
            raise HTTPException(status_code=404, detail="设定条目不存在")
        return {"ok": True}

    @app.post("/api/settings/extract", response_model=dict[str, object])
    def extract_settings(req: WorldSettingExtractIn) -> dict[str, object]:
        """S42：从图谱提炼设定草案（只含已揭示信息，LLM 生成，作者确认后入库）。

        提炼边界（防止"角色认知越界/未来设定泄露"）：只基于图谱已有实体/事件——
        图谱覆盖=已写章节=角色与叙事者都可能知道的信息；未来设定需作者手写补充。
        """
        assert model is not None
        es = graph.list_entities(req.book_id, limit=10000)
        core = [e for e in es if e.weight >= 3]
        evs = sorted(graph.list_events(req.book_id, limit=10000), key=lambda x: x.chapter_order)
        ent_txt = "\n".join(
            f"- {e.name}（{e.entity_type}，出场{e.weight}章）"
            f"{('：' + (e.state or e.description)[:60]) if (e.state or e.description) else ''}"
            for e in sorted(core, key=lambda x: -x.weight)[:60]
        )
        ev_txt = "\n".join(
            f"[{ev.chapter_ref}] {ev.label}：{ev.description[:60]}" for ev in evs[:80]
        )
        prompt = (
            "根据以下小说知识图谱数据（实体/事件），提炼【设定档草案】——"
            "只包含图谱中已出现的信息（不编造未来设定）。按类别输出：\n"
            "人物卡（主要角色：身份/性格/当前状态）/ 能力体系（已出现的职业能力）/ "
            "世界观规则 / 势力 / 地点 / 物品。\n"
            '输出 JSON：{"settings": [{"category": "人物卡", '
            '"name": "顾欣桐", "content": "..."}]}\n'
            f"【实体】\n{ent_txt}\n【事件】\n{ev_txt}"
        )
        from anyspark.core.types import Message

        out = model.respond(
            [
                Message(
                    role="system",
                    content="你是设定考据者。严格基于图谱数据提炼设定草案，不编造。",
                ),
                Message(role="user", content=prompt),
            ],
            [],
        )
        import json as _json
        import re as _re

        m = _re.search(r"\{.*\}", out.text, _re.DOTALL)
        if not m:
            return {"draft": [], "raw": out.text[:500]}
        try:
            data = _json.loads(m.group(0))
            draft = [
                s for s in data.get("settings", []) if isinstance(s, dict) and s.get("content")
            ]
        except Exception:
            return {"draft": [], "raw": out.text[:500]}
        return {"draft": draft, "raw": ""}

    # ------------------------------------------------------------------
    # S50 叙事技巧（skill 式内容载体：镜头感/对白机锋/节奏控制等，可增删改/开关）
    # ------------------------------------------------------------------
    @app.get("/api/skills", response_model=list[dict[str, Any]])
    def list_skills() -> list[dict[str, Any]]:
        """全部写作技巧。"""
        return [s.to_dict() for s in skills.list_skills()]

    @app.post("/api/skills", response_model=dict[str, Any])
    def add_skill(req: WritingSkillIn) -> dict[str, Any]:
        s = skills.add(req.name, req.description, req.content, req.example, req.tags)
        return s.to_dict()

    @app.patch("/api/skills/{skill_id}", response_model=dict[str, Any])
    def patch_skill(skill_id: str, req: WritingSkillPatch) -> dict[str, Any]:
        s = skills.update(
            skill_id, req.name, req.description, req.content, req.example, req.tags, req.enabled
        )
        if s is None:
            raise HTTPException(status_code=404, detail="技巧不存在")
        return s.to_dict()

    @app.delete("/api/skills/{skill_id}", response_model=dict[str, bool])
    def delete_skill(skill_id: str) -> dict[str, bool]:
        ok = skills.delete(skill_id)
        if not ok:
            raise HTTPException(status_code=404, detail="技巧不存在")
        return {"ok": True}

    # ------------------------------------------------------------------
    # S50 氛围维度（内容化：滑块形状硬编码，维度定义可增删改/开关）
    # ------------------------------------------------------------------
    @app.get("/api/mood/dims", response_model=list[dict[str, Any]])
    def list_mood_dims() -> list[dict[str, Any]]:
        """全部氛围维度（前端滑块据此渲染）。"""
        return [d.to_dict() for d in mood_dims.list_dims()]

    @app.post("/api/mood/dims", response_model=dict[str, Any])
    def add_mood_dim(req: MoodDimIn) -> dict[str, Any]:
        d = mood_dims.add(req.key, req.label, req.description, req.example)
        if d is None:
            raise HTTPException(status_code=409, detail=f"维度已存在: {req.key}")
        return d.to_dict()

    @app.patch("/api/mood/dims/{dim_id}", response_model=dict[str, Any])
    def patch_mood_dim(dim_id: str, req: MoodDimPatch) -> dict[str, Any]:
        d = mood_dims.update(dim_id, req.label, req.description, req.example, req.enabled)
        if d is None:
            raise HTTPException(status_code=404, detail="维度不存在")
        return d.to_dict()

    @app.delete("/api/mood/dims/{dim_id}", response_model=dict[str, bool])
    def delete_mood_dim(dim_id: str) -> dict[str, bool]:
        ok = mood_dims.delete(dim_id)
        if not ok:
            raise HTTPException(status_code=404, detail="维度不存在")
        return {"ok": True}

    @app.get("/api/bias", response_model=list[dict[str, Any]])
    def list_bias() -> list[dict[str, Any]]:
        """AI 倾向档案（双向黑盒解法）。"""
        return bias.list()

    @app.post("/api/bias", response_model=dict[str, Any])
    def add_bias(req: BiasIn) -> dict[str, Any]:
        """新增倾向自述（AI 声明或用户修正）。"""
        return bias.add(req.content, req.source)

    @app.delete("/api/bias/{bias_id}")
    def delete_bias(bias_id: str) -> dict[str, bool]:
        bias.delete(bias_id)
        return {"ok": True}

    # ------------------------------------------------------------------
    # S10 低摩擦交互层 + T2 阶段 5/6（候选卡堆/方向声明/改写渐变/一章收尾）
    # ------------------------------------------------------------------
    @app.post("/api/chat/direction", response_model=dict[str, str])
    def chat_direction(req: DirectionIn) -> dict[str, str]:
        """阶段 5 方向声明：AI 只声明"我准备写：…"不写正文（摩擦前置，用户 0.5s 确认）。"""
        ctx = f"\n已知设定：{req.context[:2000]}" if req.context else ""
        prompt = (
            "你是小说写作智能体。用户将让你写一段内容。"
            "在动笔前，先输出【方向声明】——一句话说明你准备写什么、怎么切入"
            "（像'我准备写：主角推开钟表铺的门，雨声里老周欲言又止'）。"
            "只输出声明，不要写正文。\n\n"
            f"用户要求：{req.prompt}{ctx}"
        )
        out = model.respond([Message(role="system", content=prompt)], [])
        direction = out.text.strip()
        if not direction.startswith("【方向声明】"):
            direction = f"【方向声明】{direction}"
        return {"direction": direction}

    @app.post("/api/chat/candidates", response_model=dict[str, object])
    def chat_candidates(req: CandidatesIn) -> dict[str, object]:
        """候选卡堆：并行生成 N 个差异化候选（上下文隔离→真多样性，机制 1/4）。"""
        from concurrent.futures import ThreadPoolExecutor

        ctx = f"\n已知设定：{req.context[:2000]}" if req.context else ""
        n = max(2, min(4, req.n))
        styles = ["平实叙事", "强画面感", "悬念张力", "细腻心理"]

        def _one(i: int) -> str:
            prompt = (
                f"你是小说写作智能体。按风格「{styles[i % len(styles)]}」写下面要求的一段正文"
                f"（约 150-250 字，直接输出正文，不要解释）。\n\n用户要求：{req.prompt}{ctx}"
            )
            out = model.respond([Message(role="system", content=prompt)], [])
            return out.text.strip()

        with ThreadPoolExecutor(max_workers=n) as pool:
            results = list(pool.map(_one, range(n)))
        candidates = [
            {"id": f"c{i + 1}", "style": styles[i % len(styles)], "text": results[i]}
            for i in range(n)
        ]
        return {"candidates": candidates}

    @app.post("/api/chat/rewrite", response_model=dict[str, str])
    def chat_rewrite(req: RewriteIn) -> dict[str, str]:
        """改写渐变条（机制 4）：保原味↔大幅改，温度+指令差异化。"""
        mode = req.mode if req.mode in ("subtle", "balanced", "bold") else "balanced"
        temp_map = {"subtle": 0.3, "balanced": 0.7, "bold": 1.1}
        instruct_map = {
            "subtle": "尽量保留原文结构与表达，只做轻微润色",
            "balanced": "在保留原意的基础上改写，语言更生动",
            "bold": "大胆重构：换切入角度、换句式节奏、大幅改变表达",
        }
        prompt = (
            "你是小说写作智能体。改写下面这段正文。"
            f"要求：{instruct_map[mode]}。直接输出改写后的正文，不要解释。\n\n原文：\n{req.text[:3000]}"
        )
        # 渐变条温度映射：保原味=低温，大幅改=高温（仅真实模型生效）
        rewrite_model: Any = model
        if isinstance(model, DeepSeekModel):
            rewrite_model = DeepSeekModel(temperature=temp_map[mode])
        out = rewrite_model.respond(
            [Message(role="system", content=prompt)],
            [],
        )
        return {"rewritten": out.text.strip(), "mode": mode}

    @app.post("/api/chapters/{chapter_id}/wrapup", response_model=dict[str, object])
    def chapter_wrapup(chapter_id: str) -> dict[str, object]:
        """阶段 6 一章收尾：一致性摘要卡 + 下一章衔接提示（不自动评审，轻量）。"""
        ch = chapters.get(chapter_id)
        if ch is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        prompt = (
            "你是小说写作智能体。读下面这章正文，输出两句：\n"
            "1. 一致性摘要（一句话概括本章发生了什么、推进了什么）\n"
            "2. 下一章衔接提示（建议下一章推进什么，如'推进角色弧/揭开伏笔'，给一个具体方向）\n"
            '格式（严格 JSON）：{"summary": "…", "next_hint": "…"}\n\n'
            f"章节《{ch.title}》正文：\n{ch.content[:4000]}"
        )
        out = model.respond([Message(role="system", content=prompt)], [])
        import json as _json
        import re

        cleaned = out.text.strip()
        fence = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
        if fence:
            cleaned = fence.group(1)
        start, end = cleaned.find("{"), cleaned.rfind("}")
        summary, hint = "", ""
        if start != -1 and end != -1 and end > start:
            try:
                data = _json.loads(cleaned[start : end + 1])
                if isinstance(data, dict):
                    summary = str(data.get("summary", ""))
                    hint = str(data.get("next_hint", ""))
            except _json.JSONDecodeError:
                pass
        # 图谱统计（本章涉及的实体）
        involved = graph_verifier.facts_for("main", ch.content[:2000])
        # S31：主线钩子检查——作者承诺的剧情钩子仍未回收的（轻量提示，建议非门禁）
        # 老龄化：带开放时长（中性事实，不设阈值不评判）
        open_hooks = plots.open_must("main", current_order=ch.order_index) or []
        hook_check = (
            [
                {
                    "content": h.content[:60],
                    "chapter_ref": h.chapter_ref,
                    "category": h.category,
                    "open_since": (
                        ch.order_index - h.planted_order if h.planted_order > 0 else None
                    ),
                }
                for h in open_hooks
            ][:8]
            if open_hooks
            else []
        )
        return {
            "chapter_id": chapter_id,
            "title": ch.title,
            "summary": summary or out.text.strip()[:100],
            "next_hint": hint,
            "graph_entities": [f.entity.name for f in involved][:10],
            "open_hooks": hook_check,  # S31：仍未回收的主线钩子（提醒，不阻断）
        }

    # -----------------------------------------------------------------------
    # S48 工作区：每项目一路径（上传存档/章节 md/卡片），md 文件为章节权威
    # -----------------------------------------------------------------------
    @app.get("/api/workspace", response_model=dict[str, Any])
    def workspace_overview() -> dict[str, Any]:
        """项目工作区结构总览：上传存档 / 章节文件 / 卡片。"""
        return workspace.describe("main")

    @app.post("/api/workspace/import", response_model=dict[str, Any])
    def workspace_import_chapters() -> dict[str, Any]:
        """S48：扫描章节 md 文件 → 同步入库（人工直接编辑 md 后调用）。

        仅内容变化才 upsert（版本历史只在变化时记录）。
        权威始终在文件——import 是"文件 → 库镜像"的单向同步。
        """
        imported: list[dict[str, Any]] = []
        for item in workspace.list_chapter_files("main"):
            content = workspace.read_chapter("main", item["order"], item["title"])
            if content is None:
                continue
            existing = next(
                (c for c in chapters.list_by_book("main") if c.title == item["title"]),
                None,
            )
            changed = existing is None or existing.content != content
            if changed:
                line = existing.narrative_line if existing else "main"
                chapters.upsert("main", item["title"], content, item["order"], line)
            imported.append({"title": item["title"], "order": item["order"], "changed": changed})
        return {
            "ok": True,
            "files": len(imported),
            "changed": sum(1 for i in imported if i["changed"]),
            "imported": imported,
        }

    @app.post("/api/upload", response_model=dict[str, Any])
    def upload_to_workspace(req: UploadIn) -> dict[str, Any]:
        """S48：上传原始文件进上传区（存档，不参与操作；后续消化为格式化产物）。

        用 base64 JSON（零新依赖 python-multipart）；前端/agent 都可直接传。
        """
        import base64

        try:
            data = base64.b64decode(req.data_b64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"base64 解码失败：{exc}") from exc
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="文件超过 20MB 上限")
        dest = workspace.save_upload("main", req.filename, data)
        logger.info("上传存档: %s -> %s", req.filename, dest.name)
        return {"ok": True, "name": dest.name, "path": str(dest), "size": len(data)}

    # -----------------------------------------------------------------------
    # S48-P4 角色推演：低成本多探索 + 选优（复用 explore 并行基建）
    # -----------------------------------------------------------------------
    @app.post("/api/role/card", response_model=dict[str, Any])
    def role_card_upsert(req: RoleCardIn) -> dict[str, Any]:
        """创建/更新角色卡（卡片/角色卡-{name}.md）。"""
        f = workspace.write_card("main", "角色卡", req.name, req.content)
        return {"ok": True, "name": req.name, "file": f.name}

    @app.post("/api/role/play", response_model=dict[str, Any])
    def role_play(req: RolePlayIn) -> dict[str, Any]:
        """角色推演：角色卡 + 当前状态 + 场景 → N 路隔离推演 → 判别选优（作为参考）。"""
        from anyspark.explore.roleplay import run_roleplay

        # 角色卡：文件优先，缺省从图谱实体描述兜底
        card_path = workspace.cards_dir("main") / f"角色卡-{req.role}.md"
        role_card = ""
        if card_path.exists():
            role_card = card_path.read_text(encoding="utf-8", errors="ignore")
        if not role_card.strip():
            ent = graph.get_entity("main", req.role)
            if ent is not None:
                desc = getattr(ent, "description", "") or ""
                state = getattr(ent, "state", "") or ""
                role_card = f"# {req.role}\n{desc}\n\n当前状态：{state}"
        if not role_card.strip():
            raise HTTPException(
                status_code=404, detail=f"角色卡不存在（可先 POST /api/role/card 创建）：{req.role}"
            )
        state = ""
        ent = graph.get_entity("main", req.role)
        if ent is not None:
            state = getattr(ent, "state", "") or ""
        result = run_roleplay(model, role_card, state=state, scenario=req.scenario, n=req.n)
        if not result.candidates:
            raise HTTPException(status_code=502, detail="推演失败（无有效候选）")
        logger.info(
            "角色推演: %s × %d 路 → best=%s",
            req.role,
            len(result.candidates),
            result.best.strategy if result.best else "?",
        )
        return result.to_dict()

    # -----------------------------------------------------------------------
    # S48-P4/B 扩展工具注册表：Agent 写的工具，人工批准才生效
    # -----------------------------------------------------------------------
    @app.get("/api/tools", response_model=list[dict[str, Any]])
    def list_ext_tools() -> list[dict[str, Any]]:
        return [t.to_dict() for t in ext_tools.list_all()]

    @app.post("/api/tools/register", response_model=dict[str, Any])
    def register_ext_tool(req: ToolRegisterIn) -> dict[str, Any]:
        """登记扩展工具（status=draft；人工批准后才注入 Agent 工具集）。"""
        try:
            params = json.loads(req.params_json) if req.params_json else []
            if not isinstance(params, list):
                raise ValueError("params 必须是 JSON 数组")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"params 解析失败：{exc}") from exc
        if not req.code.strip() or "def run(" not in req.code:
            raise HTTPException(
                status_code=400, detail="工具代码必须定义 run(args: dict) -> str 函数"
            )
        t = ext_tools.add(req.name, req.description, params, req.code)
        return {
            "ok": True,
            "id": t.id,
            "name": t.name,
            "status": "draft",
            "note": "已登记待审——人工批准后才生效",
        }

    @app.post("/api/tools/{tool_id}/approve", response_model=dict[str, Any])
    def approve_ext_tool(tool_id: str) -> dict[str, Any]:
        """人工批准：工具进入 active，后续请求注入 Agent 工具集（无需重启）。"""
        t = ext_tools.set_status(tool_id, "active")
        if t is None:
            raise HTTPException(status_code=404, detail="扩展工具不存在")
        logger.info("扩展工具已批准生效: %s", t.name)
        return {"ok": True, "id": t.id, "name": t.name, "status": "active"}

    @app.patch("/api/tools/{tool_id}", response_model=dict[str, Any])
    def update_ext_tool(tool_id: str, req: ToolUpdateIn) -> dict[str, Any]:
        """更新扩展工具（S49：改代码/描述/参数）。安全：改后自动回 draft 重新批准。"""
        if req.params_json is not None:
            try:
                params = json.loads(req.params_json)
                if not isinstance(params, list):
                    raise ValueError("params 必须是 JSON 数组")
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"params 解析失败：{exc}") from exc
        else:
            params = None
        if req.code is not None and ("def run(" not in req.code):
            raise HTTPException(
                status_code=400, detail="工具代码必须定义 def run(args: dict) -> str 函数"
            )
        t = ext_tools.update(tool_id, req.name, req.description, params, req.code)
        if t is None:
            raise HTTPException(status_code=404, detail="扩展工具不存在")
        return {
            "ok": True,
            "id": t.id,
            "name": t.name,
            "status": t.status,
            "note": "已更新，需重新人工批准后才生效",
        }

    @app.post("/api/tools/{tool_id}/disable", response_model=dict[str, Any])
    def disable_ext_tool(tool_id: str) -> dict[str, Any]:
        t = ext_tools.set_status(tool_id, "draft")
        if t is None:
            raise HTTPException(status_code=404, detail="扩展工具不存在")
        return {"ok": True, "id": t.id, "name": t.name, "status": "draft"}

    @app.delete("/api/tools/{tool_id}", response_model=dict[str, Any])
    def delete_ext_tool(tool_id: str) -> dict[str, Any]:
        if not ext_tools.delete(tool_id):
            raise HTTPException(status_code=404, detail="扩展工具不存在")
        return {"ok": True}

    # -----------------------------------------------------------------------
    # S48-P5 代码扩展（anyspark-codex）：沙箱执行，固定工具做不了时用
    # -----------------------------------------------------------------------
    @app.post("/api/codex/run", response_model=dict[str, Any])
    def codex_run(req: CodexIn) -> dict[str, Any]:
        """沙箱执行 Python 代码（白名单安全 + 只读数据环境 ws_*：真实统计/自定义分析）。"""
        from anyspark.server.codex import make_data_env, run_code

        return run_code(req.code, req.timeout, data_env=make_data_env(workspace, chapters, graph))

    # -----------------------------------------------------------------------
    # S48-P3 输入消化管线：上传区原始文件 → 格式化区（章节 md / 摘要卡）
    # -----------------------------------------------------------------------
    @app.post("/api/ingest", response_model=dict[str, Any])
    def ingest_upload(req: IngestIn) -> dict[str, Any]:
        """消化上传区文件：长文（多章）拆成章节 md；资料/短文本生成摘要卡。

        原始文件原地不动（存档）；产物进格式化区（章节/ 或 卡片/）。
        多模态（扫描件 OCR/图片理解）明确不做，放未来计划。
        """
        from anyspark.server.pipeline import chapterize, extract_text

        path = workspace.read_upload("main", req.filename)
        if path is None:
            raise HTTPException(status_code=404, detail=f"上传区无此文件：{req.filename}")
        if path.suffix.lower() not in (".txt", ".md", ".markdown", ".docx", ".pdf"):
            raise HTTPException(
                status_code=400, detail="仅支持 txt/md/docx/pdf 文本消化（图片放未来）"
            )
        text = extract_text(path)
        if not text.strip():
            raise HTTPException(status_code=400, detail="无法提取文本（扫描件 OCR 放未来计划）")
        chaps = chapterize(text, fallback_title=path.stem)
        # 判别：mode 强制 / 单章短文本 → 摘要卡；否则拆章
        is_card = req.mode == "card" or (
            req.mode != "chapters" and len(chaps) == 1 and len(text) < 3000
        )
        if is_card:
            digestor = MaterialDigestor(model)
            card = digestor.digest(text)
            saved = materials.save(card)
            card_md = (
                f"# {saved.title}\n\n主题：{saved.topic}\n\n"
                + "要点："
                + "；".join(saved.key_points[:6])
                + "\n设定："
                + "；".join(saved.key_settings[:6])
                + "\n角色："
                + "、".join(saved.characters[:8])
                + "\n术语："
                + "、".join(saved.terms[:8])
            )
            f = workspace.write_card("main", "摘要卡", saved.title, card_md)
            return {
                "ok": True,
                "kind": "card",
                "title": saved.title,
                "card_file": f.name,
                "material_id": saved.id,
            }
        written: list[dict[str, Any]] = []
        for i, ch in enumerate(chaps):
            workspace.write_chapter("main", i, ch["title"], ch["content"])
            chapters.upsert("main", ch["title"], ch["content"], i, "main")
            written.append({"order": i, "title": ch["title"], "chars": len(ch["content"])})
        logger.info("消化: %s → %d 章", req.filename, len(written))
        return {"ok": True, "kind": "chapters", "count": len(written), "chapters": written}

    @app.get("/api/export/book", response_model=None)
    def export_book(format: str = "md") -> Response:
        """全书导出（S48-P3）：txt/md/epub（epub 携带 md 引用的图片）。"""
        from anyspark.server.export import export_epub, export_md, export_txt

        items = chapters.list_by_book("main")
        chs = [{"title": c.title, "content": c.content} for c in items]
        fmt = format if format in ("txt", "md", "epub") else "md"
        if fmt == "epub":
            data = export_epub(
                "AnySpark 作品",
                "AnySpark",
                chs,
                image_dir=workspace.chapters_dir("main"),  # md 引用相对章节目录（../上传/x.png）
            )
            from urllib.parse import quote

            safe = quote("anyspark-book.epub")
            return Response(
                content=data,
                media_type="application/epub+zip",
                headers={
                    "Content-Disposition": (
                        f"attachment; filename=book.epub; filename*=UTF-8''{safe}"
                    )
                },
            )
        body = export_txt(chs) if fmt == "txt" else export_md(chs)
        media = "text/plain; charset=utf-8" if fmt == "txt" else "text/markdown; charset=utf-8"
        from urllib.parse import quote

        safe = quote(f"anyspark-book.{fmt}")
        return Response(
            content=body,
            media_type=media,
            headers={
                "Content-Disposition": (f"attachment; filename=book.{fmt}; filename*=UTF-8''{safe}")
            },
        )

    @app.get("/api/chapters", response_model=list[ChapterOut])
    def list_chapters() -> list[ChapterOut]:
        items = chapters.list_by_book("main")
        return [
            ChapterOut(
                id=c.id,
                book_id=c.book_id,
                title=c.title,
                content=c.content,
                order_index=c.order_index,
                updated_at=c.updated_at,
            )
            for c in items
        ]

    @app.get("/api/chapters/{chapter_id}", response_model=ChapterOut)
    def get_chapter(chapter_id: str) -> ChapterOut:
        ch = chapters.get(chapter_id)
        if ch is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        return ChapterOut(
            id=ch.id,
            book_id=ch.book_id,
            title=ch.title,
            content=ch.content,
            order_index=ch.order_index,
            updated_at=ch.updated_at,
        )

    @app.post("/api/chapters/{chapter_id}/patch", response_model=dict[str, object])
    def patch_chapter_route(chapter_id: str, req: ChapterPatchIn) -> dict[str, object]:
        """S44：定点编辑（锚点定位段落的插入/删除/替换，不重写整章）。"""
        from anyspark.server.tools_writing import apply_patch

        ch = chapters.get(chapter_id)
        if ch is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        new_content, results = apply_patch(ch.content, req.operations)
        ok_all = all(r.get("ok") for r in results)
        chapters.upsert("main", ch.title, new_content, ch.order_index, ch.narrative_line)
        return {
            "title": ch.title,
            "ok": ok_all,
            "results": results,
            "chars": len(new_content),
        }

    @app.get("/api/chapters/{chapter_id}/export")
    def export_chapter(chapter_id: str, format: str = "txt") -> Response:
        """多格式导出（S11 工具扩展：txt/md）。"""
        ch = chapters.get(chapter_id)
        if ch is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        fmt = format if format in ("txt", "md") else "txt"
        body = f"# {ch.title}\n\n{ch.content}\n" if fmt == "md" else f"{ch.title}\n{ch.content}\n"
        media = "text/markdown; charset=utf-8" if fmt == "md" else "text/plain; charset=utf-8"
        # 中文文件名用 RFC 5987 filename*（latin-1 无法直接编码中文）
        from urllib.parse import quote

        safe_name = quote(f"{ch.title}.{fmt}")
        disposition = f"attachment; filename=chapter.{fmt}; filename*=UTF-8''{safe_name}"
        return Response(
            content=body,
            media_type=media,
            headers={"Content-Disposition": disposition},
        )

    # ------------------------------------------------------------------
    # 知识图谱（S7：AI 事实源，后台自动维护）
    # ------------------------------------------------------------------
    @app.get("/api/graph/types", response_model=list[dict[str, Any]])
    def list_graph_types() -> list[dict[str, Any]]:
        """实体类型集（S50 内容化：可增删改/开关）。"""
        return graph.list_types("main")

    @app.post("/api/graph/types", response_model=dict[str, Any])
    def add_graph_type(req: GraphTypeIn) -> dict[str, Any]:
        t = graph.add_type(req.name)
        if t is None:
            raise HTTPException(status_code=409, detail=f"类型已存在: {req.name}")
        return t

    @app.patch("/api/graph/types/{type_id}", response_model=dict[str, Any])
    def patch_graph_type(type_id: str, req: GraphTypePatch) -> dict[str, Any]:
        t = graph.set_type_enabled(type_id, req.enabled)
        if t is None:
            raise HTTPException(status_code=404, detail="类型不存在")
        return t

    @app.delete("/api/graph/types/{type_id}", response_model=dict[str, bool])
    def delete_graph_type(type_id: str) -> dict[str, bool]:
        ok = graph.delete_type(type_id)
        if not ok:
            raise HTTPException(status_code=404, detail="类型不存在")
        return {"ok": True}

    @app.get("/api/graph/entities", response_model=list[dict[str, Any]])
    def list_graph_entities(q: str = "", entity_type: str = "") -> list[dict[str, Any]]:
        """图谱实体（可 q 模糊 / entity_type 过滤）。"""
        items = graph.list_entities("main", q=q or None, entity_type=entity_type or None)
        return [e.to_dict() for e in items]

    @app.get("/api/graph/relations", response_model=list[dict[str, Any]])
    def list_graph_relations() -> list[dict[str, Any]]:
        return [r.to_dict() for r in graph.list_relations("main")]

    @app.get("/api/graph/events", response_model=list[dict[str, Any]])
    def list_graph_events() -> list[dict[str, Any]]:
        return [e.to_dict() for e in graph.list_events("main")]

    @app.get("/api/graph/context", response_model=dict[str, str])
    def graph_context() -> dict[str, str]:
        """当前时空点已知事实注入块（预览）。"""
        return {"block": graph_injector.build_block("main")}

    @app.post("/api/impact", response_model=dict[str, object])
    def impact_route(req: ImpactIn) -> dict[str, object]:
        """S45：影响分析——改第 N 章（涉及实体）→ 后续受影响章节（连锁修改依据）。"""
        hits = graph.impact_chapters("main", req.chapter_order, req.entities)
        return {"changed_order": req.chapter_order, "impacted": hits, "count": len(hits)}

    # ------------------------------------------------------------------
    # S46 剧情计划（计划→执行：固化章节计划，写作注入，推进标记）
    # ------------------------------------------------------------------
    @app.get("/api/plan", response_model=list[dict[str, Any]])
    def list_plan() -> list[dict[str, Any]]:
        """全部章节计划（按 chapter_order）。"""
        return [p.to_dict() for p in plans.list()]

    @app.post("/api/plan", response_model=dict[str, Any])
    def add_plan(req: ChapterPlanIn) -> dict[str, Any]:
        p = plans.add(req.chapter_order, req.title, req.content)
        return p.to_dict()

    @app.patch("/api/plan/{plan_id}", response_model=dict[str, Any])
    def patch_plan(plan_id: str, req: ChapterPlanPatch) -> dict[str, Any]:
        p = plans.update(plan_id, req.title, req.content, req.status)
        if p is None:
            raise HTTPException(status_code=404, detail="计划不存在")
        return p.to_dict()

    @app.delete("/api/plan/{plan_id}", response_model=dict[str, bool])
    def delete_plan(plan_id: str) -> dict[str, bool]:
        ok = plans.delete(plan_id)
        if not ok:
            raise HTTPException(status_code=404, detail="计划不存在")
        return {"ok": True}

    @app.post("/api/graph/extract", response_model=dict[str, int])
    def graph_extract_route(req: GraphExtractIn) -> dict[str, int]:
        """手动抽取一章入库（真实 LLM；write_chapter 后已自动，此为补抽/重抽）。"""
        existing = [e.to_dict() for e in graph.list_entities("main")]
        ext = graph_extractor.extract(req.chapter_ref, req.text, existing)
        chs = chapters.list_by_book("main")
        order = next((c.order_index for c in chs if c.title == req.chapter_ref), len(chs))
        graph.ingest_chapter("main", req.chapter_ref, order, ext)
        return {
            "entities": len(ext.entities),
            "relations": len(ext.relations),
            "events": len(ext.events),
        }

    return app


app = build_app()
