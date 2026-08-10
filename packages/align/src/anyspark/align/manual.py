"""
anyspark.align.manual — 说明书（对齐的载体）：数据模型 + SQLite 存储。

条目元数据（DESIGN 第 6 节）：
    内容（自然语言短句）+ 来源(自动提炼|用户手写) + 置信度(0-1) + 活跃度(高|中|低) + 锁定状态
分层：项目说明书（每本书，主体）/ 全局说明书（用户级，极小化）
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

# 条目来源 / 活跃度
Source = Literal["auto", "user"]
Activity = Literal["high", "medium", "low"]
# 条目类别（S50 心智分类：协作=怎么配合/文风=怎么写/习惯=行为习惯）
# 心智模型=会话规划器：协作类指导主循环装配，文风/习惯类不再注入写作工具
Category = Literal["collab", "style", "habit"]
# 说明书层级
Scope = Literal["project", "global"]


# S55 合并式新增：关键词提取 + 内容合并（机制硬编码，治碎片）
# 中文偏好条目用双字窗口提取关键词（对 2 字词/短语有效，模型无关）
def keyword_set(content: str) -> set[str]:
    """从自然语言条目里提取关键词集合（双字窗口，去停用词）。"""
    text = content.replace(" ", "").replace("：", "").replace("（", "").replace("）", "")
    kws: set[str] = set()
    for i in range(len(text) - 1):
        w = text[i : i + 2]
        # 过滤明显停用词/无意义双字
        if all("\u4e00" <= ch <= "\u9fff" for ch in w):
            kws.add(w)
    return kws


def _merge_contents(old: str, new: str) -> str:
    """合并两条同主题条目内容：保留原有 + 追加新信息（去重）。"""
    if new in old:
        return old
    if old in new:
        return new
    return f"{old}；{new}"


@dataclass
class ManualEntry:
    """说明书的一条条目。"""

    content: str
    source: Source = "auto"
    confidence: float = 0.5
    activity: Activity = "medium"
    locked: bool = False
    scope: Scope = "project"
    book_id: str = "main"  # scope=global 时忽略
    category: Category = "style"  # S50：collab(协作)/style(文风)/habit(习惯)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=lambda: _now())
    updated_at: str = field(default_factory=lambda: _now())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "source": self.source,
            "confidence": self.confidence,
            "activity": self.activity,
            "locked": self.locked,
            "scope": self.scope,
            "book_id": self.book_id,
            "category": self.category,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


_NoticeList = list  # 类型别名：绕开 ManualStore.list 方法遮蔽（S74c 注解用）


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ManualStore:
    """说明书存储（SQLite）：项目级 + 全局级条目。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db, check_same_thread=False)
        self._lock = threading.Lock()
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS manual_entries (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'auto',
                    confidence REAL NOT NULL DEFAULT 0.5,
                    activity TEXT NOT NULL DEFAULT 'medium',
                    locked INTEGER NOT NULL DEFAULT 0,
                    scope TEXT NOT NULL DEFAULT 'project',
                    book_id TEXT NOT NULL DEFAULT 'main',
                    category TEXT NOT NULL DEFAULT 'style',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            # S50 ALTER 兼容：旧库无 category 列则补（默认 style 文风）
            cols = {r[1] for r in self._conn.execute("PRAGMA table_info(manual_entries)")}
            if "category" not in cols:
                self._conn.execute(
                    "ALTER TABLE manual_entries ADD COLUMN category TEXT NOT NULL DEFAULT 'style'"
                )
            # S74c 心智变更通知：update/delete 落通知（会话注入提醒，用户知情+指导权）
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS manual_notices (
                    id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,           -- add | update | delete
                    entry_id TEXT DEFAULT '',
                    old_content TEXT DEFAULT '',    -- 变更前（update/delete 用）
                    new_content TEXT DEFAULT '',    -- 变更后（add/update 用）
                    category TEXT DEFAULT '',
                    scope TEXT DEFAULT 'project',
                    book_id TEXT DEFAULT 'main',
                    created_at TEXT NOT NULL,
                    read INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self._conn.commit()

    def add(self, entry: ManualEntry) -> ManualEntry:
        with self._lock:
            self._conn.execute(
                "INSERT INTO manual_entries (id, content, source, confidence, activity, "
                "locked, scope, book_id, category, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    entry.id,
                    entry.content,
                    entry.source,
                    entry.confidence,
                    entry.activity,
                    1 if entry.locked else 0,
                    entry.scope,
                    entry.book_id,
                    entry.category,
                    entry.created_at,
                    entry.updated_at,
                ),
            )
            self._conn.commit()
        return entry

    def merge_add(self, entry: ManualEntry) -> tuple[ManualEntry, bool]:
        """S55 合并式新增：同 scope+category 且关键词重叠的现有条目 → 合并进现有条目。

        治碎片（Hermes 借鉴：类级条目，非一次性窄条目）：
        - 重叠判定：双字窗口关键词交集 ≥ 3（内容自然语言，机制硬编码）
        - 合并语义：内容保留原有 + 追加新信息（去重短句）、置信度取 max、活跃度升 high
        - 锁定条目不合并（用户主权）；重叠不足 → 普通新增
        返回 (条目, 是否发生合并)。
        """
        existing = self.list(entry.scope, entry.book_id)
        candidates = [e for e in existing if e.category == entry.category and not e.locked]
        new_kws = keyword_set(entry.content)
        for e in candidates:
            old_kws = keyword_set(e.content)
            overlap = new_kws & old_kws
            if len(overlap) >= 3:  # 至少 3 个双字短语重叠才判定同类（区分同主题/仅共享通用词）
                merged = self.update(
                    e.id,
                    content=_merge_contents(e.content, entry.content),
                    confidence=max(e.confidence, entry.confidence),
                )
                if merged is None:
                    merged = e
                self._touch_activity(merged.id, "high")
                return merged, True
        return self.add(entry), False

    def _touch_activity(self, entry_id: str, activity: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE manual_entries SET activity=?, updated_at=? WHERE id=?",
                (activity, _now(), entry_id),
            )
            self._conn.commit()

    def dedupe(self, scope: Scope = "project", book_id: str = "main") -> int:
        """S55 清理历史重复：同 scope+category 且关键词重叠 ≥2 的条目两两合并。

        保留锁定条目不合并（用户主权）；返回合并掉的条目数。
        贪心两两合并：对每对同类条目，关键词交集 ≥3 即并入置信度更高者
        （内容拼接去重，置信度取 max）。
        """
        entries = [e for e in self.list(scope, book_id) if not e.locked]
        removed = 0
        i = 0
        while i < len(entries):
            primary = entries[i]
            j = i + 1
            while j < len(entries):
                dup = entries[j]
                if dup.category == primary.category and dup.id != primary.id:
                    overlap = keyword_set(primary.content) & keyword_set(dup.content)
                    if len(overlap) >= 3:
                        # 主条目取置信度高者；低者并入后删除
                        if dup.confidence > primary.confidence:
                            keep, drop = dup, primary
                        else:
                            keep, drop = primary, dup
                        merged = _merge_contents(keep.content, drop.content)
                        self.update(
                            keep.id,
                            content=merged,
                            confidence=max(keep.confidence, drop.confidence),
                        )
                        self.delete(drop.id)
                        # 更新循环内引用：primary 若被删，换成 keep
                        if primary.id == drop.id:
                            primary = keep
                        entries.pop(j)
                        removed += 1
                        continue
                j += 1
            i += 1
        return removed

    def decay_stale(self, days_high: int = 30, days_medium: int = 90) -> int:
        """活跃度衰减（DESIGN §12.18 元数据收敛："活跃度衰减沉没冷条"）。

        未锁定条目按最后触达（updated_at）降级：high → medium（超过 days_high 天）
        → low（超过 days_medium 天）；low 不再降；锁定条目不降（用户主权）。
        衰减不刷新 updated_at（时间戳是"最后触达"，降级不是触达），且不自动删除
        ——冷条沉没在披露排序之后（_key_entries 活跃度优先），用户可手动清理
        （已有 DELETE）。机制硬编码；触发：list() 惰性执行 + 可显式调用。
        返回降级条目数。
        """
        from datetime import UTC as _UTC
        from datetime import datetime as _dt
        from datetime import timedelta as _td

        now = _dt.now(_UTC)
        high_cutoff = (now - _td(days=days_high)).isoformat()
        medium_cutoff = (now - _td(days=days_medium)).isoformat()
        with self._lock:
            # high → medium：超过 days_high 天未触达（不刷新时间戳，供下一级继续判定）
            c1 = self._conn.execute(
                "UPDATE manual_entries SET activity='medium' "
                "WHERE locked=0 AND activity='high' AND updated_at < ?",
                (high_cutoff,),
            ).rowcount
            # medium → low：超过 days_medium 天未触达（基于原始时间戳继续降）
            c2 = self._conn.execute(
                "UPDATE manual_entries SET activity='low' "
                "WHERE locked=0 AND activity='medium' AND updated_at < ?",
                (medium_cutoff,),
            ).rowcount
            self._conn.commit()
        return int(c1) + int(c2)

    def list(self, scope: Scope, book_id: str = "main") -> list[ManualEntry]:
        # 惰性活跃度衰减（S61：访问时收敛冷条——披露永远基于最新活跃度）
        self.decay_stale()
        with self._lock:
            if scope == "project":
                rows = self._conn.execute(
                    "SELECT * FROM manual_entries WHERE scope='project' AND book_id=? "
                    "ORDER BY confidence DESC, updated_at DESC",
                    (book_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM manual_entries WHERE scope='global' "
                    "ORDER BY confidence DESC, updated_at DESC"
                ).fetchall()
        return [_entry_from_row(r) for r in rows]

    def get(self, entry_id: str) -> ManualEntry | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM manual_entries WHERE id=?", (entry_id,)
            ).fetchone()
        return _entry_from_row(row) if row else None

    def update(
        self,
        entry_id: str,
        content: str | None = None,
        confidence: float | None = None,
        category: str | None = None,
    ) -> ManualEntry | None:
        """更新条目内容/置信度/类别（锁定条目不可改，用户主权）。

        S74c：实际变化（内容/分类）时写变更通知——用户知情（会话注入提醒）。
        """
        entry = self.get(entry_id)
        if entry is None:
            return None
        if entry.locked:
            return entry
        changed = (content is not None and content != entry.content) or (
            category is not None and category in ("collab", "style", "habit")
            and category != entry.category
        )
        with self._lock:
            sets: list[str] = []
            params: list[Any] = []
            if content is not None:
                sets.append("content=?")
                params.append(content)
            if confidence is not None:
                sets.append("confidence=?")
                params.append(confidence)
            if category is not None and category in ("collab", "style", "habit"):
                sets.append("category=?")
                params.append(category)
            sets.append("updated_at=?")
            params.append(_now())
            params.append(entry_id)
            self._conn.execute(f"UPDATE manual_entries SET {', '.join(sets)} WHERE id=?", params)
            if changed:
                self._conn.execute(
                    "INSERT INTO manual_notices"
                    " (id, action, entry_id, old_content, new_content, category, scope,"
                    "  book_id, created_at, read)"
                    " VALUES (?, 'update', ?, ?, ?, ?, ?, ?, ?, 0)",
                    (
                        uuid.uuid4().hex,
                        entry_id,
                        entry.content,
                        content or entry.content,
                        category or entry.category,
                        entry.scope,
                        entry.book_id,
                        _now(),
                    ),
                )
            self._conn.commit()
        return self.get(entry_id)

    def set_locked(self, entry_id: str, locked: bool) -> ManualEntry | None:
        with self._lock:
            self._conn.execute(
                "UPDATE manual_entries SET locked=?, updated_at=? WHERE id=?",
                (1 if locked else 0, _now(), entry_id),
            )
            self._conn.commit()
        return self.get(entry_id)

    def delete(self, entry_id: str) -> None:
        """删除条目（S74c：先取旧内容写变更通知，再删——用户知情）。"""
        entry = self.get(entry_id)
        with self._lock:
            if entry is not None:
                self._conn.execute(
                    "INSERT INTO manual_notices"
                    " (id, action, entry_id, old_content, new_content, category, scope,"
                    "  book_id, created_at, read)"
                    " VALUES (?, 'delete', ?, ?, '', ?, ?, ?, ?, 0)",
                    (
                        uuid.uuid4().hex,
                        entry_id,
                        entry.content,
                        entry.category,
                        entry.scope,
                        entry.book_id,
                        _now(),
                    ),
                )
            self._conn.execute("DELETE FROM manual_entries WHERE id=?", (entry_id,))
            self._conn.commit()

    # ------------------------------------------------------------------
    # S74c 变更通知（用户知情 + 指导权；会话注入提醒，API 供前端展示）
    # ------------------------------------------------------------------
    def unread_notices(self, book_id: str = "main") -> _NoticeList[dict[str, Any]]:
        """未读变更通知（会话注入渲染用）。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM manual_notices WHERE book_id=? AND read=0"
                " ORDER BY created_at",
                (book_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_notices_read(self, book_id: str = "main") -> int:
        """标记未读通知为已读（会话注入呈现后调用）。"""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE manual_notices SET read=1 WHERE book_id=? AND read=0", (book_id,)
            )
            self._conn.commit()
        return cur.rowcount

    def list_notices(self, book_id: str = "main", limit: int = 20) -> _NoticeList[dict[str, Any]]:
        """通知列表（API 供前端展示，含已读）。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM manual_notices WHERE book_id=? ORDER BY created_at DESC LIMIT ?",
                (book_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()


def _entry_from_row(row: sqlite3.Row) -> ManualEntry:
    return ManualEntry(
        id=row["id"],
        content=row["content"],
        source=row["source"],
        confidence=row["confidence"],
        activity=row["activity"],
        locked=bool(row["locked"]),
        scope=row["scope"],
        book_id=row["book_id"],
        category=row["category"],  # S50
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def render_manual(entries: list[ManualEntry], title: str = "写作说明书") -> str:
    """把条目渲染成可读的自然语言文档（跨模型可读，注入上下文用）。"""
    lines = [
        f"# {title}",
        "",
        "使用说明：以下为作者写作偏好/约束条目，写作时必须遵守；"
        "带 [锁定] 的条目为作者确认的硬规则，不得违反。",
    ]
    if not entries:
        lines.append("（暂无条目）")
    for e in entries:
        tag = " [锁定]" if e.locked else ""
        source_tag = "自动提炼" if e.source == "auto" else "作者手写"
        lines.append(f"- {e.content}{tag}（{source_tag}，置信度 {e.confidence:.1f}）")
    return "\n".join(lines)
