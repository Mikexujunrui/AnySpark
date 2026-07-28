import asyncio
import json
import logging
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .config import DATA_DIR, PROJECT_ROOT, config
from .llm_client import chat as llm_chat

logger = logging.getLogger(__name__)

# ── System resource paths ──
# In EXE: resources live under sys._MEIPASS
# In dev:  resources live under PROJECT_ROOT
if getattr(sys, "frozen", False):
    SYSTEM_REVIEWERS_DIR = Path(sys._MEIPASS) / "reviewers"
else:
    SYSTEM_REVIEWERS_DIR = PROJECT_ROOT / "reviewers"
USER_REVIEWERS_DIR = DATA_DIR / "reviewers"


# System reviewers: shipped with the project (tracked in git)
# User reviewers: private custom data (gitignored, user backs up)


@dataclass
class ReviewerDef:
    id: str
    name: str
    avatar: str = "user"
    category: str = "reader"
    active: bool = True
    persona: str = ""
    scoring_dimensions: list[dict] = field(default_factory=list)
    custom: bool = False
    needs_knowledge: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "avatar": self.avatar,
            "category": self.category,
            "active": self.active,
            "persona": self.persona,
            "scoring_dimensions": self.scoring_dimensions,
            "custom": self.custom,
            "needs_knowledge": self.needs_knowledge,
        }

    def to_detail(self) -> dict:
        d = self.to_dict()
        d["persona"] = self.persona
        return d


@dataclass
class ReviewResult:
    reviewer_id: str
    reviewer_name: str
    category: str
    scores: dict[str, float] = field(default_factory=dict)
    overall_score: float = 0.0
    highlights: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    raw_text: str = ""
    error: str = ""


@dataclass
class ReviewReport:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    book_id: str = ""
    chapter_ref: str = ""
    timestamp: str = ""
    overall_score: float = 0.0
    summary: str = ""
    consensus: list[str] = field(default_factory=list)
    divergences: list[str] = field(default_factory=list)
    top_suggestions: list[str] = field(default_factory=list)
    individual_reviews: list[dict] = field(default_factory=list)
    reviewer_count: int = 0


