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
from anyspark.core import Message
from anyspark.server.agent_factory import model_for_task
from anyspark.server.deps import AppDeps
from anyspark.server.logging import logger


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

    增量游标（S7x 长会话标准重定，DESIGN §12.18）：只提炼未 processed 信号，
    分批推进——不再用 recent(20) 滑动窗口（长会话早期信号会被挤掉，
    早期偏好丢失）。单批 ≤20 条（LLM 一次看 20 条质量稳），积压多则分批
    +merge_add 归并（轻量多步归并，无需索引/深读重型机制）。
    阈值语义从"会话 token 数"改为"信号积压量"，与模型上下文窗口解耦。
    S132e 多书：按书遍历（unprocessed_books），每条目落所属书——
    不再硬编码 main（非 main 书信号此前永不提炼）。
    """
    try:
        batch_size = 20
        max_batches_per_book = 5  # 防极端积压/并发下任务无限跑；剩余留待下次任务
        for book_id in deps.signals.unprocessed_books():
            for _ in range(max_batches_per_book):
                pending = deps.signals.unprocessed(limit=batch_size, book_id=book_id)
                if not pending:
                    break
                # 最近对话（任意会话，取最近 10 条）作为提炼上下文
                dialogue = deps.store.recent_messages(10)
                entries = deps.preference_extractor.extract(dialogue, pending, max_items=3)
                existing = {e.content for e in deps.manual.list("project", book_id)}
                added = 0
                for e in entries:
                    if e.content in existing:
                        continue
                    e.book_id = book_id  # S132e：条目落信号所属书（extract 默认 main）
                    # S55 合并式新增：同主题条目合并（治碎片），不重复堆窄条目
                    _, did_merge = deps.manual.merge_add(e)
                    if not did_merge:
                        added += 1
                deps.signals.mark_processed([s.id for s in pending])
                if added:
                    logger.info("信号提炼: 书=%s +%d 条新说明书条目", book_id, added)
                if len(pending) < batch_size:
                    break  # 本批不满说明无积压了
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
                type=c.get("type", "writing"),  # S127：type 替代 target
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
        # S152g：摘要按会话所属项目（此前硬编码 main——所有项目会话的场景记忆落错库）
        conv = deps.store.get(conv_id)
        book_id = conv.book_id if conv is not None else "main"
        deps.summarizer.summarize(msgs, book_id=book_id)
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


def start_bg_worker(deps: AppDeps) -> None:
    """启动后台任务 worker 单例线程（build_app 装配时调用一次）。"""

    threading.Thread(target=_bg_worker_inner, args=(deps,), daemon=True).start()
