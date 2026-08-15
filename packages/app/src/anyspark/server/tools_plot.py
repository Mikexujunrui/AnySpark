"""
anyspark.server.tools_plot — 伏笔/计划/设定查证工具（从 tools_domain.py 拆出，S188 技术债清理）。

工厂函数创建 agent 工具（ToolSpec + implementer 对），接收 store 参数，
不引用闭包——从 tools_domain.py 提取无行为变化。
"""

from __future__ import annotations

from typing import Any

from anyspark.align import render_plan
from anyspark.core import ToolCall
from anyspark.core.protocol import ParamSpec, ToolResult, ToolSpec


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
            # 返回带 id 的列表（agent 回收需要 plot_id 调 plot_resolve）
            points = plots.list_points(book_id)
            if not points:
                return ToolResult(
                    call=call,
                    ok=True,
                    content="关键点图谱为空（没有进行中的伏笔）。",
                )
            lines = ["# 伏笔列表（plot_id 用于 plot_resolve 回收）"]
            for p in points:
                if p.attention == "ignore":
                    continue
                mark = "★" if p.priority == "must" else "·"
                status = "✓" if p.status == "resolved" else "○"
                ref = f"（{p.chapter_ref}）" if p.chapter_ref else ""
                lines.append(f"{status} {mark} [{p.category}] {p.content}{ref}  →id={p.id[:12]}")
            return ToolResult(call=call, ok=True, content="\n".join(lines))
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
                    lines.append(f"【{cat}】（共 {len(items)} 条）")
                    # S157：条目内容不截断（写全了却截断没道理）；超 8 条时明确告知可精查
                    for e in items[:8]:
                        lines.append(f"- {e.name}：{e.content}")
                    if len(items) > 8:
                        lines.append(f"  …共 {len(items)} 条，仅列前 8，带关键词精查")
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
