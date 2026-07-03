"""Neo4j Graph Schema — node labels, relationship types, constraints."""

import re

ENTITY_LABELS = {
    "character": "Character",
    "location": "Location",
    "item": "Item",
    "skill": "Skill",
    "organization": "Organization",
    "race": "Race",
    "concept": "Concept",
    "event": "Event",
    # Narrative logic — independent label, not an Entity subtype
    "constraint": "Constraint",
}

# Dynamic ontology overrides (set by ontology_generator per book)
_dynamic_entity_labels: dict[str, str] = {}
_dynamic_relationship_types: list[str] = []


def register_dynamic_ontology(entity_labels: dict[str, str], relationship_types: list[str]):
    """Register a dynamically generated ontology to extend/override the fixed schema.

    Called by ontology_generator.apply_ontology_to_schema().
    Dynamic labels take precedence over built-in ENTITY_LABELS.
    """
    global _dynamic_entity_labels, _dynamic_relationship_types
    _dynamic_entity_labels = dict(entity_labels)
    _dynamic_relationship_types = list(relationship_types)


def get_active_entity_labels() -> dict[str, str]:
    """Get the currently active entity labels (dynamic overrides merged with built-in)."""
    merged = dict(ENTITY_LABELS)
    merged.update(_dynamic_entity_labels)
    return merged


def get_active_relationship_types() -> list[str]:
    """Get the currently active relationship types (dynamic merged with built-in)."""
    merged = list(RELATIONSHIP_TYPES)
    for rt in _dynamic_relationship_types:
        if rt not in merged:
            merged.append(rt)
    return merged


def entity_label(entity_type: str) -> str:
    """Convert entity type string to Neo4j label (CamelCase). Custom types auto-capitalized.
    Validated to prevent Cypher injection."""
    # Check dynamic overrides first, then built-in
    active = get_active_entity_labels()
    known = active.get(entity_type)
    if known:
        return known
    # Sanitize custom types: only allow alphanumeric + underscore
    label = entity_type.title().replace("_", "")
    if not re.match(r"^[A-Za-z][A-Za-z0-9]*$", label):
        raise ValueError(f"Invalid entity type for Neo4j label: {entity_type!r}")
    return label

RELATIONSHIP_TYPES = [
    "KNOWS", "BELONGS_TO", "LOCATED_AT", "OWNS", "ANTAGONIST",
    "ALLY", "FAMILY", "ROMANTIC", "MASTER_OF", "MENTOR_OF",
    "KILLED", "SAVED", "LOVES", "CAUSES",
    "BEFORE", "AFTER", "FORESHADOWS", "RESOLVES", "PARTICIPATES_IN",
    # P0: Graph edgification — connect Foreshadow/Timeline/Snapshot to Entity
    "INVOLVES",       # Foreshadow/Timeline → Entity
    "HAS_PHASE",      # Entity → Snapshot (character phase)
    "DEPENDS_ON",     # Foreshadow → Foreshadow (dependency chain, P2)
    # Narrative logic — constraint governance
    "GOVERNS",        # Constraint → Entity (which entity a rule applies to)
    # ── Spatial relationship types ──
    "LOCATED_IN",     # Location → Location (containment: child inside parent)
    "ADJACENT_TO",    # Location → Location (neighboring, no containment)
    "OCCURRED_AT",    # Timeline → Location (event happened at this place)
    # ── Paired relationship types (directional with different reverse type) ──
    "PARENT_OF", "CHILD_OF",
    "APPRENTICE_OF", "STUDENT_OF",
    "KILLED_BY", "SAVED_BY",
    "LOVED_BY",
    "SPOUSE_OF", "SIBLING_OF",
]

