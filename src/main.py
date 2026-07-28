# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.extractor import accept_proposal, extract_from_text
from core.graph_store import get_store
from data.json_store import json_store

try:
    from rich import box
    from rich.console import Console
    from rich.table import Table

    console = Console()
    USE_RICH = True
except ImportError:
    USE_RICH = False

    def print_colored(*args, **kwargs):
        print(*args, **kwargs)


DEFAULT_PROJECT = "cli"


def _ensure_book(project_id: str, title: str = "") -> str:
    """Ensure a book entry exists in JSON store for the given project_id.

    Returns the project_id unchanged if the book already exists, otherwise
    creates a new book entry with the given project_id as its ID.
    """
    try:
        json_store.get_book(project_id)
        return project_id
    except Exception:
        # Book doesn't exist — create it directly in the JSON store
        books = json_store.load_books()
        now = datetime.now().isoformat()
        new_book = {
            "id": project_id,
            "title": title or f"CLI项目-{project_id[:8]}",
            "description": "通过CLI自动创建",
            "entityCount": 0,
            "chapterCount": 0,
            "createdAt": now,
            "updatedAt": now,
        }
        books.append(new_book)
        json_store.save_books(books)
        return project_id


def p(text="", style=None):
    """Print with optional rich styling."""
    if USE_RICH and style:
        console.print(text, style=style)
    elif USE_RICH:
        console.print(text)
    else:
        print(text)


def cmd_help():
    """显示帮助信息。"""
    if USE_RICH:
        p("\n[bold cyan]AI 小说写作辅助 Agent — CLI[/bold cyan]\n")
        table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan")
        table.add_column("命令", style="green", min_width=20)
        table.add_column("说明", min_width=40)
        table.add_row("/s <文本>", "提交设定（AI 自动抽取结构化知识）")
        table.add_row("/w <写作指令>", "知识约束写作（严格模式）")
        table.add_row("/ws <写作指令>", "写作（建议模式，可补充设定）")
        table.add_row("/chat <消息>", "与 Agent 自由对话（使用工具链）")
        table.add_row("/query <问题>", "智能查询（使用完整 agent loop）")
        table.add_row("/search <关键词>", "搜索知识库")
        table.add_row("/read <章节号>", "读取章节内容（如 /read 1 或 /read #1）")
        table.add_row("/list", "查看当前知识库")
        table.add_row("/char <名称>", "查看角色详情")
        table.add_row("/chapters", "查看章节列表")
        table.add_row("/count", "字数统计（逐章+总计）")
        table.add_row("/history <章节号>", "查看章节历史版本")
        table.add_row("/volumes", "查看分卷")
        table.add_row("/timeline", "查看时间线")
        table.add_row("/outline", "查看大纲")
        table.add_row("/detailed", "查看细纲")
        table.add_row("/world", "查看世界设定")
        table.add_row("/graph", "图谱洞察（遗忘角色、未回收伏笔等）")
        table.add_row("/constraints", "检查叙事约束")
        table.add_row("/refs", "查看参考书")
        table.add_row("/books", "列出所有书籍项目")
        table.add_row("/del <id>", "删除实体")
        table.add_row("/export", "导出知识库摘要")
        table.add_row("/stats", "查看项目统计")
        table.add_row("/project <id>", "切换项目")
        table.add_row("/help", "显示此帮助")
        table.add_row("/quit", "退出")
        console.print(table)
    else:
        print("""
可用命令：
  /s <文本>        — 提交设定（AI 自动抽取结构化知识）
  /w <写作指令>    — 知识约束写作（严格模式）
  /ws <写作指令>   — 写作（建议模式，可补充设定）
  /chat <消息>     — 与 Agent 自由对话（使用工具链）
  /query <问题>    — 智能查询（使用完整 agent loop）
  /search <关键词> — 搜索知识库
  /read <章节号>   — 读取章节内容（如 /read 1 或 /read #1）
  /list            — 查看当前知识库
  /char <名称>     — 查看角色详情
  /chapters        — 查看章节列表
  /count           — 字数统计（逐章+总计）
  /history <章节号>— 查看章节历史版本
  /volumes         — 查看分卷
  /timeline        — 查看时间线
  /outline         — 查看大纲
  /detailed        — 查看细纲
  /world           — 查看世界设定
  /graph           — 图谱洞察
  /constraints     — 检查叙事约束
  /refs            — 查看参考书
  /books           — 列出所有书籍项目
  /del <id>        — 删除实体
  /export          — 导出知识库摘要
  /stats           — 查看项目统计
  /project <id>    — 切换项目
  /help            — 显示此帮助
  /quit            — 退出
""")


