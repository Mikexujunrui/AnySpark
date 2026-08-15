"""
anyspark.server.tools_web — 网络搜索工具（写作 Agent 侧，模型局限弥补"做不到的动作"）。

参考 pi-web-toolkit 搜索实现（思想借鉴）：首选 Exa/Parallel MCP（无密钥公开端点，
带日期/作者元数据），失败降级 360 搜索（so.com）→ Bing（按语言选引擎），
CHROME UA 伪装 + 正则解析。零第三方依赖（urllib 标准库）。
越界保护：只解析 http(s) 结果，单次结果数上限，摘要截断。

S111 对齐 pi-web-toolkit 降级层水平：
- 按语言选引擎（英文 → Bing 优先，中文 → 360 优先），空结果/全低质也降级
- 摘要正则修复：不再吃进容器 `>` 前缀与 g-linkinfo 尾部（消除 `>关注` 前缀垃圾/末尾重复域名）
- 低质结果过滤：360 AI 问答框（ai.so.com）、文库模板（wenku.so.com / baidu wenku）、
  电商导购（ftxia/taobao/tmall/jd/1688）、短视频（douyin）一律剔除
- cleanText 用 html.unescape 全量实体解码（对齐 Pi 手写实体表，Python 标准库更全）

S112 补 MCP 层（观察发现：Exa MCP 无密钥可用，Pi 的 MCP 层并不需要 API key）：
- `_mcp_call` urllib JSON-RPC 调 Exa/Parallel 公开 MCP 端点（实测加 UA 头即可过 Cloudflare）
- Exa 返回人类可读块（Title/URL/Published/Author/Highlights），Parallel 返回 JSON（results[]）
- 默认 auto：exa → parallel → 360/Bing 降级（对齐 Pi）；ANYSPARK_SEARCH_PROVIDER 可覆盖
"""

from __future__ import annotations

import base64
import html as html_mod
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from anyspark.core import ToolCall
from anyspark.core.protocol import ParamSpec, ToolResult, ToolSpec

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
)
MAX_RESULTS = 8
TIMEOUT = 12
MCP_TIMEOUT = 12  # MCP 层超时（实测 Exa 1.9~4s 正常）

# Exa/Parallel MCP 公开端点（无密钥；实测 urllib 加 UA 头即可过 Cloudflare）
EXA_URL = "https://mcp.exa.ai/mcp"
PARALLEL_URL = "https://search.parallel.ai/mcp"

# 低质/噪音域名（考据场景用不到：问答框/文库模板/电商/短视频）
_JUNK_DOMAINS = (
    "ai.so.com",  # 360 AI 问答框（自动作答，非网页结果）
    "wenku.so.com",  # 360 文库（演讲稿/作文模板）
    "wenku.baidu.com",  # 百度文库
    "ftxia.com",  # 电商导购
    "taobao.com",
    "tmall.com",
    "jd.com",
    "1688.com",
    "douyin.com",  # 短视频/音乐
)
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")


@dataclass
class WebResult:
    title: str
    url: str
    snippet: str
    published: str = ""  # MCP 层元数据（Exa/Parallel 返回；360/Bing 无）
    author: str = ""


def _fetch(url: str, headers: dict[str, str]) -> str:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return str(resp.read().decode("utf-8", errors="ignore"))


def _clean(text: str) -> str:
    """去 HTML 标签 + 解实体 + 压缩空白（对齐 pi 的 cleanText；html.unescape 全量解实体）。"""
    text = re.sub(r"<[^>]+>", "", text)
    text = str(html_mod.unescape(text))
    return str(re.sub(r"\s+", " ", text)).strip()


def _detect_language(query: str) -> str:
    """按字符构成判断查询语言：CJK 占比 < 15% 视为英文（对齐 Pi 的 language 参数）。"""
    if not query:
        return "zh"
    cjk = len(_CJK_RE.findall(query))
    return "en" if cjk / max(len(query), 1) < 0.15 else "zh"


