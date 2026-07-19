from dataclasses import dataclass, field
from enum import StrEnum


class EntityType(str):
    CHARACTER = "character"
    LOCATION = "location"
    ITEM = "item"
    ORGANIZATION = "organization"
    CONCEPT = "concept"
    EVENT = "event"
    SKILL = "skill"
    RACE = "race"

    # Built-in types in display order
    BUILTIN = [CHARACTER, LOCATION, ITEM, SKILL, ORGANIZATION, RACE, CONCEPT, EVENT]


class RelationType(StrEnum):
    KNOWS = "knows"
    BELONGS_TO = "belongs_to"
    LOCATED_AT = "located_at"
    OWNS = "owns"
    ANTAGONIST = "antagonist"
    ALLY = "ally"
    FAMILY = "family"
    ROMANTIC = "romantic"
    MASTER_OF = "master_of"
    MENTOR_OF = "mentor_of"
    KILLED = "killed"
    SAVED = "saved"
    LOVES = "loves"
    CAUSES = "causes"
    BEFORE = "before"
    AFTER = "after"
    FORESHADOWS = "foreshadows"
    RESOLVES = "resolves"
    PARTICIPATES_IN = "participates_in"
    # ── Spatial relationship types ──
    LOCATED_IN = "located_in"       # Location → Location (containment)
    ADJACENT_TO = "adjacent_to"     # Location → Location (neighboring)
    OCCURRED_AT = "occurred_at"     # Timeline → Location (event at place)
    # ── Paired reverse relationship types ──
    PARENT_OF = "parent_of"
    CHILD_OF = "child_of"
    APPRENTICE_OF = "apprentice_of"
    STUDENT_OF = "student_of"
    KILLED_BY = "killed_by"
    SAVED_BY = "saved_by"
    LOVED_BY = "loved_by"
    SPOUSE_OF = "spouse_of"
    SIBLING_OF = "sibling_of"
    FRIEND = "friend"


@dataclass
class Entity:
    id: str
    type: str
    name: str
    aliases: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    # ── Tiered priority for context injection (P0 from Wiki-Graph comparison) ──
    # 1 = must-inject, 2 = inject-if-budget, 3 = inject-if-remaining
    priority: int = 0


@dataclass
class Relation:
    id: str
    from_entity: str
    to_entity: str
    type: RelationType
    data: dict = field(default_factory=dict)


@dataclass
class Foreshadow:
    id: str
    text: str
    hint: str
    expected_resolution: str = ""
    resolved: bool = False
    resolution_text: str = ""
    related_entities: list[str] = field(default_factory=list)
    related_events: list[str] = field(default_factory=list)
    # ── Foreshadow lifecycle fields (dual-mode design) ──
    source: str = "extracted"        # "planted" (writing mode) | "extracted" (reading mode)
    # status lifecycle: open → planned → due → scheduled → resolved
    #                     ↘ dangling (unmatched) / cross_volume (deferred)
    status: str = "open"             # "open" | "planned" | "due" | "scheduled" | "resolved" | "cross_volume" | "dangling"
    plant_chapter: str = ""          # chapter where foreshadow was planted, e.g. "#3"
    resolve_chapter: str = ""        # chapter where foreshadow was resolved, e.g. "#15"
    volume_ref: str = ""             # volume/book identifier for cross-volume tracking
    planned_resolve_arc: str = ""    # (planned mode) narrative arc name for resolution, e.g. "真相揭露"
    scheduled_chapter: str = ""      # (scheduled mode) user-confirmed chapter for resolution, e.g. "#15"
    confidence: str = "high"         # "high" | "medium" | "low"
    resolve_keywords: list[str] = field(default_factory=list)  # keywords to scan for resolution matching


@dataclass
class KnowledgeProposal:
    entities: list[Entity] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    foreshadows: list[Foreshadow] = field(default_factory=list)
    timeline_events: list[dict] = field(default_factory=list)
    # timeline_events items: {time_order(float), label, chapter_ref, characters: [names],
    #                         location(optional str), sub_events(optional list),
    #                         arc_id(optional str), narrative_time(optional str)}
    spatial_relations: list[dict] = field(default_factory=list)
    # spatial_relations items: {from, to, type(located_in/adjacent_to), label(optional)}


@dataclass
class WritingTask:
    instruction: str
    chapter_id: str = ""
    scene_description: str = ""
    target_word_count: int = 500
    style_notes: str = ""
    mode: str = "strict"


@dataclass
class ValidationResult:
    is_valid: bool
    conflicts: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class CharacterSnapshot:
    """角色阶段卡片（阶段系统）。

    一个 CharacterSnapshot 表示角色在某个阶段（如"第一部·觉醒"）的完整形象。
    ``data`` 字段存该阶段的角色完整属性（appearance/personality/abilities
    /motivation/relationships/growth_note 等）。

    阶段定位采用**顺序型**模型，与章节/分卷解耦：
    - ``is_current`` 标记当前写作阶段（同一角色同时仅一个为 True）；
    - ``time_order`` 决定阶段在弧光时间线上的先后顺序；
    - 阶段点由 AI 在角色发生重大转变时自由创建，不依赖章节系统。
    写作注入时取 ``is_current`` 的阶段（无则取 ``time_order`` 最大的最新阶段），
    替代 entity.data 最新态注入 LLM。

    旧快照（无 ``phase`` 字段）在读取时惰性标记 ``phase="未分阶段"``，保持向后兼容。
    """
    id: str
    character_entity_id: str
    time_point: str
    time_order: int = 0
    label: str = ""
    data: dict = field(default_factory=dict)
    description: str = ""
    # ── 阶段定位字段（顺序型，不绑定章节/分卷）──
    phase: str = ""             # 阶段名，如 "第一部·觉醒"
    phase_key: str = ""         # 稳定 key，如 "arc1"
    is_current: bool = False    # 是否标记为当前写作阶段


@dataclass
class TimelineEvent:
    id: str
    time_point: str
    label: str
    time_order: float = 0
    description: str = ""
    chapter_ref: str = ""
    event_entity_id: str = ""
    # ── Track metadata (for multi-track timeline visualization) ──
    track_id: str = ""
    track_name: str = ""
    track_color: str = ""
    time_label: str = ""  # human-readable time marker, e.g. "1981年万圣节"
    # ── Enhanced fields for flexible granularity ──
    location_ref: str = ""   # location name where event occurred
    arc_id: str = ""         # narrative arc this event belongs to
    narrative_time: str = ""  # narrative time description (not chapter-based)
