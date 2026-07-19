"""Style Manager — load, register, and apply writing style profiles.

Style files are YAML with dual sources:
  styles/       — system default styles (open-source, committed to git)
  data/styles/  — user custom styles (private, gitignored)

Each style defines: name, description, applicable scenes, prompt slots,
and optional narrative_strategy (POV, pacing, reveal density, foreshadow budget).
The agent can list, set, suggest, and manage styles.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class NarrativeStrategy:
    """Narrator settings for the推演 system — controls HOW the simulation narrative is told.

    These parameters are used exclusively by the推演 NarratorAgent.
    Regular chapter writing uses文风 (style slots) only, not these settings.
    """
    pov: str = "third_person_limited"
    pacing_curve: str = "three_act"
    reveal_density: str = "moderate"
    foreshadow_budget: int = 3
    chapter_arc: str = "setup_development_climax_resolution"
    tone_guidance: str = ""

    @classmethod
    def from_dict(cls, d: dict | None) -> "NarrativeStrategy":
        if not d:
            return cls()
        return cls(
            pov=d.get("pov", "third_person_limited"),
            pacing_curve=d.get("pacing_curve", "three_act"),
            reveal_density=d.get("reveal_density", "moderate"),
            foreshadow_budget=d.get("foreshadow_budget", 3),
            chapter_arc=d.get("chapter_arc", "setup_development_climax_resolution"),
            tone_guidance=d.get("tone_guidance", ""),
        )

    def to_dict(self) -> dict:
        return {
            "pov": self.pov,
            "pacing_curve": self.pacing_curve,
            "reveal_density": self.reveal_density,
            "foreshadow_budget": self.foreshadow_budget,
            "chapter_arc": self.chapter_arc,
            "tone_guidance": self.tone_guidance,
        }

    def to_prompt_fragment(self) -> str:
        """Generate a prompt fragment for injecting into agent context."""
        return f"""## 叙述者设定