def cmd_submit(text: str, project_id: str = DEFAULT_PROJECT):
    print("\n正在分析设定文本，提取结构化知识...\n")
    proposal = extract_from_text(text, book_id=project_id)

    if not proposal.entities and not proposal.relations and not proposal.foreshadows:
        p("（未识别到可提取的设定信息）", "yellow")
        return

    if proposal.entities:
        p(f"识别到 {len(proposal.entities)} 个实体：", "green")
        for e in proposal.entities:
            aliases = f"（{', '.join(e.aliases)}）" if e.aliases else ""
            p(f"  [{e.type}] {e.name}{aliases}", "cyan")
            for k, v in e.data.items():
                p(f"    - {k}: {v}")

    if proposal.relations:
        p(f"\n识别到 {len(proposal.relations)} 条关系：", "green")
        for r in proposal.relations:
            p(f"  {r.from_entity} --[{r.type}]--> {r.to_entity}", "cyan")

    if proposal.foreshadows:
        p(f"\n识别到 {len(proposal.foreshadows)} 个伏笔：", "green")
        for f in proposal.foreshadows:
            p(f"  {f.text[:60]}...", "cyan")

    try:
        confirm = input("\n是否接受以上知识？(y/n): ").strip().lower()
    except (EOFError, OSError):
        # 非交互模式自动确认
        confirm = "y"
        p("  [非交互模式: 自动确认]", "dim")
    if confirm == "y":
        result = accept_proposal(proposal, project_id)
        p(f"\n{result}", "green")
    else:
        p("已放弃本次提取", "yellow")


def cmd_write(instruction: str, mode: str = "strict", project_id: str = DEFAULT_PROJECT):
    """写作命令 — 使用 Agent 对话执行，自动保存章节。"""
    mode_hint = "严格遵循知识库设定" if mode == "strict" else "可适当补充设定"
    full_instruction = f"{instruction}（{mode_hint}，写完后请用 store_chapter 保存为正式章节）"
    cmd_chat(full_instruction, project_id)


def cmd_chat(message: str, project_id: str = DEFAULT_PROJECT):
    """Agent Loop in CLI - 使用完整agent loop,支持Autopilot等高级功能。"""
    from core.agent_loop import AgentConfig, run_agent_loop
    from core.question import manager as question_manager

    p(f"\n[与Agent对话中...] {message}\n", "cyan")

    # 加载历史
    session_id = f"cli_{project_id}"
    history = _load_history(session_id)

    agent_config = AgentConfig(
        agent_type="write",
        mode="write",
        book_id=project_id,
        session_id=session_id,
        auto_mode_enabled=True,  # 启用Autopilot工具可见性
    )

    async def run_chat():
        final_text = ""
        async for event in run_agent_loop(message, agent_config, history):
            if event.type == "chunk":
                chunk = event.data.get("text", "")
                print(chunk, end="", flush=True)
                final_text += chunk
            elif event.type == "text":
                final_text += "\n" + event.data.get("content", "")
            elif event.type == "progress":
                stage = event.data.get("stage", "")
                if stage:
                    p(f"  [{stage}]", "dim")
            elif event.type == "question":
                # Agent提问(如权限确认、Autopilot计划确认)
                qs = event.data.get("questions", [])
                qid = event.data.get("id", "")
                p("\n  [Agent提问]", "cyan")
                for q in qs:
                    p(f"    {q.get('question', '')}", "yellow")
                    for opt in q.get("options", []):
                        p(f"      - {opt['label']}: {opt['description']}")
                try:
                    answer = input("  你的回答: ").strip()
                except (EOFError, OSError):
                    # 非交互模式自动选择第一个选项(通常是确认)
                    first_label = qs[0].get("options", [{}])[0].get("label", "确认")
                    answer = first_label
                    p(f"  [非交互模式: 自动选择 '{answer}']", "dim")
                # 回复问题以解除agent_loop阻塞
                if qid:
                    question_manager.reply(qid, [[answer]])
                final_text += f"\n[用户回答: {answer}]"
            elif event.type == "done":
                final_text = event.data.get("message", "")
            elif event.type == "error":
                p(f"\n错误: {event.data.get('message', '')}", "red")
        return final_text

    loop = asyncio.new_event_loop()
    try:
        final_text = loop.run_until_complete(run_chat())
    finally:
        loop.close()

    p()  # 换行
    _persist_history(session_id, message, final_text)


