"""Skill System — load, register, and execute skills as composite tool workflows.

Skill files are YAML/JSON with dual sources:
  skills/       — system default skills (open-source, committed to git)
  data/skills/  — user custom skills (private, gitignored)

They define: name, description, triggers, and a workflow of tool calls.
The agent can suggest skills based on content classification.
"""

import json
import sys
from pathlib import Path

import yaml

from .config import DATA_DIR, PROJECT_ROOT

# ── System resource paths ──
# In EXE: resources live under sys._MEIPASS
# In dev:  resources live under PROJECT_ROOT
if getattr(sys, "frozen", False):
    SYSTEM_SKILLS_DIR = Path(getattr(sys, "_MEIPASS", "")) / "skills"
else:
    SYSTEM_SKILLS_DIR = PROJECT_ROOT / "skills"
USER_SKILLS_DIR = DATA_DIR / "skills"


class Skill:
    def __init__(self, name: str, definition: dict, source: str = "system"):
        self.name = name
        self.description = definition.get("description", "")
        self.triggers = definition.get("triggers", [])
        self.steps = definition.get("steps", [])
        self.config = definition.get("config", {})
        self.instructions = definition.get("instructions", "")
        self.guardrails = definition.get("guardrails", [])
        self.outputs = definition.get("outputs", [])
        self.source = source

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "triggers": self.triggers,
            "steps": self.steps,
            "instructions": self.instructions,
            "guardrails": self.guardrails,
            "outputs": self.outputs,
            "source": self.source,
        }

    def to_definition(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "triggers": self.triggers,
            "steps": self.steps,
            "instructions": self.instructions,
            "guardrails": self.guardrails,
            "outputs": self.outputs,
            "config": self.config,
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
            if path.suffix in (".yaml", ".yml"):
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
            results.append(
                {
                    "step": step.get("label", step.get("tool", "")),
                    "tool": step.get("tool", ""),
                    "params": step.get("params", {}),
                    "status": "pending",
                }
            )
        return results

    def render_instruction(self, skill_name: str, user_input: str = "") -> str:
        """Render a skill as an executable Agent instruction.

        Skill steps often need chapter IDs or user choices that cannot be
        known when the YAML is authored.  Rendering keeps the workflow
        deterministic while allowing the Agent to fill only those arguments.
        """
        skill = self._skills.get(skill_name)
        if not skill:
            raise ValueError(f"技能不存在: {skill_name}")
        step_lines = []
        for index, step in enumerate(skill.steps, 1):
            tool = step.get("tool", "")
            label = step.get("label", tool)
            params = step.get("params", {})
            param_text = json.dumps(params, ensure_ascii=False) if params else "{}"
            step_lines.append(f"{index}. {label}：调用 `{tool}`，预设参数 {param_text}")
        guardrails = "\n".join(f"- {rule}" for rule in skill.guardrails) or "- 只执行本技能列出的范围"
        outputs = "\n".join(f"- {item}" for item in skill.outputs) or "- 报告实际执行结果"
        return f"""[已启用技能: {skill.name}]
说明：{skill.description}

用户本次补充要求：
{user_input.strip() or "无；使用当前项目、大纲和最近章节确定目标。"}

技能专用指令：
{skill.instructions or "严格按以下步骤调用工具执行，不要只描述计划。"}

固定流程：
{chr(10).join(step_lines)}

不可违反：
{guardrails}

完成时必须输出：
{outputs}

这是一次实际执行请求。需要关键选择时用 ask_user；某一步失败时停止后续写入并明确报告，
不要换另一个全章生成工具从头再写。"""


manager = SkillManager()
