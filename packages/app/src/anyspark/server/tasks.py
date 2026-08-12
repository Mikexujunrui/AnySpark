"""
anyspark.server.tasks — 后台任务（S80 拆分，从 app.py 搬移）。

原 build_app 内闭包：BgTask + _bg_worker 循环 + 批量改写/审读 + 信号提炼 +
skill 草稿提炼 + 会话摘要 + 章节图谱抽取 + 学习审查。搬移后闭包引用 → deps.xxx，
由 start_bg_worker(deps) 在 build_app 启动单例 worker 线程（deps 单例传递）。
"""

from __future__ import annotations

import threading

from anyspark.align import ManualEntry
from anyspark.align.mindup import build_learning_review_prompt, parse_learning_review_result
from anyspark.check import run_review
from anyspark.core import Message
from anyspark.server.agent_factory import model_for_task
from anyspark.server.deps import AppDeps
from anyspark.server.logging import logger


def run_batch_rewrite(
    deps: AppDeps, batch_id: str, chapter_ids: list[str], instruction: str
) -> None:
    """批量改写：逐章 LLM 按指令改写 → upsert（覆盖前旧版进版本历史）。"""
    batch = deps.batches.get(batch_id)
    if not batch:
        return
    for cid in chapter_ids:
        try:
            assert deps.model is not None  # 真实装配必有模型
            ch = deps.chapters.get(cid)
            if ch is None:
                batch["results"].append({"id": cid, "ok": False, "error": "章节不存在"})
            else:
                prompt = (
                    "按用户指令改写以下章节。保持剧情走向/人物/设定/时间线一致，"
                    "只按指令调整（风格/情节/表达）。直接输出改写后的完整正文。\n"
                    f"【指令】{instruction}\n【原章】\n{ch.content}\n【改写后正文】"
                )
                out = model_for_task(deps, "editing").respond(
                    [Message(role="user", content=prompt)], []
                )
                new_text = (out.text or "").strip()
                if new_text:
                    deps.chapters.upsert(
                        "main", ch.title, new_text, ch.order_index, ch.narrative_line
                    )
                    batch["results"].append(
                        {"id": cid, "title": ch.title, "ok": True, "chars": len(new_text)}
                    )
                else:
                    batch["results"].append(
                        {"id": cid, "title": ch.title, "ok": False, "error": "空输出"}
                    )
        except Exception as exc:
            batch["results"].append({"id": cid, "ok": False, "error": str(exc)[:150]})
        batch["done"] += 1
    batch["status"] = "done"


def run_batch_review(deps: AppDeps, batch_id: str, chapter_ids: list[str]) -> None:
    """批量审读：逐章检测网审读，汇总报告。"""
    batch = deps.batches.get(batch_id)
    if not batch:
        return
    for cid in chapter_ids:
        try:
            ch = deps.chapters.get(cid)
            if ch is None:
                batch["results"].append({"id": cid, "ok": False, "error": "章节不存在"})
            else:
                report = run_review(model_for_task(deps, "editing"), ch.title, ch.content[:20000])
                batch["results"].append(
                    {
                        "id": cid,
                        "title": ch.title,
                        "ok": True,
                        "hard": report.hard_count,
                        "report": report.render(),
                    }
                )
        except Exception as exc:
            batch["results"].append({"id": cid, "ok": False, "error": str(exc)[:150]})
        batch["done"] += 1
    batch["status"] = "done"


def _bg_worker_inner(
    deps: AppDeps,
) -> None:
    while True:
        try:
            task = deps.bg_queue.get()
            if task.kind == "chapter":
                extract_chapter(deps, task.book_id, task.title, task.content, task.order, task.line)
            elif task.kind == "refine":
                refine_from_signals(deps)
            elif task.kind == "skill_drafts":
                refine_skill_drafts(deps)
            elif task.kind == "summarize":
                summarize_conversation(deps, task.conv_id)
            else:
                logger.warning("后台任务未知 kind: %r", getattr(task, "kind", task))
        except Exception as exc:
            logger.warning("后台任务异常: %s", exc)
        finally:
            deps.bg_queue.task_done()