def cmd_query(message: str, project_id: str = DEFAULT_PROJECT):
    """智能查询 - 使用完整 agent loop，与 server 端一致。"""
    from core.agent_loop import AgentConfig, run_agent_loop

    p(f"\n[查询中...] {message}\n", "cyan")

    # 加载历史
    session_id = f"cli_{project_id}"
    history = _load_history(session_id)

    agent_config = AgentConfig(
        agent_type="write",
        mode="write",
        book_id=project_id,
        session_id=session_id,
    )

    async def run_query():
        final_text = ""
        async for event in run_agent_loop(message, agent_config, history):
            if event.type == "chunk":
                chunk = event.data.get("text", "")
                print(chunk, end="", flush=True)
                final_text += chunk
            elif event.type == "text":
                final_text += "\n" + event.data.get("content", "")
            elif event.type == "progress":
                stage = event.data.get("stage", "")
                if stage:
                    p(f"  [{stage}]", "dim")
            elif event.type == "done":
                final_text = event.data.get("message", "")
            elif event.type == "error":
                p(f"\n错误: {event.data.get('message', '')}", "red")
        return final_text

    loop = asyncio.new_event_loop()
    try:
        final_text = loop.run_until_complete(run_query())
    finally:
        loop.close()

    p()  # 换行
    _persist_history(session_id, message, final_text)


def cmd_list(project_id: str = DEFAULT_PROJECT):
    store = get_store(project_id)
    entities = store.list_entities()
    if not entities:
        p("\n知识库为空。使用 /s <文本> 来添加设定", "yellow")
        return

    count_by_type = {}
    for e in entities:
        count_by_type[e.type] = count_by_type.get(e.type, 0) + 1

    p(f"\n知识库总览（{len(entities)} 个实体）", "green")
    for t, c in count_by_type.items():
        p(f"  {t}: {c}个", "cyan")

    p()
    for e in entities:
        aliases = f"（{', '.join(e.aliases)}）" if e.aliases else ""
        p(f"  [{e.id[:8]}] [{e.type}] {e.name}{aliases}", "cyan")

    relations = store.list_relations()
    if relations:
        p(f"\n  {len(relations)} 条关系", "dim")

    foreshadows = store.list_foreshadows()
    unresolved = [f for f in foreshadows if not f.resolved]
    if unresolved:
        p(f"  {len(unresolved)} 个待回收伏笔", "yellow")


def cmd_char_detail(name: str, project_id: str = DEFAULT_PROJECT):
    store = get_store(project_id)
    entity = store.get_entity_by_name(name)
    if not entity:
        p(f"\n未找到角色: {name}", "red")
        return
    aliases = f"（{', '.join(entity.aliases)}）" if entity.aliases else ""
    p(f"\n### {entity.name} {aliases}", "bold cyan")
    p(f"类型: {entity.type}", "dim")
    for k, v in entity.data.items():
        p(f"  {k}: {v}")

    relations = store.list_relations(entity.id)
    if relations:
        entities = store.list_entities()
        p("\n关系：", "green")
        for r in relations:
            other_id = r.to_entity if r.from_entity == entity.id else r.from_entity
            other = next((e for e in entities if e.id == other_id), None)
            if other:
                arrow = "->" if r.from_entity == entity.id else "<-"
                p(f"  {arrow} [{r.type}] {other.name}", "cyan")


