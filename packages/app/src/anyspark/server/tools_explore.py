"""
anyspark.server.tools_explore — 角色推演/路径探索/推演/沙箱/资料/扩展注册工具。

工厂函数创建 agent 工具（ToolSpec + implementer 对），接收 store 参数，
不引用闭包——从 tools_domain.py 提取无行为变化。
"""

from __future__ import annotations

from typing import Any

from anyspark.core import ToolCall
from anyspark.core.protocol import ParamSpec, ToolResult, ToolSpec


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


def make_ingest_implementer(
    workspace: Any,
    chapters: Any,
    materials: Any,
    model: Any,
    book_id: str = "main",
    skills: Any | None = None,
) -> tuple[Any, Any]:
    """上传消化工具（S48-P3）：把上传区原始文档消化成章节 md / 摘要卡 / skill 草稿。

    Agent 在用户上传了原稿/设定文档后调用——拆章进格式化区（可继续写作），
    或生成摘要卡（设定/资料，进卡片区 + 图谱关联），或识别为 skill 文件
    （S118：front-matter 五段式 → 草稿待人工确认）。
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
            workspace, chapters, materials, model, book_id, filename, mode=mode, skills=skills
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
        if result.kind == "skill":
            # S118：skill 文件识别 → 草稿待人工确认
            return ToolResult(
                call=call,
                ok=True,
                content=f"识别到 skill 文件《{result.title}》，已存为草稿待确认"
                f"（草稿区可查看/采纳/拒绝）。",
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
