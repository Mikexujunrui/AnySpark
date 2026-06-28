"""Interactive Story API Routes — branch-based interactive storytelling."""


from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.interactive_agent import InteractiveAgent
from core.interactive_store import InteractiveStore

router = APIRouter(prefix="/books/{book_id}/interactive", tags=["interactive"])

# ── Request/Response Models ──

class StartRequest(BaseModel):
    chapter_id: str | None = None
    setting: str | None = None
    character_ids: list[str] = []
    style_name: str | None = None
    reference_book_ids: list[str] = []

class TurnRequest(BaseModel):
    branch_id: str
    choice_id: str | None = None
    free_input: str | None = None

class BranchCreate(BaseModel):
    name: str
    parent_branch_id: str
    source_choice_id: str | None = None
    description: str = ""


# ── Routes ──

@router.post("/start")
async def start_interactive(book_id: str, body: StartRequest):
    """Start an interactive storytelling session."""
    store = InteractiveStore(book_id)
    store.init_schema()

    agent = InteractiveAgent(book_id)

    # Create root branch
    branch = store.create_branch(
        name="主线",
        description=f"剧情推演 — 从{'章节 ' + body.chapter_id if body.chapter_id else '新场景'} 开始",
    )
    if not branch:
        raise HTTPException(status_code=500, detail="创建分支失败")

    # Generate initial narrative
    result = await agent.start(
        branch_id=branch["id"],
        chapter_id=body.chapter_id,
        setting=body.setting,
        character_ids=body.character_ids,
        style_name=body.style_name,
        reference_book_ids=body.reference_book_ids,
    )

    # Store initial event
    if result.get("narrative"):
        event = store.add_event(
            branch_id=branch["id"],
            content=result["narrative"],
            event_type="narrative",
            turn_number=0,
        )

        # Store choices
        choices = []
        for choice_text in result.get("choices", []):
            choice = store.add_choice(
                event_id=event["id"],
                text=choice_text.get("text", choice_text) if isinstance(choice_text, dict) else choice_text,
                description=choice_text.get("description", "") if isinstance(choice_text, dict) else "",
            )
            if choice:
                choices.append(choice)

        return {
            "branch": branch,
            "event": event,
            "choices": choices,
            "narrative": result["narrative"],
        }

    return {"branch": branch, "error": "未能生成初始叙事"}


@router.post("/turn")
async def process_turn(book_id: str, body: TurnRequest):
    """Process a user's choice and generate the next narrative segment."""
    store = InteractiveStore(book_id)
    agent = InteractiveAgent(book_id)

    branch = store.get_branch(body.branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="分支不存在")

    # Get previous events for context
    events = store.get_events(body.branch_id)
    turn_number = len(events)

    # Get choice text if choice_id provided
    choice_text = ""
    if body.choice_id:
        latest_event = store.get_latest_event(body.branch_id)
        if latest_event:
            choices = store.get_choices(latest_event["id"])
            for c in choices:
                if c["id"] == body.choice_id:
                    choice_text = c["text"]
                    break

    # Generate next narrative
    result = await agent.continue_story(
        branch_id=body.branch_id,
        branch_name=branch["name"],
        user_choice=choice_text or body.free_input or "",
        history=events,
        turn_number=turn_number,
    )

    # Store new event
    if result.get("narrative"):
        event = store.add_event(
            branch_id=body.branch_id,
            content=result["narrative"],
            event_type="narrative",
            turn_number=turn_number,
        )

        # Check for foreshadow effects
        affected_foreshadows = result.get("foreshadow_updates", [])
        for f_update in affected_foreshadows:
            store.link_event_to_foreshadow(
                event_id=event["id"],
                fore_id=f_update.get("fore_id"),
                action=f_update.get("action", "advances"),
            )

        # Store choices
        choices = []
        for choice_text_item in result.get("choices", []):
            choice = store.add_choice(
                event_id=event["id"],
                text=choice_text_item.get("text", choice_text_item) if isinstance(choice_text_item, dict) else choice_text_item,
                description=choice_text_item.get("description", "") if isinstance(choice_text_item, dict) else "",
            )
            if choice:
                choices.append(choice)

        return {
            "event": event,
            "choices": choices,
            "narrative": result["narrative"],
            "foreshadow_updates": affected_foreshadows,
        }

    return {"error": "未能生成叙事"}


@router.post("/branch")
async def create_branch(book_id: str, body: BranchCreate):
    """Create a new branch from an existing one."""
    store = InteractiveStore(book_id)
    branch = store.create_branch(
        name=body.name,
        parent_branch_id=body.parent_branch_id,
        source_choice_id=body.source_choice_id,
        description=body.description,
    )
    if not branch:
        raise HTTPException(status_code=500, detail="创建分支失败")
    return {"branch": branch}


@router.get("/branches")
async def list_branches(book_id: str):
    """List all interactive story branches."""
    store = InteractiveStore(book_id)
    return {"branches": store.list_branches()}


@router.get("/branches/tree")
async def get_branch_tree(book_id: str):
    """Get the full branch tree for visualization."""
    store = InteractiveStore(book_id)
    return store.get_branch_tree()


@router.get("/branches/{branch_id}")
async def get_branch(book_id: str, branch_id: str):
    """Get a single branch with its events and choices."""
    store = InteractiveStore(book_id)
    branch = store.get_branch(branch_id)
    if not branch:
        raise HTTPException(status_code=404, detail="分支不存在")

    events = store.get_events(branch_id)
    # Load choices for each event
    for event in events:
        event["choices"] = store.get_choices(event["id"])

    foreshadows = store.get_foreshadows_for_branch(branch_id)

    return {
        "branch": branch,
        "events": events,
        "foreshadows": foreshadows,
    }


@router.get("/foreshadows")
async def compare_foreshadows(book_id: str):
    """Compare foreshadow status across all branches."""
    store = InteractiveStore(book_id)
    return {"foreshadows": store.compare_foreshadows_across_branches()}


@router.put("/branches/{branch_id}")
async def update_branch(book_id: str, branch_id: str, name: str = None, description: str = None, status: str = None):
    """Update branch metadata."""
    store = InteractiveStore(book_id)
    kwargs = {}
    if name is not None:
        kwargs["name"] = name
    if description is not None:
        kwargs["description"] = description
    if status is not None:
        kwargs["status"] = status
    branch = store.update_branch(branch_id, **kwargs)
    if not branch:
        raise HTTPException(status_code=404, detail="分支不存在")
    return {"branch": branch}


@router.delete("/branches/{branch_id}")
async def delete_branch(book_id: str, branch_id: str):
    """Delete a branch and all its events."""
    store = InteractiveStore(book_id)
    store.delete_branch(branch_id)
    return {"deleted": True}