def cmd_chapters(project_id: str = DEFAULT_PROJECT):
    """查看章节列表。"""
    chapters = json_store.load_chapters(project_id)
    if not chapters:
        p("\n暂无章节", "yellow")
        return

    p(f"\n章节列表 ({len(chapters)} 章):", "green")
    total_words = 0
    for i, ch in enumerate(chapters, 1):
        status = "番外" if ch.get("is_extra") else f"第{i}章"
        # 从版本化数据中获取实际字数(版本化后 content 存储在 versions 中)
        view = json_store._chapter_view(ch)
        content = view.get("content", "")
        word_count = len(content.replace("\n", "").replace(" ", "")) if content else 0
        total_words += word_count
        p(f"  [{status}] {view.get('title', ch.get('title', '无标题'))} ({word_count}字)", "cyan")
    p(f"\n  总字数: {total_words}字", "bold green")


def cmd_volumes(project_id: str = DEFAULT_PROJECT):
    """查看分卷。"""
    volumes = json_store.load_volumes(project_id)
    if not volumes:
        p("\n暂无分卷", "yellow")
        return

    p(f"\n分卷列表 ({len(volumes)} 卷):", "green")
    for vol in volumes:
        chapters = vol.get("chapters", [])
        p(f"  [{vol.get('title', '无标题')}] ({len(chapters)}章)", "cyan")
        for ch_id in chapters:
            ch = json_store.get_chapter(project_id, ch_id)
            if ch:
                p(f"    - {ch.get('title', '无标题')}", "dim")


def cmd_timeline(project_id: str = DEFAULT_PROJECT):
    """查看时间线。"""
    store = get_store(project_id)
    events = store.list_timeline_events()
    if not events:
        p("\n暂无时间线事件", "yellow")
        return

    p(f"\n时间线 ({len(events)} 个事件):", "green")
    for e in sorted(events, key=lambda x: x.time_order):
        p(f"  [{e.time_order}] {e.label}", "cyan")
        if e.description:
            p(f"    {e.description[:80]}...", "dim")


def cmd_outline(project_id: str = DEFAULT_PROJECT):
    """查看大纲。"""
    outline = json_store.get_outline(project_id)
    if not outline or not outline.get("chapters"):
        p("\n暂无大纲", "yellow")
        return

    chapters = outline.get("chapters", [])
    p(f"\n大纲 ({len(chapters)} 章):", "green")
    for i, ch in enumerate(chapters, 1):
        title = ch.get("title", f"第{i}章")
        synopsis = ch.get("synopsis", "")
        p(f"  [{i}] {title}", "cyan")
        if synopsis:
            p(f"    {synopsis[:100]}...", "dim")


def cmd_delete(entity_id: str, project_id: str = DEFAULT_PROJECT):
    store = get_store(project_id)
    ok = store.delete_entity(entity_id)
    if ok:
        p(f"已删除: {entity_id}", "green")
    else:
        p(f"未找到: {entity_id}", "red")


def cmd_export(project_id: str = DEFAULT_PROJECT):
    store = get_store(project_id)
    summary = store.get_knowledge_summary()
    p("\n" + summary)


def cmd_stats(project_id: str = DEFAULT_PROJECT):
    """查看项目统计。"""
    stats = json_store.get_book(project_id)
    if not stats:
        p("\n项目不存在", "red")
        return

    # 从实际章节数据计算字数(版本化后不在 book 层级存储)
    chapters = json_store.load_chapters(project_id)
    total_words = 0
    for ch in chapters or []:
        view = json_store._chapter_view(ch)
        content = view.get("content", "")
        total_words += len(content.replace("\n", "").replace(" ", "")) if content else 0

    p(f"\n项目: {stats.get('title', '未知')}", "bold cyan")
    p(f"  字数: {total_words}", "cyan")
    p(f"  章节: {len(chapters) if chapters else 0}", "cyan")
    p(f"  实体: {stats.get('entity_count', 0)}", "cyan")
    p(f"  伏笔: {stats.get('foreshadow_count', 0)}", "cyan")


