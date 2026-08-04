"""
性能基线：本地 Agent 循环的 token 吞吐/时延基线（存档防退化）。

任务：真实 DeepSeek 写 300 字章节（含 list/read/write 工具链路），重复 N 次。
指标：TTFT（首个文本 delta 时延）/ 总时长 / 输出字符 / 估算 token/s / 工具执行次数。
基线写入 report/perf-<ts>.md——未来循环改动后重跑，对比是否有退化。

用法：uv run python benchmarks/parity/perf_baseline.py [--rounds 3]
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT_DIR = HERE / "report"

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "app" / "src"))

import httpx  # noqa: E402


def run_round(client: httpx.Client, round_no: int) -> dict:
    started = time.monotonic()
    ttft: float | None = None
    tokens = 0
    text = ""

    with client.stream(
        "POST",
        "http://127.0.0.1:8000/api/chat/stream",
        json={"message": f"写《性能测试章 {round_no}》300字：雾中灯塔前的场景"},
        timeout=180,
    ) as resp:
        buf = ""
        for chunk in resp.iter_text():
            buf += chunk
            while "\n\n" in buf:
                frame, buf = buf.split("\n\n", 1)
                evt = None
                data = None
                for line in frame.split("\n"):
                    if line.startswith("event:"):
                        evt = line[6:].strip()
                    elif line.startswith("data:"):
                        data = line[5:].strip()
                if evt == "text_delta" and data:
                    payload = json.loads(data)
                    content = str(payload.get("content", ""))
                    if ttft is None:
                        ttft = time.monotonic() - started
                    text += content
                    tokens += 1  # delta 帧数近似 token（真实 token 由 usage 提供，此处省 API）
                if evt == "done":
                    break

    total_s = time.monotonic() - started
    return {
        "round": round_no,
        "total_s": round(total_s, 2),
        "ttft_s": round(ttft or 0, 2),
        "chars": len(text),
        "delta_frames": tokens,
        "tokens_per_s": round(len(text) / max(total_s, 0.001), 1),
        "chars_per_s": round(len(text) / max(total_s, 0.001), 1),
    }


def main() -> None:
    rounds = int(sys.argv[sys.argv.index("--rounds") + 1]) if "--rounds" in sys.argv else 3
    REPORT_DIR.mkdir(exist_ok=True)

    with httpx.Client(trust_env=False) as client:
        results = [run_round(client, i + 1) for i in range(rounds)]

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report = REPORT_DIR / f"perf-{ts}.md"
    lines = [
        "# AnySpark 循环性能基线",
        "",
        f"> 时间：{datetime.now(timezone.utc).isoformat()} | 模型：deepseek-v4-flash | 任务：写 300 字章节（含工具链路）",
        "",
        "| 轮次 | 总时长(s) | TTFT(s) | 输出字符 | delta帧 | 字符/s |",
        "|------|-----------|---------|----------|---------|--------|",
    ]
    for r in results:
        lines.append(
            f"| {r['round']} | {r['total_s']} | {r['ttft_s']} | {r['chars']} | "
            f"{r['delta_frames']} | {r['chars_per_s']} |"
        )
    avg = {k: round(sum(r[k] for r in results) / len(results), 2) for k in ("total_s", "ttft_s", "chars_per_s")}
    lines.append(f"| **平均** | **{avg['total_s']}** | **{avg['ttft_s']}** | | | **{avg['chars_per_s']}** |")
    lines.append("")
    lines.append("**说明**：tokens/s 未直接用 API usage（流式省请求），delta 帧/字符/s 可作相对基线——")
    lines.append("改动循环后重跑本脚本，若字符/s 显著下降或 TTFT 上升即疑似退化。")
    report.write_text("\n".join(lines), encoding="utf-8")

    print(f"{'轮':<4} {'总时长s':<10} {'TTFTs':<8} {'字符':<7} {'字符/s':<8}")
    for r in results:
        print(f"{r['round']:<4} {r['total_s']:<10} {r['ttft_s']:<8} {r['chars']:<7} {r['chars_per_s']:<8}")
    print(f"平均字符/s: {avg['chars_per_s']} | 报告: {report}")


if __name__ == "__main__":
    main()
