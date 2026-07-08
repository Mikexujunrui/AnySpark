"""Web Search — MCP JSON-RPC client for Exa/Parallel + URL content fetching.

Web search via MCP JSON-RPC 2.0 protocol:
- Dual backend: Exa (mcp.exa.ai) + Parallel (search.parallel.ai)
- Session-based A/B provider selection
- MCP JSON-RPC 2.0 over HTTP
- URL content fetching with HTML text extraction
"""

import hashlib
import json
import logging
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from .config import config

logger = logging.getLogger(__name__)

EXA_BASE = "https://mcp.exa.ai/mcp"
PARALLEL_BASE = "https://search.parallel.ai/mcp"

MAX_RESPONSE_BYTES = 256 * 1024
MAX_FETCH_BYTES = 5 * 1024 * 1024
DEFAULT_TIMEOUT = 25
DEFAULT_FETCH_TIMEOUT = 30

SKIP_TAGS = {"script", "style", "noscript", "iframe", "object", "embed", "svg"}


def _exa_url() -> str:
    key = config.web_search.exa_api_key
    if key:
        return f"{EXA_BASE}?exaApiKey={key}"
    return EXA_BASE


def _parallel_url() -> str:
    return PARALLEL_BASE


def select_provider(book_id: str) -> str:
    override = config.web_search.provider
    if override in ("exa", "parallel"):
        return override
    h = int(hashlib.md5(book_id.encode()).hexdigest(), 16)
    return "exa" if h % 2 == 0 else "parallel"


def _parse_mcp_response(body: str) -> str | None:
    try:
        data = json.loads(body)
        content = data.get("result", {}).get("content", [])
        for item in content:
            if item.get("type") == "text" and item.get("text"):
                return item["text"]
        return None
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data: "):
            payload = line[6:]
            try:
                data = json.loads(payload)
                content = data.get("result", {}).get("content", [])
                for item in content:
                    if item.get("type") == "text" and item.get("text"):
                        return item["text"]
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

    return None


def _build_exa_request(query: str, num_results: int = 8) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "web_search_exa",
            "arguments": {
                "query": query,
                "type": "auto",
                "numResults": min(num_results, 20),
                "livecrawl": "fallback",
                "contextMaxCharacters": 10000,
            },
        },
    }


def _build_parallel_request(query: str, book_id: str = "") -> dict:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "web_search",
            "arguments": {
                "objective": query,
                "search_queries": [query],
                "model_name": "novel-writing-assistant",
            },
        },
    }


def web_search_sync(query: str, book_id: str = "", num_results: int = 8) -> str:
    provider = select_provider(book_id)
    timeout = config.web_search.timeout

    if provider == "parallel":
        url = _parallel_url()
        payload = _build_parallel_request(query, book_id)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        api_key = config.web_search.parallel_api_key
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
    else:
        url = _exa_url()
        payload = _build_exa_request(query, num_results)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()

            body = resp.text
            if len(body) > MAX_RESPONSE_BYTES:
                return f"搜索结果过大（{len(body)} 字节），已丢弃。请缩小搜索范围。"

            result = _parse_mcp_response(body)
            if result:
                return result
            return "未找到搜索结果。请尝试更换关键词。"

    except httpx.TimeoutException:
        return f"搜索超时（>{timeout}s）。请重试或缩短查询。"
    except httpx.HTTPStatusError as e:
        return f"搜索请求失败: HTTP {e.response.status_code}"
    except Exception as e:
        return f"搜索出错: {str(e)[:100]}"


def web_fetch_sync(url: str, fmt: str = "text", timeout: int = 0) -> str:
    if not timeout:
        timeout = DEFAULT_FETCH_TIMEOUT
    timeout = min(timeout, 120)

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"仅支持 http/https URL，收到: {parsed.scheme}"

    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=5),
        ) as client:
            resp = client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; novel-assistant/1.0)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            })
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")

            if "image/" in content_type and "svg" not in content_type:
                return "该 URL 指向图片文件，无法提取文本。"

            body = resp.text
            if len(resp.content) > MAX_FETCH_BYTES:
                return f"页面过大（{len(resp.content)} 字节），超过 5MB 限制。"

            if "text/html" in content_type or "<html" in body[:500].lower():
                if _is_cloudflare_challenge(body):
                    resp2 = client.get(url, headers={
                        "User-Agent": "novel-agent/1.0",
                        "Accept": "text/html,*/*",
                    })
                    if resp2.status_code == 200 and not _is_cloudflare_challenge(resp2.text):
                        body = resp2.text

                if fmt == "text":
                    return _html_to_text(body)
                else:
                    return _html_to_text(body)

            return body

    except httpx.TimeoutException:
        return f"抓取超时（>{timeout}s）。请重试。"
    except httpx.HTTPStatusError as e:
        return f"HTTP {e.response.status_code}: 无法访问 {url}"
    except Exception as e:
        return f"抓取出错: {str(e)[:100]}"


def _is_cloudflare_challenge(body: str) -> bool:
    markers = ["cf-browser-verification", "challenge-platform", "Just a moment"]
    return any(m in body[:2000] for m in markers)


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._pieces: list[str] = []
        self._skip_depth = 0
        self._skip_tag = ""

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip_depth += 1
            self._skip_tag = tag
        if tag in ("br", "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"):
            self._pieces.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "blockquote"):
            self._pieces.append("\n")

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._pieces.append(data)

    def get_text(self) -> str:
        text = "".join(self._pieces)
        lines = [line.strip() for line in text.splitlines()]
        lines = [line for line in lines if line]
        return "\n".join(lines)


def _html_to_text(html: str) -> str:
    extractor = _TextExtractor()
    try:
        extractor.feed(html)
    except (ValueError, UnicodeDecodeError):
        pass
    return extractor.get_text()


def web_search_enabled() -> bool:
    return config.web_search.enabled