def refine_from_signals(
    deps: AppDeps,
) -> None:
    """S28：信号 → 偏好提炼 → 说明书（后台异步，不阻塞用户操作）。

    修复对齐闭环缺口：此前 /api/deps.signals 只记录信号，说明书永不自动更新
    （PreferenceExtractor 存在但从未在 API 层接线）——用户操作无法变成
    写作约束，T7"修改率↓/说明书累积"的机制前提缺失。
    """
    try:
        recent = deps.signals.recent(limit=20)
        if not recent:
            return
        # 最近对话（任意会话，取最近 10 条）作为提炼上下文
        dialogue = deps.store.recent_messages(10)
        entries = deps.preference_extractor.extract(dialogue, recent, max_items=3)
        existing = {e.content for e in deps.manual.list("project", "main")}
        added = 0
        for e in entries:
            if e.content in existing:
                continue
            # S55 合并式新增：同主题条目合并（治碎片），不重复堆窄条目
            _, did_merge = deps.manual.merge_add(e)
            if not did_merge:
                added += 1
        if added:
            logger.info("信号提炼: +%d 条新说明书条目", added)
    except Exception as exc:
        logger.warning("信号提炼失败(不影响主链路): %s", exc)


def refine_skill_drafts(
    deps: AppDeps,
) -> None:
    """S54 B/C：心智联动 + 信号驱动 → 生成 skill 候选草稿（人工确认生效）。

    B 心智联动：deps.manual 有 style 偏好（如"喜欢白话文风"）但没有对应 skill →
      用偏好作 hint 调 SkillGenerator 生成候选草稿。
    C 信号驱动：信号/对话里体现的稳定写法 → 提炼成候选草稿。

    产出只进 skill_drafts（未生效），人工确认后转正进 writing_skills——
    对齐 tools_extensions 的"人工批准生效"哲学（S32 实证：错误内容进上下文污染主链路）。
    """
    try:
        # 素材：style 偏好条目 + 最近修改/接受信号（体现用户认可写法）
        manual_entries = deps.manual.list("project", "main")
        style_prefs = [e.content for e in manual_entries if e.category == "style"][:3]
        recent = deps.signals.recent(limit=20)
        signal_texts = [s.content for s in recent if s.kind in ("accepted", "modified")][:5]
        source_material = "\n".join(style_prefs + signal_texts).strip()
        if not source_material:
            return
        hint = ""
        if style_prefs:
            hint = f"用户文风偏好：{'；'.join(style_prefs)}"
        candidates = deps.skill_generator.generate(source_material, hint, max_items=3)
        added = 0
        for c in candidates:
            r = deps.skills.add_draft(
                name=c["name"],
                description=c["description"],
                content=c["content"],
                example=c["example"],
                tags=c["tags"],
                target=c.get("target", "writing"),  # S57
                source="mental",  # mental(心智联动) 或 signal(信号驱动) 统一落草稿
            )
            if r:
                added += 1
        if added:
            logger.info("skill 草稿提炼: +%d 条（待确认）", added)
    except Exception as exc:
        logger.warning("skill 草稿提炼失败(不影响主链路): %s", exc)


def summarize_conversation(deps: AppDeps, conv_id: str) -> None:
    """S53c ② 归档后分析：会话结束后台把对话摘要成场景记忆（双轨提炼之摘要器轨）。

    承担跨会话延续性（进行到哪/做过哪些决定），供下轮会话开头展示（④）。
    仅对"有实质内容的会话"归档（用户消息累计 ≥40 字），避免短测试/琐碎对话
    烧 token；失败不阻塞主链路。
    """
    try:
        msgs = deps.store.messages(conv_id)
        user_chars = sum(len(m.content or "") for m in msgs if m.role == "user")
        if len(msgs) < 3 or user_chars < 40:  # 空会话/琐碎对话不归档
            return
        deps.summarizer.summarize(msgs, book_id="main")
        logger.info("会话归档摘要: conv=%s 消息%d 条", conv_id, len(msgs))
    except Exception as exc:
        logger.warning("会话归档摘要失败(不影响主链路): %s", exc)


