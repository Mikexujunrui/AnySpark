"""
anyspark.server.app — FastAPI 后端（真实 API 层）。

提供：对话→写作→修改闭环的 HTTP 接口 + 章节读写接口。
所有真实组件（DeepSeekModel / SQLite 存储 / 写作工具）在此装配。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from anyspark.core import Agent, Model, ToolRegistry
from anyspark.models.deepseek import DeepSeekModel
from anyspark.server.tools_writing import register_writing_tools
from anyspark.store import ChapterStore, SqliteConversationStore

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
    model = model or DeepSeekModel()

    app = FastAPI(title="AnySpark v4 API", version="0.0.1")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 开发期；前端 Vite dev server 在此端口
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def _make_agent(system_prompt: str, temperature: float) -> Agent:
        registry = ToolRegistry()
        register_writing_tools(registry, chapters)
        m = model if temperature == 0.7 else DeepSeekModel(temperature=temperature)
        return Agent(model=m, registry=registry, store=store, system_prompt=system_prompt)

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
