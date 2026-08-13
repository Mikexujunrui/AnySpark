"""
anyspark.server.tools_domain — 写作领域工具集（S48-P2：小说特化能力进 Agent 闭环）。

把图谱/伏笔/计划/设定档从"HTTP API（人驱动）"变成"agent 可自主调用的工具"。
写作 Agent 写前可查证（graph_query/read_setting）、知道接下来写什么（plan_list）、
边写边登记承诺（plot_register）、写后推进计划（plan_mark_done）——"小说特化版 pi"的
领域层，随 enable_domain 点亮（默认开：小说写作必需；s15 按需装配哲学——工具是
能力不是负担，Agent 只在对应场景调用）。

设计边界（哲学）：
- 只读/轻量登记，无删除修改权限——内容裁决权保留在用户/API（agent 不删设定不删伏笔）
- 全部是自然语言输入输出（模型无关）；机制（工具结构/查询逻辑）硬编码
- 返回裁剪（limit 防 token 爆炸），Agent 需要细节可再查
"""

from __future__ import annotations

import json
import re
from typing import Any

from anyspark.align import ManualEntry, render_plan
from anyspark.core import ToolCall
from anyspark.core.protocol import ParamSpec, ToolResult, ToolSpec

# 查询返回上限（防 token 爆炸：Agent 是裁剪消费者，需要细节再查）
_QUERY_LIMIT = 10
_RELATION_LIMIT = 15


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