def _prefer_engine(query: str, language: str | None = None) -> str:
    """选择优先引擎：显式 language 优先，否则自动检测（英文 → Bing，中文 → 360）。"""
    if language == "en":
        return "bing"
    if language == "zh":
        return "so"
    return "bing" if _detect_language(query) == "en" else "so"


def _is_junk(url: str, title: str) -> bool:
    """低质结果过滤：命中域名黑名单即剔除（标题空已由解析层处理）。"""
    host = urllib.parse.urlparse(url).netloc.lower()
    # 站内重复搜索链接（360 加密跳转的兜底防御）
    if "so.com" in host and "/s?" in url:
        return True
    return any(host == d or host.endswith("." + d) for d in _JUNK_DOMAINS)


_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "about",
    "that",
    "this",
    "what",
    "when",
    "where",
    "which",
    "how",
    "are",
    "was",
    "were",
    "has",
    "had",
    "have",
    "its",
    "their",
    "our",
    "your",
    "will",
    "would",
    "can",
    "could",
    "should",
    "may",
    "might",
    "new",
    "latest",
    "best",
    "top",
}


def _query_terms(query: str) -> set[str]:
    """query 的实词集合（≥3 字母拉丁词，去停用词）。中文查询返回空（不做跑偏判定）。"""
    terms = {w for w in re.findall(r"[A-Za-z]{3,}", query.lower()) if w not in _STOPWORDS}
    return terms


def _results_relevant(query: str, results: list[WebResult]) -> bool:
    """跑偏检测：任一结果标题/URL 与 query 共享 ≥2 个实词 → 该批视为相关。

    cn.bing.com 英文长查询偶发严重跑偏（实测 Krasznahorkai → Reddit 橄榄球、
    quantum → 词典定义），用共享词判定在降级前拦截。中文查询（无实词）不判。
    """
    if not results:
        return False
    terms = _query_terms(query)
    if len(terms) < 2:
        return True  # 无/单个实词无法形成共享判定，不拦
    for r in results:
        blob = (r.title + " " + r.url).lower()
        hits = sum(1 for t in terms if t in blob)
        if hits >= 2:
            return True
    return False


