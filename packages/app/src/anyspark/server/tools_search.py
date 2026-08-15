"""
anyspark.server.tools_search — 正文检索/锚点阅读工具（从 tools_domain.py 拆出，S188 技术债清理）。

工厂函数创建 agent 工具（ToolSpec + implementer 对），接收 store 参数，
不引用闭包——从 tools_domain.py 提取无行为变化。
"""

from __future__ import annotations

import re
from typing import Any

from anyspark.core import ToolCall
from anyspark.core.protocol import ParamSpec, ToolResult, ToolSpec


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
                                if exclude is not None and _sent_has(c.content, m.start(), exclude):
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
                                if exclude is not None and _sent_has(c.content, idx, exclude):
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


def _sentence_at(content: str, idx: int) -> str:
    """返回 content 中包含位置 idx 的分句（按 。！？；， 换行 切分）。"""
    import re as _re

    pos = 0
    for s in _re.split(r"(?<=[。！？；，\n])", content):
        if pos <= idx < pos + len(s):
            return s
        pos += len(s)
    return content


def _sent_has(content: str, idx: int, exclude: str) -> bool:
    """句级排除：命中所在句子含 exclude 则 True（防短句互相污染/否定语境）。"""
    sent = _sentence_at(content, idx)
    return exclude in sent
