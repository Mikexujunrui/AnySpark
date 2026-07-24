"""Simulation API Routes — 推演功能3.0 API.

提供推演会话管理、SSE流式推演交互、推演结果提拔、分支管理、状态查询等端点。
"""

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from core.simulation import NarratorAgent, SimulationStore, StateAgent

router = APIRouter(prefix="/books/{book_id}/simulation", tags=["simulation"])


# ── Request/Response Models ──


class StartRequest(BaseModel):
    mode: str = "character_pov"
    setting: str = ""
    character_ids: list[str] = []
    pov_character_id: str | None = None
    condition: str | None = None
    style_name: str | None = None
    reference_book_ids: list[str] = []
    timeline_event_id: str | None = None
    user_supplement: str = ""


class TurnRequest(BaseModel):
    simulation_id: str
    choice_id: str | None = None
    choice_text: str | None = None


class PromoteRequest(BaseModel):
    event_id: str
    timeline_data: dict = {}


class CreateBranchRequest(BaseModel):
    parent_event_id: str
    title: str = ""


class SwitchBranchRequest(BaseModel):
    branch_id: str


class RegenerateTurnRequest(BaseModel):
    turn_id: str | None = None


# ── Routes ──


@router.post("/start")
async def start_simulation(book_id: str, body: StartRequest):
    """启动推演 — SSE流式返回初始叙事."""
    store = SimulationStore(book_id)

    if body.mode not in ("character_pov", "narrator_pov"):
        raise HTTPException(status_code=400, detail="mode 必须为 character_pov 或 narrator_pov")
    if body.mode == "character_pov" and not body.pov_character_id:
        raise HTTPException(status_code=400, detail="角色主视角模式需要 pov_character_id")
    if body.mode == "narrator_pov" and not body.character_ids:
        raise HTTPException(status_code=400, detail="叙事者模式需要至少一个参与角色")

    # Create session
    session = store.create_session(
        mode=body.mode,
        setting=body.setting,
        pov_character_id=body.pov_character_id,
        involved_character_ids=body.character_ids or ([body.pov_character_id] if body.pov_character_id else []),
        condition=body.condition,
        style_name=body.style_name,
        reference_book_ids=body.reference_book_ids,
    )

    sim_id = session["id"]
    narrator = NarratorAgent(book_id)

    async def event_generator():
        # First event: session info
        yield {
            "event": "session",
            "data": json.dumps(
                {
                    "type": "session",
                    "simulation_id": sim_id,
                    "mode": body.mode,
                    "setting": body.setting,
                },
                ensure_ascii=False,
            ),
        }

        # Stream narrative events
        try:
            async for event in narrator.start(
                sim_id=sim_id,
                mode=body.mode,
                setting=body.setting,
                character_ids=body.character_ids or ([body.pov_character_id] if body.pov_character_id else []),
                pov_character_id=body.pov_character_id,
                style_name=body.style_name,
                reference_book_ids=body.reference_book_ids,
                timeline_event_id=body.timeline_event_id,
                user_supplement=body.user_supplement,
            ):
                yield {
                    "event": event.get("type", "unknown"),
                    "data": json.dumps(event, ensure_ascii=False),
                }
        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"type": "error", "message": f"推演启动失败: {str(e)[:200]}"}, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


@router.post("/turn")
async def process_turn(book_id: str, body: TurnRequest):
    """处理推演回合 — SSE流式返回叙事、选项和快捷选择."""
    store = SimulationStore(book_id)
    session = store.get_session(body.simulation_id)
    if not session:
        raise HTTPException(status_code=404, detail="推演会话不存在")
    if session.get("book_id") != book_id:
        raise HTTPException(status_code=403, detail="会话不属于此书籍")

    narrator = NarratorAgent(book_id)
    state_agent = StateAgent(book_id)

    async def event_generator():
        try:
            # Collect events to extract narrative for state update
            collected_narrative = ""
            collected_user_action = body.choice_text or ""
            collected_events = []

            async for event in narrator.process_turn(
                sim_id=body.simulation_id,
                choice_text=body.choice_text or "",
                choice_id=body.choice_id,
            ):
                collected_events.append(event)
                if event.get("type") == "narrative_chunk":
                    collected_narrative += event.get("text", "")

                yield {
                    "event": event.get("type", "unknown"),
                    "data": json.dumps(event, ensure_ascii=False),
                }

            # Async state update after turn completes (fire and forget)
            if collected_narrative.strip():
                try:
                    previous_state = store.get_latest_state(body.simulation_id)
                    await state_agent.update_state(
                        sim_id=body.simulation_id,
                        narrative=collected_narrative.strip(),
                        user_action=collected_user_action,
                        previous_state=previous_state,
                        store=store,
                    )
                except Exception as e:
                    # State update failure does not affect main flow
                    import logging

                    logging.getLogger(__name__).warning("StateAgent async update failed: %s", e)

        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"type": "error", "message": f"推演回合失败: {str(e)[:200]}"}, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


# ── Session Management ──


