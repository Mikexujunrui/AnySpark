"""Discover models exposed by OpenAI-compatible API providers."""

from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx

PROVIDER_DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
}


class ModelDiscoveryError(RuntimeError):
    """A user-facing model discovery failure."""


def provider_base_url(provider_type: str, base_url: str = "") -> str:
    """Return a normalized provider URL, filling official defaults when empty."""
    value = (base_url or PROVIDER_DEFAULT_BASE_URLS.get(provider_type, "")).strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ModelDiscoveryError("Base URL 格式不正确，请填写完整的 http(s) 地址")
    return value


def _candidate_model_urls(provider_type: str, base_url: str) -> list[str]:
    base = provider_base_url(provider_type, base_url)
    if base.endswith("/models"):
        return [base]

    candidates = [f"{base}/models"]
    path = urlparse(base).path.rstrip("/")
    # Many gateways ask users to enter the service root while exposing the
    # OpenAI-compatible API below /v1.
    if provider_type == "openai" and not path.endswith("/v1"):
        candidates.append(f"{base}/v1/models")
    return list(dict.fromkeys(candidates))


def _extract_model_ids(payload: object) -> list[str]:
    if isinstance(payload, dict):
        items = payload.get("data")
        if not isinstance(items, list):
            items = payload.get("models")
    elif isinstance(payload, list):
        items = payload
    else:
        items = None

    if not isinstance(items, list):
        return []

    result = []
    for item in items:
        if isinstance(item, str):
            model_id = item
        elif isinstance(item, dict):
            model_id = item.get("id") or item.get("name") or ""
        else:
            model_id = ""
        if isinstance(model_id, str):
            model_id = model_id.strip()
            if model_id.startswith("models/"):
                model_id = model_id.removeprefix("models/")
            if model_id:
                result.append(model_id)
    return sorted(set(result), key=str.casefold)


def discover_models(
    provider_type: str,
    api_key: str,
    base_url: str = "",
    *,
    transport: httpx.BaseTransport | None = None,
) -> tuple[list[str], str]:
    """Fetch model IDs and return ``(models, successful_endpoint)``.

    The provider clients used by AnySpark all speak the OpenAI compatibility
    surface. Anthropic additionally accepts its native authentication headers,
    so both header forms are sent for compatibility.
    """
    key = api_key.strip()
    if not key:
        raise ModelDiscoveryError("请先填写 API Key")

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {key}",
    }
    if provider_type == "anthropic":
        headers["x-api-key"] = key
        headers["anthropic-version"] = "2023-06-01"

    proxy_url = os.getenv("LLM_PROXY", "").strip()
    client_kwargs: dict = {
        "timeout": httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=10.0),
        "follow_redirects": True,
        "transport": transport,
    }
    if proxy_url and transport is None:
        client_kwargs["proxy"] = proxy_url
    elif transport is None:
        client_kwargs["trust_env"] = False

    last_error = ""
    with httpx.Client(**client_kwargs) as client:
        for endpoint in _candidate_model_urls(provider_type, base_url):
            try:
                response = client.get(endpoint, headers=headers)
            except httpx.HTTPError as exc:
                last_error = f"无法连接模型接口：{exc}"
                continue

            if response.status_code in {404, 405}:
                last_error = f"模型接口不存在（HTTP {response.status_code}）"
                continue
            if response.is_error:
                detail = ""
                try:
                    error_payload = response.json()
                    if isinstance(error_payload, dict):
                        error_value = error_payload.get("error") or error_payload.get("message")
                        if isinstance(error_value, dict):
                            detail = str(error_value.get("message") or "")
                        elif error_value:
                            detail = str(error_value)
                except ValueError:
                    detail = response.text[:160]
                suffix = f"：{detail[:160]}" if detail else ""
                raise ModelDiscoveryError(f"拉取模型失败（HTTP {response.status_code}）{suffix}")

            try:
                models = _extract_model_ids(response.json())
            except ValueError as exc:
                raise ModelDiscoveryError("模型接口返回的不是有效 JSON") from exc
            if not models:
                raise ModelDiscoveryError("接口连接成功，但没有返回可用的模型名称")
            return models, endpoint

    raise ModelDiscoveryError(last_error or "无法找到模型列表接口，请检查 Base URL")