# ---------------------------------------------------------------------------
# 360 搜索（主引擎，中文时效命中好）
# ---------------------------------------------------------------------------
def _so_search(query: str, count: int = MAX_RESULTS) -> list[WebResult]:
    url = "https://www.so.com/s?" + urllib.parse.urlencode({"q": query})
    html_text = _fetch(
        url,
        {
            "User-Agent": CHROME_UA,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    results: list[WebResult] = []
    parts = html_text.split('<li class="res-list')
    for block in parts[1:]:
        if len(results) >= count:
            break
        r = _parse_so_block(block)
        if r:
            results.append(r)
    return results


def _parse_so_block(block: str) -> WebResult | None:
    md = re.search(r'data-mdurl="([^"]+)"', block)
    href = re.search(r'<a[^>]+href="([^"]+)"', block)
    raw_url = (md.group(1) if md else None) or (href.group(1) if href else "")
    url = raw_url.replace("&amp;", "&")
    if not url.startswith(("http://", "https://")):
        return None
    t = re.search(r'<h3[^>]*class="res-title"[^>]*>[\s\S]*?<a[^>]*>([\s\S]*?)</a>', block)
    title = _clean(t.group(1)) if t else ""
    if not title:
        return None
    snippet = ""
    # 摘要容器：吃掉 `>` 前缀 + 截到 </span>（实测 360 摘要后是 </span><p class="g-linkinfo">，
    # 若继续到 </div> 会把 g-linkinfo 的 cite 域名带进摘要 → 末尾重复域名垃圾）
    s = re.search(r'class="res-list-summary">([\s\S]*?)(?:</span>|</div>)', block)
    if s:
        snippet = _clean(s.group(1)).replace("反馈", "").strip()
    return WebResult(title=title, url=url, snippet=snippet)


# ---------------------------------------------------------------------------
# Bing 搜索（兜底/英文）
# ---------------------------------------------------------------------------
def _bing_search(query: str, count: int = MAX_RESULTS, language: str = "en") -> list[WebResult]:
    mkt = "en-US" if language == "en" else "zh-CN"
    params = {
        "q": query,
        "count": str(count),
        "mkt": mkt,
        "setlang": "en" if language == "en" else "zh-Hans",
    }
    url = "https://cn.bing.com/search?" + urllib.parse.urlencode(params)
    html_text = _fetch(
        url,
        {
            "User-Agent": CHROME_UA,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": (
                "en-US,en;q=0.9" if language == "en" else "zh-CN,zh;q=0.9,en;q=0.8"
            ),
        },
    )
    results: list[WebResult] = []
    parts = html_text.split('<li class="b_algo')
    for block in parts[1:]:
        if len(results) >= count:
            break
        r = _parse_bing_block(block)
        if r:
            results.append(r)
    return results


def _normalize_bing_url(raw: str) -> str:
    """Bing 跳转解真实 URL：旧格式 URL 编码 + 新格式 base64。"""
    if "bing.com/ck/a" in raw or "bing.com/rd.aspx" in raw:
        m = re.search(r"[?&]u=([^&]+)", raw)
        if m:
            target = _decode_bing_target(m.group(1))
            if target:
                return target
    return raw


def _decode_bing_target(raw: str) -> str:
    """先试 URL 解码（旧格式），再试 base64（新格式），都失败返回空。"""
    decoded = urllib.parse.unquote(raw)
    if decoded.startswith(("http://", "https://")):
        return decoded
    try:
        padded = raw + "=" * (-len(raw) % 4)
        b = base64.b64decode(padded, validate=False)
        s = b.decode("utf-8", errors="ignore")
        if s.startswith(("http://", "https://")):
            return s
    except Exception:
        pass  # best-effort: 二进制中提取 URL，失败返回空
    return ""


def _parse_bing_block(block: str) -> WebResult | None:
    h2 = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)</a>\s*</h2>', block)
    if not h2:
        return None
    url = _normalize_bing_url(h2.group(1).replace("&amp;", "&"))
    title = _clean(h2.group(2))
    if not title or not url.startswith(("http://", "https://")):
        return None
    snippet = ""
    p = re.search(r"<p[^>]*>([\s\S]*?)</p>", block)
    if p:
        snippet = _clean(p.group(1))
    if not snippet:
        cap = re.search(r'<div class="b_caption"[^>]*>([\s\S]*?)</div>', block)
        if cap:
            snippet = _clean(cap.group(1))
    return WebResult(title=title, url=url, snippet=snippet)


# ---------------------------------------------------------------------------
# MCP 层（Exa/Parallel 公开端点，无密钥；对齐 Pi mcp.ts 的 auto 顺序）
# ---------------------------------------------------------------------------
def _mcp_call(url: str, tool: str, args: dict[str, Any], timeout: int = MCP_TIMEOUT) -> str | None:
    """JSON-RPC 2.0 over HTTP 调 MCP 工具，返回 content[0].text 或 None。

    支持纯 JSON 与 SSE 两种响应（对齐 Pi extractMcpText）。
    实测：urllib 必须带 Chrome UA 头（默认 Python-urllib 被 Cloudflare 403）。
    """
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": args},
        }
    ).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": CHROME_UA,
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
    return _extract_mcp_text(raw)


def _extract_mcp_text(body: str) -> str | None:
    """从纯 JSON 或 SSE 响应中提取 content[0].text（对齐 Pi extractMcpText）。"""
    candidates: list[str] = [body]  # 纯 JSON
    for line in body.split("\n"):
        if line.startswith("data: "):
            candidates.append(line[6:])
    for cand in candidates:
        try:
            data = json.loads(cand)
        except Exception:
            continue
        content = (data or {}).get("result", {}).get("content") or []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text" and c.get("text"):
                return str(c["text"])
    return None