def extract_chapter(
    deps: AppDeps, book_id: str, title: str, content: str, order: int, line: str = "main"
) -> None:
    """章节落盘后自动：图谱抽取 + 伏笔自动回收（后台任务）。失败只记日志，绝不阻断写作。"""
    try:
        existing = [e.to_dict() for e in deps.graph.list_entities(book_id)]
        ext = deps.graph_extractor.extract(title, content, existing)
        deps.graph.ingest_chapter(book_id, title, order, ext, line)
        logger.info(
            "图谱抽取完成: 《%s》 实体%d 关系%d 事件%d",
            title,
            len(ext.entities),
            len(ext.relations),
            len(ext.events),
        )
    except Exception as exc:  # 抽取失败不影响写作主链路
        logger.warning("图谱抽取失败(不影响写作): %s", exc)
    # 伏笔自动回收：本章揭开了哪些进行中的关键点（S17，独立 try 互不影响）
    try:
        resolved = deps.plot_resolver.resolve(book_id, title, content, deps.plots)
        if resolved:
            logger.info("伏笔自动回收: 《%s》 %s", title, "、".join(resolved))
    except Exception as exc:
        logger.warning("伏笔回收失败(不影响写作): %s", exc)
    # S55 #2 后台学习审查：本章揭示了什么新偏好/习惯 → 更新心智（轻量，失败不影响）
    try:
        review_for_learning(deps, book_id, title, content)
    except Exception as exc:
        logger.warning("学习审查失败(不影响写作): %s", exc)


def review_for_learning(deps: AppDeps, book_id: str, title: str, content: str) -> None:
    """S55 #2 后台学习审查（借鉴 Hermes background_review）：

    章节落盘后，轻量 LLM 审查本章是否揭示了用户新偏好/习惯/雷区，
    有则 merge_add 进心智条目（合并式新增，治碎片）。隔离：只读快照，
    不碰主对话；失败不影响写作主链路。
    """
    try:
        entries = deps.manual.list("project", book_id)
        prompt = build_learning_review_prompt(entries, f"章节：{title}\n\n{content[:1200]}")
        output = model_for_task(deps, "extraction").respond(
            [Message(role="system", content=prompt)], []
        )
        found = parse_learning_review_result(output.text)
        added = 0
        for item in found:
            text = str(item.get("content", "")).strip()
            if not text:
                continue
            _, did_merge = deps.manual.merge_add(
                ManualEntry(
                    content=text,
                    source="auto",
                    confidence=0.6,
                    activity="medium",
                    scope="project",
                    book_id=book_id,
                    category=item["category"],  # type: ignore[arg-type]
                )
            )
            if not did_merge:
                added += 1
        if found:
            logger.info("学习审查: 《%s》 提炼%d 条 合并/新增", title, len(found))
    except Exception as exc:
        logger.warning("学习审查失败(不影响写作): %s", exc)


def _batch_worker_inner(deps: AppDeps) -> None:
    """批量任务 worker（S85 独立队列：用户同步等待的批量改写/审读，不与图谱抽取串行）。"""
    while True:
        try:
            task = deps.batch_queue.get()
            if task.kind == "batch_rewrite":
                run_batch_rewrite(deps, task.batch_id, task.ids, task.instruction)
            elif task.kind == "batch_review":
                run_batch_review(deps, task.batch_id, task.ids)
            else:
                logger.warning("批量队列未知 kind: %r", getattr(task, "kind", task))
        except Exception as exc:
            logger.warning("批量任务异常: %s", exc)
        finally:
            deps.batch_queue.task_done()


def start_bg_worker(deps: AppDeps) -> None:
    """启动后台任务 worker 单例线程（build_app 装配时调用一次）。"""

    threading.Thread(target=_bg_worker_inner, args=(deps,), daemon=True).start()
    threading.Thread(target=_batch_worker_inner, args=(deps,), daemon=True).start()
