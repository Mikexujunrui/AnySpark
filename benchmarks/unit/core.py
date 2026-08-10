"""
benchmarks.unit.core — 单元层公共设施。

黑盒原则：只通过 HTTP API 与 AnySpark 交互，不 import 任何 anyspark.* 内部模块。
半独立：本目录可单独拷走运行（需后端可达）；产物只写 report/（不入库）。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import httpx2 as httpx  # S66: httpx2（下一代，API 兼容）

GOLD_DIR = Path(__file__).parent / "gold"
REPORT_DIR = Path(__file__).resolve().parent.parent / "report"


# ---------------------------------------------------------------------------
# 文本归一化与实体匹配（容忍 OCR 变体/标点/空格差异）
# ---------------------------------------------------------------------------
def normalize(text: str) -> str:
    """去空白/标点/全半角，统一为紧凑串（匹配用）。"""
    text = re.sub(r"[\s·•．。，、；：！？!?\"'“”‘’\-—_/\\]+", "", text)
    return text.lower()


def entity_hit(gold: dict[str, Any], extracted_name: str) -> bool:
    """gold 实体（name/aliases/variants 任一）与抽取实体名双向包含即命中。

    双向包含：容忍抽取名带上下文（"哈利·波特先生"）或 OCR 变体（"德思丰L"）。
    """
    needle = normalize(extracted_name)
    if not needle:
        return False
    candidates = [gold.get("name", ""), *gold.get("aliases", []), *gold.get("variants", [])]
    for c in candidates:
        cn = normalize(c)
        if not cn:
            continue
        if needle == cn or needle in cn or cn in needle:
            return True
    return False


def similarity(a: str, b: str) -> float:
    """字符级相似度（difflib），用于能动性档位测试（0 档=高相似=只听写）。"""
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# 指标算式
# ---------------------------------------------------------------------------
def precision_recall_f1(n_true_pos: int, n_pred: int, n_gold: int) -> dict[str, float | int]:
    precision = n_true_pos / n_pred if n_pred else 0.0
    recall = n_true_pos / n_gold if n_gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)}


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------
@dataclass
class TaskResult:
    task_id: str
    name: str
    passed: bool
    metrics: dict[str, Any] = field(default_factory=dict)
    detail: str = ""

    def to_row(self) -> str:
        nums = " ".join(f"{k}={v}" for k, v in self.metrics.items())
        return f"{'PASS' if self.passed else 'FAIL'}  {self.task_id} {self.name}  {nums}"


class Reporter:
    def __init__(self) -> None:
        self.results: list[TaskResult] = []

    def record(
        self,
        task_id: str,
        name: str,
        passed: bool,
        metrics: dict[str, Any] | None = None,
        detail: str = "",
    ) -> None:
        self.results.append(TaskResult(task_id, name, passed, metrics or {}, detail))

    def write(self, layer: str, env: dict[str, str] | None = None) -> Path:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S")
        path = REPORT_DIR / f"{layer}-{ts}.md"
        lines = [
            f"# AnySpark benchmark · {layer} 层",
            "",
            f"时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        if env:
            lines += ["", "环境：" + " | ".join(f"{k}={v}" for k, v in env.items())]
        lines += ["", "| 结果 | 任务 | 指标 |", "|---|---|---|"]
        for r in self.results:
            lines.append(
                f"| {'✅' if r.passed else '❌'} | {r.task_id} {r.name} | {r.metrics or '—'} |"
            )
        n_pass = sum(1 for r in self.results if r.passed)
        lines += ["", f"**合计：{n_pass}/{len(self.results)} 通过**"]
        for r in self.results:
            if not r.passed and r.detail:
                lines += ["", f"### {r.task_id} 失败详情", "", "```", r.detail[:2000], "```"]
        path.write_text("\n".join(lines), encoding="utf-8")
        return path


# ---------------------------------------------------------------------------
# API 客户端（黑盒：只走 HTTP）
# ---------------------------------------------------------------------------
class ApiClient:
    def __init__(self, base: str = "http://127.0.0.1:8000", timeout: float = 300.0) -> None:
        self.base = base.rstrip("/")
        # trust_env=False：本地评测不走 Windows 系统代理（否则 127.0.0.1 会被代理拦成 502）
        self._client = httpx.Client(timeout=timeout, trust_env=False)

    def _request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        resp = self._client.request(method, f"{self.base}{path}", json=body or {})
        resp.raise_for_status()
        return resp.json()

    def post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("POST", path, body)

    def get(self, path: str) -> dict[str, Any]:
        return self._request("GET", path)

    def patch(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("PATCH", path, body)

    def delete(self, path: str) -> dict[str, Any]:
        return self._request("DELETE", path)

    def post_stream(self, path: str, body: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        """SSE：返回 (event_type, payload) 帧序列。"""
        frames: list[tuple[str, dict[str, Any]]] = []
        with self._client.stream("POST", f"{self.base}{path}", json=body) as resp:
            resp.raise_for_status()
            buf = ""
            for line in resp.iter_lines():
                if line == "":
                    evt = re.search(r"^event: (.+)$", buf, re.M)
                    data = re.search(r"^data: (.+)$", buf, re.M)
                    if evt and data:
                        frames.append((evt.group(1), json.loads(data.group(1))))
                    buf = ""
                else:
                    buf += line + "\n"
        return frames

    def health(self) -> dict[str, str]:
        return self.get("/api/health")
