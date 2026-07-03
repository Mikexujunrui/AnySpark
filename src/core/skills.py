"""Skill System — load, register, and execute skills as composite tool workflows.

Skill files are YAML/JSON with dual sources:
  skills/       — system default skills (open-source, committed to git)
  data/skills/  — user custom skills (private, gitignored)

They define: name, description, triggers, and a workflow of tool calls.
The agent can suggest skills based on content classification.
"""

import json
from pathlib import Path

import yaml

SYSTEM_SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"
USER_SKILLS_DIR = Path(__file__).parent.parent.parent / "data" / "skills"


class Skill:
    def __init__(self, name: str, definition: dict, source: str = "system"):
        self.name = name
        self.description = definition.get("description", "")
        self.triggers = definition.get("triggers", [])
        self.steps = definition.get("steps", [])
        self.config = definition.get("config", {})
        self.source = source

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "triggers": self.triggers,
            "steps": self.steps,
            "source": self.source,
        }

    def to_definition(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "triggers": self.triggers,
            "steps": self.steps,
        }

    def matches(self, content_type: str) -> bool:
        if not self.triggers:
            return False
        return content_type in self.triggers


class SkillManager:
    def __init__(self):
        self._skills: dict[str, Skill] = {}
        self._load_all()

    def _load_all(self):
        self._skills.clear()
        SYSTEM_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        USER_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

        for source_dir, source in [(USER_SKILLS_DIR, "user"), (SYSTEM_SKILLS_DIR, "system")]:
            for f in source_dir.glob("*.yaml"):
                self._load(f, source)
            for f in source_dir.glob("*.yml"):
                self._load(f, source)
            for f in source_dir.glob("*.json"):
                self._load(f, source)

    def _load(self, path: Path, source: str):
        try:
            text = path.read_text(encoding="utf-8")
            if path.suffix in ('.yaml', '.yml'):
                defs = yaml.safe_load(text)
            else:
                defs = json.loads(text)
            if isinstance(defs, dict):
                defs = [defs]
            if not isinstance(defs, list):
                return
            for d in defs:
                name = d.get("name", path.stem)
                self._skills[name] = Skill(name, d, source=source)
        except (ValueError, KeyError, OSError) as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to load skills from {path}: {e}")

    def _save_user_skill_file(self):
        user_skills = [s for s in self._skills.values() if s.source == "user"]
        fpath = USER_SKILLS_DIR / "custom.yaml"
        if not user_skills:
            if fpath.exists():
                fpath.unlink()
            return
        data = [s.to_definition() for s in user_skills]
        fpath.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def reload(self):
        self._load_all()

    def list_skills(self, source: str | None = None) -> list[dict]:
        result = [s.to_dict() for s in self._skills.values()]
        result.sort(key=lambda x: (0 if x["source"] == "system" else 1, x["name"]))
        if source:
            result = [s for s in result if s["source"] == source]
        return result

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def add_user_skill(self, name: str, definition: dict) -> dict:
        if self.get(name):
            raise ValueError(f"技能 '{name}' 已存在")
        definition["name"] = name
        skill = Skill(name, definition, source="user")
        self._skills[name] = skill
        self._save_user_skill_file()
        return skill.to_dict()

    def update_user_skill(self, name: str, definition: dict) -> dict:
        existing = self._skills.get(name)
        if not existing:
            raise ValueError(f"技能 '{name}' 不存在")
        if existing.source != "user":
            raise ValueError(f"不能修改系统默认技能 '{name}'")
        definition["name"] = name
        skill = Skill(name, definition, source="user")
        self._skills[name] = skill
        self._save_user_skill_file()
        return skill.to_dict()

    def delete_user_skill(self, name: str) -> bool:
        existing = self._skills.get(name)
        if not existing:
            return False
        if existing.source != "user":
            raise ValueError(f"不能删除系统默认技能 '{name}'")
        del self._skills[name]
        self._save_user_skill_file()
        return True

    def find_matching(self, content_type: str) -> list[Skill]:
        return [s for s in self._skills.values() if s.matches(content_type)]

    def execute(self, skill_name: str, context: dict) -> list[dict]:
        skill = self._skills.get(skill_name)
        if not skill:
            return [{"error": f"skill not found: {skill_name}"}]
        results = []
        for step in skill.steps:
            results.append({
                "step": step.get("label", step.get("tool", "")),
                "tool": step.get("tool", ""),
                "params": step.get("params", {}),
                "status": "pending",
            })
        return results


manager = SkillManager()