def cmd_search(query: str, project_id: str = DEFAULT_PROJECT):
    """搜索知识库。"""
    store = get_store(project_id)
    entities = store.list_entities()
    q = query.lower()
    results = [e for e in entities if q in e.name.lower() or any(q in a.lower() for a in e.aliases)]
    if not results:
        p(f"\n未找到与 '{query}' 相关的实体", "yellow")
        return
    p(f"\n搜索 '{query}' 结果 ({len(results)} 个):", "green")
    for e in results[:20]:
        p(f"  [{e.type}] {e.name} (id: {e.id[:8]})", "cyan")
        for k, v in list(e.data.items())[:3]:
            p(f"    {k}: {str(v)[:60]}", "dim")


def cmd_read_chapter(chapter_ref: str, project_id: str = DEFAULT_PROJECT):
    """读取章节内容。"""
    ch = json_store.get_chapter(project_id, chapter_ref)
    if not ch:
        p(f"\n未找到章节: {chapter_ref}", "red")
        return
    view = json_store._chapter_view(ch)
    content = view.get("content", "")
    title = view.get("title", ch.get("title", "无标题"))
    p(f"\n## {title}", "bold cyan")
    p(content[:2000] if content else "（空章节）")
    if len(content) > 2000:
        p(f"\n... (共 {len(content)} 字符，已截断)", "dim")


def cmd_worldbuilding(project_id: str = DEFAULT_PROJECT):
    """查看世界设定。"""
    store = get_store(project_id)
    metrics = store.get_worldbuilding_metrics()
    if not metrics:
        p("\n暂无世界设定", "yellow")
        return
    p("\n世界设定:", "green")
    for key, value in metrics.items():
        if isinstance(value, (list, dict)):
            p(f"  {key}: {len(value)}项", "cyan")
        else:
            p(f"  {key}: {value}", "cyan")


def cmd_detailed_outline(project_id: str = DEFAULT_PROJECT):
    """查看细纲。"""
    detailed = json_store.get_detailed_outline(project_id)
    if not detailed or not detailed.get("chapters"):
        p("\n暂无细纲", "yellow")
        return
    chapters = detailed.get("chapters", [])
    p(f"\n细纲 ({len(chapters)} 章):", "green")
    for i, ch in enumerate(chapters, 1):
        if not ch:
            continue
        title = ch.get("title", f"第{i}章")
        plot_chain = ch.get("plot_chain", [])
        p(f"  [{i}] {title} ({len(plot_chain)} 个事件)", "cyan")
        for j, ev in enumerate(plot_chain[:5], 1):
            p(f"    {j}. {str(ev)[:80]}", "dim")


def cmd_chapter_history(chapter_ref: str, project_id: str = DEFAULT_PROJECT):
    """查看章节历史版本。"""
    ch = json_store.get_chapter(project_id, chapter_ref)
    if not ch:
        p(f"\n未找到章节: {chapter_ref}", "red")
        return
    versions = ch.get("versions", [])
    if not versions:
        p("\n暂无历史版本", "yellow")
        return
    p(f"\n章节历史 ({len(versions)} 个版本):", "green")
    for v in versions:
        vid = v.get("version_id", "?")[:8]
        ts = v.get("timestamp", "")[:19]
        msg = v.get("message", "")
        p(f"  [{vid}] {ts} — {msg[:60]}", "cyan")


