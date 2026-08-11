"""
anyspark.align.skills — 叙事技巧内容载体（S50：skill 重构为名实相符的叙事技巧）。

背景（主人拍板，DESIGN §12.17）：原 S43 把粒度感知/角色认知边界/氛围克制三条
不同源的内容（能动性机制 / 一致性硬约束 / 文风偏好）塞进"写作技巧"容器——
概念混杂、全放错筐。S50 重构：
- 旧三条按真实职责归位（粒度感知→agency 机制化 / 认知边界→check 基线 /
  氛围克制→manual 文风），从 skills 移除
- skills 只装真正的**叙事技巧**：用 名 + 一句话索引 + 完整技法 + 具体情形案例
  提升文笔文风（名实相符）
- 每条技巧 = { name, description（索引）, content（技法）, example（情形案例）,
  tags（场景标签）, enabled, order }

注入（渐进式披露，对齐 pi skills）：
- 索引常驻（description 一行）
- 内容按需：<5 条全量注入；多了之后按会话意图匹配 tags 选 2-3 条
- example 案例随 content 注入（提升文笔的关键：具体样例比抽象指令有效）

哲学边界：DEFAULT_SYSTEM = A 类过程控制底线（硬编码）；叙事技巧 = 内容（自然语言，可编辑）。
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# S62：不再在写入时截断 skill 描述（内容主权——用户/模型写的描述不损坏）；
# 索引渲染层对超长描述做展示省略（render_skill_index），存储永远保全文。

# 默认叙事技巧（种子；内容自然语言，可增删改——名+技法+情形案例三段式）
DEFAULT_SKILLS: list[dict[str, str]] = [
    {
        "name": "镜头感与视角",
        "description": "动作/情感用镜头语言呈现：近景给细节、远景给氛围；谁在看决定写到多细。",
        "content": (
            "把叙事当作镜头：情绪爆点给近景特写（具体的动作、物件、身体的细微反应），"
            "场景转换给远景/环境氛围；每段明确'此刻镜头对着谁'，视角不漂移。"
            "用细节代替情绪直述——读者从动作里读到感受，而不是被告诉感受。"
        ),
        "example": ("她想逃却迈不动脚——写特写'鞋尖碾着地板，磨出吱呀声'，比写'她很害怕'有效。"),
        "tags": "开篇,心理,动作",
    },
    {
        "name": "对白机锋",
        "description": "对白不直给信息，让每句话负载潜台词与立场冲突。",
        "content": (
            "对话不是信息问答：每句对白都应携带说话人的立场、情绪、隐瞒或试探。"
            "避免'你叫什么''我叫张三'式的问答流水账；用答非所问、重复、停顿"
            "制造张力。人物说的话要符合其身份与说话方式（不千人一面）。"
        ),
        "example": ("他问'你确定？'她答'我确定过。'——一个词之差透出过往，比直白解释有力。"),
        "tags": "对白,冲突",
    },
    {
        "name": "节奏控制",
        "description": "紧张处用短句+省略连接词，舒缓处用长句铺陈；节奏服务情绪。",
        "content": (
            "句子长度即情绪刻度：激烈/紧迫段落用短句、碎片、省略连接词（'跑。撞。"
            "转身。'）；舒缓/沉思段落用长句、意象铺陈。整章要有节奏起伏，"
            "不能通篇同一密度——高密度动作之后给低密度喘息。"
        ),
        "example": (
            "追逃段落'跑。撞。转身。'对'晚风从梧桐叶间漏下，一寸一寸凉'——"
            "一快一慢，读者情绪跟着呼吸。"
        ),
        "tags": "打斗,高潮,过渡",
        "target": "both",  # S57：节奏既影响单句（写作层）又影响章节起伏（主循环层）
    },
]


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class WritingSkill:
    """一条叙事技巧（skill 式：描述常驻索引、正文+案例按需注入）。

    S57：target 分流——writing（文风/叙事技巧，注入写作调用）/ main（类型/结构
    指导，注入主循环决策）/ both（两者）。
    """

    name: str
    description: str
    content: str
    example: str = ""
    tags: str = ""
    target: str = "writing"  # writing | main | both（S57）
    enabled: bool = True
    order: int = 0
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "content": self.content,
            "example": self.example,
            "tags": self.tags,
            "target": self.target,
            "enabled": self.enabled,
            "order": self.order,
            "created_at": self.created_at,
        }

    def tag_list(self) -> list[str]:
        return [t.strip() for t in self.tags.split(",") if t.strip()]


class WritingSkillStore:
    """叙事技巧存储（SQLite）。"""

    def __init__(self, db_path: str | Path) -> None:
        self._db = str(db_path)
        Path(self._db).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db, check_same_thread=False, timeout=30)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._seed()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS writing_skills (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL,
                    example TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '',
                    target TEXT NOT NULL DEFAULT 'writing',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    order_index INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            # S54：skill 候选草稿（人工确认后转正进 writing_skills）
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS skill_drafts (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL,
                    example TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '',
                    target TEXT NOT NULL DEFAULT 'writing',
                    source TEXT NOT NULL DEFAULT 'manual',  -- manual|mental|signal
                    created_at TEXT NOT NULL
                )
                """
            )
            # S50 ALTER 兼容：旧库无 example/tags 列则补
            cols = {r[1] for r in self._conn.execute("PRAGMA table_info(writing_skills)")}
            if "example" not in cols:
                self._conn.execute(
                    "ALTER TABLE writing_skills ADD COLUMN example TEXT NOT NULL DEFAULT ''"
                )
            if "tags" not in cols:
                self._conn.execute(
                    "ALTER TABLE writing_skills ADD COLUMN tags TEXT NOT NULL DEFAULT ''"
                )
            # S57：target 列（旧库补默认 writing）
            if "target" not in cols:
                self._conn.execute(
                    "ALTER TABLE writing_skills ADD COLUMN target TEXT NOT NULL DEFAULT 'writing'"
                )
            # S57：skill_drafts 表同样补 target
            dcols = {r[1] for r in self._conn.execute("PRAGMA table_info(skill_drafts)")}
            if "target" not in dcols:
                self._conn.execute(
                    "ALTER TABLE skill_drafts ADD COLUMN target TEXT NOT NULL DEFAULT 'writing'"
                )
            self._conn.commit()

    def _seed(self) -> None:
        with self._lock:
            # 循环替代递归：旧库重播时避免锁重入（threading.Lock 不可重入）
            while True:
                n = self._conn.execute("SELECT COUNT(*) AS c FROM writing_skills").fetchone()["c"]
                if n == 0:
                    now = _now()
                    for i, s in enumerate(DEFAULT_SKILLS):
                        self._conn.execute(
                            "INSERT INTO writing_skills "
                            "(id, name, description, content, example, tags, target, enabled, "
                            "order_index, created_at) "
                            "VALUES (?,?,?,?,?,?,?,1,?,?)",
                            (
                                uuid.uuid4().hex,
                                s["name"],
                                s["description"],
                                s["content"],
                                s.get("example", ""),
                                s.get("tags", ""),
                                s.get("target", "writing"),
                                i,
                                now,
                            ),
                        )
                    self._conn.commit()
                    break
                # 旧库种子（粒度感知/角色认知边界/氛围克制）→ 清除重播新种子
                names = {
                    r["name"]
                    for r in self._conn.execute("SELECT name FROM writing_skills").fetchall()
                }
                if "粒度感知" in names or "角色认知边界" in names:
                    self._conn.execute("DELETE FROM writing_skills")
                    self._conn.commit()
                    continue  # 循环回到 n==0 分支重播
                self._conn.commit()
                break

    def list_skills(self) -> list[WritingSkill]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM writing_skills ORDER BY order_index, rowid"
            ).fetchall()
        return [_from_row(r) for r in rows]

    def revision(self) -> str:
        """S55 #3 注入缓存签名：内容变化 → 签名变化（增删改任一操作即失效）。

        签名覆盖全部可变列（name/description/content/example/enabled/order/tags/target），
        任何字段变化都会使缓存失效（S62 补：此前漏 tags/target，只改这两列时
        索引缓存不失效）。
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT name, description, content, example, enabled, order_index, "
                "tags, target FROM writing_skills"
            ).fetchall()
        sig = "".join(f"{r[0]}|{r[1]}|{r[2]}|{r[3]}|{r[5]}|{int(r[4])}|{r[6]}|{r[7]}" for r in rows)
        return sig

    def enabled(self) -> list[WritingSkill]:
        return [s for s in self.list_skills() if s.enabled]

    def add(
        self,
        name: str,
        description: str,
        content: str,
        example: str = "",
        tags: str = "",
        target: str = "writing",
    ) -> WritingSkill:
        target = target if target in ("writing", "main", "both") else "writing"
        with self._lock:
            max_order = self._conn.execute(
                "SELECT COALESCE(MAX(order_index), -1) AS m FROM writing_skills"
            ).fetchone()["m"]
            s = WritingSkill(
                name=name,
                description=description,
                content=content,
                example=example,
                tags=tags,
                target=target,
                order=int(max_order) + 1,
            )
            self._conn.execute(
                "INSERT INTO writing_skills "
                "(id, name, description, content, example, tags, target, enabled, "
                "order_index, created_at) "
                "VALUES (?,?,?,?,?,?,?,1,?,?)",
                (
                    s.id,
                    s.name,
                    s.description,
                    s.content,
                    s.example,
                    s.tags,
                    s.target,
                    s.order,
                    s.created_at,
                ),
            )
            self._conn.commit()
        return s

    def update(
        self,
        skill_id: str,
        name: str | None = None,
        description: str | None = None,
        content: str | None = None,
        example: str | None = None,
        tags: str | None = None,
        target: str | None = None,
        enabled: bool | None = None,
    ) -> WritingSkill | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM writing_skills WHERE id=?", (skill_id,)
            ).fetchone()
            if row is None:
                return None
            sets: list[str] = []
            params: list[Any] = []
            if name is not None:
                sets.append("name=?")
                params.append(name)
            if description is not None:
                sets.append("description=?")
                params.append(description)
            if content is not None:
                sets.append("content=?")
                params.append(content)
            if example is not None:
                sets.append("example=?")
                params.append(example)
            if tags is not None:
                sets.append("tags=?")
                params.append(tags)
            if target is not None and target in ("writing", "main", "both"):
                sets.append("target=?")
                params.append(target)
            if enabled is not None:
                sets.append("enabled=?")
                params.append(1 if enabled else 0)
            if sets:
                params.append(skill_id)
                self._conn.execute(
                    f"UPDATE writing_skills SET {', '.join(sets)} WHERE id=?", params
                )
                self._conn.commit()
        return self.get(skill_id)

    def get(self, skill_id: str) -> WritingSkill | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM writing_skills WHERE id=?", (skill_id,)
            ).fetchone()
        return _from_row(row) if row else None

    def delete(self, skill_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM writing_skills WHERE id=?", (skill_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()

    # -- S54 候选草稿（后台自动生成 → 人工确认转正） --
    def add_draft(
        self,
        name: str,
        description: str,
        content: str,
        example: str = "",
        tags: str = "",
        target: str = "writing",
        source: str = "manual",
    ) -> dict[str, Any] | None:
        """存一条 skill 候选草稿（未生效；人工确认后转正进 writing_skills）。"""
        target = target if target in ("writing", "main", "both") else "writing"
        with self._lock:
            # 草稿或正式技能已有同名 → 跳过（防重复堆叠）
            dup = self._conn.execute("SELECT 1 FROM skill_drafts WHERE name=?", (name,)).fetchone()
            if dup:
                return None
            dup2 = self._conn.execute(
                "SELECT 1 FROM writing_skills WHERE name=?", (name,)
            ).fetchone()
            if dup2:
                return None
            did = uuid.uuid4().hex
            self._conn.execute(
                "INSERT INTO skill_drafts "
                "(id, name, description, content, example, tags, target, source, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (did, name, description, content, example, tags, target, source, _now()),
            )
            self._conn.commit()
            return {"id": did, "name": name, "source": source, "target": target}

    def list_drafts(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM skill_drafts ORDER BY rowid DESC").fetchall()
        return [dict(r) for r in rows]

    def promote_draft(self, draft_id: str) -> WritingSkill | None:
        """人工确认：草稿转正进 writing_skills（并删除草稿）。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM skill_drafts WHERE id=?", (draft_id,)
            ).fetchone()
            if row is None:
                return None
            max_order = self._conn.execute(
                "SELECT COALESCE(MAX(order_index), -1) AS m FROM writing_skills"
            ).fetchone()["m"]
            s = WritingSkill(
                name=row["name"],
                description=row["description"],
                content=row["content"],
                example=row["example"],
                tags=row["tags"],
                target=row["target"],
                order=int(max_order) + 1,
            )
            self._conn.execute(
                "INSERT INTO writing_skills "
                "(id, name, description, content, example, tags, target, enabled, "
                "order_index, created_at) "
                "VALUES (?,?,?,?,?,?,?,1,?,?)",
                (
                    s.id,
                    s.name,
                    s.description,
                    s.content,
                    s.example,
                    s.tags,
                    s.target,
                    s.order,
                    s.created_at,
                ),
            )
            self._conn.execute("DELETE FROM skill_drafts WHERE id=?", (draft_id,))
            self._conn.commit()
        return s

    def delete_draft_by_id(self, draft_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM skill_drafts WHERE id=?", (draft_id,))
            self._conn.commit()
        return cur.rowcount > 0


def _from_row(row: sqlite3.Row) -> WritingSkill:
    return WritingSkill(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        content=row["content"],
        example=row["example"],
        tags=row["tags"],
        target=row["target"],  # S57
        enabled=bool(row["enabled"]),
        order=int(row["order_index"]),
        created_at=row["created_at"],
    )


_INDEX_DESC_ELIDE = 100  # 索引展示行描述省略阈值（仅渲染层，存储保全文）


def render_skill_index(skills: list[WritingSkill], target: str = "writing") -> str:
    """渲染技巧索引（对齐 pi skills：描述常驻，正文按需）。S57：按 target 过滤。

    S62：展示层省略超长描述（防索引块撑爆系统提示），**存储内容永不截断**——
    用户/模型写的 skill 描述是内容主权，全文保留，按需查询（skill_lookup）看全文。
    """
    enabled = [s for s in skills if s.enabled and _target_matches(s.target, target)]
    if not enabled:
        return ""
    lines = ["# 叙事技巧（可用：按需选用）"]
    for s in enabled:
        desc = s.description
        if len(desc) > _INDEX_DESC_ELIDE:
            desc = desc[:_INDEX_DESC_ELIDE] + "…（全文见 skill_lookup）"
        lines.append(f"- {s.name}：{desc}")
    return "\n".join(lines)


def _target_matches(skill_target: str, want: str) -> bool:
    """target 匹配：writing 目标收 writing/both；main 目标收 main/both。"""
    if want not in ("writing", "main"):
        return True
    return skill_target in (want, "both")


def render_skills_by_name(skills: list[WritingSkill], names: list[str]) -> str:
    """按名字渲染点名技巧的完整内容（技法 + 情形案例）。

    S60：主循环看到全部技巧索引（名字+描述）后，可在 write_chapter 的 skills 参数
    显式点名本次写作要运用的技巧——点名时按名精确匹配，找不到的忽略。
    写作调用是被执行方不自行选技巧：主循环点名了才注入（S61 删自动匹配兜底）。
    """
    want = {n.strip() for n in names if n.strip()}
    if not want:
        return ""
    selected = [s for s in skills if s.enabled and s.name in want]
    if not selected:
        return ""
    lines = ["# 叙事技巧（点名）"]
    for s in selected:
        block = f"【{s.name}】{s.content}"
        if s.example:
            block += f"\n  例：{s.example}"
        lines.append(block)
    return "\n".join(lines)
