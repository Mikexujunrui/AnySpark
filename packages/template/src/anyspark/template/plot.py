"""
anyspark.template.plot — 关键点图谱（T2 阶段 3，作品级规划，可选深入）。

DESIGN：图谱=跨章长期记忆（主线冲突/角色弧/情感核/世界规则/情绪峰值/伏笔/节奏，
网状非大纲）；每章写作时注入其当前状态（哪些推进/哪些没收）。不强制：小白可跳过。
本模块：存储 + LLM 生成草案（半硬编码：存在机制硬编码，图谱内容模型生成）。
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from anyspark.core import Message, Model
from anyspark.core.db import connect as sqlite_connect

# 关键点类别（自然语言，模型无关）
PLOT_CATEGORIES = ("主线冲突", "角色弧", "情感核", "世界规则", "情绪峰值", "伏笔", "节奏")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _age_text(p: PlotPoint, current_order: int) -> str:
    """S31 老龄化：中性事实提示——"（已开放 N 章）"。
    不设阈值、不评判（开放久可能是故意留到结局）；只在知道登记章时标年龄。"""
    if current_order <= 0 or p.planted_order <= 0:
        return ""
    age = current_order - p.planted_order
    if age <= 0:
        return ""
    return f"（已开放 {age} 章）"


@dataclass
class PlotPoint:
    """一个关键点（可增删改、标注在意/不需要——操作即对齐信号）。

    S31 A/B 分级：
    - priority="must"（剧情钩子）：作者/AI 主动声明的**主线承诺**（对读者的契约）——
      必须回收，注入明确列出、超期强烈提醒。默认不升级，机制不裁决内容重要性。
    - priority="soft"（细节线索）：写作中自然捕捉/生成的铺垫细节——
      回收是加分、不回收无损，影子层旁观不打扰。
    - resolved_chapter：回收章节（resolved 时记录）——完整书导入归档时验证结构。
    """

    id: str
    book_id: str
    category: str
    content: str
    chapter_ref: str = ""  # 关联章节（可空=全局）
    status: str = "open"  # open|resolved
    attention: str = "care"  # care|ignore（用户标注在意/不需要；ignore 不注入不回收）
    priority: str = "soft"  # S31: must（剧情钩子，必须回收）| soft（细节线索）
    resolved_chapter: str = ""  # S31: 回收章节
    planted_order: int = 0  # S31 老龄化：登记时的章节序号（开放时长 = 当前章 - planted_order）
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "book_id": self.book_id,
            "category": self.category,
            "content": self.content,
            "chapter_ref": self.chapter_ref,
            "status": self.status,
            "attention": self.attention,
            "priority": self.priority,
            "resolved_chapter": self.resolved_chapter,
            "planted_order": self.planted_order,
            "created_at": self.created_at,
        }


class PlotStore:
    """关键点图谱存储（SQLite）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        # S79：连接配置收敛到 anyspark.core.db.connect
        self._conn = sqlite_connect(self._db)
        self._lock = threading.Lock()
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS plot_points (
                id TEXT PRIMARY KEY,
                book_id TEXT NOT NULL,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                chapter_ref TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                attention TEXT NOT NULL DEFAULT 'care',
                priority TEXT NOT NULL DEFAULT 'soft',
                resolved_chapter TEXT NOT NULL DEFAULT '',
                planted_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_plot_book ON plot_points(book_id, category);
            """
        )
        # 旧库兼容：attention（S17）/ priority + resolved_chapter（S31）
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(plot_points)")}
        if "attention" not in cols:
            self._conn.execute(
                "ALTER TABLE plot_points ADD COLUMN attention TEXT NOT NULL DEFAULT 'care'"
            )
        if "priority" not in cols:
            self._conn.execute(
                "ALTER TABLE plot_points ADD COLUMN priority TEXT NOT NULL DEFAULT 'soft'"
            )
        if "resolved_chapter" not in cols:
            self._conn.execute(
                "ALTER TABLE plot_points ADD COLUMN resolved_chapter TEXT NOT NULL DEFAULT ''"
            )
        if "planted_order" not in cols:
            self._conn.execute(
                "ALTER TABLE plot_points ADD COLUMN planted_order INTEGER NOT NULL DEFAULT 0"
            )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def add(
        self,
        book_id: str,
        category: str,
        content: str,
        chapter_ref: str = "",
        attention: str = "care",
        priority: str = "soft",
        planted_order: int = 0,
    ) -> PlotPoint:
        pid = uuid.uuid4().hex
        cat = category if category in PLOT_CATEGORIES else "主线冲突"
        att = attention if attention in ("care", "ignore") else "care"
        pri = priority if priority in ("must", "soft") else "soft"
        now = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO plot_points (id, book_id, category, content, chapter_ref, "
                "status, attention, priority, resolved_chapter, planted_order, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (pid, book_id, cat, content, chapter_ref, "open", att, pri, "", planted_order, now),
            )
            self._conn.commit()
        return PlotPoint(
            pid, book_id, cat, content, chapter_ref, "open", att, pri, "", planted_order, now
        )

    def list_points(self, book_id: str = "main") -> list[PlotPoint]:
        rows = self._conn.execute(
            "SELECT * FROM plot_points WHERE book_id=? ORDER BY rowid", (book_id,)
        ).fetchall()
        return [
            PlotPoint(
                id=r["id"],
                book_id=r["book_id"],
                category=r["category"],
                content=r["content"],
                chapter_ref=r["chapter_ref"],
                status=r["status"],
                attention=r["attention"],
                priority=r["priority"],
                resolved_chapter=r["resolved_chapter"],
                planted_order=r["planted_order"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def update(
        self,
        plot_id: str,
        *,
        status: str | None = None,
        attention: str | None = None,
        priority: str | None = None,
        resolved_chapter: str | None = None,
        planted_order: int | None = None,
        chapter_ref: str | None = None,
    ) -> PlotPoint | None:
        """更新状态/关注度/优先级/回收章节（None=不变）。"""
        sets: list[str] = []
        params: list[Any] = []
        if status is not None:
            sets.append("status=?")
            params.append(status if status in ("open", "resolved") else "open")
        if attention is not None:
            sets.append("attention=?")
            params.append(attention if attention in ("care", "ignore") else "care")
        if priority is not None:
            sets.append("priority=?")
            params.append(priority if priority in ("must", "soft") else "soft")
        if resolved_chapter is not None:
            sets.append("resolved_chapter=?")
            params.append(resolved_chapter)
        if planted_order is not None:
            sets.append("planted_order=?")
            params.append(planted_order)
        if chapter_ref is not None:
            sets.append("chapter_ref=?")
            params.append(chapter_ref)
        if not sets:
            return self.get(plot_id)
        params.append(plot_id)
        with self._lock:
            self._conn.execute(f"UPDATE plot_points SET {','.join(sets)} WHERE id=?", params)
            self._conn.commit()
        return self.get(plot_id)

    def get(self, plot_id: str) -> PlotPoint | None:
        row = self._conn.execute("SELECT * FROM plot_points WHERE id=?", (plot_id,)).fetchone()
        if not row:
            return None
        return PlotPoint(
            id=row["id"],
            book_id=row["book_id"],
            category=row["category"],
            content=row["content"],
            chapter_ref=row["chapter_ref"],
            status=row["status"],
            attention=row["attention"],
            priority=row["priority"],
            resolved_chapter=row["resolved_chapter"],
            planted_order=row["planted_order"],
            created_at=row["created_at"],
        )

    def delete(self, plot_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM plot_points WHERE id=?", (plot_id,))
            self._conn.commit()

    def render(self, book_id: str = "main", max_resolved: int = 3, current_order: int = 0) -> str:
        """渲染成注入块（当前推进状态，供写作时注入）。

        S31 A/B 分级（对齐哲学：系统只对作者自己升级的承诺负责，不评价细节线索）：
        - attention=ignore 的条目不注入（用户标注"不需要"=不惦记）
        - **must 钩子（作者承诺，必须回收）明确列出** + **开放时长（老龄化，中性事实）**
        - soft 细节线索只汇总数量（旁观不打扰——回收率不是质量指标）
        - resolved 只列最近 max_resolved 条（省 token，提示推进即可）
        current_order：当前章节序号（计算开放时长用；0=未知则不标年龄）
        """
        points = [p for p in self.list_points(book_id) if p.attention != "ignore"]
        if not points:
            return ""
        open_must = [p for p in points if p.status == "open" and p.priority == "must"]
        open_soft = [p for p in points if p.status == "open" and p.priority == "soft"]
        resolved_pts = [p for p in points if p.status == "resolved"][-max_resolved:]
        lines = ["# 关键点图谱（当前推进状态）"]
        if open_must:
            lines.append("⚠ 主线钩子（作者承诺，必须回收）：")
            for p in open_must:
                ref = f"（{p.chapter_ref}）" if p.chapter_ref else ""
                age = _age_text(p, current_order)
                lines.append(f"- ★ [{p.category}] {p.content}{ref}{age}")
        if open_soft:
            lines.append(f"另有 {len(open_soft)} 条细节线索开放中（写作时自然呼应即可）。")
        if resolved_pts:
            lines.append("已回收：")
            for p in resolved_pts:
                ref = f"（{p.chapter_ref}）" if p.chapter_ref else ""
                lines.append(f"- ✓ [{p.category}] {p.content}{ref}")
        return "\n".join(lines)

    def open_must(self, book_id: str = "main", current_order: int = 0) -> list[PlotPoint]:
        """S31：未回收的主线钩子（作者承诺清单——wrapup/收尾检查用）。
        current_order：当前章节序号（老龄化提示用）。"""
        points = self.list_points(book_id)
        return [
            p
            for p in points
            if p.status == "open" and p.priority == "must" and p.attention != "ignore"
        ]

    def resolve_all(self, book_id: str = "main", chapter_ref: str = "全书导入") -> int:
        """S31：完整书导入归档——所有 open 标 resolved + 记录归档章。

        语义：完整导入的书已写完，伏笔都已揭开——提取的价值是归档验证，
        不是追踪。不输出"回收率"（伏笔管理烂不影响作品伟大性，不做质量评分）。
        """
        n = 0
        for p in self.list_points(book_id):
            if p.status == "open":
                self.update(p.id, status="resolved", resolved_chapter=chapter_ref)
                n += 1
        return n


PLOT_PROMPT = (
    "你是小说结构规划师。基于下面的作品设定与已写章节，生成**关键点图谱草案**（网状非大纲）：\n"
    "类别：主线冲突 / 角色弧 / 情感核 / 世界规则 / 情绪峰值 / 伏笔 / 节奏。\n"
    "每个关键点一句话，具体可操作（标出它大致落在哪章或全局）。\n"
    "输出（严格 JSON 数组，不要其它文字）：\n"
    '[{"category": "主线冲突", "content": "…", "chapter_ref": "第3章"}]\n\n'
    "作品设定：\n"
)


class PlotGenerator:
    """LLM 生成关键点图谱草案（模型无关）。"""

    def __init__(self, model: Model) -> None:
        self._model = model

    def generate(self, book_id: str, store: PlotStore, settings: str = "") -> list[PlotPoint]:
        prompt = (
            PLOT_PROMPT + f"\n{settings[:2000]}\n\n已有关键点：\n{store.render(book_id)[:1500]}"
        )
        out = self._model.respond(
            [Message(role="system", content=prompt)],
            [],
        )
        points: list[PlotPoint] = []
        import re

        cleaned = out.text.strip()
        fence = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
        if fence:
            cleaned = fence.group(1)
        start, end = cleaned.find("["), cleaned.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(cleaned[start : end + 1])
                if isinstance(data, list):
                    for item in data:
                        if not isinstance(item, dict):
                            continue
                        content = str(item.get("content", "")).strip()
                        if not content:
                            continue
                        points.append(
                            store.add(
                                book_id,
                                str(item.get("category", "主线冲突")),
                                content,
                                str(item.get("chapter_ref", "")),
                            )
                        )
            except json.JSONDecodeError:
                pass
        return points


RESOLVE_PROMPT = (
    "你是小说结构分析师。读下面这一章正文，判断其中**揭开了哪些进行中的关键点（伏笔/悬念）**。\n"
    "只回收真正被本章明确揭示/回应/解决的；未被涉及的不要列。\n"
    "输出（严格 JSON，不要其它文字）：\n"
    '{"resolved": [{"content": "被揭开的关键点原文（与列表高度一致）", '
    '"evidence": "章节中的证据（一句话）"}]}\n\n'
    "进行中的关键点列表：\n"
)


class PlotResolver:
    """伏笔自动回收（半硬编码）：章节落盘后，LLM 判断本章揭开哪些 open 关键点 → resolved。

    机制硬编码（匹配/更新），内容模型生成（证据/判断）。失败静默（不影响写作主链路）。
    """

    def __init__(self, model: Model) -> None:
        self._model = model

    def resolve(self, book_id: str, title: str, content: str, store: PlotStore) -> list[str]:
        """返回被回收的关键点 content 列表（失败返回空，绝不抛异常）。"""
        open_pts = [
            p for p in store.list_points(book_id) if p.status == "open" and p.attention != "ignore"
        ]
        if not open_pts:
            return []
        listing = "\n".join(f"- [{p.category}] {p.content}" for p in open_pts)
        prompt = RESOLVE_PROMPT + listing + f"\n\n章节《{title}》正文：\n{content[:6000]}"
        try:
            out = self._model.respond(
                [Message(role="system", content=prompt)],
                [],
            )
            return self._match(out.text, open_pts, title, store)
        except Exception:
            return []

    def _match(
        self,
        raw: str,
        open_pts: list[PlotPoint],
        title: str,
        store: PlotStore,
    ) -> list[str]:
        """宽容解析 + 内容匹配（LLM 输出的 content 需与库中条目高度一致才回收，防误伤）。"""
        import re as _re

        cleaned = raw.strip()
        fence = _re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, _re.DOTALL)
        if fence:
            cleaned = fence.group(1)
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            return []
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return []
        resolved_content: list[str] = []
        items = data.get("resolved") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []
        for item in items:
            if not isinstance(item, dict):
                continue
            c = str(item.get("content", "")).strip()
            if not c:
                continue
            for p in open_pts:
                if _text_match(p.content, c):
                    store.update(p.id, status="resolved", chapter_ref=title)
                    resolved_content.append(p.content)
                    break
        return resolved_content


def _text_match(a: str, b: str) -> bool:
    """双向包含匹配（容忍 LLM 复述的细微差异）。"""
    na = re.sub(r"[\s，。、；：！？「」『』\"']+", "", a)
    nb = re.sub(r"[\s，。、；：！？「」『』\"']+", "", b)
    if not na or not nb:
        return False
    return na in nb or nb in na
