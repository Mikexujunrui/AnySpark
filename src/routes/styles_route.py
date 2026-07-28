"""Style REST API — list, get, and manage writing styles."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.skills import manager as skill_manager
from core.styles import NarrativeStrategy
from core.styles import manager as style_manager

router = APIRouter(tags=["styles"])


class NarrativeStrategyUpdate(BaseModel):
    pov: str = ""  # first_person | third_limited | third_omniscient
    pacing_curve: str = ""  # fast | balanced | slow_burn
    reveal_density: str = ""  # sparse | moderate | dense
    foreshadow_budget: int = 0
    chapter_arc: str = ""  # rising_action | climax | resolution | standalone
    tone_guidance: str = ""


def _style_to_response(s: dict) -> dict:
    return {
        "name": s["name"],
        "description": s["description"],
        "priority": s["priority"],
        "applies_to": s["applies_to"],
        "slots": s["slots"],
        "source": s["source"],
    }


# ── Styles ──


@router.get("/styles")
def list_styles(source: str | None = None):
    styles = style_manager.list_styles(source=source)
    return {"styles": [_style_to_response(s) for s in styles]}


@router.get("/styles/{name}")
def get_style(name: str):
    style = style_manager.get(name)
    if not style:
        raise HTTPException(404, f"风格不存在: {name}")
    return _style_to_response(style.to_dict())


@router.post("/styles/custom")
def create_custom_style(data: dict):
    name = data.get("name", "")
    if not name:
        raise HTTPException(400, "需要 name 字段")
    try:
        result = style_manager.add_user_style(name, data)
        return result
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.put("/styles/custom/{name}")
def update_custom_style(name: str, data: dict):
    try:
        result = style_manager.update_user_style(name, data)
        return result
    except ValueError as e:
        msg = str(e)
        code = 404 if "不存在" in msg else 403 if "系统默认" in msg else 400
        raise HTTPException(code, msg)


@router.put("/books/{book_id}/style/narrative")
def set_narrative_strategy(book_id: str, data: NarrativeStrategyUpdate):
    """Set the narrative strategy for a book's active style."""
    try:
        strategy = NarrativeStrategy(
            pov=data.pov,
            pacing_curve=data.pacing_curve,
            reveal_density=data.reveal_density,
            foreshadow_budget=data.foreshadow_budget,
            chapter_arc=data.chapter_arc,
            tone_guidance=data.tone_guidance,
        )
        style_mgr = style_manager
        active_name = style_mgr.get_active_style(book_id)
        style = style_mgr.get_style(active_name)
        style.narrative_strategy = strategy
        return {
            "ok": True,
            "narrative_strategy": {
                "pov": strategy.pov,
                "pacing_curve": strategy.pacing_curve,
                "reveal_density": strategy.reveal_density,
                "foreshadow_budget": strategy.foreshadow_budget,
                "chapter_arc": strategy.chapter_arc,
                "tone_guidance": strategy.tone_guidance,
            },
        }
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/books/{book_id}/style/narrative")
def get_narrative_strategy(book_id: str):
    """Get the narrative strategy for a book's active style."""
    style_mgr = style_manager
    active_name = style_mgr.get_active_style(book_id)
    style = style_mgr.get_style(active_name)
    ns = style.narrative_strategy
    if ns:
        return {
            "pov": ns.pov,
            "pacing_curve": ns.pacing_curve,
            "reveal_density": ns.reveal_density,
            "foreshadow_budget": ns.foreshadow_budget,
            "chapter_arc": ns.chapter_arc,
            "tone_guidance": ns.tone_guidance,
        }
    return {
        "pov": "",
        "pacing_curve": "",
        "reveal_density": "",
        "foreshadow_budget": 3,
        "chapter_arc": "",
        "tone_guidance": "",
    }


@router.delete("/styles/custom/{name}")
def delete_custom_style(name: str):
    try:
        style_manager.delete_user_style(name)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(403, str(e))


# ── Skills (workflows) ──


def _skill_to_response(s: dict) -> dict:
    return {
        "name": s["name"],
        "description": s["description"],
        "triggers": s["triggers"],
        "steps": s["steps"],
        "source": s["source"],
    }


@router.get("/skills")
def list_skills(source: str | None = None):
    skills = skill_manager.list_skills(source=source)
    return {"skills": [_skill_to_response(s) for s in skills]}


@router.get("/skills/{name}")
def get_skill(name: str):
    skill = skill_manager.get(name)
    if not skill:
        raise HTTPException(404, f"技能不存在: {name}")
    return _skill_to_response(skill.to_dict())


@router.post("/skills/custom")
def create_custom_skill(data: dict):
    name = data.get("name", "")
    if not name:
        raise HTTPException(400, "需要 name 字段")
    try:
        result = skill_manager.add_user_skill(name, data)
        return result
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.put("/skills/custom/{name}")
def update_custom_skill(name: str, data: dict):
    try:
        result = skill_manager.update_user_skill(name, data)
        return result
    except ValueError as e:
        msg = str(e)
        code = 404 if "不存在" in msg else 403 if "系统默认" in msg else 400
        raise HTTPException(code, msg)


@router.delete("/skills/custom/{name}")
def delete_custom_skill(name: str):
    try:
        skill_manager.delete_user_skill(name)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(403, str(e))


# ── Book active style ──


@router.get("/books/{book_id}/style")
def get_book_style(book_id: str):
    active = style_manager.get_active_style(book_id)
    if not active:
        return {"active": None}
    style = style_manager.get(active)
    if not style:
        return {"active": active, "error": "style_deleted"}
    return {"active": active, "style": _style_to_response(style.to_dict())}


@router.put("/books/{book_id}/style")
def set_book_style(book_id: str, data: dict):
    name = data.get("name", "")
    if not name:
        style_manager.set_active_style(book_id, "")
        return {"ok": True, "active": None}
    style = style_manager.get(name)
    if not style:
        raise HTTPException(404, f"风格不存在: {name}")
    style_manager.set_active_style(book_id, name)
    return {"ok": True, "active": name}
