"""Knowledge Scope — Master Agent defines what Writing Agent can see."""

from dataclasses import dataclass, field
from enum import StrEnum


class ExposureLevel(StrEnum):
    FULL = "full"         # 完整角色卡/设定条目
    SUMMARY = "summary"   # 简要概述（3-5个关键字段）
    NAME_ONLY = "name_only"  # 仅名字，无细节
    HIDDEN = "hidden"     # 不可见


@dataclass
class EntityExposure:
    entity_name: str
    level: ExposureLevel = ExposureLevel.FULL
    reason: str = ""  # 为什么包含/排除这个实体

    def to_dict(self) -> dict:
        return {"name": self.entity_name, "level": self.level.value, "reason": self.reason}

    @classmethod
    def from_dict(cls, d: dict) -> "EntityExposure":
        level = d.get("level", "full")
        try:
            level = ExposureLevel(level)
        except ValueError:
            level = ExposureLevel.FULL
        return cls(entity_name=d["name"], level=level, reason=d.get("reason", ""))


@dataclass
class KnowledgeRequest:
    id: str
    entity_name: str  # 请求哪个实体
    reason: str       # 为什么需要
    status: str = "pending"  # pending | approved | denied
    approved_level: ExposureLevel = ExposureLevel.SUMMARY

    def to_dict(self) -> dict:
        return dict(self.__dict__.items())