POV视角: {self.pov}
节奏曲线: {self.pacing_curve}
信息揭示密度: {self.reveal_density}
伏笔预算: 每章最多 {self.foreshadow_budget} 个新伏笔
章节弧线: {self.chapter_arc}""" + (f"\n{self.tone_guidance}" if self.tone_guidance else "")

SYSTEM_STYLES_DIR = Path(__file__).parent.parent.parent / "styles"
USER_STYLES_DIR = Path(__file__).parent.parent.parent / "data" / "styles"
ACTIVE_STYLES_FILE = Path(__file__).parent.parent.parent / "data" / "active_styles.json"


class Style:
    def __init__(self, name: str, definition: dict, source: str = "system"):
        self.name = name
        self.description = definition.get("description", "")
        self.priority = definition.get("priority", "suggest")
        self.applies_to = definition.get("applies_to", [])
        self.slots = definition.get("slots", [])
        self.source = source
        self.narrative_strategy = NarrativeStrategy.from_dict(
            definition.get("narrative_strategy")
        )

    def prompt_for_targets(self, *targets: str) -> str:
        sections = []
        for slot in self.slots:
            if slot.get("target") in targets and slot.get("enabled", True):
                sections.append(slot["content"])
        return "\n\n".join(sections)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "priority": self.priority,
            "applies_to": self.applies_to,
            "slots": self.slots,
            "source": self.source,
            "narrative_strategy": self.narrative_strategy.to_dict(),
        }

    def to_definition(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "priority": self.priority,
            "applies_to": self.applies_to,
            "slots": self.slots,
            "narrative_strategy": self.narrative_strategy.to_dict(),
        }

    def matches_scene(self, scene_or_content: str) -> bool:
        s = scene_or_content.lower()
        return any(tag.lower() in s for tag in self.applies_to)


class StyleManager:
    def __init__(self):
        self._styles: dict[str, Style] = {}
        self._load_all()

    def _load_all(self):
        self._styles.clear()
        SYSTEM_STYLES_DIR.mkdir(parents=True, exist_ok=True)
        USER_STYLES_DIR.mkdir(parents=True, exist_ok=True)

        # System styles override user styles with same name
        for source_dir, source in [(USER_STYLES_DIR, "user"), (SYSTEM_STYLES_DIR, "system")]:
            for f in sorted(source_dir.glob("*.yaml")):
                self._load(f, source)
            for f in sorted(source_dir.glob("*.yml")):
                self._load(f, source)
        for source_dir, source in [(USER_STYLES_DIR, "user"), (SYSTEM_STYLES_DIR, "system")]:
            for f in sorted(source_dir.glob("*.json")):
                self._load(f, source)

    def _load(self, path: Path, source: str):
        try:
            text = path.read_text(encoding="utf-8")
            defs = yaml.safe_load(text)
            if isinstance(defs, dict):
                defs = [defs]
            if not isinstance(defs, list):
                return
            for d in defs:
                name = d.get("name", path.stem)
                self._styles[name] = Style(name, d, source=source)
        except (ValueError, KeyError, OSError) as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to load styles from {path}: {e}")

    def _save_user_style_file(self):
        """Save all user styles to the user styles directory as a single YAML file."""
        user_styles = [s for s in self._styles.values() if s.source == "user"]
        if not user_styles:
            fpath = USER_STYLES_DIR / "custom.yaml"
            if fpath.exists():
                fpath.unlink()
            return
        data = [s.to_definition() for s in user_styles]
        fpath = USER_STYLES_DIR / "custom.yaml"
        fpath.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    def reload(self):
        self._load_all()

    def list_styles(self, source: str | None = None) -> list[dict]:
        result = [s.to_dict() for s in self._styles.values()]
        result.sort(key=lambda x: (0 if x["source"] == "system" else 1, x["name"]))
        if source:
            result = [s for s in result if s["source"] == source]
        return result

    def get(self, name: str) -> Style | None:
        return self._styles.get(name)

    def add_user_style(self, name: str, definition: dict) -> dict:
        if self.get(name):
            raise ValueError(f"风格 '{name}' 已存在")
        definition["name"] = name
        style = Style(name, definition, source="user")
        self._styles[name] = style
        self._save_user_style_file()
        return style.to_dict()

    def update_user_style(self, name: str, definition: dict) -> dict:
        existing = self._styles.get(name)
        if not existing:
            raise ValueError(f"风格 '{name}' 不存在")
        if existing.source != "user":
            raise ValueError(f"不能修改系统默认风格 '{name}'")
        definition["name"] = name
        style = Style(name, definition, source="user")
        self._styles[name] = style
        self._save_user_style_file()
        return style.to_dict()

    def delete_user_style(self, name: str) -> bool:
        existing = self._styles.get(name)
        if not existing:
            return False
        if existing.source != "user":
            raise ValueError(f"不能删除系统默认风格 '{name}'")
        del self._styles[name]
        self._save_user_style_file()
        return True

    def suggest_for_content(self, text: str) -> str | None:
        best = None
        best_score = 0
        for name, style in self._styles.items():
            score = sum(1 for tag in style.applies_to if tag in text)
            if score > best_score:
                best_score = score
                best = name
        return best if best_score > 0 else None

    def suggest_for_chapter(self, chapter_outline: str = "", chapter_content: str = "") -> str | None:
        combined = chapter_outline + chapter_content
        return self.suggest_for_content(combined)

    def build_style_context(self, style_name: str) -> str:
        style = self._styles.get(style_name)
        if not style:
            return ""
        return style.prompt_for_targets("system", "scene")

    def get_narrative_strategy_prompt(self, book_id: str, style_name: str = "") -> str:
        """Get the叙述者设定 prompt fragment for推演 NarratorAgent.

        Used exclusively by the推演 system. Regular chapter writing
        does NOT use these settings — it uses文风 style slots only.
        """
        name = style_name or self.get_active_style(book_id)
        if not name:
            return ""
        style = self._styles.get(name)
        if not style or not style.narrative_strategy:
            return ""
        return style.narrative_strategy.to_prompt_fragment()

    def get_active_style(self, book_id: str) -> str:
        try:
            if ACTIVE_STYLES_FILE.exists():
                data = json.loads(ACTIVE_STYLES_FILE.read_text(encoding="utf-8"))
                return data.get(book_id, "")
        except (json.JSONDecodeError, OSError):
            pass
        return ""

    def set_active_style(self, book_id: str, style_name: str):
        data = {}
        try:
            if ACTIVE_STYLES_FILE.exists():
                data = json.loads(ACTIVE_STYLES_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
        if style_name:
            data[book_id] = style_name
        else:
            data.pop(book_id, None)
        ACTIVE_STYLES_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


manager = StyleManager()