class ReviewPanel:
    def __init__(self):
        self._reviewers: dict[str, ReviewerDef] = {}
        self._custom_reviewers: dict[str, ReviewerDef] = {}
        SYSTEM_REVIEWERS_DIR.mkdir(parents=True, exist_ok=True)
        USER_REVIEWERS_DIR.mkdir(parents=True, exist_ok=True)
        self._load_all()

    def _load_all(self):
        # Load system reviewers first, then user reviewers (user overrides system)
        for d in (SYSTEM_REVIEWERS_DIR, USER_REVIEWERS_DIR):
            for f in d.glob("*.yaml"):
                self._load_file(f)
            for f in d.glob("*.yml"):
                self._load_file(f)

    def _load_file(self, path: Path):
        try:
            text = path.read_text(encoding="utf-8")
            defs = yaml.safe_load(text)
            if isinstance(defs, dict):
                defs = [defs]
            for d in defs:
                rid = d.get("id", "")
                if not rid:
                    continue
                reviewer = ReviewerDef(
                    id=rid,
                    name=d.get("name", rid),
                    avatar=d.get("avatar", "user"),
                    category=d.get("category", "reader"),
                    active=d.get("active", True),
                    persona=d.get("persona", ""),
                    scoring_dimensions=d.get("scoring_dimensions", []),
                    needs_knowledge=d.get("needs_knowledge", False),
                    custom=d.get("custom", False),
                )
                if d.get("custom"):
                    self._custom_reviewers[rid] = reviewer
                else:
                    self._reviewers[rid] = reviewer
        except Exception as e:
            logger.error(f"Failed to load reviewer file {path}: {e}")

    def _save_reviewer(self, reviewer: ReviewerDef):
        path = USER_REVIEWERS_DIR / f"{reviewer.id}.yaml"
        try:
            data = {
                "id": reviewer.id,
                "name": reviewer.name,
                "avatar": reviewer.avatar,
                "category": reviewer.category,
                "active": reviewer.active,
                "persona": reviewer.persona,
                "scoring_dimensions": reviewer.scoring_dimensions,
                "custom": reviewer.custom,
                "needs_knowledge": reviewer.needs_knowledge,
            }
            path.write_text(yaml.safe_dump([data], allow_unicode=True, sort_keys=False), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save reviewer {reviewer.id}: {e}")

    def _delete_reviewer_file(self, rid: str):
        path = USER_REVIEWERS_DIR / f"{rid}.yaml"
        try:
            if path.exists():
                path.unlink()
        except Exception as e:
            logger.error(f"Failed to delete reviewer file {rid}: {e}")

    def list_reviewers(self, include_inactive: bool = True) -> list[dict]:
        all_revs = {**self._reviewers, **self._custom_reviewers}
        result = []
        for r in all_revs.values():
            if include_inactive or r.active:
                result.append(r.to_dict())
        return sorted(result, key=lambda x: (0 if x["category"] == "professional" else 1, x["id"]))

    def get_reviewer(self, rid: str) -> ReviewerDef | None:
        return self._custom_reviewers.get(rid) or self._reviewers.get(rid)

    def set_active(self, rid: str, active: bool) -> bool:
        r = self.get_reviewer(rid)
        if not r:
            return False
        r.active = active
        if r.custom:
            self._save_reviewer(r)
        return True

    def add_custom_reviewer(
        self,
        rid: str,
        name: str,
        persona: str,
        category: str = "reader",
        avatar: str = "user",
        scoring_dimensions: list[dict] | None = None,
        needs_knowledge: bool = False,
    ) -> ReviewerDef:
        reviewer = ReviewerDef(
            id=rid,
            name=name,
            avatar=avatar,
            category=category,
            active=True,
            persona=persona,
            custom=True,
            scoring_dimensions=scoring_dimensions or [],
            needs_knowledge=needs_knowledge,
        )
        self._custom_reviewers[rid] = reviewer
        self._save_reviewer(reviewer)
        return reviewer

    def remove_custom_reviewer(self, rid: str) -> bool:
        removed = self._custom_reviewers.pop(rid, None) is not None
        if removed:
            self._delete_reviewer_file(rid)
        return removed

    def update_reviewer(self, rid: str, **fields) -> bool:
        r = self.get_reviewer(rid)
        if not r:
            return False
        for field_name in ("name", "avatar", "category", "persona", "active", "needs_knowledge"):
            if field_name in fields:
                setattr(r, field_name, fields[field_name])
        if "scoring_dimensions" in fields:
            r.scoring_dimensions = fields["scoring_dimensions"]
        if r.custom:
            self._save_reviewer(r)
        return True

    def get_active_reviewers(self) -> list[ReviewerDef]:
        all_revs = {**self._reviewers, **self._custom_reviewers}
        return [r for r in all_revs.values() if r.active]

    async def run_review(
        self,
        chapter_text: str,
        book_id: str = "",
        chapter_ref: str = "",
        knowledge_context: str = "",
        reviewer_ids: list[str] | None = None,
        mode: str = "concurrent",
        queue=None,
    ) -> ReviewReport:
        from concurrent.futures import ThreadPoolExecutor
        from datetime import datetime

        if reviewer_ids:
            reviewers = [self.get_reviewer(rid) for rid in reviewer_ids]
            reviewers = [r for r in reviewers if r is not None]
        else:
            reviewers = self.get_active_reviewers()

        if not reviewers:
            report = ReviewReport(book_id=book_id, chapter_ref=chapter_ref)
            report.summary = "没有激活的评审员。请先激活至少一位评审员。"
            return report

        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=min(len(reviewers), 6), thread_name_prefix="reviewer")

        if queue:
            await queue.put({"_progress": f"启动评审团（{len(reviewers)}位评审员）..."})

        if mode == "serial":
            results, _ = await self._run_serial(reviewers, chapter_text, knowledge_context, loop, executor, queue)
            pending_tasks = {}
            pending_reviewers = []
        else:
            results, pending_tasks, pending_reviewers = await self._run_concurrent(
                reviewers, chapter_text, knowledge_context, loop, executor, queue
            )

        if queue and pending_reviewers:
            names = ", ".join(r.name for r in pending_reviewers)
            await queue.put({"_progress": f"  ⏳ {names} 仍在后台评审，完成后自动补充..."})

        if queue:
            await queue.put({"_progress": "评审完毕，正在生成汇总报告..."})

        report = await self._summarize(results, chapter_text, book_id, chapter_ref, loop, executor)
        report.timestamp = datetime.now().isoformat()
        report._pending_tasks = pending_tasks

        executor.shutdown(wait=False)
        return report

    async def _run_concurrent(self, reviewers, chapter_text, knowledge_context, loop, executor, queue):
        pending = {}
        for r in reviewers:
            ctx = knowledge_context if r.needs_knowledge else ""
            task = asyncio.ensure_future(self._single_review(r, chapter_text, ctx, loop, executor, queue))
            pending[task] = r

        results = []
        MAX_TIMEOUT = 90
        deadline = loop.time() + MAX_TIMEOUT

        while pending and loop.time() < deadline:
            done, _ = await asyncio.wait(
                pending.keys(),
                timeout=2.0,
                return_when=asyncio.FIRST_COMPLETED,
            )

            for coro in done:
                r = pending.pop(coro)
                try:
                    result = coro.result()
                except Exception:
                    result = ReviewResult(
                        reviewer_id=r.id, reviewer_name=r.name, category=r.category, error="评审异常终止"
                    )
                results.append(result)
                if queue and not result.error:
                    self._report_progress(result, r, queue)
                elif queue and result.error:
                    await queue.put({"_progress": f"  ❌ {r.name}: {result.error[:60]}"})

            # If only needs_knowledge reviewers remain, cut off and let them finish in background
            if pending and all(r.needs_knowledge for r in pending.values()):
                slow_names = ", ".join(r.name for r in pending.values())
                if queue:
                    await queue.put({"_progress": f"  ⏳ {slow_names} 正在查知识库，先出报告，完成后自动追加..."})
                break

        # Collect remaining as in-progress placeholder
        pending_reviewers = []
        for coro, r in pending.items():
            pending_reviewers.append(r)
            results.append(
                ReviewResult(
                    reviewer_id=r.id,
                    reviewer_name=r.name,
                    category=r.category,
                    error=f"{r.name} 评审仍在进行中，完成后将自动补充...",
                )
            )

        return results, pending, pending_reviewers

    def _report_progress(self, result, reviewer, queue):
        hl = "; ".join(result.highlights[:2]) if result.highlights else ""
        iss = "; ".join(result.issues[:2]) if result.issues else ""
        lines = [f"  ✅ {result.reviewer_name} ({result.overall_score:.1f}/10)"]
        if hl:
            lines.append(f"     亮点: {hl}")
        if iss:
            lines.append(f"     问题: {iss}")
        asyncio.ensure_future(queue.put({"_progress": "\n".join(lines)}))

    async def _run_serial(self, reviewers, chapter_text, knowledge_context, loop, executor, queue):
        results = []
        prev_reviews = ""
        for r in reviewers:
            ctx = knowledge_context if r.needs_knowledge else ""
            if prev_reviews:
                ctx += f"\n\n# 前序评审意见（仅供参考，请给出你自己的独立判断）\n{prev_reviews}"
            result = await self._single_review(r, chapter_text, ctx, loop, executor, queue)
            results.append(result)
            if not result.error:
                prev_reviews += f"\n---\n{result.reviewer_name}: {result.raw_text[:300]}"
        return results, []

    async def _single_review(
        self, reviewer: ReviewerDef, chapter_text: str, knowledge_context: str, loop, executor, queue
    ) -> ReviewResult:
        if queue:
            await queue.put({"_progress": f"  {reviewer.name} 正在评审..."})

        system = self._build_reviewer_prompt(reviewer)
        prompt_parts = []
        if knowledge_context:
            prompt_parts.append(f"# 知识库上下文（角色设定、世界观等）\n{knowledge_context[:4000]}")
        prompt_parts.append(f"# 待评审章节\n{chapter_text[: config.storage.max_context_chars]}")
        prompt_parts.append("\n请按照你的评审维度逐项评分(0-10)，并给出亮点、问题、建议。输出JSON格式。")
        prompt = "\n\n".join(prompt_parts)

        last_error = ""
        for _attempt in range(2):
            try:
                response = await asyncio.wait_for(
                    loop.run_in_executor(executor, llm_chat, prompt, system, 0.3, "extraction"),
                    timeout=90,
                )
                result = self._parse_review(response, reviewer)
                return result
            except TimeoutError:
                last_error = "评审超时"
            except Exception as e:
                last_error = str(e)[:100]
                if "connection" in str(e).lower():
                    await asyncio.sleep(2)
                    continue
                break

        return ReviewResult(
            reviewer_id=reviewer.id,
            reviewer_name=reviewer.name,
            category=reviewer.category,
            error=last_error,
        )

    def _build_reviewer_prompt(self, reviewer: ReviewerDef) -> str:
        dims_desc = ""
        if reviewer.scoring_dimensions:
            dims = "\n".join(
                f"- {d['name']}（权重{d.get('weight', 0.2):.0%}）: {d.get('desc', '')}"
                for d in reviewer.scoring_dimensions
            )
            dims_desc = f"\n\n# 评分维度\n{dims}"

        return f"""你是一位小说评审员。以下是你的身份和评审标准：

# 身份
{reviewer.persona}
{dims_desc}

# 输出要求
你必须输出严格的JSON格式（不要加```标记）：
{{
  "scores": {{"维度名": 分数(0-10), ...}},
  "overall_score": 综合评分(0-10),
  "highlights": ["亮点1", "亮点2", ...],
  "issues": ["问题1", "问题2", ...],
  "suggestions": ["建议1", "建议2", ...],
  "comment": "一段100-200字的整体评价"
}}

规则：
1. 严格按照你的角色人设和语气风格写评价
2. 每个维度独立评分，综合分是加权平均
3. 亮点至少1条，问题至少1条，建议至少1条
4. comment 用你的角色语气写，体现你的个性"""

    def _parse_review(self, response: str, reviewer: ReviewerDef) -> ReviewResult:
        result = ReviewResult(
            reviewer_id=reviewer.id,
            reviewer_name=reviewer.name,
            category=reviewer.category,
            raw_text=response,
        )
        try:
            j = response.strip()
            if j.startswith("```json"):
                j = j[7:]
            if j.startswith("```"):
                j = j[3:]
            if j.endswith("```"):
                j = j[:-3]
            data = json.loads(j.strip())
            result.scores = data.get("scores", {})
            result.overall_score = float(data.get("overall_score", 0))
            result.highlights = data.get("highlights", [])
            result.issues = data.get("issues", [])
            result.suggestions = data.get("suggestions", [])
            if data.get("comment"):
                result.raw_text = data["comment"]
        except (json.JSONDecodeError, ValueError):
            result.raw_text = response[:500]
        return result

    async def _summarize(
        self, results: list[ReviewResult], chapter_text: str, book_id: str, chapter_ref: str, loop, executor
    ) -> ReviewReport:
        report = ReviewReport(book_id=book_id, chapter_ref=chapter_ref)
        valid = [r for r in results if not r.error]
        report.reviewer_count = len(results)

        if not valid:
            report.summary = "所有评审员均未返回有效结果。"
            report.individual_reviews = [{"reviewer": r.reviewer_name, "error": r.error} for r in results]
            return report

        scores = [r.overall_score for r in valid if r.overall_score > 0]
        report.overall_score = round(sum(scores) / len(scores), 1) if scores else 0

        for r in results:
            entry = {
                "reviewer_id": r.reviewer_id,
                "reviewer_name": r.reviewer_name,
                "category": r.category,
                "overall_score": r.overall_score,
                "scores": r.scores,
                "highlights": r.highlights,
                "issues": r.issues,
                "suggestions": r.suggestions,
                "comment": r.raw_text[:500],
            }
            if r.error:
                entry["error"] = r.error
            report.individual_reviews.append(entry)

        reviews_text = ""
        for r in valid:
            reviews_text += f"\n## {r.reviewer_name}（{r.category}）— {r.overall_score}/10\n"
            reviews_text += f"亮点: {', '.join(r.highlights[:3])}\n"
            reviews_text += f"问题: {', '.join(r.issues[:3])}\n"
            reviews_text += f"建议: {', '.join(r.suggestions[:3])}\n"

        summary_system = """你是评审团主席，负责汇总所有评审意见。输出JSON格式（不要加```标记）：
{
  "summary": "200字以内的综合评价，概括整体质量和关键发现",
  "consensus": ["所有评审员都认同的观点1", "观点2", ...],
  "divergences": ["评审员之间的分歧1", "分歧2", ...],
  "top_suggestions": ["最重要的改进建议1", "建议2", "建议3"]
}
规则：
1. summary 要客观中立，兼顾专业评审和读者反馈
2. consensus 提取多数评审员都提到的共同问题或优点
3. divergences 找出评审员之间意见相反的地方
4. top_suggestions 从所有建议中选出最有价值的3-5条"""

        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(
                    executor,
                    llm_chat,
                    f"# 各评审员意见\n{reviews_text}\n\n请汇总：",
                    summary_system,
                    0.2,
                    "extraction",
                ),
                timeout=120,
            )
            j = response.strip()
            if j.startswith("```json"):
                j = j[7:]
            if j.startswith("```"):
                j = j[3:]
            if j.endswith("```"):
                j = j[:-3]
            data = json.loads(j.strip())
            report.summary = data.get("summary", "")
            report.consensus = data.get("consensus", [])
            report.divergences = data.get("divergences", [])
            report.top_suggestions = data.get("top_suggestions", [])
        except Exception as e:
            report.summary = f"汇总失败: {str(e)[:80]}。各评审员意见请查看详细反馈。"

        return report


panel = ReviewPanel()