def _parse_exa_text(text: str, count: int) -> list[WebResult]:
    """Exa MCP 返回（人类可读块）：Title/URL/Published/Author/Highlights，`\n---\n` 分隔。"""
    results: list[WebResult] = []
    for block in text.split("\n---\n"):
        if len(results) >= count:
            break
        lines = block.split("\n")
        title = url = published = author = ""
        highlights: list[str] = []
        in_highlights = False
        for ln in lines:
            if in_highlights:
                highlights.append(ln)
            elif ln.startswith("Title: "):
                title = ln[7:].strip()
            elif ln.startswith("URL: "):
                url = ln[5:].strip()
            elif ln.startswith("Published: "):
                published = ln[11:].strip()
            elif ln.startswith("Author: "):
                author = ln[8:].strip()
            elif ln.startswith("Highlights:"):
                in_highlights = True
        url = url.replace("&amp;", "&")
        if not title or not url.startswith(("http://", "https://")):
            continue
        published = "" if published in ("", "N/A") else published
        author = "" if author in ("", "N/A") else author
        snippet = " ".join(x.strip() for x in highlights if x.strip())[:400]
        if not snippet:
            snippet = title
        results.append(
            WebResult(title=title, url=url, snippet=snippet, published=published, author=author)
        )
    return results


def _parse_parallel_text(text: str, count: int) -> list[WebResult]:
    """Parallel MCP 返回（JSON 字符串）：{"results": [{url,title,publish_date,excerpts[]}]}。"""
    try:
        data = json.loads(text)
    except Exception:
        return []
    results: list[WebResult] = []
    for item in (data or {}).get("results") or []:
        if len(results) >= count:
            break
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not title or not url.startswith(("http://", "https://")):
            continue
        excerpts = item.get("excerpts") or []
        snippet = " ".join(str(x).strip() for x in excerpts if str(x).strip())[:400]
        published = str(item.get("publish_date") or "").strip()
        results.append(
            WebResult(title=title, url=url, snippet=snippet or title, published=published)
        )
    return results


def _exa_search(query: str, count: int = MAX_RESULTS) -> list[WebResult]:
    """Exa MCP 搜索（对齐 Pi exaSearch 参数：livecrawl fallback + contextMaxCharacters）。"""
    text = _mcp_call(
        EXA_URL,
        "web_search_exa",
        {
            "query": query,
            "type": "auto",
            "numResults": count,
            "livecrawl": "fallback",
            "contextMaxCharacters": 8000,
        },
    )
    return _parse_exa_text(text, count) if text else []


def _parallel_search(query: str, count: int = MAX_RESULTS) -> list[WebResult]:
    """Parallel MCP 搜索（对齐 Pi parallelSearch：objective + search_queries）。"""
    text = _mcp_call(PARALLEL_URL, "web_search", {"objective": query, "search_queries": [query]})
    return _parse_parallel_text(text, count) if text else []


def _mcp_provider_order(provider: str | None) -> list[str]:
    """provider 解析：auto 默认 exa → parallel；ANYSPARK_SEARCH_PROVIDER 环境变量可覆盖。"""
    env = (os.environ.get("ANYSPARK_SEARCH_PROVIDER") or "").strip().lower()
    p = (provider or env or "auto").lower()
    if p == "exa":
        return ["exa"]
    if p == "parallel":
        return ["parallel"]
    if p == "web":
        return []
    return ["exa", "parallel"]