# ── Relationship direction metadata ──
# Three categories:
#   "symmetric"      — reverse edge has the SAME type (A KNOWS B → B KNOWS A)
#   "unidirectional" — strictly one-way, never add reverse (A OWNS B, B does NOT own A)
#   "paired:XXX"    — reverse edge has a DIFFERENT type (A PARENT_OF B → B CHILD_OF A)
#
# Dynamic relationship types not listed here default to "unidirectional" (safe default:
# don't blindly add reverse edges for unknown types).
RELATIONSHIP_DIRECTION: dict[str, str] = {
    # ── Symmetric: bidirectional with same type ──
    "KNOWS": "symmetric",
    "ALLY": "symmetric",
    "ANTAGONIST": "symmetric",
    "ROMANTIC": "symmetric",
    "FRIEND": "symmetric",
    "FAMILY": "symmetric",       # generic family member (use PARENT_OF/CHILD_OF for specific)
    "SPOUSE_OF": "symmetric",
    "SIBLING_OF": "symmetric",
    "ADJACENT_TO": "symmetric",

    # ── Strictly unidirectional: never add reverse ──
    "LOCATED_IN": "unidirectional",
    "LOCATED_AT": "unidirectional",
    "BELONGS_TO": "unidirectional",
    "OWNS": "unidirectional",
    "CAUSES": "unidirectional",
    "BEFORE": "unidirectional",
    "AFTER": "unidirectional",
    "FORESHADOWS": "unidirectional",
    "RESOLVES": "unidirectional",
    "PARTICIPATES_IN": "unidirectional",
    "OCCURRED_AT": "unidirectional",
    "INVOLVES": "unidirectional",
    "HAS_PHASE": "unidirectional",
    "DEPENDS_ON": "unidirectional",
    "GOVERNS": "unidirectional",

    # ── Paired: directional with different reverse type ──
    "PARENT_OF": "paired:CHILD_OF",
    "CHILD_OF": "paired:PARENT_OF",
    "MENTOR_OF": "paired:APPRENTICE_OF",
    "APPRENTICE_OF": "paired:MENTOR_OF",
    "MASTER_OF": "paired:STUDENT_OF",
    "STUDENT_OF": "paired:MASTER_OF",
    "KILLED": "paired:KILLED_BY",
    "KILLED_BY": "paired:KILLED",
    "SAVED": "paired:SAVED_BY",
    "SAVED_BY": "paired:SAVED",
    "LOVES": "paired:LOVED_BY",
    "LOVED_BY": "paired:LOVES",
}


def get_relationship_direction(rel_type: str) -> str:
    """Get the direction category for a relationship type.

    Returns:
        "symmetric", "unidirectional", or "paired:REVERSE_TYPE"
        Defaults to "unidirectional" for unknown types (safe default).
    """
    return RELATIONSHIP_DIRECTION.get(rel_type.upper(), "unidirectional")


def is_symmetric(rel_type: str) -> bool:
    """Check if a relationship type is symmetric (should have bidirectional edges)."""
    return get_relationship_direction(rel_type) == "symmetric"


def is_unidirectional(rel_type: str) -> bool:
    """Check if a relationship type is strictly unidirectional."""
    return get_relationship_direction(rel_type) == "unidirectional"


def get_paired_reverse(rel_type: str) -> str | None:
    """Get the paired reverse type for a directional relationship.

    Returns:
        The reverse relationship type (e.g. "CHILD_OF" for "PARENT_OF"),
        or None if the type is not paired.
    """
    direction = get_relationship_direction(rel_type)
    if direction.startswith("paired:"):
        return direction[7:]
    return None


def get_symmetric_types() -> list[str]:
    """Get all symmetric relationship types (for auto-completion)."""
    return [rt for rt, d in RELATIONSHIP_DIRECTION.items() if d == "symmetric"]

CONSTRAINTS = [
    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT project_id IF NOT EXISTS FOR (p:Project) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT timeline_id IF NOT EXISTS FOR (t:Timeline) REQUIRE t.id IS UNIQUE",
    "CREATE CONSTRAINT snapshot_id IF NOT EXISTS FOR (s:Snapshot) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT chapter_id IF NOT EXISTS FOR (c:Chapter) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT constraint_id IF NOT EXISTS FOR (c:Constraint) REQUIRE c.id IS UNIQUE",
]

INDEXES = [
    "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)",
    "CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.entity_type)",
    "CREATE INDEX entity_project IF NOT EXISTS FOR (e:Entity) ON (e.project_id)",
    "CREATE INDEX snapshot_char IF NOT EXISTS FOR (s:Snapshot) ON (s.character_id)",
    "CREATE FULLTEXT INDEX entity_text IF NOT EXISTS FOR (e:Entity) ON EACH [e.name, e.aliases]",
    "CREATE INDEX constraint_project IF NOT EXISTS FOR (c:Constraint) ON (c.project_id)",
]

PROPERTY_KEYS = [
    "id", "entity_type", "name", "aliases",
    "data", "project_id", "created_at", "updated_at",
    "label", "time_point", "time_order", "description",
    "chapter_ref", "content", "title",
]
