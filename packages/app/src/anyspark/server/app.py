"""
anyspark.server.app — FastAPI 后端（真实 API 层）。

提供：对话→写作→修改闭环的 HTTP 接口 + 章节读写接口。
所有真实组件（DeepSeekModel / SQLite 存储 / 写作工具）在此装配。
"""

from __future__ import annotations

import json
import queue
import threading
from pathlib import Path
from typing import Any, Literal, cast

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from anyspark.align import (
    AGENCY_LEVELS,
    AgencyStore,
    BiasStore,
    ManualEntry,
    ManualInjector,
    ManualStore,
    SignalCollector,
    SignalStore,
    build_agency_block,
    build_mood_block,
    parse_agency_declaration,
    temperature_for,
)
from anyspark.check import compile_rule, run_review
from anyspark.core import Agent, Message, Model, RetryingModel, ToolRegistry
from anyspark.explore import (
    DirectionCard,
    IntentUnderstander,
    ProjectArchive,
    run_exploration,
)
from anyspark.graph import GraphExtractor, GraphInjector, GraphStore, GraphVerifier
from anyspark.models.deepseek import DeepSeekModel
from anyspark.server.context import TokenBudget, make_summarizer
from anyspark.server.logging import log_path, logger, setup_logging
from anyspark.server.stats import compute_stats
from anyspark.server.tools_writing import register_writing_tools
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
    "写正文前用 list_chapters/read_chapter 查看已有内容保持连贯，"
    "写正文可用 write_chapter 保存。"
    "正文要具体、有画面感，杜绝空泛总结。"
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
    extract_graph: bool = True  # 章节落盘后图谱抽取（默认开保持现状；可关省 token）
    skip_inject: list[str] = []  # 细粒度跳过注入：manual/graph/agency/bias/mood/plot 子集


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


class ManualEntryPatch(BaseModel):
    content: str | None = None
    locked: bool | None = None


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


class CheckRequest(BaseModel):
    text: str
    target: str = "当前章节"
    chapter_order: int | None = None  # 时序校验：当前章节序号（校验时空倒置）


class RuleRequest(BaseModel):
    rule: str
    text: str


class MaterialIn(BaseModel):
    text: str
    title: str = ""
    purpose: str = "fact"  # style|fact|both


class GraphExtractIn(BaseModel):
    chapter_ref: str
    text: str


class AgencyIn(BaseModel):
    level: int


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


