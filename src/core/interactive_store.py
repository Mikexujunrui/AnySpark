"""Interactive Story Store — Neo4j-backed branch story data model.

Extends the existing graph store with story branch, event, and choice nodes.
Integrates with existing Fore (foreshadow) nodes for cross-branch foreshadow tracking.
"""

import json as _json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from .graph_store import GraphStore

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent.parent / "data"

# ── New Neo4j constraints for interactive story nodes ──
INTERACTIVE_CONSTRAINTS = [
    "CREATE CONSTRAINT branch_id IF NOT EXISTS FOR (b:StoryBranch) REQUIRE b.id IS UNIQUE",
    "CREATE CONSTRAINT branchevent_id IF NOT EXISTS FOR (e:BranchEvent) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT choice_id IF NOT EXISTS FOR (c:Choice) REQUIRE c.id IS UNIQUE",
]

INTERACTIVE_INDEXES = [
    "CREATE INDEX branch_project IF NOT EXISTS FOR (b:StoryBranch) ON (b.project_id)",
    "CREATE INDEX branchevent_branch IF NOT EXISTS FOR (e:BranchEvent) ON (e.branch_id)",
    "CREATE INDEX choice_event IF NOT EXISTS FOR (c:Choice) ON (c.event_id)",
]


class InteractiveStore:
    """Manages interactive story branches, events, and choices.

    Uses Neo4j as primary storage; falls back to JSON files when Neo4j
    is unavailable (e.g. in dev environments without Docker)."""

    def __init__(self, book_id: str):
        self.book_id = book_id
        self.graph = GraphStore(project_id=book_id)
        self._neo4j_ok = self._check_neo4j()
        if not self._neo4j_ok:
            logger.info("InteractiveStore: Neo4j unavailable, using JSON fallback for book=%s", book_id)
        self._json_path = DATA_DIR / f"interactive_{book_id}.json"

    def _check_neo4j(self) -> bool:
        """Quick check if Neo4j is reachable."""
        try:
            result = self.graph._run("RETURN 1 AS ok", {})
            return len(result) > 0
        except Exception:
            return False

    def _load_json(self) -> dict:
        if self._json_path.exists():
            try:
                return _json.loads(self._json_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"branches": [], "events": [], "choices": [], "foreshadow_links": []}

    def _save_json(self, data: dict):
        self._json_path.parent.mkdir(parents=True, exist_ok=True)
        self._json_path.write_text(_json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")

    def init_schema(self):
        """Ensure interactive story constraints and indexes exist."""
        for constraint in INTERACTIVE_CONSTRAINTS:
            try:
                self.graph._run(constraint)
            except Exception as e:
                logger.debug("Interactive constraint skipped: %s", e)
        for index in INTERACTIVE_INDEXES:
            try:
                self.graph._run(index)
            except Exception as e:
                logger.debug("Interactive index skipped: %s", e)

    # ── Branch CRUD ──

    def create_branch(
        self,
        name: str,
        parent_branch_id: str | None = None,
        source_choice_id: str | None = None,
        description: str = "",
    ) -> dict:
        """Create a new story branch."""
        branch_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        # JSON fallback
        if not self._neo4j_ok:
            data = self._load_json()
            branch = {
                "id": branch_id, "project_id": self.book_id, "name": name,
                "description": description, "parent_branch_id": parent_branch_id,
                "source_choice_id": source_choice_id, "status": "active",
                "created_at": now, "updated_at": now,
            }
            data["branches"].append(branch)
            self._save_json(data)
            return branch

        # Neo4j path
        query = """
        CREATE (b:StoryBranch {
            id: $branch_id, project_id: $project_id, name: $name,
            description: $description, parent_branch_id: $parent_branch_id,
            source_choice_id: $source_choice_id, status: 'active',
            created_at: $now, updated_at: $now
        }) RETURN b
        """
        params = {"branch_id": branch_id, "project_id": self.book_id, "name": name,
                  "description": description, "parent_branch_id": parent_branch_id,
                  "source_choice_id": source_choice_id, "now": now}
        result = self.graph._run_single(query, params)
        if not result:
            # Neo4j write failed — fall back to JSON
            logger.warning("Neo4j write failed for branch %s, falling back to JSON", branch_id)
            self._neo4j_ok = False
            data = self._load_json()
            branch = {
                "id": branch_id, "project_id": self.book_id, "name": name,
                "description": description, "parent_branch_id": parent_branch_id,
                "source_choice_id": source_choice_id, "status": "active",
                "created_at": now, "updated_at": now,
            }
            data["branches"].append(branch)
            self._save_json(data)
            return branch

        if parent_branch_id:
            self.graph._run("MATCH (p:StoryBranch {id:$pid}) MATCH (c:StoryBranch {id:$cid}) MERGE (c)-[:BRANCHES_FROM]->(p)",
                           {"pid": parent_branch_id, "cid": branch_id})
            if source_choice_id:
                self.graph._run("MATCH (ch:Choice {id:$cid}) MATCH (b:StoryBranch {id:$bid}) MERGE (b)-[:BRANCHES_FROM]->(ch)",
                               {"cid": source_choice_id, "bid": branch_id})
        return self._branch_from_record(result["b"])

    def get_branch(self, branch_id: str) -> dict | None:
        """Get a single branch by ID."""
        if not self._neo4j_ok:
            data = self._load_json()
            for b in data.get("branches", []):
                if b["id"] == branch_id:
                    return b
            return None
        query = """MATCH (b:StoryBranch {id:$bid}) OPTIONAL MATCH (b)-[:BRANCHES_FROM]->(p:StoryBranch)
            RETURN b, p.id AS parent_id"""
        result = self.graph._run_single(query, {"bid": branch_id})
        if not result:
            return None
        branch = self._branch_from_record(result["b"])
        branch["parent_id"] = result.get("parent_id")
        return branch

    def list_branches(self, status: str | None = None) -> list[dict]:
        """List all branches for this book, optionally filtered by status."""
        if not self._neo4j_ok:
            data = self._load_json()
            branches = data.get("branches", [])
            if status:
                branches = [b for b in branches if b.get("status") == status]
            branches.sort(key=lambda b: b.get("created_at", ""), reverse=True)
            return branches
        if status:
            query = "MATCH (b:StoryBranch {project_id:$pid, status:$st}) RETURN b ORDER BY b.created_at DESC"
            params = {"pid": self.book_id, "st": status}
        else:
            query = "MATCH (b:StoryBranch {project_id:$pid}) RETURN b ORDER BY b.created_at DESC"
            params = {"pid": self.book_id}
        results = self.graph._run(query, params)
        return [self._branch_from_record(r["b"]) for r in results]

    def update_branch(self, branch_id: str, **kwargs) -> dict | None:
        """Update branch fields (name, description, status)."""
        allowed = {"name", "description", "status"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return self.get_branch(branch_id)

        updates["updated_at"] = datetime.utcnow().isoformat()
        set_clause = ", ".join(f"b.{k} = ${k}" for k in updates)
        query = f"""
        MATCH (b:StoryBranch {{id: $branch_id}})
        SET {set_clause}
        RETURN b
        """
        params = {"branch_id": branch_id, **updates}
        result = self.graph._run_single(query, params)
        if not result:
            return None
        return self._branch_from_record(result["b"])

    def delete_branch(self, branch_id: str) -> bool:
        """Delete a branch and its events/choices (cascading)."""
        query = """
        MATCH (b:StoryBranch {id: $branch_id})
        OPTIONAL MATCH (b)-[:HAS_EVENT]->(e:BranchEvent)
        OPTIONAL MATCH (e)-[:HAS_CHOICE]->(c:Choice)
        DETACH DELETE c, e, b
        """
        self.graph._run(query, {"branch_id": branch_id})
        return True

    # ── BranchEvent CRUD ──

    def add_event(
        self, branch_id: str, content: str,
        event_type: str = "narrative", turn_number: int = 0,
    ) -> dict:
        """Add a narrative event to a branch."""
        event_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        if not self._neo4j_ok:
            data = self._load_json()
            event = {"id": event_id, "branch_id": branch_id, "content": content,
                     "event_type": event_type, "turn_number": turn_number, "created_at": now}
            data["events"].append(event)
            # Update branch timestamp
            for b in data["branches"]:
                if b["id"] == branch_id:
                    b["updated_at"] = now
            self._save_json(data)
            return event

        query = """MATCH (b:StoryBranch {id: $bid}) CREATE (e:BranchEvent {
            id:$eid, branch_id:$bid, content:$content, event_type:$etype,
            turn_number:$tn, created_at:$now}) MERGE (b)-[:HAS_EVENT]->(e) RETURN e"""
        params = {"bid": branch_id, "eid": event_id, "content": content,
                  "etype": event_type, "tn": turn_number, "now": now}
        result = self.graph._run_single(query, params)
        if not result:
            return None
        self.graph._run("MATCH (b:StoryBranch {id:$bid}) SET b.updated_at=$now",
                       {"bid": branch_id, "now": now})
        return self._event_from_record(result["e"])

    def get_events(self, branch_id: str) -> list[dict]:
        """Get all events for a branch, ordered by turn_number."""
        if not self._neo4j_ok:
            data = self._load_json()
            events = [e for e in data.get("events", []) if e.get("branch_id") == branch_id]
            events.sort(key=lambda e: (e.get("turn_number", 0), e.get("created_at", "")))
            return events
        query = """MATCH (b:StoryBranch {id:$bid})-[:HAS_EVENT]->(e:BranchEvent)
            RETURN e ORDER BY e.turn_number, e.created_at"""
        results = self.graph._run(query, {"bid": branch_id})
        return [self._event_from_record(r["e"]) for r in results]

    def get_latest_event(self, branch_id: str) -> dict | None:
        """Get the most recent event in a branch."""
        query = """
        MATCH (b:StoryBranch {id: $branch_id})-[:HAS_EVENT]->(e:BranchEvent)
        RETURN e ORDER BY e.turn_number DESC LIMIT 1
        """
        result = self.graph._run_single(query, {"branch_id": branch_id})
        return self._event_from_record(result["e"]) if result else None

    # ── Choice CRUD ──

    def add_choice(self, event_id: str, text: str, description: str = "") -> dict:
        """Add a choice option to an event."""
        choice_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        if not self._neo4j_ok:
            data = self._load_json()
            choice = {"id": choice_id, "event_id": event_id, "text": text,
                      "description": description, "created_at": now}
            data["choices"].append(choice)
            self._save_json(data)
            return choice

        query = """MATCH (e:BranchEvent {id:$eid}) CREATE (c:Choice {
            id:$cid, event_id:$eid, text:$text, description:$desc, created_at:$now})
            MERGE (e)-[:HAS_CHOICE]->(c) RETURN c"""
        params = {"eid": event_id, "cid": choice_id, "text": text,
                  "desc": description, "now": now}
        result = self.graph._run_single(query, params)
        return self._choice_from_record(result["c"]) if result else None

    def get_choices(self, event_id: str) -> list[dict]:
        """Get all choices for an event."""
        if not self._neo4j_ok:
            data = self._load_json()
            return [c for c in data.get("choices", []) if c.get("event_id") == event_id]
        query = "MATCH (e:BranchEvent {id:$eid})-[:HAS_CHOICE]->(c:Choice) RETURN c"
        results = self.graph._run(query, {"eid": event_id})
        return [self._choice_from_record(r["c"]) for r in results]

    # ── Foreshadow Integration ──

    def link_event_to_foreshadow(self, event_id: str, fore_id: str, action: str = "advances"):
        """Link a branch event to an existing foreshadow node.

        action: 'triggers' | 'advances' | 'resolves'
        """
        query = """
        MATCH (e:BranchEvent {id: $event_id})
        MATCH (f:Fore {id: $fore_id})
        MERGE (e)-[:AFFECTS {action: $action}]->(f)
        """
        self.graph._run(query, {"event_id": event_id, "fore_id": fore_id, "action": action})

        if action == "resolves":
            # Mark foreshadow as resolved in the context of this branch
            branch_query = """
            MATCH (e:BranchEvent {id: $event_id})
            MATCH (b:StoryBranch)-[:HAS_EVENT]->(e)
            MATCH (f:Fore {id: $fore_id})
            MERGE (f)-[:RESOLVES_IN]->(b)
            """
            self.graph._run(branch_query, {"event_id": event_id, "fore_id": fore_id})

    def get_foreshadows_for_branch(self, branch_id: str) -> list[dict]:
        """Get all foreshadows affected by events in this branch."""
        query = """
        MATCH (b:StoryBranch {id: $branch_id})-[:HAS_EVENT]->(e:BranchEvent)
        MATCH (e)-[r:AFFECTS]->(f:Fore)
        RETURN f, r.action AS action, e.id AS event_id, e.turn_number AS turn
        ORDER BY e.turn_number
        """
        results = self.graph._run(query, {"branch_id": branch_id})
        foreshadows = []
        for r in results:
            f = dict(r["f"])
            f["action"] = r.get("action")
            f["event_id"] = r.get("event_id")
            f["turn"] = r.get("turn")
            foreshadows.append(f)
        return foreshadows

    def compare_foreshadows_across_branches(self) -> list[dict]:
        """Compare foreshadow resolution status across all branches.

        Returns a matrix-like structure for visualization.
        """
        query = """
        MATCH (f:Fore)
        OPTIONAL MATCH (f)-[:RESOLVES_IN]->(b:StoryBranch)
        WITH f, collect(DISTINCT b.id) AS resolved_in
        OPTIONAL MATCH (e:BranchEvent)-[r:AFFECTS]->(f)
        WITH f, resolved_in, collect(DISTINCT {branch: e.branch_id, action: r.action}) AS affecting_events
        RETURN f.id AS fore_id, f.text AS text, f.resolved AS globally_resolved,
               resolved_in, affecting_events
        """
        results = self.graph._run(query, {})
        return [dict(r) for r in results]

    # ── Branch Tree ──

    def get_branch_tree(self) -> dict:
        """Get the full branch tree structure for visualization."""
        query = """
        MATCH (b:StoryBranch {project_id: $project_id})
        OPTIONAL MATCH (b)-[:BRANCHES_FROM]->(parent:StoryBranch)
        OPTIONAL MATCH (child:StoryBranch)-[:BRANCHES_FROM]->(b)
        WITH b, parent, collect(DISTINCT child.id) AS children
        OPTIONAL MATCH (b)-[:HAS_EVENT]->(e:BranchEvent)
        WITH b, parent, children, count(e) AS event_count
        RETURN b, parent.id AS parent_id, children, event_count
        ORDER BY b.created_at
        """
        params = {"project_id": self.book_id}
        results = self.graph._run(query, params)

        nodes = []
        for r in results:
            branch = self._branch_from_record(r["b"])
            branch["parent_id"] = r.get("parent_id")
            branch["children"] = r.get("children", [])
            branch["event_count"] = r.get("event_count", 0)
            nodes.append(branch)

        # Build tree structure
        roots = [n for n in nodes if not n.get("parent_id")]
        return {"roots": roots, "all_nodes": nodes}

    # ── Serialization helpers ──

    def _branch_from_record(self, record) -> dict:
        if record is None:
            return None
        return {
            "id": record.get("id"),
            "project_id": record.get("project_id"),
            "name": record.get("name", ""),
            "description": record.get("description", ""),
            "parent_branch_id": record.get("parent_branch_id"),
            "source_choice_id": record.get("source_choice_id"),
            "status": record.get("status", "active"),
            "created_at": record.get("created_at", ""),
            "updated_at": record.get("updated_at", ""),
        }

    def _event_from_record(self, record) -> dict:
        if record is None:
            return None
        return {
            "id": record.get("id"),
            "branch_id": record.get("branch_id"),
            "content": record.get("content", ""),
            "event_type": record.get("event_type", "narrative"),
            "turn_number": record.get("turn_number", 0),
            "created_at": record.get("created_at", ""),
        }

    def _choice_from_record(self, record) -> dict:
        if record is None:
            return None
        return {
            "id": record.get("id"),
            "event_id": record.get("event_id"),
            "text": record.get("text", ""),
            "description": record.get("description", ""),
            "created_at": record.get("created_at", ""),
        }
