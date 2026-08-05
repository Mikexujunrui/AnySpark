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

from typing import Any

from anyspark.core.protocol import ParamSpec, ToolResult, ToolSpec
from anyspark.core.types import ToolCall

# 查询返回上限（防 token 爆炸：Agent 是裁剪消费者，需要细节再查）
_QUERY_LIMIT = 10
_RELATION_LIMIT = 15


def make_graph_query_implementer(graph: Any) -> tuple[Any, Any]:
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
            entities = graph.list_entities("main", q=q, limit=_QUERY_LIMIT)
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
            relations = graph.list_relations("main", limit=_RELATION_LIMIT)
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


def make_plot_implementer(plots: Any) -> tuple[list[Any], list[Any]]:
    """伏笔工具：登记（埋钩子）+ 列表（看还欠哪些承诺）。"""

    register_spec = ToolSpec(
        name="plot_register",
        description=(
            "登记一个伏笔/剧情钩子（关键点图谱）。写作中埋下线索、悬念、承诺时使用——"
            "一句话'记一下'，系统记入关键点图谱并在后续注入中持续提醒。"
            "priority=must 表示主线承诺（必须回收，会重点标注）；默认 soft（细节线索）。"
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
                book_id="main",
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
            render = plots.render("main")
            return ToolResult(
                call=call,
                ok=True,
                content=render if render.strip() else "关键点图谱为空（没有进行中的伏笔）。",
            )
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"查询失败：{exc}")

    return [register_spec, list_spec], [register, list_points]


def make_plan_implementer(plans: Any) -> tuple[list[Any], list[Any]]:
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
            from anyspark.align.plan import render_plan

            entries = plans.list("main")
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
            entries = plans.list("main")
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


def make_setting_implementer(settings: Any) -> tuple[Any, Any]:
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
            entries = settings.list("main")
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
    workspace: Any, chapters: Any, materials: Any, model: Any
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
        try:
            from anyspark.server.pipeline import chapterize, extract_text

            path = workspace.read_upload("main", filename)
            if path is None:
                ups = workspace.list_uploads("main")
                names = "、".join(u["name"] for u in ups) or "（空）"
                return ToolResult(
                    call=call, ok=False, content=f"上传区无「{filename}」。现有：{names}"
                )
            text = extract_text(path)
            if not text.strip():
                return ToolResult(
                    call=call,
                    ok=False,
                    content="无法提取文本（扫描件 OCR 放未来计划），可先列上传区确认文件格式。",
                )
            chaps = chapterize(text, fallback_title=path.stem)
            is_card = mode == "card" or (
                mode != "chapters" and len(chaps) == 1 and len(text) < 3000
            )
            if is_card:
                from anyspark.template import MaterialDigestor

                digestor = MaterialDigestor(model)
                saved = materials.save(digestor.digest(text))
                card_md = (
                    f"# {saved.title}\n\n主题：{saved.topic}\n\n"
                    + "要点："
                    + "；".join(saved.key_points[:6])
                    + "\n设定："
                    + "；".join(saved.key_settings[:6])
                    + "\n角色："
                    + "、".join(saved.characters[:8])
                    + "\n术语："
                    + "、".join(saved.terms[:8])
                )
                f = workspace.write_card("main", "摘要卡", saved.title, card_md)
                return ToolResult(
                    call=call,
                    ok=True,
                    content=f"已消化「{filename}」为摘要卡《{saved.title}》（{f.name}）。"
                    f"\n主题：{saved.topic}\n要点：{'；'.join(saved.key_points[:4])}",
                )
            written: list[str] = []
            for i, ch in enumerate(chaps):
                workspace.write_chapter("main", i, ch["title"], ch["content"])
                chapters.upsert("main", ch["title"], ch["content"], i, "main")
                written.append(f"{i + 1}. {ch['title']}（{len(ch['content'])}字）")
            return ToolResult(
                call=call,
                ok=True,
                content=f"已消化「{filename}」为 {len(written)} 章：\n" + "\n".join(written),
            )
        except Exception as exc:
            return ToolResult(call=call, ok=False, content=f"消化失败：{exc}")

    return spec, implementer


def make_codex_implementer(workspace: Any, chapters: Any, graph: Any) -> tuple[Any, Any]:
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

        r = run_code(code, timeout, data_env=make_data_env(workspace, chapters, graph))
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


def make_roleplay_implementer(workspace: Any, graph: Any, model: Any) -> tuple[Any, Any]:
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
            from anyspark.explore.roleplay import run_roleplay

            card_path = workspace.cards_dir("main") / f"角色卡-{role}.md"
            role_card = ""
            if card_path.exists():
                role_card = card_path.read_text(encoding="utf-8", errors="ignore")
            state = ""
            ent = graph.get_entity("main", role)
            if ent is not None:
                st = getattr(ent, "state", "") or ""
                desc = getattr(ent, "description", "") or ""
                state = st
                if not role_card.strip():
                    role_card = f"# {role}\n{desc}\n\n当前状态：{st}"
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
