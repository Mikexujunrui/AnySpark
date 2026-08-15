"""
anyspark.server.tools_fetch — 网页正文抓取工具（搜索闭环：search_web 拿线索 → fetch_page 读全文）。

参考 pi-web-toolkit webfetch（思想借鉴）：UA 伪装 + 5MB 上限 + 超时 + HTML → 文本。
零第三方依赖（urllib 标准库）。越界保护：只允许 http(s)、正文截断上限。
"""

from __future__ import annotations

import html as html_mod
import re
import urllib.request
from dataclasses import dataclass
from typing import Any

from anyspark.core import ToolCall
from anyspark.core.protocol import ParamSpec, ToolResult, ToolSpec

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
)
MAX_BYTES = 5 * 1024 * 1024  # 5MB（对齐 pi webfetch）
TIMEOUT = 20
MAX_CHARS = 20000  # 正文截断上限（防超长回填）

# 网页噪音标签：抓取正文时整块剔除
_NOISE_TAGS = ("script", "style", "noscript", "nav", "footer", "aside", "iframe")


@dataclass
class FetchResult:
    title: str
    text: str
    truncated: bool


def _strip_noise(html_text: str) -> str:
    """剔除噪音标签对 + 注释（在去标签前做，避免噪音内容混入正文）。"""
    out = re.sub(r"<!--[\s\S]*?-->", " ", html_text)
    for tag in _NOISE_TAGS:
        out = re.sub(rf"<\s*{tag}[\s\S]*?<\s*/\s*{tag}\s*>", " ", out, flags=re.IGNORECASE)
    return out


def _extract_title(html_text: str) -> str:
    m = re.search(r"<\s*title[^>]*>([\s\S]*?)<\s*/\s*title\s*>", html_text, re.IGNORECASE)
    if not m:
        return ""
    text = re.sub(r"<[^>]+>", "", m.group(1))
    return str(html_mod.unescape(text)).strip()


def html_to_text(html_text: str, max_chars: int = MAX_CHARS) -> tuple[str, str, bool]:
    """HTML → (title, 正文文本, 是否截断)。供测试直调；fetch_page 走网络。"""
    cleaned = _strip_noise(html_text)
    title = _extract_title(cleaned)
    # 去掉 head 整体（title 已提取）
    cleaned = re.sub(r"<\s*head[\s\S]*?<\s*/\s*head\s*>", " ", cleaned, flags=re.IGNORECASE)
    # 块级标签转空格（避免"字字相连"），再统一去标签
    cleaned = re.sub(
        r"<\s*(?:p|div|br|li|h[1-6]|tr|td|th|section|article|blockquote)[^>]*>",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"<[^>]+>", "", cleaned)
    text = str(html_mod.unescape(text))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    text = text.strip()
    truncated = len(text) > max_chars
    return title, text[:max_chars], truncated


def fetch_page(url: str, max_chars: int = 8000) -> FetchResult:
    """抓取网页并提取正文文本。失败抛异常（由 implementer 转 ToolResult 失败）。"""
    if not url.startswith(("http://", "https://")):
        raise ValueError("URL 必须以 http:// 或 https:// 开头")
    max_chars = max(500, min(MAX_CHARS, max_chars))
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": CHROME_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        # 5MB 上限：多读 1 字节判断是否超限截断
        raw = resp.read(MAX_BYTES + 1)
    truncated_bytes = len(raw) > MAX_BYTES
    raw = raw[:MAX_BYTES]
    html_text = raw.decode("utf-8", errors="ignore")
    title, text, truncated_chars = html_to_text(html_text, max_chars)
    return FetchResult(title=title, text=text, truncated=truncated_bytes or truncated_chars)


# ToolSpec 实现（与 search_web 同开关注册进写作 Agent）
def make_fetch_implementer() -> Any:
    """返回 (ToolSpec, implementer)。"""

    spec = ToolSpec(
        name="fetch_page",
        description=(
            "抓取网页正文并转为纯文本（配合 search_web 使用：搜索结果只给摘要，"
            "需要完整内容时用本工具读全文）。适用于考据细节、资料通读。"
        ),
        params=[
            ParamSpec(name="url", type="string", required=True, description="http(s) 网页地址"),
            ParamSpec(
                name="max_chars",
                type="integer",
                required=False,
                description="正文截断字符数（默认 8000，上限 20000）",
            ),
        ],
    )

    def implementer(spec_: ToolSpec, arguments: dict[str, Any]) -> ToolResult:
        call = ToolCall(name=spec_.name, arguments=arguments)
        url = str(arguments.get("url", "")).strip()
        if not url:
            return ToolResult(call=call, ok=False, content="缺少有效的 url 参数。")
        try:
            max_chars = int(arguments.get("max_chars") or 8000)
        except (TypeError, ValueError):
            max_chars = 8000
        try:
            result = fetch_page(url, max_chars=max_chars)
        except Exception as exc:  # 网络/超时/解析失败：明确告知而非静默
            return ToolResult(call=call, ok=False, content=f"抓取失败：{type(exc).__name__}: {exc}")
        lines = [f"网页正文（{result.title or url}）："]
        if result.truncated:
            lines.append(f"（内容过长已截断，前 {max_chars} 字符）")
        lines.append(result.text or "（无正文文本）")
        return ToolResult(call=call, ok=True, content="\n".join(lines))

    return spec, implementer
