from fastapi import APIRouter

from core.plugin_loader import plugin_manager
from core.skills import manager as skill_manager

router = APIRouter(tags=["skills"])


@router.get("/skills")
def list_skills():
    return {
        "skills": skill_manager.list_skills(),
        "plugins": plugin_manager.list_plugins(),
    }


@router.get("/skills/{skill_name}")
def get_skill(skill_name: str):
    skill = skill_manager.get(skill_name)
    if not skill:
        return {"error": f"skill not found: {skill_name}"}
    return skill.to_dict()
