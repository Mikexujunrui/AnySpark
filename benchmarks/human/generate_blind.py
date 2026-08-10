"""
human.generate_blind — 生成盲测材料（人工层）。

流程：
1. 跑对比层三任务（A 设定忠实度 / B 长书一致性 / C 偏好跨轮记忆），保存**完整终稿**
2. 每任务两篇终稿随机匿名为 A/B（映射表单独加密存储，打分后解锁）
3. 输出打分表 score_card.md：三档粗筛（🗑垃圾/📖能读/✨不错）+ 二选一 + 一句话理由

用法：
    uv run --project benchmarks python -m benchmarks.human.generate_blind --spawn
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

from benchmarks.compare.baseline import BareLLM
from benchmarks.compare.tasks import (
    HP_SETTINGS,
    PREFERENCE_C,
    SEED_B,
    _anyspark_write,
    run_task_a,
    run_task_b,
    run_task_c,
)
from benchmarks.unit.core import ApiClient

HUMAN_DIR = Path(__file__).resolve().parent.parent / "report" / "human"


def main() -> None:
    parser = argparse.ArgumentParser(description="AnySpark benchmark · 人工层（盲测材料）")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--spawn", action="store_true")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--seed", type=int, default=42, help="匿名映射随机种子（可复现）")
    args = parser.parse_args()

    proc = None
    base = args.base
    if args.spawn:
        from benchmarks.unit.run_unit import _spawn_backend, _stop_tree

        proc, _db = _spawn_backend(args.port)
        base = f"http://127.0.0.1:{args.port}"
        print(f"[spawn] 隔离后端 {base}")

    try:
        api = ApiClient(base)
        bare = BareLLM()
        judge = BareLLM(temperature=0.2)

        # 跑三任务，取完整终稿
        tasks = {
            "A_设定忠实度": (run_task_a, _extract_a),
            "B_长书一致性": (run_task_b, _extract_b),
            "C_偏好跨轮记忆": (run_task_c, _extract_c),
        }
        rng = random.Random(args.seed)
        ts = time.strftime("%Y%m%d-%H%M%S")
        out_dir = HUMAN_DIR / ts
        out_dir.mkdir(parents=True, exist_ok=True)

        card_lines = [
            "# AnySpark 盲测打分表（隐藏来源）",
            "",
            f"时间：{time.strftime('%Y-%m-%d %H:%M:%S')} | 匿名种子：{args.seed}",
            "",
            "> 每任务两篇终稿（A/B，来源已隐藏）。三步打分：",
            "> ① 每篇三档粗筛：🗑垃圾（读不下去）/ 📖能读（有故事的样子）/ ✨不错（真想读下去）",
            "> ② 二选一：哪个更好？（必须选，不许平局）",
            '> ③ 一句话理由（最宝贵："A 的情感更真实""B 逻辑崩了"…）',
            "",
        ]

        mapping: dict[str, dict[str, str]] = {}
        for name, (fn, extract) in tasks.items():
            print(f"▶ {name} ...", flush=True)
            result = fn(api, bare, judge)
            bare_text, any_text = extract(result)
            # 匿名映射：随机决定 A/B 谁是谁
            swap = rng.random() < 0.5
            a_text, b_text = (any_text, bare_text) if swap else (bare_text, any_text)
            mapping[name] = {
                "A": "anyspark" if swap else "bare",
                "B": "bare" if swap else "anyspark",
            }
            task_dir = out_dir / name
            task_dir.mkdir(exist_ok=True)
            (task_dir / "A.txt").write_text(a_text or "（空）", encoding="utf-8")
            (task_dir / "B.txt").write_text(b_text or "（空）", encoding="utf-8")
            card_lines += [
                f"## {name}",
                "",
                f"- 任务说明：{_desc(name)}",
                f"- 稿 A：`{task_dir.name}/A.txt`（{len(a_text or '')} 字）",
                f"- 稿 B：`{task_dir.name}/B.txt`（{len(b_text or '')} 字）",
                "",
                "| 项 | 稿 A | 稿 B |",
                "|---|---|---|",
                "| 三档粗筛 | 🗑/📖/✨ | 🗑/📖/✨ |",
                "| 二选一（更好） | ☐ | ☐ |",
                "| 一句话理由 | | |",
                "",
            ]

        # 映射表单独存（打分完成前不看！）
        (out_dir / "_mapping.json").write_text(
            json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        card_lines += [
            "---",
            "打完后运行解锁：",
            "`python -c \"import json;print(json.load(open('" + "_mapping.json" + "')))\"`",
            "（或告诉我，我来揭晓）",
        ]
        (out_dir / "score_card.md").write_text("\n".join(card_lines), encoding="utf-8")
        print(f"\n盲测材料已生成: {out_dir}")
        print(f"打分表: {out_dir / 'score_card.md'}（三档 + 二选一 + 理由）")
        print("映射表已锁定在 _mapping.json（打分前勿看）")
    finally:
        if proc is not None:
            from benchmarks.unit.run_unit import _stop_tree

            _stop_tree(proc)
            print("[spawn] 隔离后端已停止")


def _desc(name: str) -> str:
    d = {
        "A_设定忠实度": f"哈利波特设定续写第4章，核对 6 条设定违规。设定：{HP_SETTINGS[:60]}…",
        "B_长书一致性": f"原创种子连写 5 章，看跨章名字漂移。种子：{SEED_B}",
        "C_偏好跨轮记忆": f"偏好：{PREFERENCE_C}；第 2 章不重复偏好，测记忆。",
    }
    return d.get(name, "")


def _extract_a(r: dict) -> tuple[str, str]:
    return r["bare"]["text"], r["anyspark"]["text"]


def _extract_b(r: dict) -> tuple[str, str]:
    return "\n\n".join(r["bare"]["chapters"]), "\n\n".join(r["anyspark"]["chapters"])


def _extract_c(r: dict) -> tuple[str, str]:
    return r["bare"]["text"], r["anyspark"]["text"]


if __name__ == "__main__":
    main()
