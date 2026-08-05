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


def make_search_chapters_implementer(chapters: Any) -> tuple[Any, Any]:
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
                required=True,
                description="要检索的关键词/短语（如'红绳'、'怀表背面'）",
            ),
            ParamSpec(
                name="exclude",
                type="string",
                required=False,
                description="排除词：命中位置片段内包含该词的命中不算（如搜'怀表'排除'没有'）",
            ),
            ParamSpec(
                name="fragment",
                type="string",
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
        if not kw:
            return ToolResult(call=call, ok=False, content="缺少参数 keyword。")
        try:
            import re as _re

            exclude = str(arguments.get("exclude", "")).strip() or None
            try:
                frag = max(0, min(int(str(arguments.get("fragment", "20")) or "20"), 500))
            except ValueError:
                frag = 20
            use_regex = str(arguments.get("regex", "")).strip().lower() in ("true", "1", "yes")
            items = chapters.list_by_book("main")
            if not items:
                return ToolResult(call=call, ok=True, content="暂无章节。")
            hits: list[dict[str, Any]] = []
            total = 0
            for c in items:
                n = 0
                first_ctx = ""
                if use_regex:
                    try:
                        matches = list(_re.finditer(kw, c.content))
                    except _re.error as exc:
                        return ToolResult(call=call, ok=False, content=f"正则表达式错误：{exc}")
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
                else:
                    start = 0
                    while True:
                        idx = c.content.find(kw, start)
                        if idx == -1:
                            break
                        if frag > 0:
                            ctx = c.content[max(0, idx - frag) : idx + len(kw) + frag]
                            if exclude is not None and _sent_has(c.content, idx, len(kw), exclude):
                                start = idx + len(kw)
                                continue
                            n += 1
                            if not first_ctx:
                                first_ctx = "…" + ctx + "…"
                        else:
                            n += 1
                        start = idx + len(kw)
                if n > 0:
                    total += n
                    hits.append({"title": c.title, "count": n, "context": first_ctx})
            if not hits:
                return ToolResult(
                    call=call, ok=True, content=f"全书未找到「{kw}」（共检索 {len(items)} 章）。"
                )
            lines = [f"「{kw}」命中 {len(hits)} 章共 {total} 次："]
            for h in hits:
                if h["context"]:
                    lines.append(f"- 《{h['title']}》×{h['count']}：{h['context']}")
                else:
                    lines.append(f"- 《{h['title']}》×{h['count']}")
            lines.append("（字面命中，需读上下文判断相关性；看命中处完整段落用 read_context）")
            return ToolResult(
                call=call,
                ok=True,
                content="\n".join(lines),
                data={"hits": hits, "chapters": len(hits), "total": total},
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


def make_read_context_implementer(chapters: Any) -> tuple[Any, Any]:
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
                type="string",
                required=False,
                description="锚点前读几段（默认 2，上限 5）",
            ),
            ParamSpec(
                name="after",
                type="string",
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
            ch = next((c for c in chapters.list_by_book("main") if c.title == title), None)
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
