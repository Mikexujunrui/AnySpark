"""
anyspark.server.tools_align — 心智登记/管理 + 技巧提炼工具。

工厂函数创建 agent 工具（ToolSpec + implementer 对），接收 store 参数，
不引用闭包——从 tools_domain.py 提取无行为变化。
"""

from __future__ import annotations

from typing import Any

from anyspark.align import ManualEntry
from anyspark.core import ToolCall
from anyspark.core.protocol import ParamSpec, ToolResult, ToolSpec


def make_mind_register_implementer(manual: Any, book_id: str = "main") -> tuple[Any, Any]:
    """S53c ① 心智登记工具：用户对话中"记一下"→ 立即落心智条目（user 来源，高置信度）。

    对应 DESIGN §12.18 更新方式 #1（用户主动登记）。让 agent 在对话中识别
    用户的明确偏好陈述并即时登记——不用等轮末提炼，不用打开说明书面板。
    category：collab(协作)/style(文风)/habit(习惯)。
    """

    spec = ToolSpec(
        name="mind_register",
        description=(
            "把用户说出的明确写作偏好/习惯/雷区登记进心智模型（写作说明书）。"
            "当用户在对话中明确表达偏好时使用，如'我写对话喜欢克制''不要用破折号'"
            "'我一般晚上写作'。用户否定/纠正你的写作（'我说了不要X''怎么又用了X'）时，"
            "若该偏好不在已披露的心智条目里，也登记为雷区/偏好；已存在则不重复登记。"
            "登记后后续写作自动遵循。"
            "category=collab(协作方式)/style(文风)/habit(习惯，含雷区)。"
        ),
        params=[
            ParamSpec(
                name="content",
                type="string",
                required=True,
                description="偏好内容（自然语言，如'对话要克制，少用感叹号'）",
            ),
            ParamSpec(
                name="category",
                type="string",
                required=False,
                description="collab/style/habit（缺省 style）",
            ),
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        content = str(arguments.get("content", "")).strip()
        category = str(arguments.get("category", "style")).strip() or "style"
        if not content:
            return ToolResult(call=call, ok=False, content="缺少参数 content。")
        if category not in ("collab", "style", "habit"):
            category = "style"
        try:
            entry = manual.add(
                ManualEntry(
                    content=content,
                    source="user",  # 用户亲口，高置信度
                    confidence=0.9,
                    activity="high",
                    scope="project",
                    book_id=book_id,
                    category=category,  # type: ignore[arg-type]
                )
            )
            return ToolResult(
                call=call,
                ok=True,
                content=f"已登记心智条目#{entry.id[:8]}（{category}）：{content}",
                data={"manual_id": entry.id, "category": category},
            )
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"登记失败：{exc}")

    return spec, implementer


def make_mind_manage_implementer(manual: Any, book_id: str = "main") -> tuple[list[Any], list[Any]]:
    """S73d 心智纠正工具：用户明确要求改/删心智条目时 agent 代执行。

    边界（对齐哲学）：内容裁决权在用户——agent 只在用户明确口头要求时
    修改/删除（"那条记错了/改成…/删掉"），不主动改删。
    """

    def _locate(query: str) -> list[Any]:
        """定位条目：id 精确匹配；否则内容/分类包含匹配。"""
        query = query.strip()
        if not query:
            return []
        all_entries = [*manual.list("global"), *manual.list("project", book_id)]
        if len(query) == 32 and all(c in "0123456789abcdef" for c in query):
            exact = manual.get(query)
            if exact is not None:
                return [exact]
        hits = [e for e in all_entries if query in e.content or query in e.category]
        return hits

    update_spec = ToolSpec(
        name="mind_update",
        description=(
            "修改心智条目（写作说明书）：用户明确说'那条记错了/改成…/锁定'时使用。"
            "用条目 id 或内容关键词定位（多个命中返回列表让用户确认）；"
            "可改 content（新内容）/category（collab/style/habit）/locked（锁定）。"
            "仅用户明确要求修改时调用，不主动改。"
        ),
        params=[
            ParamSpec(
                name="query",
                type="string",
                required=True,
                description="定位：条目 id（32 位）或内容关键词",
            ),
            ParamSpec(
                name="content",
                type="string",
                required=False,
                description="新内容（缺省不改内容）",
            ),
            ParamSpec(
                name="category",
                type="string",
                required=False,
                description="新分类 collab/style/habit（缺省不改）",
            ),
            ParamSpec(
                name="locked",
                # S135：bool→boolean（JSON Schema 标准类型；DeepSeek 官方 API 严格校验会 400）
                type="boolean",
                required=False,
                description="true 锁定/false 解锁（缺省不改）",
            ),
        ],
    )

    def update(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        query = str(arguments.get("query", "")).strip()
        if not query:
            return ToolResult(call=call, ok=False, content="缺少参数 query。")
        hits = _locate(query)
        if not hits:
            return ToolResult(call=call, ok=False, content=f"未找到匹配的心智条目：{query}")
        if len(hits) > 1:
            lines = [f"匹配到 {len(hits)} 条，请用更精确的 id 定位："]
            lines.extend(f"- {e.id} [{e.category}] {e.content}" for e in hits[:8])
            return ToolResult(call=call, ok=False, content="\n".join(lines))
        entry = hits[0]
        new_content = str(arguments.get("content", "")).strip()
        new_category = str(arguments.get("category", "")).strip() or entry.category
        if new_category not in ("collab", "style", "habit"):
            new_category = entry.category
        locked = arguments.get("locked")
        if locked is not None:
            manual.set_locked(entry.id, bool(locked))
        if entry.locked and (new_content or new_category != entry.category):
            return ToolResult(
                call=call,
                ok=False,
                content=(
                    f"条目已锁定（用户主权不可改）：[{entry.category}] {entry.content}"
                    "；先解锁再修改"
                ),
            )
        updated = manual.update(
            entry.id,
            content=new_content or entry.content,
            category=new_category,
        )
        if updated is None:
            return ToolResult(call=call, ok=False, content="更新失败（条目可能已被删除）。")
        return ToolResult(
            call=call,
            ok=True,
            content=f"已更新心智条目 [{updated.category}] {updated.content}"
            f"（锁定={'是' if updated.locked else '否'}）",
            data={"entry": updated.to_dict()},
        )

    delete_spec = ToolSpec(
        name="mind_delete",
        description=(
            "删除心智条目（写作说明书）：用户明确说'那条删掉/不要了'时使用。"
            "用条目 id 或内容关键词定位（多个命中返回列表让用户确认）；"
            "返回被删条目内容供追溯。仅用户明确要求删除时调用，不主动删。"
        ),
        params=[
            ParamSpec(
                name="query",
                type="string",
                required=True,
                description="定位：条目 id（32 位）或内容关键词",
            ),
        ],
    )

    def delete(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        query = str(arguments.get("query", "")).strip()
        if not query:
            return ToolResult(call=call, ok=False, content="缺少参数 query。")
        hits = _locate(query)
        if not hits:
            return ToolResult(call=call, ok=False, content=f"未找到匹配的心智条目：{query}")
        if len(hits) > 1:
            lines = [f"匹配到 {len(hits)} 条，请用更精确的 id 定位："]
            lines.extend(f"- {e.id} [{e.category}] {e.content}" for e in hits[:8])
            return ToolResult(call=call, ok=False, content="\n".join(lines))
        entry = hits[0]
        manual.delete(entry.id)
        return ToolResult(
            call=call,
            ok=True,
            content=f"已删除心智条目 [{entry.category}] {entry.content}",
            data={"deleted": entry.to_dict()},
        )

    return [update_spec, delete_spec], [update, delete]


def make_mind_reconcile_implementer(
    manual: Any, signals: Any, model: Any, book_id: str = "main"
) -> tuple[Any, Any]:
    """S132c 跨会话对账工具：条目 vs 最近行为信号 → 冲突/需更新提示（真实 LLM）。

    对应 DESIGN §12.18 更新方式 #6（跨会话对账纠偏）。agent 在合适时机主动调用
    （如用户质疑"你怎么老不按我说的来"/想检查心智是否记偏），结果转述用户，
    纠正走 mind_update/mind_delete（已有）。只读分析不自动改（用户主权），
    失败不影响主链路。不做周期任务——对账结果需要人工消费，agent 按需调用
    比定时跑更符合"相信模型+人工确认"哲学（克制：不加调度机制）。
    """

    spec = ToolSpec(
        name="mind_reconcile",
        description=(
            "跨会话对账：把已沉淀的心智条目（写作说明书）与最近实际行为信号比对，"
            "发现'标了雷区却在用/标了偏好却没遵守'的冲突。"
            "当用户质疑'你怎么老不按我说的来'、或想检查心智是否记偏时使用。"
            "只读分析（不自动改条目）；发现冲突后转述用户确认，纠正用 mind_update/mind_delete。"
        ),
        params=[],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        try:
            from anyspark.align.mindup import build_reconcile_prompt, parse_reconcile_result
            from anyspark.core.types import Message

            entries = manual.list("project", book_id)
            recent_signals = signals.recent(limit=30, book_id=book_id)
            if not entries:
                return ToolResult(call=call, ok=True, content="心智暂无条目，无需对账。")
            prompt = build_reconcile_prompt(entries, recent_signals)
            output = model.respond([Message(role="system", content=prompt)], [])
            results = parse_reconcile_result(output.text)
            if not results:
                return ToolResult(
                    call=call, ok=True, content="对账完成：未发现条目与实际行为冲突。"
                )
            lines = [
                "心智对账发现以下冲突/需更新（转述用户确认，纠正用 mind_update/mind_delete）："
            ]
            for r in results[:8]:
                lines.append(
                    f"- 条目「{r.get('entry', '')}」→ {r.get('verdict', '')}：{r.get('note', '')}"
                )
            return ToolResult(
                call=call, ok=True, content="\n".join(lines), data={"results": results}
            )
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"对账失败：{exc}")

    return spec, implementer


def make_skill_lookup_implementer(skills_store: Any) -> tuple[Any, Any]:
    """技巧查证工具：按名查看某条叙事技巧的完整内容（技法+案例）。

    S60：主循环只注入技巧索引（名字+描述，常驻轻量）；完整内容按需——
    智能体看到索引后，决定要用哪条时用本工具细看全文（对齐 graph_query：
    内容不常驻注入，需要时查）。与写作调用注入解耦：写作调用仍由主循环
    write_chapter 的 skills 参数点名或 style_prefs 自动匹配。
    """

    spec = ToolSpec(
        name="skill_lookup",
        description=(
            "查看某条叙事技巧的完整内容（技法正文 + 情形案例）。系统已注入全部技巧的"
            "名字+一句话索引；当你决定运用某条技巧、需要它的具体做法与案例时，"
            "用本工具细看。写作时可把点名技巧传给 write_chapter 的 skills 参数。"
        ),
        params=[
            ParamSpec(
                name="name",
                type="string",
                required=True,
                description="技巧名（索引里的名字，如'节奏控制'）",
            )
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        name = str(arguments.get("name", "")).strip()
        if not name:
            return ToolResult(call=call, ok=False, content="缺少参数 name。")
        skills = skills_store.list_skills() if skills_store is not None else []
        # 精确匹配优先，其次包含匹配（索引名字是权威，包含匹配兜底防笔误）
        hit = next((s for s in skills if s.name == name), None)
        if hit is None:
            hit = next((s for s in skills if name in s.name), None)
        if hit is None:
            # 自纠引导：列出可用技巧名（agent 可能笔误/带引号/多字）
            avail = "、".join(s.name for s in skills) or "（无）"
            return ToolResult(
                call=call,
                ok=False,
                content=f"技巧库中没有「{name}」。可用技巧：{avail}。",
            )
        block = f"【{hit.name}】\n{hit.content}"
        if hit.example:
            block += f"\n例：{hit.example}"
        return ToolResult(call=call, ok=True, content=block)

    return spec, implementer


def make_skill_refine_implementer(
    generator: Any,
    materials: Any,
    library: Any = None,
    skills: Any = None,
    workflow_store: Any = None,
    workflow_engine: Any = None,
    book_id: str = "main",  # S152g：当前项目（此前装配不传，任务落 main）
) -> tuple[Any, Any]:
    """文风参考书 → skill 提炼工具（S72）：把原文/资料提炼成叙事技法候选。

    S103：加 library_book_id（从书库取原文）+ 候选存草稿（skills.add_draft，
    前端草稿区人工确认转正——对话触发的提炼不再断链）。
    S135（WORKFLOW 收尾，W1-B 归一不降级）：mode=book（拆书多步管道）改走
    「拆书提炼」workflow 模板（同步实例化+跑，断点/重试/持久化统一）；
    模板不存在时回退 generator.generate_book（向后兼容）。

    需要借鉴某本书/资料的写法（句式/节奏/用词/视角）时使用——生成 skill 候选
    供用户确认（人工确认闸门：不自动入库，对齐 S54 哲学）。
    """

    spec = ToolSpec(
        name="skill_refine",
        description=(
            "从原文、资料库或书库提炼叙事技法 skill 候选（把文风参考书变成方法论）。"
            "需要借鉴某本书/某资料的写法（句式/节奏/用词/视角）时使用——"
            "生成候选存草稿供用户确认（确认后生效，不自动入库）。"
            "三种来源三选一：library_book_id（书库的书）、material_id（资料库，"
            "read_material 返回的 ids）、或直接传 source_text。"
            "mode=book（拆书）：把整本书写法多维拆解（文风/节奏/结构/人设/对白/信息投放/钩子）"
            "融合成一份「书名」skill（name=书名，一次点名拿到整本方法论）。"
        ),
        params=[
            ParamSpec(
                name="library_book_id",
                type="string",
                required=False,
                description="书库的书 id（reference_lookup 可查；从其全文提炼，拆书模式推荐）",
            ),
            ParamSpec(
                name="material_id",
                type="string",
                required=False,
                description="资料 ID（read_material 返回；从其原文提炼）",
            ),
            ParamSpec(
                name="source_text",
                type="string",
                required=False,
                description="原文文本（与 library_book_id/material_id 三选一）",
            ),
            ParamSpec(
                name="hint",
                type="string",
                required=False,
                description="可选指引（如'侧重打斗文风'/'侧重节奏'）",
            ),
            ParamSpec(
                name="mode",
                type="string",
                required=False,
                description=(
                    "writing=单维度提炼 N 条技法候选（默认）；"
                    "book=整本书拆解融合成一份「书名」skill"
                ),
            ),
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        source_text = str(arguments.get("source_text", "")).strip()
        material_id = str(arguments.get("material_id", "")).strip()
        library_book_id = str(arguments.get("library_book_id", "")).strip()
        hint = str(arguments.get("hint", "")).strip()
        # S103：书库取原文（read_book 拼全书，拆书模式覆盖多章）
        if library_book_id:
            if library is None:
                return ToolResult(call=call, ok=False, content="书库不可用（未装配）")
            try:
                book = library.get_book(library_book_id)
                if book is None:
                    return ToolResult(call=call, ok=False, content=f"书库无此书：{library_book_id}")
                # S106：拆书需全文（12MB 级整本书）——不截断，抽样归并由 generate_book 内部做
                source_text = library.read_book(library_book_id, max_chars=None).strip()
                if not source_text:
                    return ToolResult(
                        call=call, ok=False, content=f"书库《{book['name']}》无内容（先导入文本）"
                    )
            except Exception as exc:
                return ToolResult(call=call, ok=False, content=f"读取书库失败：{exc}")
        if material_id:
            try:
                card = materials.get(material_id)
            except Exception as exc:
                return ToolResult(call=call, ok=False, content=f"读取资料失败：{exc}")
            if card is None:
                return ToolResult(call=call, ok=False, content=f"资料不存在：{material_id}")
            if card.kind == "copy":
                # S79：copy 冷藏副本智能体不可见（备份不提炼）
                return ToolResult(
                    call=call, ok=False, content=f"资料 {material_id} 为冷藏副本，不可用于提炼"
                )
            if not (card.source_text or "").strip():
                return ToolResult(
                    call=call, ok=False, content=f"资料无原文（{card.title}），无法提炼"
                )
            source_text = card.source_text.strip()
        if not source_text:
            return ToolResult(call=call, ok=False, content="需要 material_id 或 source_text。")
        mode = str(arguments.get("mode", "writing")).strip() or "writing"
        via_template = False
        try:
            if mode == "book":
                # S135（WORKFLOW 收尾）：拆书多步管道优先走「拆书提炼」workflow 模板
                # （W1-B 归一不降级：工具变快捷入口，底层统一 workflow 机制）；
                # 模板缺失或未装配 engine 时回退 generator.generate_book（向后兼容）。
                book_name = book.get("name", "") if library_book_id else ""
                template_ok = _run_refine_template(
                    workflow_store,
                    workflow_engine,
                    "拆书提炼",
                    {"library_book_id": library_book_id or ""},
                    skills,
                    book_id=book_id,  # S152g：任务绑定当前项目
                )
                if template_ok:
                    # 模板 finish 已落草稿；candidates 仅作展示摘要（不重复 add_draft）
                    via_template = True
                    candidates = template_ok
                    tag = "拆书 skill（workflow）"
                else:
                    candidates = generator.generate_book(source_text, hint, book_name=book_name)
                    tag = "拆书 skill"
            else:
                candidates = generator.generate(source_text, hint, 5, mode="writing")
                tag = "skill 候选"
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"提炼失败：{exc}")
        if not candidates:
            # S113：透出可读失败原因（generate_book 全段失败时 last_error 有分类汇总）
            err = getattr(generator, "last_error", "")
            content = "提炼失败（无有效候选）。"
            if err:
                content += f"原因：{err}"
            return ToolResult(call=call, ok=False, content=content)
        # S103：候选存草稿（skills.add_draft）——前端草稿区人工确认转正，对话链路不再断链
        draft_ids: list[str] = []
        # S130：拆书产物同书名一包（pack_id=书名，整包引用写作只取 writing/both）
        pack_id = book.get("name", "") if (mode == "book" and library_book_id) else ""
        if skills is not None and not via_template:
            # 模板路径：finish 节点已落草稿，不重复添加（S135）
            for c in candidates:
                d = skills.add_draft(
                    name=str(c.get("name", "")),
                    description=str(c.get("description", ""))[:500],
                    content=str(c.get("content", "")),
                    example=str(c.get("example", ""))[:2000],
                    tags=str(c.get("tags", "")),
                    type=str(c.get("type", "writing")),
                    pack_id=pack_id,
                    source="agent",
                )
                if d:
                    draft_ids.append(str(d["id"]))
        lines = [f"【{tag} {len(candidates)} 条（已存草稿，待人工确认生效）】"]
        for i, c in enumerate(candidates, 1):
            name = c.get("name", f"候选{i}")
            desc = str(c.get("description", ""))  # S157：候选描述不截断（草稿数量有限，全量供判断）
            lines.append(f"{i}. {name}：{desc}")
        if mode == "book" and not via_template:
            content = str(candidates[0].get("content", ""))
            lines.append(
                f"   （整本方法论 {len(content)} 字，分小节："
                "文风/节奏/结构/人设/对白/信息投放/钩子）"
            )
        elif via_template:
            lines.append("   （workflow「拆书提炼」模板执行完成，草稿已入待确认区）")
        if draft_ids:
            lines.append(f"（草稿已生成 {len(draft_ids)} 条，去书库/技巧标签确认后生效）")
        elif skills is not None:
            lines.append("（已有同名草稿或技能，未重复生成——可先确认/删除旧的再提炼）")
        return ToolResult(call=call, ok=True, content="\n".join(lines))

    return spec, implementer


def _run_refine_template(
    workflow_store: Any,
    workflow_engine: Any,
    template_name: str,
    params: dict[str, str],
    skills: Any,
    book_id: str = "main",  # S152g：任务绑定当前项目（此前硬编码 main）
) -> list[dict[str, str]] | None:
    """S135：按模板名同步跑拆书 workflow → 返回候选摘要。

    通过「拆书提炼」模板执行（实例化 + create_task + run_task 同步跑），
    落草稿由模板 finish 节点完成（与直接 generate_book 同源）。
    返回轻量候选列表供工具展示（从草稿反查）；模板缺失/engine 未装配 → None
    （调用方回退 generate_book）。
    """
    if workflow_store is None or workflow_engine is None or skills is None:
        return None
    wf = None
    for t in workflow_store.list_templates():
        if t["name"] == template_name:
            wf = workflow_store.get_template(t["id"])
            break
    if wf is None:
        return None
    if not params.get("library_book_id"):
        return None
    before = len(skills.list_drafts())
    task_id = workflow_store.create_task(wf, book_id=book_id, template_id=wf.id, params=params)
    try:
        workflow_engine.run_task(task_id)
    except Exception:
        # 模板执行失败 → 回退直接生成（保工具可用性）
        return None
    # 从草稿反查本任务新产出的候选（finish 落库的，取 before 之后的）
    drafts = skills.list_drafts()
    new_drafts = drafts[: max(0, len(drafts) - before)]
    return [
        {"name": str(d.get("name", "")), "description": str(d.get("description", ""))}
        for d in new_drafts
    ] or None
