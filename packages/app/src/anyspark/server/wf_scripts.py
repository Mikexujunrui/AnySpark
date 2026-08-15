"""
anyspark.server.wf_scripts — workflow script 函数集（从 app.py 拆出，S187 技术债清理）。

包含工作流执行器所需的：
- WfScriptDeps：依赖容器（持有 model/chapters/graph/settings/library/workspace/skills/deps）
- wf_run_agent / wf_run_subagent / wf_run_script / wf_run_approval / wf_runner：节点执行器
- wf_resolve：变量插值（{{var}} → 上游节点输出）
- wf_judge：model 型条件判断
- wf_scripts：script 函数注册表（20 个确定性函数：读写章节/设定/图谱/参考书/信号提炼等）

从 app.py 闭包提取为模块级函数，依赖通过 WfScriptDeps 传入（不再捕获 build_app 局部变量）。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from anyspark.check import run_review
from anyspark.core import Message
from anyspark.library.search import search_reference_books
from anyspark.server.logging import logger
from anyspark.server.tools_domain import render_reference_knowledge
from anyspark.workflow import NodeResult, RunContext, wait_approval


class WfScriptDeps:
    """工作流脚本依赖容器（build_app 装配后传入）。

    持有闭包变量替代：model/chapters/graph/settings/library/workspace/skills/deps。
    deps 在 build_app 中后赋值（先创建 engine 占位，deps 就绪后回填）。
    """

    def __init__(self) -> None:
        self.model: Any = None  # Model（build_app 赋值）
        self.chapters: Any = None  # ChapterStore
        self.graph: Any = None  # GraphStore
        self.settings: Any = None  # WorldSettingStore
        self.library: Any = None  # LibraryStore
        self.workspace: Any = None  # Workspace | None
        self.skills: Any = None  # WritingSkillStore | None
        self.deps: Any = None  # AppDeps（后赋值）


def wf_run_agent(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    """agent 节点：干净单次 LLM 调用（无对话历史/工具记录——对齐 S56 干净写作）。

    S115 提案 B：params.delegate 存在 → 子 Agent 执行（独立上下文跑完整工具循环，
    工具白名单 scope.tools，预算 budget.max_turns）——工作流=通用固定流程执行器。
    变量插值：instruction/system_prompt 中的 {{var}} 从上游节点输出解析
    （如 {{chapter_text}} = 前序 read_chapter 脚本的产出）——真实链路暴露的
    接缝：AI 生成的流程若不插值，agent 拿不到章节内容。
    """
    if node.params.get("delegate"):
        return wf_run_subagent(wfd, ctx, node)

    instruction = wf_resolve(str(node.params.get("instruction") or ""), ctx)
    system = wf_resolve(str(node.params.get("system_prompt") or ""), ctx)
    # 便捷注入：params.chapter_title 指定章节时自动附带正文
    chapter_title = str(node.params.get("chapter_title") or "")
    if chapter_title:
        ch = next(
            (c for c in wfd.chapters.list_by_book(ctx.book_id) if c.title == chapter_title),
            None,
        )
        if ch is not None:
            # S109：工作流章节注入阈值 8000→15000；超限告知边界（直调无工具）
            ch_content = ch.content or ""
            if len(ch_content) > 15000:
                ch_content = (
                    f"【注意：本章全文 {len(ch.content)} 字，以下仅前 15000 字，"
                    "末尾部分未展示】\n" + ch_content[:15000]
                )
            instruction = f"【章节正文】\n{ch_content}\n\n{instruction}"
    messages: list[Any] = []
    if system:
        messages.append(Message(role="system", content=system))
    messages.append(Message(role="user", content=instruction))
    out = wfd.model.respond(messages, [])
    text = (out.text or "").strip()
    if not text:
        return NodeResult(error="agent 节点空输出")
    usage = getattr(out, "usage", None)
    tokens = int(getattr(usage, "total_tokens", 0) or 0)
    return NodeResult(output=text, token_usage=tokens)


def wf_run_subagent(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    """S115 提案 B：子 Agent 执行（独立上下文跑完整工具循环）。

    delegate 配置（节点 params.delegate）：
        {
          "scope": {"tools": [工具名...]},   # 工具白名单（空=全量）
          "budget": {"max_turns": 10},       # 子 Agent 轮数护栏
        }
    - fresh 上下文：InMemoryConversationStore（不落库、不受父会话污染）
    - 复用 core Agent 完整循环（含 S108b 重复检测/取消/工具执行）
    - 产出：turn.text 作为 NodeResult.output（返回父流程，作为一条工具结果）
    """
    from anyspark.server.subagent import run_subagent_task

    instruction = wf_resolve(str(node.params.get("instruction") or ""), ctx)
    system = wf_resolve(str(node.params.get("system_prompt") or ""), ctx)
    delegate = node.params.get("delegate") or {}
    scope = delegate.get("scope") or {}
    scope_tools = list(scope.get("tools") or [])
    budget = delegate.get("budget") or {}
    max_turns = int(budget.get("max_turns") or 10)

    r = run_subagent_task(
        wfd.deps,
        instruction=instruction,
        system_prompt=system,
        scope_tools=scope_tools or None,
        max_turns=max_turns,
        book_id=ctx.book_id,
    )
    if not r["ok"]:
        return NodeResult(error=r["error"])
    return NodeResult(output=r["output"], token_usage=0)


def wf_resolve(text: str, ctx: RunContext) -> str:
    """把 {{var}} 占位符替换为上游节点输出（缺失保留原样）。"""
    import re

    def _repl(m: re.Match[str]) -> str:
        key = m.group(1)
        val = ctx.results.get(key, "")
        if val is None or val == "":
            return f"{{{{{key}}}}}"
        # S158：list/dict 变量 JSON 序列化——str(list) 是 python repr（单引号），
        # 下游 json.loads 会失败（8-15 实测：agent 传 chapter_ids 数组 → batch_prepare
        # 解析失败 → 误跑全部 1282 章 + loop 0 次）
        if isinstance(val, (list, dict)):
            return json.dumps(val, ensure_ascii=False)
        return str(val)

    return re.sub(r"\{\{\s*([A-Za-z0-9_.\-]+)\s*\}\}", _repl, text)


# ------------------------------------------------------------------
# S150（REPAIR-LIST D1）：script 函数拆分——每个 script 独立方法 + 注册表分发
# （此前 500 行 if/elif 单函数，每阶段加分支持续膨胀）
wf_scripts: dict[str, Callable[[WfScriptDeps, RunContext, Any], NodeResult]] = {}


def wf_script_noop(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    # 无操作（AI 生成流程常用来做循环体出口占位）
    return NodeResult(output=str(node.params.get("output_key") or "done"))


wf_scripts["noop"] = wf_script_noop


def wf_script_read_chapter(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    title = wf_resolve(str(node.params.get("chapter_title") or ""), ctx)
    chs = wfd.chapters.list_by_book(ctx.book_id)
    ch = next((c for c in chs if c.title == title), None)
    if ch is None:
        # 模糊匹配（AI 生成标题可能不精确——真实链路暴露）：
        # ① 双向包含 ② 提取双方"第X章"片段做章号匹配
        def _chapter_no(t: str) -> str:
            import re as _re

            m = _re.search(r"第\s*([0-9一二三四五六七八九十百]+)\s*章", t)
            return m.group(1) if m else ""

        t_no = _chapter_no(title)
        for c in chs:
            if title and (title in c.title or c.title in title):
                ch = c
                break
            if t_no and _chapter_no(c.title) == t_no:
                ch = c
                break
    if ch is None:
        return NodeResult(
            error=f"章节不存在: {title}（可用章节: " + ", ".join(c.title for c in chs[:8]) + "）"
        )
    return NodeResult(output=ch.content)


wf_scripts["read_chapter"] = wf_script_read_chapter


def wf_script_review_chapter(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    title = wf_resolve(str(node.params.get("chapter_title") or ""), ctx)
    ch = next((c for c in wfd.chapters.list_by_book(ctx.book_id) if c.title == title), None)
    if ch is None:
        return NodeResult(error=f"章节不存在: {title}")
    report = run_review(wfd.model, ch.title, ch.content[:20000])
    return NodeResult(output=f"硬伤数: {report.hard_count}\n" + report.render())


wf_scripts["review_chapter"] = wf_script_review_chapter


def wf_script_list_chapters(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    chs = wfd.chapters.list_by_book(ctx.book_id)
    if not chs:
        return NodeResult(output="（无章节）")
    return NodeResult(output="\n".join(f"{c.order_index}. {c.title}" for c in chs))


wf_scripts["list_chapters"] = wf_script_list_chapters


def wf_script_write_chapter(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    """写回章节：参数 chapter_title + content（或 {{var}} 引用上游改写结果）。

    content 缺失时取 params.text_key（缺省 'rewritten'）对应的上游输出——
    AI 生成的流程常用：改写 agent 输出 rewritten → write_chapter 脚本落盘。
    chapter_title/content 支持 {{var}} 解析（如 {{chapter_title}} 来自 run params）。
    """
    title = wf_resolve(str(node.params.get("chapter_title") or ""), ctx)
    content = wf_resolve(str(node.params.get("content") or ""), ctx)
    if not content:
        text_key = str(node.params.get("text_key") or "rewritten")
        content = str(ctx.results.get(text_key, ""))
    if not title:
        return NodeResult(error="write_chapter 缺 chapter_title")
    if not content.strip():
        return NodeResult(error="write_chapter 无内容（检查 text_key 上游输出）")
    try:
        # S138（B1）：版本 note 携带来源——批量任务写回带任务标识，
        # 供批级回滚（rollback）按来源聚合定位改前快照。
        src_note = (
            f"批量任务/任务{getattr(ctx, 'task_id', '')}"
            if getattr(ctx, "task_id", "")
            else "修改前"
        )
        chs = wfd.chapters.list_by_book(ctx.book_id)
        ch = next((c for c in chs if c.title == title), None)
        if ch is None:
            order = len(chs) + 1
            wfd.chapters.upsert(ctx.book_id, title, content, order, note=src_note)
        else:
            wfd.chapters.upsert(ctx.book_id, title, content, ch.order_index, note=src_note)
            # 双写落盘（工作区 md 权威，与 write_chapter 工具一致）
        try:
            if wfd.workspace is not None:
                order = ch.order_index if ch else (len(chs) + 1)
                wfd.workspace.write_chapter(ctx.book_id, order, title, content)
        except Exception:
            pass  # 库镜像已更新，落盘失败不阻断
        return NodeResult(output=f"已写回章节: {title}")
    except Exception as exc:
        return NodeResult(error=f"写回失败: {exc}")


wf_scripts["write_chapter"] = wf_script_write_chapter


def wf_script_read_settings(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    """读本项目设定档（正典设定）→ 文本块（供 agent 注入，防 OOC）。

    params: keyword 可选（过滤分类/名称/内容）；limit 缺省 40。
    """
    keyword = str(node.params.get("keyword") or "").strip()
    try:
        limit = max(1, min(200, int(str(node.params.get("limit") or "40"))))
    except ValueError:
        limit = 40
    try:
        items = wfd.settings.list(ctx.book_id)
    except Exception as exc:
        return NodeResult(error=f"读设定档失败: {exc}")
    lines = []
    for s in items:
        if keyword and keyword.lower() not in f"{s.name} {s.content} {s.category}".lower():
            continue
        # S157：条目内容不截断（设定条目是查证核心信息，写全了却截断没道理）
        lines.append(f"[{s.category}] {s.name or s.content[:30]}：{s.content}")
        if len(lines) >= limit:
            break
    if not lines:
        return NodeResult(output=f"（项目「{ctx.book_id}」设定档无匹配条目）")
    # S157：超限告知（limit 可调，但 agent 需知道还有更多条目）
    if len(items) > len(lines):
        lines.append(f"（设定档共 {len(items)} 条，已列 {len(lines)}，可调 limit 或带关键词精查）")
    return NodeResult(output="\n".join(lines))


wf_scripts["read_settings"] = wf_script_read_settings


def wf_script_read_graph(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    """读本项目图谱（人物/地点/伏笔状态 + 关系）→ 文本块（供 agent 注入）。

    params: keyword 可选（实体名/别名匹配）；limit 缺省 20（按出场章数取 Top N）。
    """
    keyword = str(node.params.get("keyword") or "").strip()
    try:
        limit = max(1, min(100, int(str(node.params.get("limit") or "20"))))
    except ValueError:
        limit = 20
    try:
        ents = wfd.graph.list_entities(ctx.book_id, q=keyword or None, limit=200)
    except Exception as exc:
        return NodeResult(error=f"读图谱失败: {exc}")
    ents = sorted(ents, key=lambda e: -e.weight)[:limit]
    if not ents:
        return NodeResult(output=f"（项目「{ctx.book_id}」图谱无匹配实体）")
    lines = []
    try:
        rels = wfd.graph.list_relations(ctx.book_id, limit=500)
    except Exception:
        rels = []
    for e in ents:
        state = (e.state or e.description or "").strip()
        # S157：状态不截断（图谱实体状态是写作查证核心；实体数由 limit 控制防爆）
        line = f"实体[{e.entity_type}] {e.name}（出场{e.weight}章）" + (
            f"：{state}" if state else ""
        )
        for r in rels:
            if r.from_name == e.name or r.to_name == e.name:
                line += f"\n  ↳ {r.from_name} {r.rel_type} {r.to_name}"
        lines.append(line)
    return NodeResult(output="\n".join(lines))


wf_scripts["read_graph"] = wf_script_read_graph


def wf_script_query_reference(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    """查参考书（分级检索）：原文片段 + 高级参考书（项目）的图谱/设定知识层。

    params: keyword 必填（支持 {{var}} 解析，如 run params 传 ref_keyword）；
    max_per_book 缺省 3。复用 reference_lookup 分级检索。
    """
    keyword = wf_resolve(str(node.params.get("keyword") or ""), ctx).strip()
    if not keyword:
        return NodeResult(error="query_reference 缺 keyword")
    try:
        max_per = max(1, min(5, int(str(node.params.get("max_per_book") or "3"))))
    except ValueError:
        max_per = 3

    def _project_files(ref_book_id: str) -> str:
        parts = []
        for ch in wfd.chapters.list_by_book(ref_book_id):
            parts.append(f"【{ch.title}】\n{ch.content}")
        return "\n\n".join(parts)

    try:
        res = search_reference_books(
            wfd.library,
            ctx.book_id,
            keyword,
            project_files=_project_files,
            max_per_book=max_per,
        )
    except Exception as exc:
        return NodeResult(error=f"参考书检索失败: {exc}")
    lines = [f"参考书命中「{keyword}」："]
    for item in res.get("results", []):
        lines.append(f"——{item['ref_name']}——")
        for h in item.get("hits", []):
            lines.append(f"({h['count']}次) {h['snippet']}")
        # 高级参考书（项目）知识层：图谱/设定
    if wfd.library is not None:
        try:
            for ref in wfd.library.get_references(ctx.book_id):
                if ref.get("type") != "project":
                    continue
                klines = render_reference_knowledge(
                    wfd.graph, wfd.settings, str(ref.get("id", "")), keyword
                )
                if klines:
                    lines.append(f"——项目「{ref.get('id', '?')}」（知识层：图谱/设定）——")
                    lines.extend(klines)
        except Exception as exc:
            logger.warning("参考书知识层渲染失败: %s", exc)
    if len(lines) == 1:
        return NodeResult(output=f"参考书中未命中「{keyword}」（含图谱/设定层）。")
    return NodeResult(output="\n\n".join(lines))


wf_scripts["query_reference"] = wf_script_query_reference


def wf_script_chapter_extract(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    """S134（WORKFLOW 第 3 批）：单章图谱抽取+伏笔回收+学习审查。

    复用 tasks.extract_chapter（落库形态与现后台任务一致）：读 chapter_id →
    图谱抽取/伏笔回收/学习审查三合一。params.item_var（缺省 "item"）= chapter_id。
    """
    from anyspark.server import tasks as _tasks

    cid = str(ctx.var(str(node.params.get("item_var") or "item")) or "").strip()
    if not cid:
        return NodeResult(error="chapter_extract 缺 item（chapter_id）")
    ch = wfd.chapters.get(cid)
    if ch is None:
        # S158：宽容回退——按标题/序号查（batch_prepare 已归一，此为直跑/手写模板兜底）
        for c in wfd.chapters.list_by_book(ctx.book_id):
            if c.title == cid or str(c.order_index) == cid:
                ch = c
                break
    if ch is None:
        return NodeResult(error=f"章节不存在: {cid}")
    _tasks.extract_chapter(wfd.deps, ctx.book_id, ch.title, ch.content or "", ch.order_index)
    return NodeResult(output=f"图谱抽取完成: 《{ch.title}》")


wf_scripts["chapter_extract"] = wf_script_chapter_extract


def wf_script_signal_refine(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    """S134：信号 → 偏好提炼 → 说明书（复用 tasks.refine_from_signals，增量游标）。"""
    from anyspark.server import tasks as _tasks

    before = len(wfd.deps.manual.list("project", "main"))
    _tasks.refine_from_signals(wfd.deps)
    after = len(wfd.deps.manual.list("project", "main"))
    return NodeResult(output=f"信号提炼完成（说明书 {before}→{after} 条）")


wf_scripts["signal_refine"] = wf_script_signal_refine


def wf_script_conversation_summarize(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    """S134：会话 → 场景记忆摘要（复用 tasks.summarize_conversation）。

    params.conv_id：会话 id（{{var}} 解析）。
    """
    from anyspark.server import tasks as _tasks

    conv_id = wf_resolve(str(node.params.get("conv_id") or ""), ctx).strip()
    if not conv_id:
        return NodeResult(error="conversation_summarize 缺 conv_id")
    _tasks.summarize_conversation(wfd.deps, conv_id)
    return NodeResult(output=f"会话归档摘要完成: {conv_id}")


wf_scripts["conversation_summarize"] = wf_script_conversation_summarize


def wf_script_enrich_stitch(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    """S137：加料拼接——把 agent 生成的插入内容合并进原文（定点插入，原文保留）。

    agent 输出含 【插入】...【/插入】 标记（可多处；带锚点说明）：
      原文……【插入】新增内容【/插入】原文……
    stitch 把标记块原位展开并入原文；未提供完整标记时把插入块追加到章末。
    params：source_var（原章文本变量名，缺省 "chapter_text"）/ insert_var
    （agent 输出变量名，缺省 "enriched"）。输出完整增强版正文。
    """
    import re as _re

    src = str(ctx.var(str(node.params.get("source_var") or "chapter_text")) or "")
    insert = str(ctx.var(str(node.params.get("insert_var") or "enriched")) or "")
    if not src.strip():
        return NodeResult(error="enrich_stitch 缺源章文本（source_var 上游未产出）")
    if not insert.strip():
        return NodeResult(error="enrich_stitch 缺插入内容（insert_var 上游未产出）")
        # 方案 A：agent 已产出带【插入】标记的完整正文 → 直接合并标记块
    if "【插入】" in insert:

        def _expand(m: _re.Match[str]) -> str:
            return m.group(1)

        merged = _re.sub(r"【插入】\s*(.*?)\s*【/插入】", _expand, insert, flags=_re.S)
        if merged.strip():
            return NodeResult(output=merged)
        # 方案 B：agent 只产出纯插入段 → 追加到章末（保原文不丢）
    return NodeResult(output=f"{src.rstrip()}\n\n{insert.strip()}")


wf_scripts["enrich_stitch"] = wf_script_enrich_stitch


def wf_script_batch_prepare(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    """S133（WORKFLOW 第 2 批）：批量任务准备——收集章节 id 集合（遍历源）。

    params：chapter_ids（逗号分隔或 JSON 数组，支持 {{var}} 从 run params 传入）；
    缺省=当前项目全部章节（list_chapters 同源）。输出 JSON 数组供 loop collection_var。
    """
    import json as _json

    raw = wf_resolve(str(node.params.get("chapter_ids") or ""), ctx).strip()
    ids: list[str] = []
    if raw:
        raw_items: list[str] = []
        try:
            parsed = _json.loads(raw)
            raw_items = [str(x) for x in parsed] if isinstance(parsed, list) else [str(parsed)]
        except Exception:
            raw_items = [x.strip() for x in raw.split(",") if x.strip()]
        # S158：宽容解析——id/标题/序号都接受（8-15 实测：agent 拿不到 id 时
        # 会传标题数组或序号，直接原样透传 chapter_extract 会查不到章节）
        all_chs = wfd.chapters.list_by_book(ctx.book_id)
        by_title = {c.title: c.id for c in all_chs}
        by_order = {str(c.order_index): c.id for c in all_chs}
        existing = {c.id for c in all_chs}
        for it in raw_items:
            if it in existing:
                ids.append(it)
            elif it in by_title:
                ids.append(by_title[it])
            elif it in by_order:
                ids.append(by_order[it])
    if not ids:
        # 缺省全部章节
        ids = [c.id for c in wfd.chapters.list_by_book(ctx.book_id)]
    if not ids:
        return NodeResult(error="batch_prepare 无章节（chapter_ids 为空且项目无章节）")
    # S158：output 保持纯 JSON 数组（loop 的 collection_var 直接 json.loads）——
    # 之前把 unresolved 报告拼在 JSON 后面会破坏解析（loop 读到空 collection 0 次）
    return NodeResult(output=_json.dumps(ids, ensure_ascii=False))


wf_scripts["batch_prepare"] = wf_script_batch_prepare


def wf_script_chapter_by_id(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    """S133：按 chapter_id 读章节（标题+正文）——loop 集合遍历逐项喂 agent。

    读 params.item_var（缺省 "item"）为 chapter_id，输出「标题\n正文」；
    超长章（>20000）告知边界（对齐 run_batch_rewrite）。
    """
    cid = str(ctx.var(str(node.params.get("item_var") or "item")) or "").strip()
    if not cid:
        return NodeResult(error="chapter_by_id 缺 item（chapter_id）")
    ch = wfd.chapters.get(cid)
    if ch is None:
        return NodeResult(error=f"章节不存在: {cid}")
    ch_content = ch.content or ""
    if len(ch_content) > 20000:
        ch_content = (
            f"【注意：本章全文 {len(ch.content)} 字，以下仅前 20000 字，"
            "末尾部分未展示】\n" + ch_content[:20000]
        )
    return NodeResult(output=f"【{ch.title}】\n{ch_content}")


wf_scripts["chapter_by_id"] = wf_script_chapter_by_id


def wf_script_chapter_title_by_id(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    """S133：按 chapter_id 取章标题（write_chapter 落盘用）。

    读 params.item_var（缺省 "item"）为 chapter_id → 输出标题。
    """
    cid = str(ctx.var(str(node.params.get("item_var") or "item")) or "").strip()
    if not cid:
        return NodeResult(error="chapter_title_by_id 缺 item（chapter_id）")
    ch = wfd.chapters.get(cid)
    if ch is None:
        return NodeResult(error=f"章节不存在: {cid}")
    return NodeResult(output=ch.title)


wf_scripts["chapter_title_by_id"] = wf_script_chapter_title_by_id


def wf_script_book_refine_prepare(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    """S129（WORKFLOW 第 1 批）：拆书准备——从书库读全书 → 选章 → 分批。

    确定性步骤（复用 skillgen 选章/分批逻辑）：
    params.library_book_id：书库书 id（支持 {{var}} 解析，如 run params 传入）
    params.batch_size：每批章数（缺省 4，对齐 skillgen._BATCH_SIZE）
    输出 JSON：{"batches": [...], "titles": [...]}——batches 供 loop collection_var
    遍历，titles 供骨架扫描（章标题轨迹）。
    """
    import json as _json

    from anyspark.align.skillgen import (
        _BATCH_SIZE as _SK_BATCH,
    )
    from anyspark.align.skillgen import (
        _build_batches as _build_batches_fn,
    )
    from anyspark.align.skillgen import (
        _parse_chapters as _parse_chapters_fn,
    )
    from anyspark.align.skillgen import (
        _select_structural_chapters as _select_fn,
    )

    bid = wf_resolve(str(node.params.get("library_book_id") or ""), ctx).strip()
    if not bid:
        return NodeResult(error="book_refine_prepare 缺 library_book_id")
    try:
        batch_size = max(1, min(8, int(str(node.params.get("batch_size") or _SK_BATCH))))
    except ValueError:
        batch_size = _SK_BATCH
    if wfd.library is None:
        return NodeResult(error="书库不可用（未装配）")
    book = wfd.library.get_book(bid)
    if book is None:
        return NodeResult(error=f"书库无此书：{bid}")
    source = wfd.library.read_book(bid, max_chars=None).strip()
    if not source:
        return NodeResult(error=f"书库《{book['name']}》无内容（先导入文本）")
    chaps = _parse_chapters_fn(source)
    if len(chaps) < 5:  # 无章节结构回退均匀抽样（对齐 generate_book）
        batches = [source]
        titles = []
    else:
        selected = _select_fn(chaps)
        batches = _build_batches_fn(chaps, selected, batch_size)
        titles = [t for t, _ in chaps]
    return NodeResult(
        output=_json.dumps(
            {"batches": batches, "titles": titles, "book_name": book["name"]},
            ensure_ascii=False,
        )
    )


wf_scripts["book_refine_prepare"] = wf_script_book_refine_prepare


def wf_script_book_refine_titles(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    """S129：取全书章标题（骨架扫描输入——标题轨迹无正文）。

    params.library_book_id：书库书 id。输出："第1章 标题\n第2章 标题..."
    （超 _MAX_SKELETON_TITLES 抽稀，对齐 skillgen 骨架扫描）。
    """
    from anyspark.align.skillgen import (
        _MAX_SKELETON_TITLES as _SK_TITLES,
    )
    from anyspark.align.skillgen import (
        _parse_chapters as _parse_chapters_fn,
    )

    bid = wf_resolve(str(node.params.get("library_book_id") or ""), ctx).strip()
    if not bid:
        return NodeResult(error="book_refine_titles 缺 library_book_id")
    if wfd.library is None:
        return NodeResult(error="书库不可用（未装配）")
    book = wfd.library.get_book(bid)
    if book is None:
        return NodeResult(error=f"书库无此书：{bid}")
    source = wfd.library.read_book(bid, max_chars=None).strip()
    chaps = _parse_chapters_fn(source)
    n = len(chaps)
    if n < 1:
        return NodeResult(output=f"《{book['name']}》（无章节标题）")
    titles = [t for t, _ in chaps]
    if n > _SK_TITLES:
        step = n / _SK_TITLES
        titles = [titles[int(i * step)] for i in range(_SK_TITLES - 1)] + [titles[-1]]
    lines = [f"第{i + 1}章 {t}" for i, t in enumerate(titles)]
    return NodeResult(output=f"《{book['name']}》\n" + "\n".join(lines))


wf_scripts["book_refine_titles"] = wf_script_book_refine_titles


def wf_script_book_refine_accumulate(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    """S129：累计单批拆解结果 → partials JSON 数组。
    读 params.item_var（缺省 "partial"）对应的上游 agent 输出，append 进
    params.list_var（缺省 "partials"）数组；输出更新后的数组（供归并 agent 读）。
    """
    import json as _json

    item_var = str(node.params.get("item_var") or "partial")
    list_var = str(node.params.get("list_var") or "partials")
    item = str(ctx.var(item_var) or "")
    if not item.strip():
        return NodeResult(error=f"book_refine_accumulate 缺 {item_var}（上游未产出）")
    current = ctx.var(list_var)
    try:
        arr = _json.loads(current) if isinstance(current, str) and current.strip() else []
    except Exception:
        arr = []
    arr.append(item)
    return NodeResult(output=_json.dumps(arr, ensure_ascii=False))


wf_scripts["book_refine_accumulate"] = wf_script_book_refine_accumulate


def wf_script_book_refine_refine_input(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    """S129：定点精读输入准备——从骨架笔记定位机关章 → 精读原文片段。

    复用 skillgen 的 _extract_chapter_nums / _locate_mechanism_passages：
    骨架笔记提到机关章号 → 拼机关章 + 首尾章 + 关键词定位段（确定性，防案例幻觉的
    先给原文）。params.note：骨架笔记（{{var}} 解析）；params.library_book_id。
    """
    from anyspark.align.skillgen import (
        _extract_chapter_nums as _ext_nums,
    )
    from anyspark.align.skillgen import (
        _locate_mechanism_passages as _locate_passages,
    )

    note = wf_resolve(str(node.params.get("note") or ""), ctx).strip()
    bid = wf_resolve(str(node.params.get("library_book_id") or ""), ctx).strip()
    if not note or not bid:
        return NodeResult(error="book_refine_refine_input 缺 note/library_book_id")
    if wfd.library is None:
        return NodeResult(error="书库不可用（未装配）")
    book = wfd.library.get_book(bid)
    if book is None:
        return NodeResult(error=f"书库无此书：{bid}")
    source = wfd.library.read_book(bid, max_chars=None).strip()
    from anyspark.align.skillgen import _parse_chapters as _parse_chapters_fn

    chaps = _parse_chapters_fn(source)
    if len(chaps) < 2:
        return NodeResult(output="（章节不足，跳过定点精读）")
    nums = _ext_nums(note)
    idxs: set[int] = set()
    for a, b in nums:
        for k in range(a, min(b, a + 4) + 1):
            if 1 <= k <= len(chaps):
                idxs.add(k - 1)
    idxs.add(0)
    idxs.add(len(chaps) - 1)
    ref_idx = sorted(i for i in idxs if 0 < i < len(chaps) - 1)
    ordered = ([*ref_idx, 0, len(chaps) - 1])[:6]
    parts = []
    for i in ordered:
        t, body = chaps[i]
        # S157：截断保留（防爆）但必须告知——agent 知道片段不完整，需要时用 read_chapter 读全文
        cut = f"（正文 {len(body)} 字，仅列前 4000）" if len(body) > 4000 else ""
        parts.append(f"【第{i + 1}章 {t}】{cut}\n{body[:4000]}")
    passages = _locate_passages(chaps, note)
    excerpt = "\n\n".join([*passages, *parts])
    note_cut = f"（笔记 {len(note)} 字，仅列前 2500）" if len(note) > 2500 else ""
    return NodeResult(output=f"{note[:2500]}{note_cut}\n\n{excerpt}")


wf_scripts["book_refine_refine_input"] = wf_script_book_refine_refine_input


def wf_script_book_refine_finish(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    """S129：拆书落草稿——解析三路 agent 候选 → skills.add_draft。

    params：merge(书名方法论)/arch(架构技法)/plot(剧情模式) 三路文本
    （{{var}} 解析）+ refine_excerpt（精读原文，供架构技法案例机器校验）。
    确定性解析复用 skillgen._parse_skills/_parse_templates（含枚举校验回落）
    + _sanitize_examples（防案例幻觉：引号句必须逐字在精读片段）。
    类型映射对齐 generate_book：merge→both（文风给写作、结构给主循环）；
    arch→main（架构机关给主循环）；plot→plot（四要素进 ext）。
    """
    import json as _json

    from anyspark.align.skillgen import (
        _parse_skills as _ps,
    )
    from anyspark.align.skillgen import (
        _parse_templates as _pt,
    )
    from anyspark.align.skillgen import (
        _sanitize_examples as _san,
    )

    merge_raw = wf_resolve(str(node.params.get("merge") or ""), ctx).strip()
    arch_raw = wf_resolve(str(node.params.get("arch") or ""), ctx).strip()
    plot_raw = wf_resolve(str(node.params.get("plot") or ""), ctx).strip()
    excerpt = wf_resolve(str(node.params.get("refine_excerpt") or ""), ctx)
    # S130：拆书产物同书名一包（pack_id=书名，整包引用写作只取 writing/both）
    pack_id = wf_resolve(str(node.params.get("pack_id") or ""), ctx).strip()
    if not pack_id:
        # 回退：从 library_book_id 解析书名
        bid = wf_resolve(str(node.params.get("library_book_id") or ""), ctx).strip()
        if bid and wfd.library is not None:
            bk = wfd.library.get_book(bid)
            if bk is not None:
                pack_id = str(bk.get("name", ""))
    if wfd.skills is None:
        return NodeResult(error="skills 未装配（无法落草稿）")
    cands: list[dict[str, str]] = []
    # 书名方法论（GENERATE_PROMPT_BOOK 单元素输出）→ both
    for mk in _ps(merge_raw)[:1]:
        mk["type"] = "both"
        cands.append(mk)
        # 架构技法（REFINE_PROMPT 多元素）→ main + 案例机器校验
    arch_cands = _ps(arch_raw)
    for ac in arch_cands:
        ac["type"] = "main"
    cands.extend(_san(arch_cands, excerpt))
    # 剧情模式（骨架笔记版四要素）→ plot（content 由 description 派生）
    for pc in _pt(plot_raw):
        cands.append(
            {
                "name": pc["name"],
                "description": pc["description"],
                "content": f"剧情模式：{pc['description']}",
                "example": "",
                "tags": "剧情模式",
                "type": "plot",
                "granularity": pc["granularity"],
                "position": pc["position"],
                "function": pc["function"],
                "params": pc["params"],
            }
        )
    if not cands:
        return NodeResult(output="（无有效候选）")
    added = 0
    for cd in cands:
        typ = cd.get("type", "writing")
        ext = ""
        if typ == "plot":
            params: Any = cd.get("params", [])
            if isinstance(params, str):
                params = [p.strip() for p in params.split(",") if p.strip()]
            ext = _json.dumps(
                {
                    "granularity": cd.get("granularity", "章"),
                    "position": cd.get("position", "发展"),
                    "function": cd.get("function", "主线"),
                    "params": params or [],
                },
                ensure_ascii=False,
            )
        d = wfd.skills.add_draft(
            name=str(cd.get("name", ""))[:120],
            description=str(cd.get("description", ""))[:500],
            content=str(cd.get("content", "")),
            example=str(cd.get("example", ""))[:2000],
            tags=str(cd.get("tags", "")),
            type=typ,
            ext=ext,
            pack_id=pack_id,
            source="workflow",
        )
        if d:
            added += 1
    return NodeResult(output=f"已存 {added} 条 skill 草稿（人工确认后生效）")


wf_scripts["book_refine_finish"] = wf_script_book_refine_finish


def wf_run_script(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    """script 节点：确定性函数（内置白名单）——查表分发（S150 拆分）。"""
    fn = str(node.params.get("function") or "")
    handler = wf_scripts.get(fn)
    if handler is None:
        return NodeResult(error=f"未注册的 script 函数: {fn}")
    result = handler(wfd, ctx, node)
    assert isinstance(result, NodeResult)
    return result


def wf_run_approval(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    """approval 节点：抛等待信号（任务置 waiting_approval，人工 approve 后续跑）。"""
    wait_approval()
    return NodeResult(output="approved")


def wf_runner(wfd: WfScriptDeps, ctx: RunContext, node: Any) -> NodeResult:
    if node.kind == "agent":
        return wf_run_agent(wfd, ctx, node)
    if node.kind == "script":
        return wf_run_script(wfd, ctx, node)
    if node.kind == "approval":
        return wf_run_approval(wfd, ctx, node)
    return NodeResult(error=f"未知节点类型: {node.kind}")


def wf_judge(wfd: WfScriptDeps, prompt: str, ctx: RunContext) -> bool:
    """model 型条件：自然语言问题 → 模型判断 yes/no。

    真实链路暴露：模型答"否/不通过"时旧逻辑误判。强制输出 是/否 首字判定，
    明确否定词优先级（避免"没有硬伤"被"有"字误判）。
    """
    out = wfd.model.respond(
        [
            Message(
                role="system",
                content="你只判断一个条件是否成立。必须严格以单个字'是'或'否'开头回答，不要解释。",
            ),
            Message(role="user", content=prompt),
        ],
        [],
    )
    text = (out.text or "").strip()
    if not text:
        return False
    first = text[0]
    # 否定词优先（'不'/'没'/'无'/'否' 开头 → False；'是'/'通' 开头 → True）
    if first in ("不", "没", "无", "否", "非"):
        return False
    if first in ("是", "通", "可", "同", "y", "Y", "t", "T"):
        return True
    # 兜底：整句包含强肯定词且无否定词
    lower = text.lower()
    has_pos = any(w in lower for w in ("yes", "true", "通过", "可以", "同意"))
    has_neg = any(w in lower for w in ("no", "false", "不是", "不通过", "没有", "无法"))
    return has_pos and not has_neg
