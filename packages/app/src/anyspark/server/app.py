"""
anyspark.server.app — FastAPI 后端（真实 API 层）。

提供：对话→写作→修改闭环的 HTTP 接口 + 章节读写接口。
所有真实组件（DeepSeekModel / SQLite 存储 / 写作工具）在此装配。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, cast

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from anyspark.align import ManualEntry, ManualInjector, ManualStore, SignalCollector, SignalStore
from anyspark.check import compile_rule, run_review
from anyspark.core import Agent, Model, ToolRegistry
from anyspark.explore import (
    DirectionCard,
    IntentUnderstander,
    ProjectArchive,
    run_exploration,
)
from anyspark.models.deepseek import DeepSeekModel
from anyspark.server.tools_writing import register_writing_tools
from anyspark.store import ChapterStore, SqliteConversationStore
from anyspark.template import MaterialDigestor, MaterialStore, default_library

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


# ---------------------------------------------------------------------------
# Pydantic 请求/响应模型
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户输入")
    conversation_id: str | None = None
    system_prompt: str | None = None
    temperature: float = 0.7


class ToolEvent(BaseModel):
    type: str
    payload: dict[str, Any]


class ChatResponse(BaseModel):
    conversation_id: str
    text: str
    turns: list[dict[str, Any]]
    events: list[ToolEvent]


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


class RuleRequest(BaseModel):
    rule: str
    text: str


class MaterialIn(BaseModel):
    text: str
    title: str = ""
    purpose: str = "fact"  # style|fact|both


# ---------------------------------------------------------------------------
# 应用装配
# ---------------------------------------------------------------------------
def build_app(model: Model | None = None, db_path: str | Path | None = None) -> FastAPI:
    """装配后端应用。

    - model: 真实 DeepSeekModel（默认）；测试可注入 fake model（实现 core.Model 协议）
    - db_path: 默认 data/anyspark.db；测试可注入临时路径
    """
    load_dotenv(PROJECT_ROOT / ".env")

    real_db = db_path or DB_PATH
    store = SqliteConversationStore(real_db)
    chapters = ChapterStore(real_db)
    manual = ManualStore(real_db)
    signals = SignalStore(real_db)
    archive = ProjectArchive(real_db)
    materials = MaterialStore(real_db)
    manual_injector = ManualInjector(manual)
    signal_collector = SignalCollector(signals)
    model = model or DeepSeekModel()

    app = FastAPI(title="AnySpark v4 API", version="0.0.1")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 开发期；前端 Vite dev server 在此端口
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _make_agent(system_prompt: str, temperature: float, book_id: str = "main") -> Agent:
        registry = ToolRegistry()
        register_writing_tools(registry, chapters)
        m = model if temperature == 0.7 else DeepSeekModel(temperature=temperature)
        # 对齐注入：说明书（项目级>全局级）追加进系统提示
        align_block = manual_injector.build_system_block(book_id)
        full_prompt = system_prompt
        if align_block:
            full_prompt = full_prompt + "\n\n" + align_block
        return Agent(model=m, registry=registry, store=store, system_prompt=full_prompt)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        name = getattr(model, "model_name", "unknown")
        return {"status": "ok", "model": str(name)}

    @app.post("/api/chat", response_model=ChatResponse)
    def chat(req: ChatRequest) -> ChatResponse:
        events: list[ToolEvent] = []
        agent = _make_agent(
            req.system_prompt or DEFAULT_SYSTEM,
            req.temperature,
        )
        agent.events.on(
            "tool_call", lambda e: events.append(ToolEvent(type=e.type, payload=e.payload))
        )
        agent.events.on(
            "tool_result", lambda e: events.append(ToolEvent(type=e.type, payload=e.payload))
        )

        # 无会话时显式创建，保证 conversation_id 可回传（多轮续写）
        conv_id = req.conversation_id
        if not conv_id:
            conv = agent.store.create()
            conv_id = conv.id

        turn = agent.run(req.message, conv_id)
        if not turn.tool_calls and "达到最大工具迭代" in turn.text:
            raise HTTPException(status_code=500, detail=turn.text)

        turns_payload = [{"text": turn.text, "tool_calls": [c.name for c in turn.tool_calls]}]
        return ChatResponse(
            conversation_id=conv_id,
            text=turn.text,
            turns=turns_payload,
            events=events,
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
        """采集用户操作信号（接受/修改/删除/自定义等）。"""
        if req.kind == "accepted":
            sig = signal_collector.accepted(req.content, req.context)
        elif req.kind == "deleted":
            sig = signal_collector.deleted(req.content, req.context)
        elif req.kind == "rejected":
            sig = signal_collector.rejected(req.content, req.context)
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
        """多检测者审读正文（骨架检测项，并行）。"""
        report = run_review(model, req.target, req.text)
        return {
            "target": report.target,
            "hard_count": report.hard_count,
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
        """L2 默认模式库（探索方向生成器）。"""
        return [t.to_dict() for t in default_library()]

    @app.post("/api/materials", response_model=dict[str, object])
    def add_material(req: MaterialIn) -> dict[str, object]:
        """上传材料 → 真实 LLM 消化成摘要卡 → 入库（原文保留）。"""
        purpose: Any = req.purpose if req.purpose in ("style", "fact", "both") else "fact"
        digestor = MaterialDigestor(model)
        card = digestor.digest(req.text, purpose=purpose)
        if req.title:
            card.title = req.title
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

    return app


app = build_app()
