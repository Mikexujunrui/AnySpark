"""
对照测试 runner：pi 循环 vs 本地循环 行为语义一致性。

跑 scenarios.json 全部场景，两个 harness 各执行一遍，
对比归一化轨迹。JSON 参数序列化差异（空格）先解析再比较。

用法：uv run python benchmarks/parity/run_parity.py
输出：控制台 PASS/FAIL 表格 + report/parity-<ts>.md
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT_DIR = HERE / "report"

PYTHON = sys.executable
NODE = "node"

SCENARIOS = json.loads((HERE / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]


def run_pi(scenario_id: str) -> list[str]:
    out = subprocess.run(
        [NODE, str(HERE / "pi_harness.mjs"), scenario_id],
        capture_output=True,
        text=True,
        cwd=HERE,
        timeout=30,
    )
    if out.returncode != 0:
        return [f"harness_error:{out.stderr.strip()[:200]}"]
    data = json.loads(out.stdout)
    return data["trace"]


def run_local(scenario_id: str) -> list[str]:
    out = subprocess.run(
        [PYTHON, str(HERE / "local_harness.py"), scenario_id],
        capture_output=True,
        text=True,
        cwd=HERE,
        timeout=30,
    )
    if out.returncode != 0:
        return [f"harness_error:{out.stderr.strip()[:200]}"]
    data = json.loads(out.stdout)
    return data["trace"]


def normalize_json_spacing(s: str) -> str:
    """把内嵌 JSON 的参数部分重新压缩（消除 "a": 1 vs "a":1 差异）。"""
    import re

    return re.sub(r"\{[^{}]*\}", lambda m: json.dumps(json.loads(m.group(0))), s)


def normalize_trace(trace: list[str]) -> list[str]:
    return [normalize_json_spacing(t) for t in trace]


def main() -> None:
    REPORT_DIR.mkdir(exist_ok=True)
    results: list[tuple[str, str, bool, list[str], list[str]]] = []
    all_pass = True

    for sc in SCENARIOS:
        sid = sc["id"]
        pi_trace = run_pi(sid)
        local_trace = run_local(sid)
        same = normalize_trace(pi_trace) == normalize_trace(local_trace)
        all_pass = all_pass and same
        results.append((sid, sc["desc"], same, pi_trace, local_trace))

    lines: list[str] = []
    lines.append("# pi vs 本地 循环行为对照（parity）")
    lines.append("")
    lines.append(f"> 时间：{datetime.now(timezone.utc).isoformat()} | 引擎：pi-agent-core dist/agent-loop.js vs anyspark core/loop.py | 模型：脚本化（确定性）")
    lines.append("")
    lines.append("| 场景 | 结果 |")
    lines.append("|------|------|")
    for sid, desc, same, _, _ in results:
        lines.append(f"| {sid} {desc} | {'✅ PASS' if same else '❌ FAIL'} |")
    lines.append("")
    lines.append(f"**总计：{sum(1 for _, _, s, _, _ in results if s)}/{len(results)} PASS**")
    lines.append("")

    for sid, desc, same, pi_t, local_t in results:
        if same:
            continue
        lines.append(f"## ❌ {sid} {desc}")
        lines.append("")
        lines.append("**pi 轨迹：**")
        lines.append("```")
        lines.extend(pi_t)
        lines.append("```")
        lines.append("**本地轨迹：**")
        lines.append("```")
        lines.extend(local_t)
        lines.append("```")
        lines.append("")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report = REPORT_DIR / f"parity-{ts}.md"
    report.write_text("\n".join(lines), encoding="utf-8")

    print(f"{'场景':<60} {'结果'}")
    print("-" * 66)
    for sid, desc, same, _, _ in results:
        print(f"{sid + ' ' + desc:<60} {'✅' if same else '❌'}")
    print("-" * 66)
    print(f"总计 {sum(1 for _, _, s, _, _ in results if s)}/{len(results)} PASS")
    print(f"报告: {report}")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