def cmd_count_words(project_id: str = DEFAULT_PROJECT):
    """统计字数。"""
    chapters = json_store.load_chapters(project_id)
    if not chapters:
        p("\n暂无章节", "yellow")
        return
    total = 0
    p(f"\n字数统计 ({len(chapters)} 章):", "green")
    for i, ch in enumerate(chapters, 1):
        view = json_store._chapter_view(ch)
        content = view.get("content", "")
        wc = len(content.replace("\n", "").replace(" ", "")) if content else 0
        total += wc
        title = view.get("title", ch.get("title", "无标题"))
        p(f"  [{i}] {title}: {wc}字", "cyan")
    p(f"\n  总计: {total}字", "bold green")


def cmd_graph_insights(project_id: str = DEFAULT_PROJECT):
    """获取图谱洞察。"""
    store = get_store(project_id)
    try:
        insights = store.get_graph_insights()
    except Exception:
        p("\n图谱查询失败（Neo4j 可能未运行）", "yellow")
        return
    if not insights:
        p("\n暂无图谱数据", "yellow")
        return
    p("\n图谱洞察:", "green")
    for key, value in insights.items():
        if isinstance(value, list):
            p(f"  {key}: {len(value)}条", "cyan")
            for item in value[:5]:
                p(f"    - {str(item)[:80]}", "dim")
        else:
            p(f"  {key}: {value}", "cyan")


def cmd_constraints(project_id: str = DEFAULT_PROJECT):
    """检查叙事约束。"""
    from core.narrative_logic.constraint_checker import ConstraintChecker

    store = get_store(project_id)
    checker = ConstraintChecker(store)
    violations = checker.check_all()
    if not violations:
        p("\n✅ 所有约束通过", "green")
        return
    p(f"\n约束违反 ({len(violations)} 项):", "yellow")
    for v in violations[:10]:
        sev = "🔴" if v.severity == "hard" else "🟡"
        p(f"  {sev} [{v.severity}] {v.description}", "cyan")
        for detail in v.violations[:3]:
            p(f"     - {detail}", "dim")


def cmd_refs(project_id: str = DEFAULT_PROJECT):
    """查看参考书。"""
    ref_ids = json_store.get_reference_books(project_id)
    if not ref_ids:
        p("\n暂无参考书", "yellow")
        return
    p(f"\n参考书 ({len(ref_ids)} 本):", "green")
    for ref_id in ref_ids:
        book = json_store.get_book(ref_id)
        if book:
            p(f"  [{ref_id[:8]}] {book.get('title', '未知')}", "cyan")


def cmd_list_books():
    """列出所有书籍项目。"""
    books = json_store.load_books()
    if not books:
        p("\n暂无书籍项目", "yellow")
        return
    p(f"\n书籍列表 ({len(books)} 本):", "green")
    for b in books:
        bid = b.get("id", "")[:16]
        title = b.get("title", "无标题")
        # Compute real chapter/entity counts from actual data
        chapters = json_store.load_chapters(bid) if bid else []
        chapter_count = len(chapters) if chapters else b.get("chapterCount", 0)
        try:
            store = get_store(bid)
            entity_count = len(store.list_entities())
        except Exception:
            entity_count = b.get("entityCount", 0)
        p(f"  [{bid}] {title} ({chapter_count}章, {entity_count}实体)", "cyan")


