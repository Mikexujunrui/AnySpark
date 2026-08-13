"""
anyspark.server.tools_web — 网络搜索工具（写作 Agent 侧，模型局限弥补"做不到的动作"）。

参考 pi-web-toolkit 搜索实现（思想借鉴）：360 搜索（so.com）主引擎 + Bing 兜底，
CHROME UA 伪装 + 正则解析，失败自动降级。零第三方依赖（urllib 标准库）。
越界保护：只解析 http(s) 结果，单次结果数上限，摘要截断。

S111 对齐 pi-web-toolkit 降级层水平：
- 按语言选引擎（英文 → Bing 优先，中文 → 360 优先），空结果/全低质也降级
- 摘要正则修复：不再吃进容器 `>` 前缀与 g-linkinfo 尾部（消除 `>关注` 前缀垃圾/末尾重复域名）
- 低质结果过滤：360 AI 问答框（ai.so.com）、文库模板（wenku.so.com / baidu wenku）、
  电商导购（ftxia/taobao/tmall/jd/1688）、短视频（douyin）一律剔除
- cleanText 用 html.unescape 全量实体解码（对齐 Pi 手写实体表，Python 标准库更全）
"""

from __future__ import annotations

import base64
import html as html_mod
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
        pass
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
# 统一入口（按语言选引擎，空/全低质/失败自动降级另一引擎）
# ---------------------------------------------------------------------------
def search_web(
    query: str, count: int = MAX_RESULTS, language: str | None = None
) -> list[WebResult]:
    """搜索并返回结果列表。

    - language: 'zh'/'en' 显式指定；None 时按查询字符构成自动检测（对齐 Pi）
    - 优先引擎失败/无结果/结果全为低质 → 自动降级另一引擎
    - 双引擎均失败 → 返回空列表（不抛异常，设计上失败不挂）
    """
    count = max(1, min(MAX_RESULTS, count))
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
        lines.append(f"{i}. {r.title}\n   {r.url}{snippet}")
    return "\n".join(lines)


# ToolSpec 实现（注册进写作 Agent）
def make_search_implementer() -> Any:
    """返回 (ToolSpec, implementer)。"""

    spec = ToolSpec(
        name="search_web",
        description=(
            "搜索网络获取最新/参考资料（360 主引擎 + Bing 兜底，按查询语言自动选引擎）。"
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
        results = search_web(query, language=language)
        return ToolResult(call=call, ok=True, content=render_results(results, query))

    return spec, implementer
