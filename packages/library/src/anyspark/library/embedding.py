"""
anyspark.library.embedding — 文本向量化客户端（S244，书库语义检索用）。

OpenAI 兼容 /embeddings 端点（DashScope/硅基流动/OpenAI/本地 tei 均兼容）。
httpx2 直连（trust_env=False，同 models/ 适配器约定——防环境代理劫持本地端点）。

配置约定（app.py 装配时从环境解析，均带兜底）：
- EMBEDDING_BASE_URL  ← DEEPSEEK_BASE_URL（阿里云兼容端点同时服务 embeddings）
- EMBEDDING_API_KEY   ← DEEPSEEK_API_KEY
- EMBEDDING_MODEL     ← 默认 text-embedding-v3（DashScope OpenAI 兼容，1024 维）

未配置 key 时客户端不可用（available=False），检索降级为纯关键词——
书库 RAG 是增强层，不阻塞任何既有功能。
"""

from __future__ import annotations

import os
from typing import Any

import httpx2 as httpx

# DashScope text-embedding-v3 单次批量上限 10 条（官方限制；其他端点兼容）
BATCH_SIZE = 10
DEFAULT_MODEL = "text-embedding-v3"
TIMEOUT = 30.0


def resolve_embedding_config() -> dict[str, str | None]:
    """从环境解析 embedding 配置（EMBEDDING_* 优先，DEEPSEEK_* 兜底）。"""
    return {
        "base_url": (
            os.getenv("EMBEDDING_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL") or ""
        ).rstrip()
        or None,
        "api_key": os.getenv("EMBEDDING_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or None,
        "model": os.getenv("EMBEDDING_MODEL") or DEFAULT_MODEL,
    }


class EmbeddingClient:
    """文本 → 向量。批量的（batch≤10）、不可用时 available=False。"""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        cfg = resolve_embedding_config()
        self._base_url = (base_url or cfg["base_url"] or "").rstrip("/")
        self._api_key = api_key or cfg["api_key"] or ""
        self._model = model or cfg["model"] or DEFAULT_MODEL
        self._client = httpx.Client(
            trust_env=False,
            timeout=httpx.Timeout(connect=10.0, read=None, write=30.0, pool=10.0),
        )

    @property
    def available(self) -> bool:
        """未配置端点/key 时不可用（调用方降级关键词检索）。"""
        return bool(self._base_url and self._api_key)

    @property
    def model(self) -> str:
        return self._model

    def embed(self, texts: list[str], dim_hint: int | None = None) -> list[list[float]]:
        """批量向量化（自动分批）。返回与输入等长的向量列表。

        dim_hint：DashScope text-embedding-v3 支持 dimensions 参数（默认 1024）。
        非兼容端点忽略该参数——错误时报 RuntimeError 带响应详情。
        """
        if not self.available:
            raise RuntimeError("Embedding 未配置（EMBEDDING_BASE_URL/EMBEDDING_API_KEY）")
        out: list[list[float]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            body: dict[str, Any] = {"model": self._model, "input": batch}
            if dim_hint:
                body["dimensions"] = dim_hint
            resp = self._client.post(
                f"{self._base_url}/embeddings",
                json=body,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Embedding API {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            items = sorted(data.get("data", []), key=lambda d: d.get("index", 0))
            if len(items) != len(batch):
                raise RuntimeError(f"Embedding 返回数不符：要 {len(batch)} 得 {len(items)}")
            out.extend(item["embedding"] for item in items)
        return out