def _load_history(session_id: str):
    """加载历史记录。"""
    try:
        with open(f"data/{session_id}_history.json", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _persist_history(session_id: str, user_message: str, agent_response: str):
    """持久化历史记录。"""
    history = _load_history(session_id)
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": agent_response})
    # 保留最近 50 轮
    history = history[-100:]
    try:
        with open(f"data/{session_id}_history.json", "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except (OSError, TypeError) as e:
        import logging

        logging.getLogger(__name__).warning(f"Failed to save history: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="AI 小说写作辅助 Agent CLI — 基于 LLM 的小说创作辅助工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 交互模式
  python -m src.main

  # 非交互模式（执行单条命令后退出）
  python -m src.main --non-interactive "/s 主角是一个穿越到异世界的程序员"
  python -m src.main --non-interactive "/w 写第一章，主角发现自己有了魔法能力"

  # 指定项目
  python -m src.main -p my_novel

在线文档:
  API 文档: http://localhost:8191/docs
  项目文档: docs/README.md
""",
    )
    parser.add_argument("-v", "--version", action="version", version="AI Novel Agent 0.5.0")
    parser.add_argument("-p", "--project", default=DEFAULT_PROJECT, help="项目 ID（默认: cli）")
    parser.add_argument("--non-interactive", action="store_true", help="非交互模式（执行单条命令后退出）")
    parser.add_argument("command", nargs="*", help="要执行的命令（非交互模式）")

    args = parser.parse_args()
    current_project = args.project

    if args.non_interactive and args.command:
        # 非交互模式：执行单条命令后退出
        cmd_str = " ".join(args.command)
        _execute_command(cmd_str, current_project)
        sys.exit(0)

    # 交互模式
    p("\n[bold cyan]====================================[/bold cyan]")
    p("[bold cyan]  AI 小说写作辅助 Agent — CLI[/bold cyan]")
    p("[bold cyan]====================================[/bold cyan]")
    p(f"当前项目: {current_project}", "dim")
    p("输入 /help 查看命令")
    p()

    while True:
        try:
            user_input = input(f"[{current_project}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            p("\n再见！", "dim")
            break

        if not user_input:
            continue

        if user_input.startswith("/project "):
            new_project = user_input[9:].strip()
            current_project = new_project
            p(f"已切换到项目: {current_project}", "green")
            continue

        _execute_command(user_input, current_project)


def _execute_command(user_input: str, project_id: str):
    """执行单条命令。"""
    # 移除可能的 BOM 字符
    user_input = user_input.lstrip("\ufeff").strip()

    # Auto-create book entry for CLI projects (Neo4j + JSON dual-store sync)
    _ensure_book(project_id)

    if user_input.startswith("/s "):
        cmd_submit(user_input[3:], project_id)
    elif user_input.startswith("/w "):
        cmd_write(user_input[3:], mode="strict", project_id=project_id)
    elif user_input.startswith("/ws "):
        cmd_write(user_input[4:], mode="suggest", project_id=project_id)
    elif user_input.startswith("/chat "):
        cmd_chat(user_input[6:], project_id)
    elif user_input.startswith("/query "):
        cmd_query(user_input[7:], project_id)
    elif user_input == "/list":
        cmd_list(project_id)
    elif user_input.startswith("/char "):
        cmd_char_detail(user_input[6:], project_id)
    elif user_input == "/chapters":
        cmd_chapters(project_id)
    elif user_input == "/volumes":
        cmd_volumes(project_id)
    elif user_input == "/timeline":
        cmd_timeline(project_id)
    elif user_input == "/outline":
        cmd_outline(project_id)
    elif user_input.startswith("/del "):
        cmd_delete(user_input[5:], project_id)
    elif user_input == "/export":
        cmd_export(project_id)
    elif user_input == "/stats":
        cmd_stats(project_id)
    elif user_input.startswith("/search "):
        cmd_search(user_input[8:], project_id)
    elif user_input.startswith("/read "):
        cmd_read_chapter(user_input[6:], project_id)
    elif user_input == "/world":
        cmd_worldbuilding(project_id)
    elif user_input == "/detailed":
        cmd_detailed_outline(project_id)
    elif user_input.startswith("/history "):
        cmd_chapter_history(user_input[9:], project_id)
    elif user_input == "/count":
        cmd_count_words(project_id)
    elif user_input == "/graph":
        cmd_graph_insights(project_id)
    elif user_input == "/constraints":
        cmd_constraints(project_id)
    elif user_input == "/refs":
        cmd_refs(project_id)
    elif user_input == "/books":
        cmd_list_books()
    elif user_input == "/help":
        cmd_help()
    elif user_input == "/quit":
        p("再见！", "dim")
        sys.exit(0)
    else:
        # Unknown command that starts with / — show helpful error
        if user_input.startswith("/"):
            p(
                f"未知命令: {user_input.split()[0] if ' ' in user_input else user_input}。输入 /help 查看可用命令。",
                "yellow",
            )
        else:
            cmd_query(user_input, project_id)


if __name__ == "__main__":
    main()