# ---------------------------------------------------------------------------
# 应用装配
# ---------------------------------------------------------------------------
def build_app(model: Model | None = None, db_path: str | Path | None = None) -> FastAPI:
    """装配后端应用。

    - model: 真实 DeepSeekModel（默认）；测试可注入 fake model（实现 core.Model 协议）
    - db_path: 默认 data/anyspark.db；测试可注入临时路径
    """
    load_dotenv(PROJECT_ROOT / ".env")
    setup_logging()

    real_db = db_path or DB_PATH
    store = SqliteConversationStore(real_db)
    chapters = ChapterStore(real_db)
    manual = ManualStore(real_db)
    signals = SignalStore(real_db)
    archive = ProjectArchive(real_db)
    materials = MaterialStore(real_db)
    templates_external = ExternalLibrary(real_db)
    plots = PlotStore(real_db)
    manual_injector = ManualInjector(manual)
    signal_collector = SignalCollector(signals)
    # 默认真实模型套上组合式重试包装（S15：重试是 core 可拼接组件，不内嵌在模型里）
    model = model or RetryingModel(DeepSeekModel())
    plot_generator = PlotGenerator(model)  # 依赖 model，须在其初始化之后
    plot_resolver = PlotResolver(model)  # 伏笔自动回收（S17：章节落盘后台识别揭开）
    # 知识图谱（S7：AI 事实源）
    graph = GraphStore(real_db)
    graph_extractor = GraphExtractor(model)
    graph_injector = GraphInjector(graph)
    graph_verifier = GraphVerifier(graph)
    # token 预算 + 两阶段压缩（S8：长书上下文刚需）
    budget = TokenBudget(budget=12000, summarize=make_summarizer(model))
    # 能动性协议（机制 2）+ AI 倾向档案（S9）
    agency = AgencyStore(real_db)
    bias = BiasStore(real_db)

    app = FastAPI(title="AnySpark v4 API", version="0.0.1")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 开发期；前端 Vite dev server 在此端口
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _make_agent(
        system_prompt: str,
        temperature: float,
        book_id: str = "main",
        on_delta: Any | None = None,
        agency_level: int | None = None,
        mood: dict[str, float] | None = None,
        enable_search: bool = False,
        skip_inject: set[str] | None = None,
    ) -> Agent:
        registry = ToolRegistry()
        register_writing_tools(registry, chapters)
        # 网络搜索工具：按需注册（S15 起默认关——写作主链路不背考据能力，需要时点亮）
        if enable_search:
            from anyspark.server.tools_web import make_search_implementer

            search_spec, search_impl = make_search_implementer()
            registry.register(search_spec, search_impl)
        # 能动级别：显式传入 > 已存档位；温度映射（档位低=精确执行温度低）
        if agency_level is None:
            agency_level = agency.get_level(book_id)
        eff_temp = temperature_for(agency_level) if temperature == 0.7 else temperature
        # 解包重试包装（RetryingModel.inner）判断底层是否真实 DeepSeek（流式能力）
        base_model = getattr(model, "inner", model)
        m: Model
        if on_delta is not None and isinstance(base_model, DeepSeekModel):
            # SSE 流式：真实 DeepSeek 流式传输 + delta 回调（重试由组合包装提供）
            m = RetryingModel(DeepSeekModel(temperature=eff_temp, stream=True, on_delta=on_delta))
        elif on_delta is not None:
            m = model  # 测试 fake：无逐字流，仅事件帧
        elif isinstance(base_model, DeepSeekModel) and eff_temp != 0.7:
            # 真实模型 + 能动性温度映射（档位低=精确执行温度低）
            m = RetryingModel(DeepSeekModel(temperature=eff_temp))
        else:
            m = model  # 共享 model（测试注入或默认真实）；温度由构造决定
        # 注入块装配：核心注入默认全开，skip_inject 可细粒度关闭（S15 增强按需）
        skip = skip_inject or set()
        full_prompt = system_prompt
        # 对齐注入：说明书（项目级>全局级）追加进系统提示
        align_block = manual_injector.build_system_block(book_id)
        if "manual" not in skip and align_block:
            full_prompt = full_prompt + "\n\n" + align_block
        # 图谱注入：当前时空点已知事实（AI 事实源，模型局限弥补）
        graph_block = graph_injector.build_block(book_id)
        if "graph" not in skip and graph_block:
            full_prompt = full_prompt + "\n\n" + graph_block
        # 能动性注入：本轮档位（机制 2）
        agency_block = build_agency_block(agency_level)
        if "agency" not in skip and agency_block:
            full_prompt = full_prompt + "\n\n" + agency_block
        # AI 倾向档案注入（双向黑盒解法）
        bias_block = bias.render()
        if "bias" not in skip and bias_block:
            full_prompt = full_prompt + "\n\n" + bias_block
        # 关键点图谱注入（T2 阶段 3：当前推进状态——哪些伏笔还开着/刚回收）
        plot_block = plots.render("main")
        if "plot" not in skip and plot_block:
            full_prompt = full_prompt + "\n\n" + plot_block
        # 氛围滑块注入（机制 4：本段氛围要求）
        mood_block = build_mood_block(mood)
        if "mood" not in skip and mood_block:
            full_prompt = full_prompt + "\n\n" + mood_block
        return Agent(
            model=m,
            registry=registry,
            store=store,
            system_prompt=full_prompt,
            context_compressor=budget.compress,  # token 预算两阶段压缩（S8）
        )

    def _extract_chapter(book_id: str, title: str, content: str, order: int) -> None:
        """章节落盘后自动：图谱抽取 + 伏笔自动回收（后台任务）。失败只记日志，绝不阻断写作。"""
        try:
            existing = [e.to_dict() for e in graph.list_entities(book_id)]
            ext = graph_extractor.extract(title, content, existing)
            graph.ingest_chapter(book_id, title, order, ext)
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

    @app.get("/api/stats")
    def stats() -> dict[str, Any]:
        """T7 验证指标（代理指标，纯 SQL 统计现有表，零新表）：修改率/提问率/完成率。"""
        return compute_stats(real_db)

    @app.post("/api/chat", response_model=ChatResponse)
    def chat(req: ChatRequest, background_tasks: BackgroundTasks) -> ChatResponse:
        logger.info("chat 请求: conv=%s len=%d", req.conversation_id or "(新)", len(req.message))
        events: list[ToolEvent] = []
        agent = _make_agent(
            req.system_prompt or DEFAULT_SYSTEM,
            req.temperature,
            agency_level=req.agency_level,
            mood=req.mood,
            enable_search=req.enable_search,
            skip_inject=set(req.skip_inject),
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

        try:
            turn = agent.run(req.message, conv_id)
        except Exception as exc:  # 记录并返回 500
            logger.exception("chat 执行异常: %s", exc)
            raise HTTPException(status_code=500, detail=f"执行失败: {exc}") from exc
        if not turn.tool_calls and "达到最大工具迭代" in turn.text:
            logger.warning("chat 达到最大工具迭代: conv=%s", conv_id)
            raise HTTPException(status_code=500, detail=turn.text)

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
                        background_tasks.add_task(_extract_chapter, "main", title, content, order)
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

        def on_event(e: Any) -> None:
            events_queue.put((e.type, e.payload))

        def run_agent(agent: Agent, msg: str, conv_id: str) -> None:
            try:
                turn = agent.run(msg, conv_id)
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
                                _extract_chapter("main", title, content, order)
            except Exception as exc:  # 异常转 error 帧（不中断连接）
                logger.exception("chat/stream 执行异常: %s", exc)
                events_queue.put(("error", {"message": f"执行失败: {exc}"}))

        def gen() -> Any:
            agent = _make_agent(
                req.system_prompt or DEFAULT_SYSTEM,
                req.temperature,
                on_delta=lambda c: events_queue.put(("text_delta", {"content": c})),
                agency_level=req.agency_level,
                mood=req.mood,
                enable_search=req.enable_search,
                skip_inject=set(req.skip_inject),
            )
            for t in ("turn_start", "text", "tool_call", "tool_result", "done", "error"):
                agent.events.on(t, on_event)
            conv_id = req.conversation_id
            if not conv_id:
                conv = agent.store.create()
                conv_id = conv.id
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
        )
        manual.add(entry)
        return entry.to_dict()

    @app.patch("/api/manual/{entry_id}", response_model=dict[str, Any])
    def update_manual(entry_id: str, req: ManualEntryPatch) -> dict[str, Any]:
        """修改条目内容（锁定条目拒绝，用户主权）。"""
        entry = manual.update(entry_id, content=req.content)
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
        )
        return [c.to_dict() for c in cards]

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
        temporal = (
            graph_verifier.check_temporal("main", req.text, req.chapter_order)
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
        return [p.to_dict() for p in plots.list()]

    @app.patch("/api/plot/{plot_id}", response_model=dict[str, object])
    def update_plot_status(plot_id: str, req: PlotPatchIn) -> dict[str, object]:
        """更新关键点：状态（回收/重开）+ 关注度（在意/不需要）——操作即对齐信号。"""
        p = plots.update(
            plot_id,
            status=req.status,
            attention=req.attention,
        )
        if p is None:
            raise HTTPException(status_code=404, detail="关键点不存在")
        return p.to_dict()

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
        """能动档位（机制 2）：当前级别 + 五级协议描述。"""
        return {"level": agency.get_level(), "levels": AGENCY_LEVELS}

    @app.post("/api/agency", response_model=dict[str, object])
    def set_agency(req: AgencyIn) -> dict[str, object]:
        """用户点选档位（一键修正，摩擦前置）。"""
        level = agency.set_level(req.level)
        return {"level": level, "levels": AGENCY_LEVELS}

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
        return {
            "chapter_id": chapter_id,
            "title": ch.title,
            "summary": summary or out.text.strip()[:100],
            "next_hint": hint,
            "graph_entities": [f.entity.name for f in involved][:10],
        }

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
