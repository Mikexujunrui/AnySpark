from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from core.errors import NotFoundError
from core.event_store import event_store
from core.llm_client import MODELS as LLM_MODELS
from core.permissions import permission_manager
from core.token_counter import count_tokens, get_context_limit
from data.json_store import json_store

router = APIRouter(tags=["sessions"])


class SessionCreate(BaseModel):
    title: str = ""


class SessionUpdate(BaseModel):
    model_config = ConfigDict(extra='allow')


class MessagesSaveRequest(BaseModel):
    messages: list[dict] = []


@router.get("/books/{book_id}/sessions")
def list_sessions(book_id: str):
    return json_store.load_sessions(book_id)


@router.post("/books/{book_id}/sessions")
def create_session(book_id: str, data: SessionCreate | None = None):
    title = data.title if data else ""
    return json_store.create_session(book_id, title)


@router.patch("/books/{book_id}/sessions/{session_id}")
def update_session(book_id: str, session_id: str, data: SessionUpdate):
    try:
        return json_store.update_session(book_id, session_id, data.model_dump())
    except NotFoundError as e:
        raise HTTPException(404, e.message)


@router.delete("/books/{book_id}/sessions/{session_id}")
def delete_session(book_id: str, session_id: str):
    json_store.delete_session(book_id, session_id)
    return {"ok": True}


@router.get("/books/{book_id}/sessions/{session_id}/messages")
def get_messages(book_id: str, session_id: str):
    # Try EventStore first, fall back to legacy JSON store
    if event_store.has_events(session_id):
        return event_store.replay_messages(session_id)
    return json_store.load_messages(session_id)


@router.post("/books/{book_id}/sessions/{session_id}/messages")
def save_messages(book_id: str, session_id: str, data: MessagesSaveRequest):
    msgs = data.messages
    json_store.save_messages(book_id, session_id, msgs)
    # When the frontend explicitly saves messages (e.g. after revert/edit),
    # truncate the EventStore so replay doesn't resurrect deleted events.
    # The JSON store is now the canonical source.
    event_store.truncate(session_id)
    return {"ok": True, "count": len(msgs)}


@router.get("/books/{book_id}/sessions/{session_id}/context")
def get_context_usage(book_id: str, session_id: str):
    # Try EventStore first, fall back to legacy JSON store
    if event_store.has_events(session_id):
        messages = event_store.replay_messages(session_id)
    else:
        messages = json_store.load_messages(session_id)
    total_text = ""
    for m in messages[-100:]:
        text = m.get("text", "")
        if isinstance(text, str) and text:
            total_text += text + "\n"

    token_count = count_tokens(total_text)

    model_name = LLM_MODELS.get("flash", "deepseek-v4-flash")
    context_limit = get_context_limit(model_name)

    return {
        "tokens": token_count,
        "limit": context_limit,
        "ratio": round(token_count / context_limit * 100, 1),
        "message_count": len(messages),
        "model": model_name,
    }


# ── Autonomous Mode ──

class AutonomousToggle(BaseModel):
    enabled: bool


@router.put("/books/{book_id}/sessions/{session_id}/autonomous")
def toggle_autonomous(book_id: str, session_id: str, data: AutonomousToggle):
    """Toggle autonomous mode for this session.

    When enabled, the Agent can execute dangerous tools (delete_chapter,
    delete_entity, etc.) without user confirmation. The flag resets when
    the server restarts or permission_manager is manually reset.
    """
    permission_manager.autonomous_mode = data.enabled
    return {
        "autonomous": data.enabled,
        "message": "自主模式已启用 — Agent 可直接执行危险操作" if data.enabled
                   else "自主模式已关闭 — Agent 执行危险操作前需用户确认",
    }


@router.get("/books/{book_id}/sessions/{session_id}/autonomous")
def get_autonomous(book_id: str, session_id: str):
    return {"autonomous": permission_manager.autonomous_mode}
