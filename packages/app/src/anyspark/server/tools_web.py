"""
anyspark.server.tools_web — 网络搜索工具（写作 Agent 侧，模型局限弥补"做不到的动作"）。

参考 pi-web-toolkit 搜索实现（思想借鉴）：360 搜索（so.com）主引擎 + Bing 兜底，
CHROME UA 伪装 + 正则解析，失败自动降级。零第三方依赖（urllib 标准库）。
越界保护：只解析 http(s) 结果，单次结果数上限，摘要截断。
"""

from __future__ import annotations

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
    """去 HTML 标签 + 解实体 + 压缩空白（对齐 pi 的 cleanText）。"""
    text = re.sub(r"<[^>]+>", "", text)
    text = str(html_mod.unescape(text))
    return str(re.sub(r"\s+", " ", text)).strip()


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
    s = re.search(r'class="res-list-summary"([\s\S]*?)</div>', block)
    if s:
        snippet = _clean(s.group(1)).replace("反馈", "").strip()
    return WebResult(title=title, url=url, snippet=snippet)


# ---------------------------------------------------------------------------
# Bing 搜索（兜底/英文）
# ---------------------------------------------------------------------------
def _bing_search(query: str, count: int = MAX_RESULTS) -> list[WebResult]:
    params = {"q": query, "count": str(count), "mkt": "zh-CN", "setlang": "zh-Hans"}
    url = "https://cn.bing.com/search?" + urllib.parse.urlencode(params)
    html_text = _fetch(
        url,
        {
            "User-Agent": CHROME_UA,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
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
    if "bing.com/ck/a" in raw or "bing.com/rd.aspx" in raw:
        m = re.search(r"[?&]u=([^&]+)", raw)
        if m:
            target = urllib.parse.unquote(m.group(1))
            if target.startswith(("http://", "https://")):
                return target
    return raw


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
# 统一入口（主 360 → 兜底 Bing，失败自动降级）
# ---------------------------------------------------------------------------
def search_web(query: str, count: int = MAX_RESULTS) -> list[WebResult]:
    """搜索并返回结果列表；360 失败自动降级 Bing。"""
    count = max(1, min(MAX_RESULTS, count))
    try:
        results = _so_search(query, count)
        if results:
            return results
    except Exception:
        pass
    try:
        return _bing_search(query, count)
    except Exception:
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
            "搜索网络获取最新/参考资料（360 主引擎 + Bing 兜底）。"
            "用于写实细节考据、设定查证、真实地名/历史/科技等外部知识。"
        ),
        params=[ParamSpec(name="query", type="string", required=True, description="搜索关键词")],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        query = str(arguments.get("query", "")).strip()
        if not query or len(query) > 200:
            return ToolResult(call=call, ok=False, content="缺少有效的 query 参数。")
        results = search_web(query)
        return ToolResult(call=call, ok=True, content=render_results(results, query))

    return spec, implementer