@dataclass
class WritingKnowledgeScope:
    """Master Agent 为写作 Agent 划定的可见知识范围"""
    book_id: str = ""
    chapter_ref: str = ""

    # ── 实体白名单（按类型分组，带暴露级别）──
    characters: list[EntityExposure] = field(default_factory=list)
    locations: list[EntityExposure] = field(default_factory=list)
    concepts: list[EntityExposure] = field(default_factory=list)
    items: list[EntityExposure] = field(default_factory=list)

    # ── 结构约束（必传）──
    chapter_outline: str = ""
    prev_chapter_summary: str = ""

    # ── 写作指示 ──
    style_requirements: str = ""
    target_word_count: int = 0
    additional_instructions: str = ""

    # ── 写作禁令 ──
    forbidden_characters: list[str] = field(default_factory=list)
    forbidden_revelations: list[str] = field(default_factory=list)
    writing_rules: str = ""

    # ── 知识请求队列（子Agent发起，Master审核）──
    pending_requests: list[KnowledgeRequest] = field(default_factory=list)

    def _exposure_map(self, items: list[EntityExposure]) -> dict[str, EntityExposure]:
        return {e.entity_name: e for e in items}

    def add_character(self, name: str, level: ExposureLevel = ExposureLevel.FULL, reason: str = ""):
        existing = self._exposure_map(self.characters)
        if name not in existing:
            self.characters.append(EntityExposure(name, level, reason))
        elif existing[name].level != level:
            existing[name].level = level

    def add_location(self, name: str, level: ExposureLevel = ExposureLevel.FULL, reason: str = ""):
        existing = self._exposure_map(self.locations)
        if name not in existing:
            self.locations.append(EntityExposure(name, level, reason))
        elif existing[name].level != level:
            existing[name].level = level

    def add_concept(self, name: str, level: ExposureLevel = ExposureLevel.FULL, reason: str = ""):
        existing = self._exposure_map(self.concepts)
        if name not in existing:
            self.concepts.append(EntityExposure(name, level, reason))
        elif existing[name].level != level:
            existing[name].level = level

    def add_item(self, name: str, level: ExposureLevel = ExposureLevel.FULL, reason: str = ""):
        existing = self._exposure_map(self.items)
        if name not in existing:
            self.items.append(EntityExposure(name, level, reason))
        elif existing[name].level != level:
            existing[name].level = level

    def remove_entity(self, name: str):
        for lst in [self.characters, self.locations, self.concepts, self.items]:
            for i, e in enumerate(lst):
                if e.entity_name == name:
                    lst.pop(i)
                    return

    def get_all_entity_names(self) -> set[str]:
        names = set()
        for lst in [self.characters, self.locations, self.concepts, self.items]:
            for e in lst:
                names.add(e.entity_name)
        return names

    def get_entities_by_level(self, level: ExposureLevel) -> list[tuple[str, str]]:
        """Return [(name, type), ...] for entities at given exposure level."""
        result = []
        for lst, label in [(self.characters, "character"), (self.locations, "location"),
                           (self.concepts, "concept"), (self.items, "item")]:
            for e in lst:
                if e.level == level:
                    result.append((e.entity_name, label))
        return result

    def add_request(self, entity_name: str, reason: str) -> str:
        import uuid
        rid = f"req_{uuid.uuid4().hex[:6]}"
        req = KnowledgeRequest(id=rid, entity_name=entity_name, reason=reason)
        self.pending_requests.append(req)
        return rid

    def approve_request(self, request_id: str, level: ExposureLevel = ExposureLevel.SUMMARY) -> str | None:
        for r in self.pending_requests:
            if r.id == request_id:
                r.status = "approved"
                r.approved_level = level
                return r.entity_name
        return None

    def deny_request(self, request_id: str) -> str | None:
        for r in self.pending_requests:
            if r.id == request_id:
                r.status = "denied"
                return r.entity_name
        return None

    def to_dict(self) -> dict:
        return {
            "book_id": self.book_id,
            "chapter_ref": self.chapter_ref,
            "characters": [e.to_dict() for e in self.characters],
            "locations": [e.to_dict() for e in self.locations],
            "concepts": [e.to_dict() for e in self.concepts],
            "items": [e.to_dict() for e in self.items],
            "chapter_outline": self.chapter_outline[:500],
            "prev_chapter_summary": self.prev_chapter_summary[:300],
            "style_requirements": self.style_requirements,
            "target_word_count": self.target_word_count,
            "additional_instructions": self.additional_instructions,
            "forbidden_characters": self.forbidden_characters,
            "forbidden_revelations": self.forbidden_revelations,
            "writing_rules": self.writing_rules,
            "pending_requests": [r.to_dict() for r in self.pending_requests],
        }

    def to_summary(self) -> str:
        """Human-readable summary for Master Agent display."""
        lines = [f"写作知识范围 — {self.chapter_ref or '未指定章节'}", ""]
        for label, lst in [("角色", self.characters), ("地点", self.locations),
                           ("世界观", self.concepts), ("物品/法宝", self.items)]:
            if lst:
                lines.append(f"## {label} ({len(lst)}个)")
                for e in lst:
                    level_icon = {"full": "●", "summary": "○", "name_only": "·"}.get(e.level.value, "?")
                    lines.append(f"  {level_icon} {e.entity_name} [{e.level.value}] {e.reason or ''}")
        if self.forbidden_characters:
            lines.append(f"\n## 禁止出场 ({len(self.forbidden_characters)}个)")
            for c in self.forbidden_characters:
                lines.append(f"  ✕ {c}")
        if self.forbidden_revelations:
            lines.append(f"\n## 禁止揭露 ({len(self.forbidden_revelations)}个)")
            for r in self.forbidden_revelations:
                lines.append(f"  ✕ {r}")
        if self.writing_rules:
            lines.append(f"\n## 写作规则\n{self.writing_rules}")
        if self.target_word_count:
            lines.append(f"\n目标字数: {self.target_word_count}")
        return "\n".join(lines)

    @classmethod
    def from_dict(cls, d: dict) -> "WritingKnowledgeScope":
        return cls(
            book_id=d.get("book_id", ""),
            chapter_ref=d.get("chapter_ref", ""),
            characters=[EntityExposure.from_dict(e) for e in d.get("characters", [])],
            locations=[EntityExposure.from_dict(e) for e in d.get("locations", [])],
            concepts=[EntityExposure.from_dict(e) for e in d.get("concepts", [])],
            items=[EntityExposure.from_dict(e) for e in d.get("items", [])],
            chapter_outline=d.get("chapter_outline", ""),
            prev_chapter_summary=d.get("prev_chapter_summary", ""),
            style_requirements=d.get("style_requirements", ""),
            target_word_count=d.get("target_word_count", 0),
            additional_instructions=d.get("additional_instructions", ""),
            forbidden_characters=d.get("forbidden_characters", []),
            forbidden_revelations=d.get("forbidden_revelations", []),
            writing_rules=d.get("writing_rules", ""),
            pending_requests=[KnowledgeRequest(**r) for r in d.get("pending_requests", [])],
        )


class ScopeManager:
    """管理当前活跃的写作知识范围"""
    def __init__(self):
        self._scopes: dict[str, WritingKnowledgeScope] = {}

    def set_scope(self, book_id: str, scope: WritingKnowledgeScope):
        scope.book_id = book_id
        self._scopes[book_id] = scope

    def get_scope(self, book_id: str) -> WritingKnowledgeScope | None:
        return self._scopes.get(book_id)

    def clear_scope(self, book_id: str):
        self._scopes.pop(book_id, None)

    def auto_expand(self, book_id: str, entity_name: str, entity_type: str = "character",
                    level: ExposureLevel = ExposureLevel.FULL, reason: str = "用户提及"):
        """静默扩展作用域——用户提到某个不在范围的角色时自动加入"""
        scope = self._scopes.get(book_id)
        if not scope:
            return
        add_methods = {
            "character": scope.add_character,
            "location": scope.add_location,
            "concept": scope.add_concept,
            "item": scope.add_item,
        }
        method = add_methods.get(entity_type)
        if method:
            method(entity_name, level, reason)


scope_manager = ScopeManager()
