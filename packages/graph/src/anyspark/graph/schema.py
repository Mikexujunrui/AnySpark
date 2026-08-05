"""
anyspark.graph.schema — 知识图谱存储（实体/关系/事件 + FTS 检索）。

设计（DESIGN §8 数据设计第 3/7 项）：实体（角色/地点/事件/物件/设定）/ 关系 / 时间线事件
= AI 事实源。写作时"当前时空点已知事实"检索注入（模型局限弥补表）。
模型无关：全部承载物为明确无歧义自然语言（name/aliases/description/rel_type/time_point）。
旧系统 novel.db 的 entities/relations/timeline_events/entities_fts 仅作思想参考，不复刻代码。

存储策略（幂等，可重复抽取）：
- 实体按 (book_id, name) 合并：别名取并集、描述覆盖、出现章节范围累计
- 关系按 (from_id, to_id, rel_type) 去重：描述覆盖
- 事件按 (book_id, chapter_ref, label) 去重：整体替换
- FTS5 trigram 派生索引（≥3 字子串检索），短名（1-2 字）回退 LIKE
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _merge_state(old_state: str, delta: str) -> str:
    """状态增量拼接：旧状态 + 本章变化（S20 角色/地点随时间演化）。

    - 无变化（delta 空）→ 保留旧状态
    - 旧状态空 → 直接取 delta
    - 都有 → "旧；本章：变化"（自然语言承载，模型无关）
    """
    d = delta.strip().rstrip("；;").strip()
    o = old_state.strip().rstrip("；;").strip()
    if not d:
        return old_state
    if not o:
        return d
    return f"{o}；{d}"


# 实体类型：明确无歧义的自然语言分类（模型无关）
ENTITY_TYPES = ("角色", "地点", "事件", "物件", "设定")


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class Entity:
    """图谱实体（角色/地点/事件/物件/设定）。"""

    id: str
    book_id: str
    entity_type: str
    name: str
    aliases: list[str] = field(default_factory=list)
    description: str = ""
    state: str = ""  # 截至最新章节的状态（自然语言增量拼接；S20 角色/地点随时间演化）
    first_chapter: str = ""
    last_chapter: str = ""
    first_order: int = 0
    last_order: int = 0
    # S37（重要性信号）：实体出现的**不同章节数**（中性事实——出场越广=贯穿性越强）。
    # 注入时"高频保底 + 最近补充"混合选取，保证百章级超长书早期主线不丢（S37）。
    weight: int = 0
    # S29（多线叙事）：实体出现过的叙事线（如 ["main", "line_b"]）——时序校验按线比较，
    # 跨线首现不误报"时空倒置"（A 线第 3 章提到 B 线第 5 章才首现的角色是并行叙事，非倒叙）。
    lines: list[str] = field(default_factory=lambda: ["main"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "book_id": self.book_id,
            "entity_type": self.entity_type,
            "name": self.name,
            "aliases": self.aliases,
            "description": self.description,
            "state": self.state,
            "first_chapter": self.first_chapter,
            "last_chapter": self.last_chapter,
            "first_order": self.first_order,
            "last_order": self.last_order,
            "weight": self.weight,
            "lines": self.lines,
        }


@dataclass
class Relation:
    """实体间关系（自然语言类型 + 描述）。"""

    id: str
    book_id: str
    from_id: str
    from_name: str
    to_id: str
    to_name: str
    rel_type: str
    description: str = ""
    chapter_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "book_id": self.book_id,
            "from_id": self.from_id,
            "from_name": self.from_name,
            "to_id": self.to_id,
            "to_name": self.to_name,
            "rel_type": self.rel_type,
            "description": self.description,
            "chapter_ref": self.chapter_ref,
        }


@dataclass
class GraphEvent:
    """时间线事件（时间点自然语言，如"第3章"）。"""

    id: str
    book_id: str
    chapter_ref: str
    chapter_order: int
    time_point: str
    label: str
    description: str = ""
    involved: list[str] = field(default_factory=list)  # 涉及实体名

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "book_id": self.book_id,
            "chapter_ref": self.chapter_ref,
            "chapter_order": self.chapter_order,
            "time_point": self.time_point,
            "label": self.label,
            "description": self.description,
            "involved": self.involved,
        }


class GraphStore:
    """知识图谱存储（SQLite）：实体/关系/事件 + FTS5 派生索引。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False：嵌入式 SQLite 供 FastAPI 多线程 endpoint 共用
        self._conn = sqlite3.connect(self._db, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS graph_entities (
                id TEXT PRIMARY KEY,
                book_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                name TEXT NOT NULL,
                aliases TEXT NOT NULL DEFAULT '[]',
                description TEXT NOT NULL DEFAULT '',
                state TEXT NOT NULL DEFAULT '',
                first_chapter TEXT NOT NULL DEFAULT '',
                last_chapter TEXT NOT NULL DEFAULT '',
                first_order INTEGER NOT NULL DEFAULT 0,
                last_order INTEGER NOT NULL DEFAULT 0,
                weight INTEGER NOT NULL DEFAULT 0,
                lines TEXT NOT NULL DEFAULT '["main"]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(book_id, name)
            );
            CREATE TABLE IF NOT EXISTS entity_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id TEXT NOT NULL,
                chapter_ref TEXT NOT NULL DEFAULT '',
                state_after TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_entity_states_eid
                ON entity_states(entity_id, id);
            CREATE TABLE IF NOT EXISTS graph_relations (
                id TEXT PRIMARY KEY,
                book_id TEXT NOT NULL,
                from_id TEXT NOT NULL,
                to_id TEXT NOT NULL,
                rel_type TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                chapter_ref TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(from_id, to_id, rel_type)
            );
            CREATE TABLE IF NOT EXISTS graph_events (
                id TEXT PRIMARY KEY,
                book_id TEXT NOT NULL,
                chapter_ref TEXT NOT NULL,
                chapter_order INTEGER NOT NULL DEFAULT 0,
                time_point TEXT NOT NULL DEFAULT '',
                label TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                involved TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                UNIQUE(book_id, chapter_ref, label)
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS graph_entities_fts USING fts5(
                name, aliases, id UNINDEXED, tokenize='trigram'
            );
            CREATE INDEX IF NOT EXISTS idx_graph_entities_book
                ON graph_entities(book_id, last_order);
            CREATE INDEX IF NOT EXISTS idx_graph_relations_book
                ON graph_relations(book_id);
            CREATE INDEX IF NOT EXISTS idx_graph_events_book
                ON graph_events(book_id, chapter_order);
            """
        )
        # 旧库兼容（S20 state / S29 lines）
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(graph_entities)")}
        if "state" not in cols:
            self._conn.execute(
                "ALTER TABLE graph_entities ADD COLUMN state TEXT NOT NULL DEFAULT ''"
            )
        if "lines" not in cols:
            self._conn.execute(
                "ALTER TABLE graph_entities ADD COLUMN lines TEXT NOT NULL DEFAULT '[\"main\"]'"
            )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # 实体
    # ------------------------------------------------------------------
    def upsert_entity(
        self,
        book_id: str,
        name: str,
        entity_type: str,
        aliases: list[str] | None = None,
        description: str = "",
        chapter_ref: str = "",
        chapter_order: int = 0,
        state_delta: str = "",
        line: str = "main",
    ) -> Entity:
        """同名实体合并：别名并集、描述覆盖、出现章节范围累计。

        state_delta（S20）：本章状态变化——增量拼接到旧状态（"旧；本章：变化"），
        并记录演化快照到 entity_states（角色/地点随时间自然变化）。
        line（S29 多线叙事）：实体出现的叙事线并入 lines（跨线并行不覆盖）。
        """
        aliases = aliases or []
        eid = uuid.uuid4().hex
        now = _now()
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM graph_entities WHERE book_id=? AND name=?",
                (book_id, name),
            ).fetchone()
            if row:
                eid = row["id"]
                # 类型：空串=保留原类型（S20 states 只更新状态时用）
                etype = entity_type if entity_type in ENTITY_TYPES else row["entity_type"]
                merged = list(dict.fromkeys(json.loads(row["aliases"]) + aliases))
                first_ch = row["first_chapter"] or chapter_ref
                first_ord = row["first_order"] or chapter_order
                last_ch = chapter_ref if chapter_order >= row["last_order"] else row["last_chapter"]
                last_ord = max(row["last_order"], chapter_order)
                # S37 重要性：新章节首次出现 → weight+1（同章重复 upsert 不累计）
                new_weight = int(row["weight"] or 0) + (
                    1 if chapter_order > row["last_order"] else 0
                )
                # 状态增量拼接（S20）：旧状态 + 本章变化
                old_state = str(row["state"] or "")
                new_state = _merge_state(old_state, state_delta)
                # S29：叙事线并入（跨线并行不覆盖）
                old_lines = json.loads(row["lines"] or '["main"]')
                merged_lines = list(dict.fromkeys([*old_lines, line]))
                self._conn.execute(
                    "UPDATE graph_entities SET entity_type=?, aliases=?, description=?, "
                    "state=?, first_chapter=?, last_chapter=?, first_order=?, "
                    "last_order=?, weight=?, lines=?, updated_at=? WHERE id=?",
                    (
                        etype,
                        json.dumps(merged, ensure_ascii=False),
                        description,
                        new_state,
                        first_ch,
                        last_ch,
                        first_ord,
                        last_ord,
                        new_weight,
                        json.dumps(merged_lines, ensure_ascii=False),
                        now,
                        eid,
                    ),
                )
            else:
                etype = entity_type if entity_type in ENTITY_TYPES else "设定"
                new_state = state_delta
                new_weight = 1  # S37：新实体首章出现，出场章节数=1
                self._conn.execute(
                    "INSERT INTO graph_entities (id, book_id, entity_type, name, aliases, "
                    "description, state, first_chapter, last_chapter, first_order, "
                    "last_order, weight, lines, created_at, updated_at) VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        eid,
                        book_id,
                        etype,
                        name,
                        json.dumps(aliases, ensure_ascii=False),
                        description,
                        new_state,
                        chapter_ref,
                        chapter_ref,
                        chapter_order,
                        chapter_order,
                        new_weight,
                        json.dumps([line], ensure_ascii=False),
                        now,
                        now,
                    ),
                )
            # 状态演化快照（S20）：有变化才记录
            if new_state and (not row or new_state != str(row["state"] or "")):
                self._conn.execute(
                    "INSERT INTO entity_states (entity_id, chapter_ref, state_after, created_at) "
                    "VALUES (?,?,?,?)",
                    (eid, chapter_ref, new_state, now),
                )
            self._sync_fts(eid, name, aliases)
            self._conn.commit()
        ent = self.get_entity(book_id, name)
        assert ent is not None
        return ent

    def _sync_fts(self, eid: str, name: str, aliases: list[str]) -> None:
        """同步 FTS 派生索引（trigram 内联表：删旧插新）。"""
        self._conn.execute("DELETE FROM graph_entities_fts WHERE id=?", (eid,))
        self._conn.execute(
            "INSERT INTO graph_entities_fts (name, aliases, id) VALUES (?,?,?)",
            (name, json.dumps(aliases, ensure_ascii=False), eid),
        )

    def get_entity(self, book_id: str, name: str) -> Entity | None:
        row = self._conn.execute(
            "SELECT * FROM graph_entities WHERE book_id=? AND name=?", (book_id, name)
        ).fetchone()
        return self._entity_from_row(row) if row else None

    def list_entities(
        self,
        book_id: str,
        q: str | None = None,
        entity_type: str | None = None,
        limit: int = 200,
    ) -> list[Entity]:
        where = "book_id=?"
        args: list[Any] = [book_id]
        if q:
            where += " AND (name LIKE ? OR aliases LIKE ?)"
            args += [f"%{q}%", f"%{q}%"]
        if entity_type:
            where += " AND entity_type=?"
            args.append(entity_type)
        rows = self._conn.execute(
            f"SELECT * FROM graph_entities WHERE {where} "
            "ORDER BY last_order DESC, rowid DESC LIMIT ?",
            (*args, limit),
        ).fetchall()
        return [self._entity_from_row(r) for r in rows]

    def search(self, book_id: str, query: str, limit: int = 10) -> list[Entity]:
        """FTS5 trigram 优先（≥3 字子串），短名（<3 字）回退 LIKE。"""
        q = query.strip()
        if not q:
            return []
        if len(q) >= 3:
            phrase = '"' + q.replace('"', "") + '"'
            rows = self._conn.execute(
                "SELECT e.* FROM graph_entities_fts f "
                "JOIN graph_entities e ON e.id = f.id "
                "WHERE f.graph_entities_fts MATCH ? AND e.book_id=? "
                "ORDER BY e.last_order DESC, e.rowid DESC LIMIT ?",
                (phrase, book_id, limit),
            ).fetchall()
            if rows:
                return [self._entity_from_row(r) for r in rows]
        rows = self._conn.execute(
            "SELECT * FROM graph_entities WHERE book_id=? "
            "AND (name LIKE ? OR aliases LIKE ?) "
            "ORDER BY last_order DESC, rowid DESC LIMIT ?",
            (book_id, f"%{q}%", f"%{q}%", limit),
        ).fetchall()
        return [self._entity_from_row(r) for r in rows]

    def resolve_names(self, book_id: str, names: list[str]) -> list[Entity]:
        """把材料/事件里的名字解析到图谱实体（按实体去重、保序、最佳命中）。"""
        seen_input: set[str] = set()
        seen_ids: set[str] = set()
        out: list[Entity] = []
        for raw in names:
            n = str(raw).strip()
            if not n or n in seen_input:
                continue
            seen_input.add(n)
            matches = self.search(book_id, n, limit=1)
            if matches and matches[0].id not in seen_ids:
                seen_ids.add(matches[0].id)
                out.append(matches[0])
        return out

    # ------------------------------------------------------------------
    # 关系
    # ------------------------------------------------------------------
    def upsert_relation(
        self,
        book_id: str,
        from_name: str,
        to_name: str,
        rel_type: str,
        description: str = "",
        chapter_ref: str = "",
    ) -> Relation | None:
        """按名字解析两端实体，同三元组去重。任一端解析失败返回 None。"""
        f = self.get_entity(book_id, from_name)
        t = self.get_entity(book_id, to_name)
        if not f or not t:
            return None
        rid = uuid.uuid4().hex
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM graph_relations WHERE from_id=? AND to_id=? AND rel_type=?",
                (f.id, t.id, rel_type),
            ).fetchone()
            if row:
                rid = row["id"]
                self._conn.execute(
                    "UPDATE graph_relations SET description=?, chapter_ref=? WHERE id=?",
                    (description, chapter_ref, rid),
                )
            else:
                self._conn.execute(
                    "INSERT INTO graph_relations (id, book_id, from_id, to_id, rel_type, "
                    "description, chapter_ref, created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (rid, book_id, f.id, t.id, rel_type, description, chapter_ref, _now()),
                )
            self._conn.commit()
        return Relation(
            id=rid,
            book_id=book_id,
            from_id=f.id,
            from_name=f.name,
            to_id=t.id,
            to_name=t.name,
            rel_type=rel_type,
            description=description,
            chapter_ref=chapter_ref,
        )

    def list_relations(self, book_id: str, limit: int = 200) -> list[Relation]:
        rows = self._conn.execute(
            "SELECT r.*, fe.name AS from_name, te.name AS to_name "
            "FROM graph_relations r "
            "JOIN graph_entities fe ON fe.id = r.from_id "
            "JOIN graph_entities te ON te.id = r.to_id "
            "WHERE r.book_id=? ORDER BY r.rowid DESC LIMIT ?",
            (book_id, limit),
        ).fetchall()
        return [self._relation_from_row(r) for r in rows]

    def relations_of(self, book_id: str, entity_id: str, limit: int = 50) -> list[Relation]:
        """某实体涉及的全部关系（双向）。"""
        rows = self._conn.execute(
            "SELECT r.*, fe.name AS from_name, te.name AS to_name "
            "FROM graph_relations r "
            "JOIN graph_entities fe ON fe.id = r.from_id "
            "JOIN graph_entities te ON te.id = r.to_id "
            "WHERE r.book_id=? AND (r.from_id=? OR r.to_id=?) "
            "ORDER BY r.rowid DESC LIMIT ?",
            (book_id, entity_id, entity_id, limit),
        ).fetchall()
        return [self._relation_from_row(r) for r in rows]

    # ------------------------------------------------------------------
    # 事件（时间线）
    # ------------------------------------------------------------------
    def upsert_event(
        self,
        book_id: str,
        chapter_ref: str,
        chapter_order: int,
        time_point: str,
        label: str,
        description: str = "",
        involved: list[str] | None = None,
    ) -> GraphEvent:
        """按 (book_id, chapter_ref, label) 去重：整体替换。"""
        involved = involved or []
        eid = uuid.uuid4().hex
        now = _now()
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM graph_events WHERE book_id=? AND chapter_ref=? AND label=?",
                (book_id, chapter_ref, label),
            ).fetchone()
            if row:
                eid = row["id"]
                self._conn.execute(
                    "UPDATE graph_events SET chapter_order=?, time_point=?, description=?, "
                    "involved=? WHERE id=?",
                    (
                        chapter_order,
                        time_point,
                        description,
                        json.dumps(involved, ensure_ascii=False),
                        eid,
                    ),
                )
            else:
                self._conn.execute(
                    "INSERT INTO graph_events (id, book_id, chapter_ref, chapter_order, "
                    "time_point, label, description, involved, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        eid,
                        book_id,
                        chapter_ref,
                        chapter_order,
                        time_point,
                        label,
                        description,
                        json.dumps(involved, ensure_ascii=False),
                        now,
                    ),
                )
            self._conn.commit()
        return GraphEvent(
            id=eid,
            book_id=book_id,
            chapter_ref=chapter_ref,
            chapter_order=chapter_order,
            time_point=time_point,
            label=label,
            description=description,
            involved=involved,
        )

    def list_events(
        self, book_id: str, chapter_ref: str | None = None, limit: int = 200
    ) -> list[GraphEvent]:
        where = "book_id=?"
        args: list[Any] = [book_id]
        if chapter_ref:
            where += " AND chapter_ref=?"
            args.append(chapter_ref)
        rows = self._conn.execute(
            f"SELECT * FROM graph_events WHERE {where} ORDER BY chapter_order, rowid LIMIT ?",
            (*args, limit),
        ).fetchall()
        return [self._event_from_row(r) for r in rows]

    # ------------------------------------------------------------------
    # 已知事实（当前时空点检索注入）
    # ------------------------------------------------------------------
    def known_facts(
        self,
        book_id: str,
        up_to_order: int | None = None,
        max_entities: int = 15,
        max_relations: int = 20,
        max_events: int = 8,
    ) -> dict[str, list[Any]]:
        """当前时空点已知事实：最近出现实体 + 其间关系 + 最近事件。

        up_to_order：截止章节序号（写作第 N 章时注入 ≤N 的已知事实）。
        """
        where = "book_id=?"
        args: list[Any] = [book_id]
        if up_to_order is not None:
            where += " AND last_order<=?"
            args.append(up_to_order)
        # S37：最近 N×2/3 + 高频 N/3 混合（高频=出场章节数多=贯穿主线，保证早期核心不丢）
        n_recent = max(1, int(max_entities * 2 / 3))
        n_high = max_entities - n_recent
        rows = self._conn.execute(
            f"SELECT * FROM graph_entities WHERE {where} "
            "ORDER BY last_order DESC, rowid DESC LIMIT ?",
            (*args, n_recent),
        ).fetchall()
        recent_ids = [r["id"] for r in rows]
        if n_high > 0:
            placeholders = ",".join("?" * len(recent_ids)) or "NULL"
            extra = self._conn.execute(
                f"SELECT * FROM graph_entities WHERE {where} AND id NOT IN ({placeholders}) "
                "ORDER BY weight DESC, last_order DESC LIMIT ?",
                (*args, *recent_ids, n_high),
            ).fetchall()
            rows = rows + extra
        entities = [self._entity_from_row(r) for r in rows]
        ids = {e.id for e in entities}
        rels = [r for r in self.list_relations(book_id) if r.from_id in ids and r.to_id in ids][
            :max_relations
        ]

        ewhere = "book_id=?"
        eargs: list[Any] = [book_id]
        if up_to_order is not None:
            ewhere += " AND chapter_order<=?"
            eargs.append(up_to_order)
        erows = self._conn.execute(
            f"SELECT * FROM graph_events WHERE {ewhere} "
            "ORDER BY chapter_order DESC, rowid DESC LIMIT ?",
            (*eargs, max_events),
        ).fetchall()
        events = [self._event_from_row(r) for r in erows]
        return {"entities": entities, "relations": rels, "events": events}

    def ingest_chapter(
        self,
        book_id: str,
        chapter_ref: str,
        chapter_order: int,
        extraction: object,
        line: str = "main",
    ) -> None:
        """把抽取结果幂等落库（实体合并/关系三元组去重/事件替换）。

        引用完整性：关系/事件里引用但未被抽出的名字，自动补建"设定"占位实体。
        """
        entities = getattr(extraction, "entities", [])
        relations = getattr(extraction, "relations", [])
        events = getattr(extraction, "events", [])
        for e in entities:
            self.upsert_entity(
                book_id,
                e.name,
                e.entity_type,
                e.aliases,
                e.description,
                chapter_ref,
                chapter_order,
                getattr(e, "state", ""),
                line,
            )
        # 补建引用缺失实体（引用完整性）
        referenced: list[str] = []
        for r in relations:
            referenced.extend([r.from_name, r.to_name])
        for ev in events:
            referenced.extend(ev.involved)
        for name in referenced:
            if not self.get_entity(book_id, name):
                self.upsert_entity(
                    book_id, name, "设定", [], "", chapter_ref, chapter_order, "", line
                )
        # S20：已有实体状态更新（仅更新已存在实体的 state，不建新实体）
        states = getattr(extraction, "states", [])
        for st in states:
            if not self.get_entity(book_id, st.name):
                continue  # states 语义=已有实体；不存在则跳过（防误建）
            self.upsert_entity(
                book_id,
                st.name,
                "",
                None,
                "",
                chapter_ref,
                chapter_order,
                st.state,
                line,
            )
        for r in relations:
            self.upsert_relation(
                book_id, r.from_name, r.to_name, r.rel_type, r.description, chapter_ref
            )
        for ev in events:
            self.upsert_event(
                book_id,
                chapter_ref,
                chapter_order,
                ev.time_point or chapter_ref,
                ev.label,
                ev.description,
                ev.involved,
            )

    def _ensure_weight_column(self) -> None:
        """S37：旧库 ALTER 补 weight 列（老数据 weight=1 起步，后续按新逻辑累计）。"""
        with self._lock:
            cols = [r[1] for r in self._conn.execute("PRAGMA table_info(graph_entities)")]
            if "weight" not in cols:
                self._conn.execute(
                    "ALTER TABLE graph_entities ADD COLUMN weight INTEGER NOT NULL DEFAULT 0"
                )
                self._conn.execute("UPDATE graph_entities SET weight=1 WHERE weight=0")
                self._conn.commit()

    def rebuild_fts(self) -> None:
        """重建 FTS 派生索引（可恢复）。"""
        with self._lock:
            self._conn.execute("DELETE FROM graph_entities_fts")
            for r in self._conn.execute("SELECT id, name, aliases FROM graph_entities").fetchall():
                self._conn.execute(
                    "INSERT INTO graph_entities_fts (name, aliases, id) VALUES (?,?,?)",
                    (r["name"], r["aliases"], r["id"]),
                )
            self._conn.commit()

    # ------------------------------------------------------------------
    # 行转换
    # ------------------------------------------------------------------
    @staticmethod
    def _entity_from_row(row: sqlite3.Row) -> Entity:
        return Entity(
            id=row["id"],
            book_id=row["book_id"],
            entity_type=row["entity_type"],
            name=row["name"],
            aliases=json.loads(row["aliases"] or "[]"),
            description=row["description"],
            state=row["state"] or "",
            first_chapter=row["first_chapter"],
            last_chapter=row["last_chapter"],
            first_order=row["first_order"],
            last_order=row["last_order"],
            weight=int(row["weight"] or 0),
            lines=json.loads(row["lines"] or '["main"]'),
        )

    @staticmethod
    def _relation_from_row(row: sqlite3.Row) -> Relation:
        return Relation(
            id=row["id"],
            book_id=row["book_id"],
            from_id=row["from_id"],
            from_name=row["from_name"],
            to_id=row["to_id"],
            to_name=row["to_name"],
            rel_type=row["rel_type"],
            description=row["description"],
            chapter_ref=row["chapter_ref"],
        )

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> GraphEvent:
        return GraphEvent(
            id=row["id"],
            book_id=row["book_id"],
            chapter_ref=row["chapter_ref"],
            chapter_order=row["chapter_order"],
            time_point=row["time_point"],
            label=row["label"],
            description=row["description"],
            involved=json.loads(row["involved"] or "[]"),
        )