# ---------------------------------------------------------------------------
# 统一入口（MCP 优先 → 360/Bing 降级，空/全低质/失败自动降级）
# ---------------------------------------------------------------------------
def search_web(
    query: str,
    count: int = MAX_RESULTS,
    language: str | None = None,
    provider: str | None = None,
) -> list[WebResult]:
    """搜索并返回结果列表。

    - provider: 'auto'（默认，exa→parallel→web）/ 'exa' / 'parallel' / 'web'（跳过 MCP）
    - language: 'zh'/'en' 显式指定；None 时按查询字符构成自动检测（对齐 Pi）
    - MCP 层失败/无结果 → 降级 360/Bing；双引擎均失败 → 返回空（不抛异常）
    """
    count = max(1, min(MAX_RESULTS, count))
    # MCP 层（带日期/作者元数据，质量高于抓取降级层）
    for p in _mcp_provider_order(provider):
        try:
            results = _exa_search(query, count) if p == "exa" else _parallel_search(query, count)
            results = [r for r in results if not _is_junk(r.url, r.title)]
            if results:
                return results
        except Exception:
            continue
    # 抓取降级层（360/Bing，按语言选引擎 + 跑偏拦截）
    preferred = _prefer_engine(query, language)
    fallback = "bing" if preferred == "so" else "so"
    for engine in (preferred, fallback):
        try:
            if engine == "so":
                results = _so_search(query, count)
            else:
                lang = language or _detect_language(query)
                results = _bing_search(query, count, language=lang)
            results = [r for r in results if not _is_junk(r.url, r.title)]
            # 跑偏拦截：结果与 query 无共享词（cn.bing 英文长查询偶发）→ 降级另一引擎
            if results and _results_relevant(query, results):
                return results
        except Exception:
            continue
    return []


def render_results(results: list[WebResult], query: str) -> str:
    """渲染成工具回填文本（截断防超长）。"""
    if not results:
        return f"搜索「{query}」无结果（引擎均失败或命中为空）。"
    lines = [f"网络搜索结果（{query}）："]
    for i, r in enumerate(results, 1):
        snippet = f" —— {r.snippet[:120]}" if r.snippet else ""
        meta = ""
        if r.published:
            meta += f"（发布于 {r.published[:10]}）"
        if r.author:
            meta += f" 作者：{r.author[:20]}"
        lines.append(f"{i}. {r.title}{meta}\n   {r.url}{snippet}")
    return "\n".join(lines)


# ToolSpec 实现（注册进写作 Agent）
def make_search_implementer() -> Any:
    """返回 (ToolSpec, implementer)。"""

    spec = ToolSpec(
        name="search_web",
        description=(
            "搜索网络获取最新/参考资料（首选 Exa/Parallel MCP 带日期作者，"
            "降级 360/Bing 按语言选引擎）。"
            "用于写实细节考据、设定查证、真实地名/历史/科技等外部知识。"
            "返回标题/链接/摘要；需要完整正文时再用 fetch_page 抓取。"
        ),
        params=[
            ParamSpec(name="query", type="string", required=True, description="搜索关键词"),
            ParamSpec(
                name="language",
                type="string",
                required=False,
                description="zh/en（可选；缺省按查询自动检测）",
            ),
            ParamSpec(
                name="provider",
                type="string",
                required=False,
                description=(
                    "auto/exa/parallel/web（可选；缺省 auto，环境变量 "
                    "ANYSPARK_SEARCH_PROVIDER 可覆盖）"
                ),
            ),
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        query = str(arguments.get("query", "")).strip()
        if not query or len(query) > 200:
            return ToolResult(call=call, ok=False, content="缺少有效的 query 参数。")
        language = str(arguments.get("language") or "").strip() or None
        if language not in (None, "zh", "en"):
            language = None
        provider = str(arguments.get("provider") or "").strip() or None
        if provider not in (None, "auto", "exa", "parallel", "web"):
            provider = None
        results = search_web(query, language=language, provider=provider)
        return ToolResult(call=call, ok=True, content=render_results(results, query))

    return spec, implementer