def make_graph_query_implementer(graph: Any, book_id: str = "main") -> tuple[Any, Any]:
    """图谱查询工具：查实体（含当前状态）/关系/事件，写作前查证用。"""

    spec = ToolSpec(
        name="graph_query",
        description=(
            "查询知识图谱：按关键词/名字查实体（角色/地点/事件/物件/设定，含当前状态）、"
            "实体间关系、时间线事件。写作前需要确认某人/某地/某设定的已知信息时使用"
            "（系统已自动注入当前时空点已知事实，本工具用于查更细的细节）。"
        ),
        params=[
            ParamSpec(
                name="query",
                type="string",
                required=True,
                description="关键词/实体名（可模糊匹配，如'陈渡'、'雾城'）",
            )
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        q = str(arguments.get("query", "")).strip()
        if not q:
            return ToolResult(call=call, ok=False, content="缺少参数 query。")
        try:
            entities = graph.list_entities(book_id, q=q, limit=_QUERY_LIMIT)
            if not entities:
                return ToolResult(call=call, ok=False, content=f"图谱中未找到与「{q}」相关的实体。")
            names = [e.name for e in entities]
            lines = [f"图谱中与「{q}」相关的实体（{len(entities)} 个）："]
            for e in entities:
                state = getattr(e, "state", "") or ""
                desc = getattr(e, "description", "") or ""
                line = f"- {e.name}（{e.entity_type}）"
                if state:
                    line += f" 当前状态：{state[:80]}"
                elif desc:
                    line += f" {desc[:80]}"
                lines.append(line)
            # 相关关系（实体参与的三元组）
            relations = graph.list_relations(book_id, limit=_RELATION_LIMIT)
            rels = [r for r in relations if r.from_name in names or r.to_name in names][
                :_RELATION_LIMIT
            ]
            if rels:
                lines.append(f"相关关系（{len(rels)} 条）：")
                lines.extend(f"- {r.from_name} —{r.type}→ {r.to_name}" for r in rels)
            return ToolResult(
                call=call,
                ok=True,
                content="\n".join(lines),
                data={"names": names},
            )
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"图谱查询失败：{exc}")

    return spec, implementer


def make_plot_implementer(plots: Any, book_id: str = "main") -> tuple[list[Any], list[Any]]:
    """伏笔工具：登记（埋钩子）+ 列表（看还欠哪些承诺）。"""

    register_spec = ToolSpec(
        name="plot_register",
        description=(
            "登记一个伏笔/剧情钩子（关键点图谱）。写作中埋下线索、悬念、承诺时使用——"
            "一句话'记一下'，系统记入关键点图谱并在后续注入中持续提醒。"
            "priority=must 表示主线承诺（必须回收，会重点标注）；默认 soft（细节线索）。"
            "只记剧情承诺/钩子；事实类设定（谁是谁/世界规则）用 graph_register，"
            "不要两处重复登记。"
        ),
        params=[
            ParamSpec(
                name="content",
                type="string",
                required=True,
                description="伏笔内容（自然语言，如'怀表背面刻有一串数字'）",
            ),
            ParamSpec(
                name="priority",
                type="string",
                required=False,
                description="must（主线承诺）或 soft（细节线索，默认）",
            ),
        ],
    )

    def register(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        content = str(arguments.get("content", "")).strip()
        priority = str(arguments.get("priority", "soft")).strip() or "soft"
        if not content:
            return ToolResult(call=call, ok=False, content="缺少参数 content。")
        try:
            p = plots.add(
                book_id=book_id,
                category="伏笔",
                content=content,
                priority=priority,
            )
            mark = "（主线承诺★）" if p.priority == "must" else ""
            return ToolResult(
                call=call,
                ok=True,
                content=f"已登记伏笔#{p.id[:8]}：{content} {mark}（开放中，将自动提醒回收）",
                data={"plot_id": p.id, "priority": p.priority},
            )
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"登记失败：{exc}")

    list_spec = ToolSpec(
        name="plot_list",
        description=(
            "查看关键点图谱当前状态：还有哪些伏笔/剧情钩子开放未回收"
            "（must 主线承诺会★标注、标已开放章数）。写章前看还欠读者哪些承诺时使用。"
        ),
        params=[],
    )

    def list_points(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        try:
            render = plots.render(book_id)
            return ToolResult(
                call=call,
                ok=True,
                content=render if render.strip() else "关键点图谱为空（没有进行中的伏笔）。",
            )
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"查询失败：{exc}")

    # ── S104：回收归档（写完发现伏笔已揭开 → 自己标记 resolved）──
    resolve_spec = ToolSpec(
        name="plot_resolve",
        description=(
            "回收归档一个伏笔/剧情钩子（标记已解决）。"
            "写完章节发现某个伏笔已在文中揭开/回收时使用——把它标记 resolved，"
            "伏笔图谱不再提醒，承诺闭环。需先 plot_list 查伏笔 id。"
        ),
        params=[
            ParamSpec(
                name="plot_id",
                type="string",
                required=True,
                description="伏笔 id（plot_list 返回）",
            ),
            ParamSpec(
                name="chapter_ref",
                type="string",
                required=False,
                description="回收章节（如'第 12 章'）；缺省记当前轮次",
            ),
        ],
    )

    def resolve(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        plot_id = str(arguments.get("plot_id", "")).strip()
        if not plot_id:
            return ToolResult(call=call, ok=False, content="缺少参数 plot_id。")
        try:
            p = plots.get(plot_id)
            if p is None:
                return ToolResult(call=call, ok=False, content=f"伏笔不存在：{plot_id}")
            chapter_ref = str(arguments.get("chapter_ref", "")).strip() or None
            updated = plots.update(
                plot_id,
                status="resolved",
                resolved_chapter=chapter_ref or p.resolved_chapter,
            )
            assert updated is not None
            where = f"（回收于 {updated.resolved_chapter}）" if updated.resolved_chapter else ""
            return ToolResult(
                call=call,
                ok=True,
                content=f"已回收归档伏笔#{plot_id[:8]}：{updated.content} {where}",
                data={"plot_id": plot_id, "status": "resolved"},
            )
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"回收失败：{exc}")

    # ── S104：修改伏笔（优先级/关注度/回收章节/状态）──
    update_spec = ToolSpec(
        name="plot_update",
        description=(
            "修改一个伏笔的元信息（优先级/关注度/回收章节/状态）。"
            "写的过程中调整伏笔重要性（升级为 must 主线承诺 / 降级为 soft）时使用。"
            "改内容本身请删除后重新登记（plot_delete + plot_register）。"
        ),
        params=[
            ParamSpec(
                name="plot_id",
                type="string",
                required=True,
                description="伏笔 id（plot_list 返回）",
            ),
            ParamSpec(
                name="priority",
                type="string",
                required=False,
                description="must（主线承诺）或 soft（细节线索）",
            ),
            ParamSpec(
                name="attention",
                type="string",
                required=False,
                description="care（在意，重点跟进）或 ignore（忽略）",
            ),
            ParamSpec(
                name="status",
                type="string",
                required=False,
                description="open（开放）或 resolved（已回收）",
            ),
            ParamSpec(
                name="chapter_ref",
                type="string",
                required=False,
                description="回收/关联章节",
            ),
        ],
    )

    def update_point(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        plot_id = str(arguments.get("plot_id", "")).strip()
        if not plot_id:
            return ToolResult(call=call, ok=False, content="缺少参数 plot_id。")
        try:
            priority = str(arguments.get("priority", "")).strip() or None
            attention = str(arguments.get("attention", "")).strip() or None
            status = str(arguments.get("status", "")).strip() or None
            chapter_ref = str(arguments.get("chapter_ref", "")).strip() or None
            updated = plots.update(
                plot_id,
                priority=priority,
                attention=attention,
                status=status,
                chapter_ref=chapter_ref,
            )
            if updated is None:
                return ToolResult(call=call, ok=False, content=f"伏笔不存在：{plot_id}")
            return ToolResult(
                call=call, ok=True, content=f"已更新伏笔#{plot_id[:8]}（{updated.status}）"
            )
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"更新失败：{exc}")

    # ── S104：删除伏笔（误登记/废弃线索）──
    delete_spec = ToolSpec(
        name="plot_delete",
        description=(
            "删除一个伏笔（误登记/废弃线索时清理）。"
            "注意：已回收的伏笔保留作归档记录，通常不需要删除。"
        ),
        params=[
            ParamSpec(
                name="plot_id",
                type="string",
                required=True,
                description="伏笔 id（plot_list 返回）",
            ),
        ],
    )

    def delete_point(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        plot_id = str(arguments.get("plot_id", "")).strip()
        if not plot_id:
            return ToolResult(call=call, ok=False, content="缺少参数 plot_id。")
        try:
            if plots.get(plot_id) is None:
                return ToolResult(call=call, ok=False, content=f"伏笔不存在：{plot_id}")
            plots.delete(plot_id)
            return ToolResult(call=call, ok=True, content=f"已删除伏笔#{plot_id[:8]}")
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"删除失败：{exc}")

    return [register_spec, list_spec, resolve_spec, update_spec, delete_spec], [
        register,
        list_points,
        resolve,
        update_point,
        delete_point,
    ]


def make_plan_implementer(plans: Any, book_id: str = "main") -> tuple[list[Any], list[Any]]:
    """剧情计划工具：看计划（当前章+后续）+ 标记完成（推进）。"""

    list_spec = ToolSpec(
        name="plan_list",
        description=(
            "查看剧情计划：当前章安排与后续计划（planned 状态）。"
            "开始写某章前看接下来该写什么时使用。"
        ),
        params=[],
    )

    def list_plans(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        try:
            entries = plans.list(book_id)
            if not entries:
                return ToolResult(call=call, ok=True, content="尚无剧情计划。")
            return ToolResult(call=call, ok=True, content=render_plan(entries, horizon=5))
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"查询失败：{exc}")

    done_spec = ToolSpec(
        name="plan_mark_done",
        description=(
            "标记剧情计划中的一章为已完成（status=done），自动推进到下一章计划。"
            "写完计划中的某章落盘后调用。"
        ),
        params=[
            ParamSpec(
                name="title",
                type="string",
                required=True,
                description="要标记完成的计划章节标题",
            )
        ],
    )

    def mark_done(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        title = str(arguments.get("title", "")).strip()
        if not title:
            return ToolResult(call=call, ok=False, content="缺少参数 title。")
        try:
            entries = plans.list(book_id)
            target = next((p for p in entries if p.title == title), None)
            if target is None:
                titles = "、".join(p.title for p in entries) or "（空）"
                return ToolResult(
                    call=call, ok=False, content=f"计划中未找到「{title}」。现有计划：{titles}"
                )
            if target.status == "done":
                return ToolResult(call=call, ok=True, content=f"计划章《{title}》已是完成状态。")
            plans.update(target.id, status="done")
            return ToolResult(call=call, ok=True, content=f"计划章《{title}》已标记完成。")
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"操作失败：{exc}")

    return [list_spec, done_spec], [list_plans, mark_done]


def make_setting_implementer(settings: Any, book_id: str = "main") -> tuple[Any, Any]:
    """设定档工具：查正典条目（人物卡/能力体系/世界观规则）。"""

    spec = ToolSpec(
        name="read_setting",
        description=(
            "查阅设定档（作者正典）：人物卡/能力体系/世界观/势力/地点/物品/规则/禁忌。"
            "写正文需要确认某个设定细节时使用；keyword 可给关键词，不给则列出全部类别。"
        ),
        params=[
            ParamSpec(
                name="keyword",
                type="string",
                required=True,
                description="关键词（可模糊匹配，如'假死'、'能力'；给'列出'可看全部）",
            )
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        q = str(arguments.get("keyword", "")).strip()
        try:
            entries = settings.list(book_id)
            if not entries:
                return ToolResult(call=call, ok=True, content="设定档为空。")
            if not q or q in ("列出", "全部", "list"):
                lines = ["设定档全部条目（按类别）："]
                cats: dict[str, list[Any]] = {}
                for e in entries:
                    cats.setdefault(e.category, []).append(e)
                for cat, items in cats.items():
                    lines.append(f"【{cat}】")
                    lines.extend(f"- {e.name}：{e.content[:60]}" for e in items[:8])
                return ToolResult(call=call, ok=True, content="\n".join(lines))
            matched = [e for e in entries if q in e.name or q in e.content or q in e.category]
            if not matched:
                names = "、".join(e.name for e in entries) or "（空）"
                return ToolResult(
                    call=call, ok=False, content=f"设定档未找到「{q}」。现有条目：{names}"
                )
            parts = []
            for e in matched[:5]:
                parts.append(f"【{e.category}】{e.name}\n{e.content}")
            return ToolResult(call=call, ok=True, content="\n\n".join(parts))
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"查询失败：{exc}")

    return spec, implementer


def make_ingest_implementer(
    workspace: Any, chapters: Any, materials: Any, model: Any, book_id: str = "main"
) -> tuple[Any, Any]:
    """上传消化工具（S48-P3）：把上传区原始文档消化成章节 md 或摘要卡。

    Agent 在用户上传了原稿/设定文档后调用——拆章进格式化区（可继续写作），
    或生成摘要卡（设定/资料，进卡片区 + 图谱关联）。
    """

    spec = ToolSpec(
        name="ingest_document",
        description=(
            "消化上传区的原始文档：长文（小说/多章稿件）按章节标题拆成章节文件，"
            "资料/设定类生成摘要卡。用户上传 txt/md/docx/pdf 后、需要基于它写作时使用。"
            "mode=chapters 强制拆章，mode=card 强制摘要卡，缺省自动判别。"
        ),
        params=[
            ParamSpec(
                name="filename",
                type="string",
                required=True,
                description="上传区文件名（如'原稿.docx'，可先列上传区确认）",
            ),
            ParamSpec(
                name="mode",
                type="string",
                required=False,
                description="auto/chapters/card（缺省 auto）",
            ),
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        filename = str(arguments.get("filename", "")).strip()
        mode = str(arguments.get("mode", "auto")).strip() or "auto"
        if not filename:
            return ToolResult(call=call, ok=False, content="缺少参数 filename。")
        # S83 R2：消化编排收敛到 ingest_pipeline（原内联实现零变化搬移）
        from anyspark.server.ingest import ingest_pipeline

        result = ingest_pipeline(
            workspace, chapters, materials, model, book_id, filename, mode=mode
        )
        if not result.ok:
            return ToolResult(call=call, ok=False, content=result.error)
        if result.kind == "card":
            return ToolResult(
                call=call,
                ok=True,
                content=f"已消化「{filename}」为摘要卡《{result.title}》（{result.card_file}）。"
                f"\n主题：{result.topic}\n要点：{'；'.join(result.key_points)}",
            )
        written = [
            f"{i + 1}. {ch['title']}（{ch['chars']}字）" for i, ch in enumerate(result.chapters)
        ]
        return ToolResult(
            call=call,
            ok=True,
            content=f"已消化「{filename}」为 {len(written)} 章：\n" + "\n".join(written),
        )

    return spec, implementer


def make_codex_implementer(
    workspace: Any, chapters: Any, graph: Any, book_id: str = "main"
) -> tuple[Any, Any]:
    """代码扩展工具（S48-P5 anyspark-codex）：沙箱执行 Python，固定工具做不了时用。

    S48-P4/A：注入只读数据环境 ws_*（章节/图谱/上传）——可真实统计/自定义分析，
    如全书字数分布、高频词、角色出现频率、对话占比等（数据进沙箱内存，不占模型 token）。
    """

    spec = ToolSpec(
        name="run_code",
        description=(
            "在受限沙箱执行 Python 代码（安全：无文件/网络/任意 import，白名单 "
            "math/re/json/random 等，超时上限）。用于固定工具无法实现的自定义处理："
            "特殊格式解析、批量数据转换、统计计算等。不可用于读写文件或访问网络。"
        ),
        params=[
            ParamSpec(
                name="code",
                type="string",
                required=True,
                description="要执行的 Python 代码（print 输出会被返回）",
            ),
            ParamSpec(
                name="timeout",
                type="string",
                required=False,
                description="超时秒数（默认 10，上限 60）",
            ),
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        code = str(arguments.get("code", "")).strip()
        if not code:
            return ToolResult(call=call, ok=False, content="缺少参数 code。")
        try:
            timeout = float(str(arguments.get("timeout", "10")) or "10")
        except ValueError:
            timeout = 10.0
        from anyspark.server.codex import make_data_env, run_code

        r = run_code(code, timeout, data_env=make_data_env(workspace, chapters, graph, book_id))
        lines = []
        if r["stdout"]:
            lines.append("【输出】\n" + r["stdout"].rstrip())
        if r["stderr"]:
            lines.append("【stderr】\n" + r["stderr"].rstrip())
        if r["error"]:
            lines.append(f"【错误】{r['error']}")
        body = "\n\n".join(lines) if lines else "（无输出）"
        return ToolResult(call=call, ok=r["ok"], content=body)

    return spec, implementer


def make_roleplay_implementer(
    workspace: Any, graph: Any, model: Any, book_id: str = "main"
) -> tuple[Any, Any]:
    """角色推演工具（S48-P4）：低成本多路探索，选最好的作为参考。"""

    spec = ToolSpec(
        name="role_play",
        description=(
            "推演某个角色在给定场景中的反应（心理/言语/动作）。"
            "写作时不确定角色会怎么做、或需要角色视角的灵感时使用——"
            "系统多路并行推演（最可能/最戏剧化/最反常/最克制）并选最优，"
            "返回最佳推演与备选作为写作参考（不直接写入正文）。"
        ),
        params=[
            ParamSpec(
                name="role",
                type="string",
                required=True,
                description="角色名（须有角色卡或图谱实体）",
            ),
            ParamSpec(
                name="scenario",
                type="string",
                required=True,
                description="推演场景（自然语言描述）",
            ),
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        role = str(arguments.get("role", "")).strip()
        scenario = str(arguments.get("scenario", "")).strip()
        if not role or not scenario:
            return ToolResult(call=call, ok=False, content="缺少参数 role 或 scenario。")
        try:
            from anyspark.explore import load_role_card, run_roleplay

            role_card, state = load_role_card(workspace, graph, role, book_id=book_id)
            if not role_card.strip():
                return ToolResult(
                    call=call,
                    ok=False,
                    content=f"角色「{role}」没有角色卡或图谱实体，可先创建角色卡。",
                )
            result = run_roleplay(model, role_card, state=state, scenario=scenario, n=4)
            if not result.candidates:
                return ToolResult(call=call, ok=False, content="推演失败（无有效候选）。")
            lines = [f"【{role} 在「{scenario}」的推演】"]
            if result.best:
                lines.append(f"★ 最佳（{result.best.strategy}）：\n{result.best.text}")
            lines.append("\n【备选】")
            for i, c in enumerate(result.candidates, 1):
                mark = "（最佳）" if result.best and c.strategy == result.best.strategy else ""
                lines.append(f"{i}. [{c.strategy}]{mark} {c.text[:80]}…")
            return ToolResult(call=call, ok=True, content="\n".join(lines))
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"推演失败：{exc}")

    return spec, implementer


def _sentence_at(content: str, idx: int) -> str:
    """返回 content 中包含位置 idx 的分句（按 。！？；， 换行 切分）。"""
    import re as _re

    pos = 0
    for s in _re.split(r"(?<=[。！？；，\n])", content):
        if pos <= idx < pos + len(s):
            return s
        pos += len(s)
    return content


def _sent_has(content: str, idx: int, kw_len: int, exclude: str) -> bool:
    """句级排除：命中所在句子含 exclude 则 True（防短句互相污染/否定语境）。"""
    sent = _sentence_at(content, idx)
    return exclude in sent


def make_search_chapters_implementer(chapters: Any, book_id: str = "main") -> tuple[Any, Any]:
    """正文检索工具（S48-P4/B：图谱是结构化事实检索，正文定位靠这个）。

    对齐 pi 的 grep 定位 + 计数：关键词/意象/短语在哪些章节出现、
    出现次数、上下文片段——长书一致性核对/意象追踪的刚需
    （图谱只存抽取后的实体关系，正文原文细节不在图谱里）。
    """

    spec = ToolSpec(
        name="search_chapters",
        description=(
            "在全书正文中检索关键词/意象/短语：返回命中的章节、每章出现次数、"
            "上下文片段（含统计'共命中 N 章 M 次'）。用于确认某个细节/意象/名字"
            "在哪些章节出现过（一致性核对、伏笔追踪、避免重复描写）。"
            "注意：这是字面命中，需阅读上下文片段判断是否真正相关"
            "（否定/比喻/指代等不算真相关）；需要看命中处前后完整段落时"
            "再用 read_context。选词用独特短语（如'怀表背面'）而非高频词。"
        ),
        params=[
            ParamSpec(
                name="keyword",
                type="string",
                required=False,
                description="要检索的关键词/短语（如'红绳'、'怀表背面'）——与 keywords 二选一",
            ),
            ParamSpec(
                name="keywords",
                type="string",
                required=False,
                description=(
                    "词表批量：逗号/顿号分隔的多个关键词（如'拳,刀,撞,踢'）。"
                    "逐词统计每章命中数，返回各词分布 + 聚合。"
                    "用于定位'某类描写'（先字面召回多词 → 再 read_context 精读）。"
                    "与 keyword 二选一；都传时以 keywords 为准。"
                ),
            ),
            ParamSpec(
                name="exclude",
                type="string",
                required=False,
                description="排除词：命中位置片段内包含该词的命中不算（如搜'怀表'排除'没有'）",
            ),
            ParamSpec(
                name="fragment",
                type="number",
                required=False,
                description=(
                    "上下文宽度（命中位置前后各多少字；默认 20——定位够用；"
                    "需要更多时加大或直接用 read_context 看完整段落；0=只要章节和次数）"
                ),
            ),
            ParamSpec(
                name="regex",
                type="string",
                required=False,
                description="true 时 keyword 按正则表达式匹配（模糊/多形，如'怀表|怀表盖'）",
            ),
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        kw = str(arguments.get("keyword", "")).strip()
        kw_list = str(arguments.get("keywords", "")).strip()
        # S56 词表批量：keywords 优先（与 keyword 二选一；都传时以 keywords 为准）
        if kw_list:
            terms = [t.strip() for t in re.split(r"[,，、\s]+", kw_list) if t.strip()]
            if not terms:
                return ToolResult(call=call, ok=False, content="keywords 为空。")
        elif kw:
            terms = [kw]
        else:
            return ToolResult(call=call, ok=False, content="缺少参数 keyword（或 keywords 词表）。")
        try:
            exclude = str(arguments.get("exclude", "")).strip() or None
            try:
                frag = max(0, min(int(str(arguments.get("fragment", "20")) or "20"), 500))
            except ValueError:
                frag = 20
            use_regex = str(arguments.get("regex", "")).strip().lower() in ("true", "1", "yes")
            items = chapters.list_by_book(book_id)
            if not items:
                return ToolResult(call=call, ok=True, content="暂无章节。")
            # 逐章逐词统计：{chapter: {term: count, _first_ctx: ...}}
            chapter_stats: list[dict[str, Any]] = []
            grand_total = 0
            grand_chapters = 0
            for c in items:
                per_term: dict[str, int] = {}
                first_ctx = ""
                chapter_total = 0
                for term in terms:
                    if use_regex:
                        try:
                            matches = list(re.finditer(term, c.content))
                        except re.error as exc:
                            return ToolResult(call=call, ok=False, content=f"正则表达式错误：{exc}")
                        n = 0
                        for m in matches:
                            if not m:
                                continue
                            if frag > 0:
                                ctx = c.content[max(0, m.start() - frag) : m.end() + frag]
                                if exclude is not None and _sent_has(
                                    c.content, m.start(), m.end() - m.start(), exclude
                                ):
                                    continue
                                n += 1
                                if not first_ctx:
                                    first_ctx = "…" + ctx + "…"
                            else:
                                n += 1
                        per_term[term] = n
                        chapter_total += n
                    else:
                        n = 0
                        start = 0
                        while True:
                            idx = c.content.find(term, start)
                            if idx == -1:
                                break
                            if frag > 0:
                                ctx = c.content[max(0, idx - frag) : idx + len(term) + frag]
                                if exclude is not None and _sent_has(
                                    c.content, idx, len(term), exclude
                                ):
                                    start = idx + len(term)
                                    continue
                                n += 1
                                if not first_ctx:
                                    first_ctx = "…" + ctx + "…"
                            else:
                                n += 1
                            start = idx + len(term)
                        per_term[term] = n
                        chapter_total += n
                if chapter_total > 0:
                    grand_total += chapter_total
                    grand_chapters += 1
                    chapter_stats.append(
                        {
                            "title": c.title,
                            "total": chapter_total,
                            "per_term": per_term,
                            "context": first_ctx,
                        }
                    )
            if not chapter_stats:
                shown = ",".join(terms)
                return ToolResult(
                    call=call,
                    ok=True,
                    content=f"全书未找到「{shown}」（共检索 {len(items)} 章）。",
                    data={"query": shown, "hits": [], "chapters": 0, "total": 0},
                )
            # 渲染：批量模式显示各词分布；单关键词模式保持原格式
            if len(terms) == 1:
                label = terms[0]
                lines = [f"「{label}」命中 {grand_chapters} 章共 {grand_total} 次："]
                for cs in chapter_stats:
                    if cs["context"]:
                        lines.append(f"- 《{cs['title']}》×{cs['total']}：{cs['context']}")
                    else:
                        lines.append(f"- 《{cs['title']}》×{cs['total']}")
                lines.append("（字面命中，需读上下文判断相关性；看命中处完整段落用 read_context）")
            else:
                label = ",".join(terms)
                lines = [f"词表 [{label}] 命中 {grand_chapters} 章共 {grand_total} 次："]
                for cs in chapter_stats:
                    dist = " ｜ ".join(f"{t}×{n}" for t, n in cs["per_term"].items() if n)
                    lines.append(f"- 《{cs['title']}》共{cs['total']}次（{dist}）")
                    if cs["context"]:
                        lines.append(f"    {cs['context']}")
                lines.append(
                    "（字面召回；确认某处是否真相关 → read_context(title, anchor=上下文片段)。"
                    "词表可再扩：定位'某类描写'用多词召回 + 精读）"
                )
            return ToolResult(
                call=call,
                ok=True,
                content="\n".join(lines),
                data={
                    "query": label,
                    "hits": chapter_stats,
                    "chapters": grand_chapters,
                    "total": grand_total,
                },
            )
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"检索失败：{exc}")

    return spec, implementer


def make_register_tool_implementer(ext_tools: Any) -> tuple[Any, Any]:
    """扩展工具登记工具（S48-P4/B）：Agent 写代码给自己加工具（人工批准生效）。"""

    spec = ToolSpec(
        name="register_tool",
        description=(
            "编写并登记一个可复用的自定义工具（扩展工具）。当固定工具无法实现某个"
            "反复需要的处理时使用——写 Python 函数 `run(args: dict) -> str` 登记，"
            "经用户人工批准后生效，之后可直接调用该工具。"
        ),
        params=[
            ParamSpec(
                name="name",
                type="string",
                required=True,
                description="工具名（英文小写，唯一，如 analyze_dialogue）",
            ),
            ParamSpec(
                name="description",
                type="string",
                required=True,
                description="工具描述（说明何时调用、做什么，agent 靠它判断）",
            ),
            ParamSpec(
                name="code",
                type="string",
                required=True,
                description=(
                    "Python 代码，定义 def run(args: dict) -> str。可用 ws_chapters/"
                    "ws_entities/ws_read 等只读数据函数（沙箱安全）。"
                ),
            ),
            ParamSpec(
                name="params_json",
                type="string",
                required=False,
                description=(
                    "参数定义 JSON 数组（可选），如 [{'name':'x','type':'string','required':true}]"
                ),
            ),
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        name = str(arguments.get("name", "")).strip()
        description = str(arguments.get("description", "")).strip()
        code = str(arguments.get("code", "")).strip()
        params_json = str(arguments.get("params_json", "[]")).strip() or "[]"
        if not name or not description or not code:
            return ToolResult(call=call, ok=False, content="缺少 name/description/code 参数。")
        if "def run(" not in code:
            return ToolResult(
                call=call, ok=False, content="代码必须定义 def run(args: dict) -> str 函数。"
            )
        try:
            import json as _json

            params = _json.loads(params_json)
            if not isinstance(params, list):
                raise ValueError("params 必须是数组")
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"params_json 解析失败：{exc}")
        try:
            t = ext_tools.add(name, description, params, code)
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"登记失败：{exc}")
        return ToolResult(
            call=call,
            ok=True,
            content=(
                f"已登记扩展工具「{name}」（#{t.id[:8]}）状态=draft。"
                "已提交待审——请向用户说明并请求批准（批准后生效，可被直接调用）。"
            ),
            data={"tool_id": t.id, "name": name},
        )

    return spec, implementer


def make_read_context_implementer(chapters: Any, book_id: str = "main") -> tuple[Any, Any]:
    """上下文段落阅读（S48-P4/B：命中后看上下段落，不读全文省 token）。

    与 search_chapters 配套：检索定位到章节后，用锚点读该处前后 N 段
    （段落=空行分隔，中文正文自然分段）——比 read_chapter 读全文省 token。
    """

    spec = ToolSpec(
        name="read_context",
        description=(
            "读取某章中指定锚点位置的前后若干段落（不读全文，省 token）。"
            "search_chapters 定位到命中章节后，想确认命中处的完整语境时用——"
            "段落=空行分隔；锚点用章内出现的短语/句子。"
        ),
        params=[
            ParamSpec(
                name="title",
                type="string",
                required=True,
                description="章节标题",
            ),
            ParamSpec(
                name="anchor",
                type="string",
                required=True,
                description="章内锚点文本（含它的段落将被定位）",
            ),
            ParamSpec(
                name="before",
                type="number",
                required=False,
                description="锚点前读几段（默认 2，上限 5）",
            ),
            ParamSpec(
                name="after",
                type="number",
                required=False,
                description="锚点后读几段（默认 2，上限 5）",
            ),
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        title = str(arguments.get("title", "")).strip()
        anchor = str(arguments.get("anchor", "")).strip()
        if not title or not anchor:
            return ToolResult(call=call, ok=False, content="缺少参数 title 或 anchor。")
        try:
            before = min(max(int(str(arguments.get("before", "2")) or "2"), 0), 5)
            after = min(max(int(str(arguments.get("after", "2")) or "2"), 0), 5)
        except ValueError:
            before, after = 2, 2
        try:
            ch = next((c for c in chapters.list_by_book(book_id) if c.title == title), None)
            if ch is None:
                return ToolResult(
                    call=call,
                    ok=False,
                    content=f"未找到章节《{title}》（可用 list_chapters 查看）。",
                )
            paras = [p.strip() for p in ch.content.split("\n\n") if p.strip()]
            if not paras:
                return ToolResult(call=call, ok=False, content=f"《{title}》为空。")
            idx = next((i for i, p in enumerate(paras) if anchor in p), None)
            if idx is None:
                # 锚点未命中：返回开头若干段 + 提示
                head = "\n\n".join(paras[: min(before + after + 1, 3)])
                return ToolResult(
                    call=call,
                    ok=False,
                    content=(
                        f"《{title}》未找到锚点「{anchor}」（共 {len(paras)} 段）。"
                        f"开头片段：\n{head[:300]}"
                    ),
                )
            lo = max(0, idx - before)
            hi = min(len(paras), idx + after + 1)
            body = "\n\n".join(paras[lo:hi])
            marker = f"（第 {idx + 1}/{len(paras)} 段附近）"
            return ToolResult(call=call, ok=True, content=f"《{title}》{marker}\n\n{body}")
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"读取失败：{exc}")

    return spec, implementer


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
            "'我一般晚上写作'。登记后后续写作自动遵循。"
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


def make_material_register_implementer(materials: Any, book_id: str = "main") -> tuple[Any, Any]:
    """S80：灵感登记工具——把灵感/参考内容写进资料库（inspiration 卡）。

    资料库 = 灵感冷藏库（DESIGN §12.39）：inspiration 卡智能体可见可检索（read_material），
    不注入写作；copy 冷藏副本不可见（仅人工/导入产生，本工具不写 copy）。
    随手记不强制 LLM 消化（快）；AI 可用 title 组织，原文保留在 source_text。
    """

    spec = ToolSpec(
        name="material_register",
        description=(
            "把灵感/参考内容登记进资料库（灵感卡，智能体可见可检索，不注入写作）。"
            "用户说'记一下这个灵感/这段参考'，或写作中发现值得留存的素材时使用——"
            "如历史文献摘录、人设灵感、场景点子。purpose=fact(事实/设定)/style(文风参考)/both。"
            "随手记不强制消化，原文保留；需要结构化摘要时可后续走资料消化。"
        ),
        params=[
            ParamSpec(
                name="content",
                type="string",
                required=True,
                description="灵感/参考内容（自然语言）",
            ),
            ParamSpec(
                name="title",
                type="string",
                required=False,
                description="可选标题（缺省用内容前 30 字）",
            ),
            ParamSpec(
                name="purpose",
                type="string",
                required=False,
                description="fact/style/both（缺省 fact）",
            ),
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        content = str(arguments.get("content", "")).strip()
        title = str(arguments.get("title", "")).strip()
        purpose = str(arguments.get("purpose", "fact")).strip() or "fact"
        if not content:
            return ToolResult(call=call, ok=False, content="缺少参数 content。")
        if purpose not in ("style", "fact", "both"):
            purpose = "fact"
        try:
            from anyspark.template import MaterialCard

            card = MaterialCard(
                title=title or content[:30],
                topic="",
                key_points=[],
                key_settings=[],
                characters=[],
                terms=[],
                purpose=purpose,  # type: ignore[arg-type]
                source_text=content,
                kind="inspiration",
            )
            materials.save(card, book_id=book_id)
            return ToolResult(
                call=call,
                ok=True,
                content=f"已记录灵感《{card.title}》到资料库（purpose={purpose}）。",
                data={"material_id": card.id},
            )
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"记录失败：{exc}")

    return spec, implementer


def make_graph_register_implementer(graph: Any, book_id: str = "main") -> tuple[Any, Any]:
    """S72：图谱登记工具——对话中"把XX记进图谱"→ 立即登记实体（+可选关系）。

    对齐 mind_register（用户主动登记模式）：抽取会错/会漏，用户明确表述的设定
    应即时落库（source=user 高置信度），不依赖自动抽取。只登记不删除
    （删除走 API，内容裁决权在用户）。
    """

    spec = ToolSpec(
        name="graph_register",
        description=(
            "把用户明确表述的设定/角色/关系登记进知识图谱。"
            "当用户在对话中明确陈述设定（如'顾欣桐是赵光离的线人''雾城是边境城市'）"
            "或纠正图谱错误时使用。登记后写作时图谱注入会自动包含。"
            "只记事实（谁是谁/世界规则/关系）；剧情承诺/伏笔（'埋了线索待回收'）用"
            "plot_register，不要两处重复登记。"
        ),
        params=[
            ParamSpec(
                name="name",
                type="string",
                required=True,
                description="实体名（角色/地点/物件/设定）",
            ),
            ParamSpec(
                name="entity_type",
                type="string",
                required=False,
                description="类型：角色/地点/事件/物件/设定（缺省 设定）",
            ),
            ParamSpec(
                name="description",
                type="string",
                required=False,
                description="实体描述（自然语言）",
            ),
            ParamSpec(
                name="rel_to",
                type="string",
                required=False,
                description="关联的另一实体名（可选，同时登记关系时给）",
            ),
            ParamSpec(
                name="rel_type",
                type="string",
                required=False,
                description="关系类型（如 师父/线人/敌对；rel_to 有值时生效）",
            ),
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        name = str(arguments.get("name", "")).strip()
        if not name:
            return ToolResult(call=call, ok=False, content="缺少参数 name。")
        etype = str(arguments.get("entity_type", "设定")).strip() or "设定"
        desc = str(arguments.get("description", "")).strip()
        rel_to = str(arguments.get("rel_to", "")).strip()
        rel_type = str(arguments.get("rel_type", "")).strip()
        try:
            ent = graph.get_entity(book_id, name)
            if ent is None:
                graph.upsert_entity(book_id, name, etype, description=desc)
            elif desc:
                graph.update_entity_fields(book_id, name, description=desc, entity_type=etype)
            lines = [f"已登记实体：{name}（{etype}）"]
            if rel_to and rel_type:
                rel = graph.upsert_relation(book_id, name, rel_to, rel_type, description=desc)
                if rel is None:
                    lines.append(f"关系未登记：{rel_to} 不存在（先登记该实体）")
                else:
                    lines.append(f"已登记关系：{name} —{rel_type}→ {rel_to}")
            return ToolResult(
                call=call,
                ok=True,
                content="\n".join(lines),
                data={"entity": name, "type": etype},
            )
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"登记失败：{exc}")

    return spec, implementer


def make_play_implementer(engine: Any) -> tuple[list[Any], list[Any]]:
    """互动推演工具（S65，enable_play 点亮，默认关）：扮演角色多轮选择推进。

    play_start / play_choose / play_status / play_export——灵感来源 + 互动玩法：
    - 卡文/想剧情时：扮演一个角色从场景切入，多轮选择推演，看剧情怎么发酵；
    - 推演路径导出灵感卡，作为写正文的参考素材（对齐哲学：参考，不直接写正文）。
    只读 + 启动，无删除（内容裁决权保留在用户/API）。
    """

    specs: list[Any] = []
    impls: list[Any] = []

    start_spec = ToolSpec(
        name="play_start",
        description=(
            "启动一次互动推演（扮演角色从场景切入，多轮选择推进剧情）。"
            "需要灵感/想玩推演时使用——返回初始场景与 3-5 个候选行动，"
            "后续用 play_choose 选择推进。role 须已有角色卡。"
        ),
        params=[
            ParamSpec(
                name="role",
                type="string",
                required=True,
                description="扮演的角色名（须有角色卡）",
            ),
            ParamSpec(
                name="seed",
                type="string",
                required=True,
                description="切入场景（自然语言，如'码头雨夜，有人送来一封信'）",
            ),
            ParamSpec(
                name="title",
                type="string",
                required=False,
                description="推演标题（可选）",
            ),
        ],
    )

    def start(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        role = str(arguments.get("role", "")).strip()
        seed = str(arguments.get("seed", "")).strip()
        if not role or not seed:
            return ToolResult(call=call, ok=False, content="缺少参数 role 或 seed。")
        try:
            result = engine.create(role=role, seed=seed, title=str(arguments.get("title", "")))
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"启动推演失败：{exc}")
        node = result["node"]
        lines = [
            f"【互动推演已启动】会话 {result['session']['id']}",
            f"扮演：{role}",
            f"场景：{node['scene']}",
            "候选行动：",
        ]
        for i, o in enumerate(node["options"], 1):
            lines.append(f"{i}. {o['label']}")
        lines.append("（用 play_choose 选择，或输入自定义行动）")
        return ToolResult(call=call, ok=True, content="\n".join(lines))

    choose_spec = ToolSpec(
        name="play_choose",
        description=(
            "互动推演中选择一个候选行动（或自定义行动），剧情结算并推进到下一场景，"
            "返回新的候选行动。option_id 来自 play_start / 上次 play_choose 的结果；"
            "也可传 custom_text 输入自定义行动。"
        ),
        params=[
            ParamSpec(
                name="session_id",
                type="string",
                required=True,
                description="推演会话 ID（play_start 返回）",
            ),
            ParamSpec(
                name="option_id",
                type="string",
                required=False,
                description="候选行动 ID（与 custom_text 二选一）",
            ),
            ParamSpec(
                name="custom_text",
                type="string",
                required=False,
                description="自定义行动文本（与 option_id 二选一）",
            ),
        ],
    )

    def choose(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        sid = str(arguments.get("session_id", "")).strip()
        if not sid:
            return ToolResult(call=call, ok=False, content="缺少参数 session_id。")
        try:
            result = engine.choose(
                sid,
                option_id=str(arguments.get("option_id", "")).strip(),
                custom_text=str(arguments.get("custom_text", "")).strip(),
            )
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"推进失败：{exc}")
        node = result["node"]
        lines = [
            f"【第 {node['depth']} 步】你选择了：{node['chosen_label']}",
            node["scene"],
        ]
        if result["ended"]:
            lines.append("\n（故事自然收束，推演结束。可用 play_export 导出灵感卡）")
        else:
            lines.append("候选行动：")
            for i, o in enumerate(node["options"], 1):
                lines.append(f"{i}. {o['label']}")
            lines.append("（继续 play_choose，或自定义行动；可回溯重走）")
        return ToolResult(call=call, ok=True, content="\n".join(lines))

    status_spec = ToolSpec(
        name="play_status",
        description="查看互动推演的当前状态：当前场景、候选行动、已走的路径。",
        params=[
            ParamSpec(
                name="session_id",
                type="string",
                required=True,
                description="推演会话 ID",
            ),
        ],
    )

    def status(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        sid = str(arguments.get("session_id", "")).strip()
        if not sid:
            return ToolResult(call=call, ok=False, content="缺少参数 session_id。")
        try:
            node = engine.current_node(sid)
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"查看失败：{exc}")
        lines = [
            f"【推演状态】会话 {sid}（深度 {node['depth']}）",
            node["scene"],
            "候选行动：",
        ]
        for i, o in enumerate(node["options"], 1):
            lines.append(f"{i}. {o['label']}")
        return ToolResult(call=call, ok=True, content="\n".join(lines))

    export_spec = ToolSpec(
        name="play_export",
        description=(
            "把互动推演的当前路径导出为灵感卡（markdown）——作为写作参考素材，"
            "可交给 write_chapter 参考或给作者浏览。"
        ),
        params=[
            ParamSpec(
                name="session_id",
                type="string",
                required=True,
                description="推演会话 ID",
            ),
        ],
    )

    def export(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        sid = str(arguments.get("session_id", "")).strip()
        if not sid:
            return ToolResult(call=call, ok=False, content="缺少参数 session_id。")
        try:
            md = engine.export_markdown(sid)
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"导出失败：{exc}")
        return ToolResult(call=call, ok=True, content=md)

    specs = [start_spec, choose_spec, status_spec, export_spec]
    impls = [start, choose, status, export]
    return specs, impls


def make_path_explore_implementer(model: Any) -> tuple[Any, Any]:
    """叙事路径探索工具（S67）：起点 A → 终点 B 的中间串联路径候选。

    章节间过渡/情节点连接/卡文找过渡时使用——生成 N 条不同思路的事件链
    （A → 事件1 → 事件2 → B）供作者选择。作为参考，不直接写正文。
    """

    spec = ToolSpec(
        name="path_explore",
        description=(
            "叙事路径探索：给定起点和终点（两个情节点/章节间），生成 2-4 条不同的"
            "中间串联路径候选（每条一串中间事件：A → 事件1 → 事件2 → B）。"
            "章节间过渡、情节点连接、卡文找过渡方向时使用——返回候选路径供呈现"
            "给用户选择，作为写作参考（不直接写正文）。"
        ),
        params=[
            ParamSpec(
                name="from_desc",
                type="string",
                required=True,
                description="起点（自然语言描述，如'陈渡收到旧船票'）",
            ),
            ParamSpec(
                name="to_desc",
                type="string",
                required=True,
                description="终点（如'陈渡发现父亲没死'）",
            ),
            ParamSpec(
                name="constraints",
                type="string",
                required=False,
                description="已固化设定约束（可空，'女主=医者'之类）",
            ),
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        from_desc = str(arguments.get("from_desc", "")).strip()
        to_desc = str(arguments.get("to_desc", "")).strip()
        if not from_desc or not to_desc:
            return ToolResult(call=call, ok=False, content="缺少参数 from_desc 或 to_desc。")
        constraints = [
            c.strip() for c in str(arguments.get("constraints", "")).split("；") if c.strip()
        ] or None
        try:
            from anyspark.explore import explore_path

            result = explore_path(model, from_desc, to_desc, constraints, n=4)
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"路径探索失败：{exc}")
        if not result.paths:
            return ToolResult(call=call, ok=False, content="路径探索失败（无有效候选）。")
        lines = [f"【路径探索】{from_desc} → {to_desc}"]
        for i, p in enumerate(result.paths, 1):
            chain = " → ".join(["A", *p.events, "B"])
            lines.append(f"{i}. [{p.style or '路径'}] {chain}")
            if p.note:
                lines.append(f"   （{p.note}）")
        lines.append("（供作者选择作为过渡参考；不直接写正文）")
        return ToolResult(call=call, ok=True, content="\n".join(lines))

    return spec, implementer


def make_skill_refine_implementer(
    generator: Any,
    materials: Any,
    library: Any = None,
    skills: Any = None,
) -> tuple[Any, Any]:
    """文风参考书 → skill 提炼工具（S72）：把原文/资料提炼成叙事技法候选。

    S103：加 library_book_id（从书库取原文）+ 候选存草稿（skills.add_draft，
    前端草稿区人工确认转正——对话触发的提炼不再断链）。

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
        try:
            if mode == "book":
                # S78/S106 拆书：整本书多维拆解 → 一份「书名」skill（大书分块抽样+归并）
                candidates = generator.generate_book(source_text, hint)
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
        if skills is not None:
            for c in candidates:
                d = skills.add_draft(
                    name=str(c.get("name", "")),
                    description=str(c.get("description", ""))[:500],
                    content=str(c.get("content", "")),
                    example=str(c.get("example", ""))[:2000],
                    tags=str(c.get("tags", "")),
                    target=str(c.get("target", "writing")),
                    source="agent",
                )
                if d:
                    draft_ids.append(str(d["id"]))
        lines = [f"【{tag} {len(candidates)} 条（已存草稿，待人工确认生效）】"]
        for i, c in enumerate(candidates, 1):
            name = c.get("name", f"候选{i}")
            desc = str(c.get("description", ""))[:60]
            lines.append(f"{i}. {name}：{desc}")
        if mode == "book":
            content = str(candidates[0].get("content", ""))
            lines.append(
                f"   （整本方法论 {len(content)} 字，分小节："
                "文风/节奏/结构/人设/对白/信息投放/钩子）"
            )
        if draft_ids:
            lines.append(f"（草稿已生成 {len(draft_ids)} 条，去书库/技巧标签确认后生效）")
        elif skills is not None:
            lines.append("（已有同名草稿或技能，未重复生成——可先确认/删除旧的再提炼）")
        return ToolResult(call=call, ok=True, content="\n".join(lines))

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
                type="bool",
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


def make_reference_lookup_implementer(
    library_store: Any, chapters: Any, book_id: str = "main"
) -> tuple[Any, Any]:
    """参考书检索工具（S86）：搜当前项目已选的参考书（书库的书 + 其他项目）。

    参考书不注入任何信息——需要借鉴某本书的写法/设定/氛围时主动检索原文片段。
    """

    spec = ToolSpec(
        name="reference_lookup",
        description=(
            "检索本项目已选的参考书（书库的书或其他项目），按关键词返回原文片段"
            "（含书名/章节）。需要借鉴某本参考书的写法、设定细节、氛围、结构时使用——"
            "如模仿某书的群像描写、确认同世界观旧作的人物设定、参考同题材书的"
            "官职/礼法细节。注意：参考书是借鉴来源，不是本项目正典——检索到后"
            "对照自身剧情判断是否适用，不要照搬设定。"
        ),
        params=[
            ParamSpec(
                name="keyword",
                type="string",
                required=True,
                description="检索关键词/短语（独特词效果好，如'钟表铺'而非'门'）",
            ),
            ParamSpec(
                name="max_per_book",
                type="string",
                required=False,
                description="每本书最多返回几段（缺省 3）",
            ),
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        keyword = str(arguments.get("keyword", "")).strip()
        if not keyword:
            return ToolResult(call=call, ok=False, content="缺少参数 keyword。")
        try:
            max_per = max(1, min(5, int(str(arguments.get("max_per_book", "3")) or 3)))
        except ValueError:
            max_per = 3

        def _project_files(ref_book_id: str) -> str:
            """工作区其他项目：读章节内容拼文本（参考书只读检索）。"""
            if chapters is None:
                return ""
            parts = []
            for ch in chapters.list_by_book(ref_book_id):
                parts.append(f"【{ch.title}】\n{ch.content}")
            return "\n\n".join(parts)

        from anyspark.library.search import search_reference_books

        res = search_reference_books(
            library_store, book_id, keyword, project_files=_project_files, max_per_book=max_per
        )
        if not res["results"]:
            refs = library_store.get_references(book_id) if library_store else []
            names = "、".join(r.get("name", r.get("id", "?")) for r in refs) or "（未选参考书）"
            return ToolResult(
                call=call,
                ok=False,
                content=f"参考书「{names}」中未命中「{keyword}」。",
            )
        lines = [f"参考书命中「{keyword}」共 {res['total_hits']} 段："]
        for r in res["results"]:
            lines.append(f"——{r['ref_name']}——")
            for h in r["hits"]:
                lines.append(f"({h['count']}次) {h['snippet']}")
        return ToolResult(call=call, ok=True, content="\n\n".join(lines))

    return spec, implementer


def make_batch_implementer(chapters: Any, book_id: str = "main") -> tuple[list[Any], list[Any]]:
    """S102：批量改写/批量审读**提议工具**（agent 自主发起，人工批准后执行）。

    与 /api/batch/* 的关系：agent 工具只做"提议"——解析章节、返回待确认申请，
    **不执行**（批量改写多章原稿是重操作，执行权在用户确认后由前端调 /api/batch/*）。
    返回结构化待确认信息（匹配到的章节 + 指令），agent 转告用户等待批准。
    """

    def _parse_titles(raw: Any) -> list[str]:
        """chapter_titles 参数解析：兼容数组 / JSON 字符串 / 逗号·顿号·换行分隔。"""
        if isinstance(raw, list):
            return [str(x).strip() for x in raw if str(x).strip()]
        s = str(raw or "").strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except (ValueError, TypeError):
            pass
        return [t.strip() for t in re.split(r"[,，、;；\n]", s) if t.strip()]

    def _resolve_titles(chs: list[Any], titles: list[str]) -> tuple[list[Any], list[str]]:
        """标题模糊匹配章节（标题包含/被包含），去重保序。返回 (匹配章节, 未匹配标题)。"""
        matched: list[Any] = []
        unmatched: list[str] = []
        for t in titles:
            found = [c for c in chs if t in c.title or c.title in t]
            if found:
                matched.extend(found)
            else:
                unmatched.append(t)
        seen: set[str] = set()
        dedup: list[Any] = []
        for c in matched:
            if c.id not in seen:
                seen.add(c.id)
                dedup.append(c)
        return dedup, unmatched

    def _chapters() -> list[Any]:
        try:
            return list(chapters.list_by_book(book_id))
        except Exception as exc:
            raise RuntimeError(f"读取章节失败: {exc}") from exc

    def _fmt_proposal(
        kind: str, matched: list[Any], unmatched: list[str], instruction: str = ""
    ) -> str:
        lines = [f"【批量{kind}申请·待用户批准】"]
        if instruction:
            lines.append(f"指令：{instruction}")
        lines.append(f"目标章节（{len(matched)}章）：")
        lines.extend(f"- {c.title}" for c in matched)
        if unmatched:
            lines.append(f"未匹配（已忽略）：{'、'.join(unmatched)}")
        lines.append("请转告用户确认；用户批准后批量才会真正执行（本工具只提交申请）。")
        return "\n".join(lines)

    rewrite_spec = ToolSpec(
        name="batch_rewrite",
        description=(
            "提议批量改写多章（统一指令应用：改文风/改情节/统一细节）。"
            "需要一次性处理多章时使用；chapter_titles 传章节标题，多个用逗号分隔"
            "（支持部分匹配，如'第三章,雨夜'）。**注意：本工具只提交申请不直接执行**"
            "——多章原稿批量修改需用户批准后才执行，批准后进度会另行呈现。"
        ),
        params=[
            ParamSpec(
                name="chapter_titles",
                type="string",
                required=True,
                description="要改写的章节标题（多个用逗号分隔，可部分匹配）",
            ),
            ParamSpec(
                name="instruction",
                type="string",
                required=True,
                description="统一改写指令（如'统一为冷峻克制的都市感'）",
            ),
        ],
    )

    def rewrite_impl(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        titles = _parse_titles(arguments.get("chapter_titles"))
        instruction = str(arguments.get("instruction", "")).strip()
        if not titles or not instruction:
            return ToolResult(
                call=call,
                ok=False,
                content=(
                    "参数不完整：需要 chapter_titles（章节标题，逗号分隔）"
                    "和 instruction（改写指令）。"
                ),
            )
        try:
            matched, unmatched = _resolve_titles(_chapters(), titles)
        except RuntimeError as exc:
            return ToolResult(call=call, ok=False, content=str(exc))
        if not matched:
            return ToolResult(
                call=call,
                ok=False,
                content=(
                    "未匹配到任何章节。现有章节标题："
                    f"{'、'.join(c.title for c in _chapters()[:10]) or '（空）'}"
                ),
            )
        return ToolResult(
            call=call, ok=True, content=_fmt_proposal("改写", matched, unmatched, instruction)
        )

    review_spec = ToolSpec(
        name="batch_review",
        description=(
            "提议批量审读多章（检测网：一致性/动机因果/情感连贯等 7 类问题）。"
            "需要一次性审读多章时使用；chapter_titles 传章节标题，多个用逗号分隔"
            "（支持部分匹配）。**注意：本工具只提交申请不直接执行**——"
            "用户批准后才真正审读，审读报告批准后另行呈现。"
        ),
        params=[
            ParamSpec(
                name="chapter_titles",
                type="string",
                required=True,
                description="要审读的章节标题（多个用逗号分隔，可部分匹配）",
            ),
        ],
    )

    def review_impl(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        titles = _parse_titles(arguments.get("chapter_titles"))
        if not titles:
            return ToolResult(
                call=call,
                ok=False,
                content="参数不完整：需要 chapter_titles（章节标题，逗号分隔）。",
            )
        try:
            matched, unmatched = _resolve_titles(_chapters(), titles)
        except RuntimeError as exc:
            return ToolResult(call=call, ok=False, content=str(exc))
        if not matched:
            return ToolResult(
                call=call,
                ok=False,
                content=(
                    "未匹配到任何章节。现有章节标题："
                    f"{'、'.join(c.title for c in _chapters()[:10]) or '（空）'}"
                ),
            )
        return ToolResult(call=call, ok=True, content=_fmt_proposal("审读", matched, unmatched))

    return [rewrite_spec, review_spec], [rewrite_impl, review_impl]
