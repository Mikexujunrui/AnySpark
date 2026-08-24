"""
compare.baseline — 裸 LLM 基线客户端（同模型、零系统）。

黑盒独立性：直接用 httpx 调 OpenAI 兼容端点（DashScope），
不 import 任何 anyspark 模块；API key 从主项目 .env 读取（仅读文件，不 import）。
这是对比层的"零系统"对照——同一模型、同一任务、没有任何 AnySpark 能力。
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx2 as httpx  # S66: httpx2（下一代，API 兼容）

ROOT = Path(__file__).resolve().parent.parent.parent


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


class BareLLM:
    """裸 DeepSeek 调用（无 Agent 循环、无图谱、无对齐、无任何系统）。"""

    def __init__(
        self,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        timeout: float = 180.0,
    ) -> None:
        _load_env(ROOT / ".env")
        self.base_url = os.getenv(
            "DEEPSEEK_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("缺少 DEEPSEEK_API_KEY（compare 层需要读主项目 .env）")
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = httpx.Client(timeout=timeout, trust_env=False)

    def chat(self, system: str, user: str) -> str:
        """单轮对话返回文本（裸 LLM 的长程任务通过反复调用实现）。"""
        resp = self._client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": self._temperature,
                "max_tokens": self._max_tokens,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return str(data["choices"][0]["message"]["content"])

    def tokens_of(self, text: str) -> int:
        """近似 token 数（中英混合启发式：中文≈1字1token，英文≈4字符1token）。"""
        cn = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        other = len(text) - cn
        return cn + other // 4