@router.get("/sessions")
async def list_sessions(book_id: str, status: str | None = None):
    """列出所有推演会话."""
    store = SimulationStore(book_id)
    sessions = store.list_sessions(status=status)
    return {"sessions": sessions}


@router.get("/sessions/{sim_id}")
async def get_session(book_id: str, sim_id: str):
    """获取推演会话详情（含回合和选项）."""
    store = SimulationStore(book_id)
    session = store.get_session(sim_id)
    if not session:
        raise HTTPException(status_code=404, detail="推演会话不存在")

    turns = store.get_turns(sim_id)
    state = store.get_latest_state(sim_id)
    hot_choices = store.get_hot_choices(sim_id)
    choices = store.get_latest_choices(sim_id)

    return {
        "session": session,
        "turns": turns,
        "state": state,
        "hot_choices": hot_choices,
        "choices": choices,
    }


@router.delete("/sessions/{sim_id}")
async def delete_session(book_id: str, sim_id: str):
    """删除推演会话及所有相关数据."""
    store = SimulationStore(book_id)
    session = store.get_session(sim_id)
    if not session:
        raise HTTPException(status_code=404, detail="推演会话不存在")
    store.delete_session(sim_id)
    return {"deleted": True, "simulation_id": sim_id}


@router.put("/sessions/{sim_id}")
async def update_session(book_id: str, sim_id: str, status: str | None = None, summary: str | None = None):
    """更新推演会话状态或摘要."""
    store = SimulationStore(book_id)
    kwargs = {}
    if status is not None:
        kwargs["status"] = status
    if summary is not None:
        kwargs["summary"] = summary
    if not kwargs:
        raise HTTPException(status_code=400, detail="需要提供 status 或 summary")
    session = store.update_session(sim_id, **kwargs)
    if not session:
        raise HTTPException(status_code=404, detail="推演会话不存在")
    return {"session": session}


# ── State ──


@router.get("/sessions/{sim_id}/state")
async def get_session_state(book_id: str, sim_id: str):
    """获取推演会话的当前结构化状态."""
    store = SimulationStore(book_id)
    state = store.get_latest_state(sim_id)
    return {"state": state}


# ── Branch Management ──


@router.post("/sessions/{sim_id}/branch")
async def create_branch(book_id: str, sim_id: str, body: CreateBranchRequest):
    """创建推演分支."""
    store = SimulationStore(book_id)
    result = store.create_branch(sim_id, body.parent_event_id, title=body.title)
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/sessions/{sim_id}/switch-branch")
async def switch_branch(book_id: str, sim_id: str, body: SwitchBranchRequest):
    """切换推演当前分支."""
    store = SimulationStore(book_id)
    result = store.switch_branch(sim_id, body.branch_id)
    if not result:
        raise HTTPException(status_code=404, detail="分支不存在")
    return {"session": result}


@router.get("/sessions/{sim_id}/branches")
async def list_branches(book_id: str, sim_id: str):
    """列出推演会话的所有分支."""
    store = SimulationStore(book_id)
    branches = store.list_branches(sim_id)
    return {"branches": branches}


# ── Hot Choices ──


@router.get("/sessions/{sim_id}/hot-choices")
async def get_hot_choices(book_id: str, sim_id: str, parent_id: str | None = None):
    """获取推演会话的最新快捷选择."""
    store = SimulationStore(book_id)
    choices = store.get_hot_choices(sim_id, parent_id=parent_id)
    return {"choices": choices}


# ── Promote ──


@router.post("/sessions/{sim_id}/promote")
async def promote_event(book_id: str, sim_id: str, body: PromoteRequest):
    """将推演事件提拔为正史时间线."""
    store = SimulationStore(book_id)
    result = store.promote_to_timeline(body.event_id, body.timeline_data)
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    return result


# ── Characters ──


@router.get("/sessions/{sim_id}/characters")
async def get_session_characters(book_id: str, sim_id: str):
    """返回参与推演的角色画像信息."""
    from core.simulation import CharacterAgent

    store = SimulationStore(book_id)
    session = store.get_session(sim_id)
    if not session:
        raise HTTPException(status_code=404, detail="推演会话不存在")

    char_agent = CharacterAgent(book_id)
    involved_ids = session.get("involved_character_ids", [])
    if session.get("pov_character_id") and session["pov_character_id"] not in involved_ids:
        involved_ids.insert(0, session["pov_character_id"])

    profiles = []
    for cid in involved_ids:
        profile = char_agent.build_profile(cid)
        if profile:
            profiles.append(profile.to_dict())

    return {"characters": profiles}


@router.get("/characters")
async def list_book_characters(book_id: str):
    """列出书籍的所有角色（供前端角色选择器使用）."""
    from core.graph_store import GraphStore

    graph = GraphStore(project_id=book_id)
    entities = graph.list_entities(entity_type="character")
    return {
        "characters": [
            {
                "id": e.id,
                "name": e.name,
                "description": (e.data or {}).get("description", "")[:200],
                "aliases": e.aliases,
            }
            for e in entities
        ]
    }
