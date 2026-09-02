"""
anyspark.server.tools_reference — 参考书检索/批量任务工具。

工厂函数创建 agent 工具（ToolSpec + implementer 对），接收 store 参数，
不引用闭包——从 tools_domain.py 提取无行为变化。
"""

from __future__ import annotations

import json
import re
from typing import Any

from anyspark.core import ToolCall
from anyspark.core.protocol import ParamSpec, ToolResult, ToolSpec
from anyspark.server.logging import logger


def make_reference_lookup_implementer(
    library_store: Any,
    chapters: Any,
    book_id: str = "main",
    graph: Any = None,
    settings: Any = None,
    vectors: Any = None,
    embedder: Any = None,
) -> tuple[Any, Any]:
    """参考书检索工具（S86 + 分级 + S244 语义通道）：搜当前项目已选的参考书
    （书库的书 + 其他项目）+ S244 起可语义检索**全书库**。

    参考书分级（设计定案）：
    - 低级参考书（书库的书）：只检索原文文本片段（现状）。
    - 高级参考书（项目）：除原文片段外，还可检索该项目的知识层——图谱实体卡片
      （名称/类型/状态/关系）与设定档条目（分类/内容），只读、不注入、按需检索。

    S244 语义通道：vectors+embedder 可用时（mode=auto/semantic），额外对**全书库**
    做 embedding 余弦检索——零关键词重叠的模糊查询（「像中世纪行会的设定」）
    也能命中；不可用时自动降级纯关键词，不报错。
    """

    spec = ToolSpec(
        name="reference_lookup",
        description=(
            "检索参考书：① 项目已选参考书按关键词返回原文片段（含书名/章节）；"
            "项目型参考书还会返回图谱实体卡片与设定档条目（人物状态/关系/世界观规则）。"
            "② S244 语义检索：mode=semantic 或 auto 时对**全书库**做语义相似检索，"
            "适合模糊描述（'类似中世纪行会的权力斗争设定'）——无精确关键词也能命中。"
            "需要借鉴某本书的写法、设定细节、氛围、结构，或确认同世界观旧作/原作的"
            "人物设定时使用；模糊探索书库内容时用 mode=semantic。"
            "注意：参考书是借鉴来源，不是本项目正典——检索到后对照自身剧情判断"
            "是否适用，不要照搬设定。"
        ),
        params=[
            ParamSpec(
                name="keyword",
                type="string",
                required=True,
                description=(
                    "检索关键词/短语或自然语言描述。mode=keyword 时用独特词"
                    "（如'钟表铺'而非'门'）；mode=semantic 时可用自然语言短语"
                ),
            ),
            ParamSpec(
                name="mode",
                type="string",
                required=False,
                description=(
                    "检索模式：auto（缺省，关键词+语义双通道合并）/"
                    "keyword（仅项目参考书关键词）/semantic（仅全书库语义相似）"
                ),
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
        mode = str(arguments.get("mode", "auto") or "auto").strip().lower()
        if mode not in ("auto", "keyword", "semantic"):
            mode = "auto"
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

        # S244 语义通道（mode=auto/semantic 且向量索引可用时）：全书库余弦检索
        semantic_lines: list[str] = []
        semantic_failed = False
        semantic_unavailable = vectors is None or embedder is None or not embedder.available
        if mode in ("auto", "semantic") and not semantic_unavailable:
            try:
                qvec = embedder.embed([keyword])[0]
                for h in vectors.search(qvec, top_k=5):
                    book = library_store.get_book(h["book_id"]) if library_store else None
                    name = book["name"] if book else h["book_id"]
                    fname = str(h.get("filename", "")).replace(".md", "")
                    semantic_lines.append(
                        f"——全书库语义命中（相似度 {h['score']:.2f}）"
                        f"《{name}》{fname}——\n{h['text'][:300]}"
                    )
            except Exception as exc:  # embedding 故障降级，不阻断关键词通道
                logger.warning("reference_lookup 语义通道降级: %s", exc)
                semantic_failed = True

        # 关键词通道（mode=semantic 时跳过项目参考书关键词检索）
        res: dict[str, Any] = {"results": []}
        knowledge_sections: list[str] = []
        knowledge_hits = 0
        if mode in ("auto", "keyword"):
            from anyspark.library.search import search_reference_books

            res = search_reference_books(
                library_store, book_id, keyword, project_files=_project_files, max_per_book=max_per
            )
            # 知识层命中（高级参考书=项目）：对每个 project 类型参考书追加图谱/设定条目
            if library_store is not None:
                for ref in library_store.get_references(book_id):
                    if ref.get("type") != "project":
                        continue
                    klines = render_reference_knowledge(
                        graph, settings, str(ref.get("id", "")), keyword
                    )
                    if klines:
                        knowledge_hits += len(klines)
                        knowledge_sections.append(
                            f"——项目「{ref.get('id', '?')}」（知识层：图谱/设定）——\n"
                            + "\n".join(klines)
                        )
        if not res["results"] and not knowledge_sections and not semantic_lines:
            if mode == "semantic" and semantic_unavailable:
                return ToolResult(
                    call=call,
                    ok=False,
                    content="语义检索不可用：未配置 EMBEDDING（可用 DEEPSEEK_* 兑底）；"
                    "可改用 mode=keyword 关键词检索。",
                )
            if mode == "semantic" and semantic_failed:
                return ToolResult(
                    call=call,
                    ok=False,
                    content="语义检索暂不可用（embedding 服务异常），请稍后重试或改用关键词模式。",
                )
            refs = library_store.get_references(book_id) if library_store else []
            names = "、".join(str(r.get("name") or r.get("id") or "?") for r in refs)
            names = names or "（未选参考书）"
            hint = (
                "；也可尝试 mode=semantic 用自然语言描述模糊搜全书库" if mode == "keyword" else ""
            )
            return ToolResult(
                call=call,
                ok=False,
                content=f"参考书「{names}」中未命中「{keyword}」（含图谱/设定层）{hint}。",
            )
        lines = [f"参考书命中「{keyword}」："]
        if semantic_lines:
            lines.append("【语义匹配（全书库）】")
            lines.extend(semantic_lines)
        if res["results"]:
            lines.append("【关键词匹配（项目已选参考书）】")
            for r in res["results"]:
                lines.append(f"——{r['ref_name']}——")
                for h in r.get("hits", []):
                    lines.append(f"({h['count']}次) {h['snippet']}")
        lines.extend(knowledge_sections)
        if knowledge_hits:
            lines.append(f"（含 {knowledge_hits} 条图谱/设定命中）")
        return ToolResult(call=call, ok=True, content="\n\n".join(lines))

    return spec, implementer


def render_reference_knowledge(
    graph: Any, settings: Any, ref_book_id: str, keyword: str, *, limit: int = 6
) -> list[str]:
    """高级参考书（项目）知识层检索：图谱实体卡片 + 设定档条目（只读）。

    模块级公共函数——reference_lookup 工具与工作流 script（query_reference）共用。
    返回人类可读行；无命中返回空列表。图谱实体带当前状态与关系，设定档条目
    带分类——同人文/续写拿原作事实用，不注入、只按需返回。
    """
    lines: list[str] = []
    if graph is not None:
        try:
            ents = graph.list_entities(ref_book_id, q=keyword, limit=limit)
            for e in ents:
                state = (e.state or e.description or "").strip()
                line = f"实体[{e.entity_type}] {e.name}（出场{e.weight}章）" + (
                    f"：{state[:120]}" if state else ""
                )
                # 该实体的关系（从/到命中本实体）
                rels = [
                    r
                    for r in graph.list_relations(ref_book_id, limit=500)
                    if r.from_name == e.name or r.to_name == e.name
                ][:3]
                for r in rels:
                    line += f"\n  ↳ {r.from_name} {r.rel_type} {r.to_name}"
                lines.append(line)
        except Exception:
            pass  # 知识层检索失败不阻断文本检索
    if settings is not None:
        try:
            for s in settings.list(ref_book_id):
                blob = f"{s.name} {s.content} {s.category}"
                if keyword.lower() in blob.lower():
                    # S157：设定查证全量注入（按需精查场景，截断会丢关键设定）
                    lines.append(f"设定[{s.category}] {s.name}：{s.content}")
        except Exception as exc:
            logger.warning("设定档查证失败: %s", exc)
    return lines


def make_batch_implementer(chapters: Any, book_id: str = "main") -> tuple[list[Any], list[Any]]:
    """S102：批量改写/批量审读**提议工具**（agent 自主发起，人工批准后执行）。

    与 workflow 模板的关系：agent 工具只做"提议"——解析章节、返回待确认申请，
    **不执行**（批量改写多章原稿是重操作，执行权在用户确认后由前端工作流模式跑
    「批量改写」「批量审读」预置模板——S140 收编 /api/batch/* 后唯一执行路径，
    带断点/续跑/回滚）。返回结构化待确认信息（匹配到的章节 + 指令），agent 转告
    用户等待批准。
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


def make_citation_export_implementer(library_store: Any) -> tuple[Any, Any]:
    """引用格式导出工具（S250，D2）：书库书 → GB/T 7714 / BibTeX 条目文本。

    文献=书库条目+cite_meta（S250 合并方案）：无元数据的书诚实降级为
    「待补全」条目（题名=书名），不编造作者/年份。
    """
    from anyspark.library.citation import fmt_bibtex, fmt_gbt7714, format_note, minimal_meta

    def implementer(spec: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        # S254：必填参数改 .get+诊断（原 arguments[...] 直取与同层风格离群）
        bid = str(arguments.get("library_book_id", "")).strip()
        if not bid:
            return ToolResult(
                call=ToolCall(name=spec.name, arguments=arguments),
                ok=False,
                content="缺少参数 library_book_id（先用 search_materials/list 找书）。",
            )
        style = str(arguments.get("style") or "gbt7714").lower()
        book = library_store.get_book(bid)
        if book is None:
            return ToolResult(
                call=ToolCall(name=spec.name, arguments=arguments),
                ok=False,
                content=f"书库无此书：{bid}",
            )
        meta = book.get("cite_meta")
        if not meta:
            meta = minimal_meta(book["name"])
        entry = fmt_gbt7714(meta) if style in ("gbt7714", "gb/t 7714", "gb") else fmt_bibtex(meta)
        note = format_note(meta)
        text = entry + (f"\n{note}" if note else "")
        return ToolResult(
            call=ToolCall(name=spec.name, arguments=arguments),
            ok=True,
            content=text,
            data={"style": style, "meta": meta},
        )

    spec = ToolSpec(
        name="citation_export",
        description=(
            "导出书库书的引用条目（GB/T 7714 或 BibTeX 格式）。"
            "参数：library_book_id=书库书 id；style=gbt7714（默认）| bibtex。"
            "写论文/综述时生成参考文献条目。"
        ),
        params=[
            ParamSpec(
                name="library_book_id",
                type="string",
                required=True,
                description="书库书 id（reference_lookup 可查）",
            ),
            ParamSpec(
                name="style",
                type="string",
                required=False,
                description="引用格式：gbt7714（中文论文常用）| bibtex（LaTeX）",
            ),
        ],
    )
    return spec, implementer
