"""对比层入口：同一长程任务 × AnySpark vs 裸 LLM，输出对比报告。

用法：
    uv run --project benchmarks python -m benchmarks.compare.run_compare --spawn
    uv run --project benchmarks python -m benchmarks.compare.run_compare --base http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from benchmarks.compare.baseline import BareLLM
from benchmarks.compare.tasks import run_task_a, run_task_b, run_task_c

REPORT_DIR = Path(__file__).resolve().parent.parent / "report"


def main() -> None:
    parser = argparse.ArgumentParser(description="AnySpark benchmark · 对比层")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--spawn", action="store_true", help="自动启动隔离后端（独立 db）")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--task", default=None, help="只跑 a|b|c")
    args = parser.parse_args()

    proc = None
    base = args.base
    if args.spawn:
        from benchmarks.unit.run_unit import _spawn_backend, _stop_tree

        proc, _db = _spawn_backend(args.port)
        base = f"http://127.0.0.1:{args.port}"
        print(f"[spawn] 隔离后端 {base}")

    try:
        from benchmarks.unit.core import ApiClient

        api = ApiClient(base)
        bare = BareLLM()
        judge = BareLLM(temperature=0.2)  # 裁判低温度=稳定

        tasks = []
        if args.task in (None, "a"):
            tasks.append(("A 设定忠实度", run_task_a))
        if args.task in (None, "b"):
            tasks.append(("B 长书一致性(5章)", run_task_b))
        if args.task in (None, "c"):
            tasks.append(("C 偏好遵守(禁破折号)", run_task_c))

        results: dict[str, dict] = {}
        for name, fn in tasks:
            print(f"▶ {name} ...", flush=True)
            t0 = time.time()
            results[name] = fn(api, bare, judge)
            print(f"  ⏱ {time.time() - t0:.0f}s")

        _write_report(results, {"backend": base, "model": bare.model})

        # 控制台摘要
        for name, r in results.items():
            print(f"\n=== {name} ===")
            for side in ("bare", "anyspark"):
                d = r[side]
                label = "裸LLM  " if side == "bare" else "AnySpark"
                print(f"  {label} {_brief(d)}")
    finally:
        if proc is not None:
            from benchmarks.unit.run_unit import _stop_tree

            _stop_tree(proc)
            print("[spawn] 隔离后端已停止")


def _brief(d: dict) -> str:
    if "violations" in d:
        return f"设定违规 {len(d['violations'])} 处 | {d['tokens']} tok"
    if "drifts" in d:
        return f"跨章漂移 {len(d['drifts'])} 处 | {d['tokens']} tok"
    if "dash_count" in d:
        return f"破折号 {d['dash_count']} 次 | {d['tokens']} tok"
    return str(d)[:80]


def _write_report(results: dict, env: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = REPORT_DIR / f"compare-{ts}.md"
    lines = [
        "# AnySpark benchmark · 对比层（AnySpark vs 裸 LLM）",
        "",
        f"时间：{time.strftime('%Y-%m-%d %H:%M:%S')} | "
        + " | ".join(f"{k}={v}" for k, v in env.items()),
        "",
        "> 同一任务、同一模型（deepseek-v4-flash）、同输入；裸 LLM = 无任何系统能力的直接调用。",
        "",
    ]
    for name, r in results.items():
        lines.append(f"## {name}")
        if "长书" in name:
            lines.append("\n> 5 章连写（约250字/章）：让上下文遗忘在长程中自然发生。")
        lines.append("")
        lines.append("| 指标 | 裸 LLM | AnySpark |")
        lines.append("|---|---|---|")
        bare, anyspark = r["bare"], r["anyspark"]
        if "violations" in bare:
            lines.append(
                f"| 设定违规 | {len(bare['violations'])} | {len(anyspark['violations'])} |"
            )
            lines.append(f"| token 消耗 | {bare['tokens']} | {anyspark['tokens']} |")
            lines += _violation_block("裸 LLM", bare["violations"])
            lines += _violation_block("AnySpark", anyspark["violations"])
            lines += _excerpt_block("裸 LLM", bare["text"])
            lines += _excerpt_block("AnySpark", anyspark["text"])
        elif "drifts" in bare:
            lines.append(f"| 跨章名字漂移 | {len(bare['drifts'])} | {len(anyspark['drifts'])} |")
            lines.append(f"| token 消耗 | {bare['tokens']} | {anyspark['tokens']} |")
            lines += _drift_block("裸 LLM", bare)
            lines += _drift_block("AnySpark", anyspark)
            lines += _excerpt_block("裸 LLM 第1章", bare["chapters"][0])
            lines += _excerpt_block("裸 LLM 第3章", bare["chapters"][2])
            lines += _excerpt_block("AnySpark 第1章", anyspark["chapters"][0])
            lines += _excerpt_block("AnySpark 第3章", anyspark["chapters"][2])
        elif "dash_count" in bare:
            lines.append(
                f"| 破折号次数（应≈0） | {bare['dash_count']} | {anyspark['dash_count']} |"
            )
            lines.append(
                f"| 第1章（偏好明说时） | {bare.get('dash_ch1', '—')} | {anyspark.get('dash_ch1', '—')} |"
            )
            lines.append(
                f"| 第2章（偏好不再重复，测记忆） | {bare.get('dash_ch2', '—')} | {anyspark.get('dash_ch2', '—')} |"
            )
            lines.append(f"| token 消耗 | {bare['tokens']} | {anyspark['tokens']} |")
            lines += _excerpt_block("裸 LLM", bare["text"])
            lines += _excerpt_block("AnySpark", anyspark["text"])
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告: {path}")


def _violation_block(side: str, violations: list) -> list[str]:
    if not violations:
        return []
    lines = [f"**{side} 违规详情**", ""]
    for v in violations:
        lines.append(f"- {v.get('setting', '')[:60]} ← {v.get('reason', '')[:80]}")
    lines.append("")
    return lines


def _excerpt_block(side: str, text: str) -> list[str]:
    if not text:
        return []
    excerpt = text[:180].replace("\n", " ")
    return [f"**{side} 正文摘录**：{excerpt}…", ""]


def _drift_block(side: str, d: dict) -> list[str]:
    if not d["drifts"]:
        return []
    lines = [f"**{side} 漂移详情**", ""]
    for dr in d["drifts"]:
        lines.append(
            f"- {dr.get('ch1_name', '')} → {dr.get('ch3_name', '')}（{dr.get('type', '')}）"
        )
    lines.append("")
    return lines


if __name__ == "__main__":
    main()
