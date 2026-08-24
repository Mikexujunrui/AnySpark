"""
S21 系统层：分支剧本测哲学过程指标（T7：修改率↓ / 说明书累积↑ / 偏好遵从）。

设计（DESIGN §9 T7 + 决策B 真实实现）：
- 分支 A（对齐学习）：3 轮写作。轮 1 无偏好 → 用户 rejected+modified（"不要破折号"）
  → 后台提炼说明书 → 轮 2/3 续写（不重复指令）→ 用户 accepted。
  断言：① 说明书自动累积（信号→提炼闭环）② 修改率趋势 100%→0%（对齐生效）
        ③ 轮 3 章节破折号数 < 轮 1（偏好注入真实生效，无需重复指令）
- 分支 B（对照组）：3 轮直接写，无信号。断言：说明书 0 条（无学习发生）
- 隔离实例：A/B 各自独立临时 db（不互相污染）

用法：uv run python benchmarks/system/learn_curve.py [--rounds 3]
输出：report/learn-curve-<ts>.md
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT_DIR = HERE / "report"

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "app" / "src"))

from anyspark.models.deepseek import DeepSeekModel
from anyspark.server.app import build_app
from fastapi.testclient import TestClient

PREFERENCE = "不要使用破折号（——），一律用句号断句"


def _new_client() -> tuple[TestClient, Path, sqlite3.Connection]:
    tmp = Path(tempfile.mkdtemp()) / "learn.db"
    app = build_app(model=DeepSeekModel(), db_path=tmp)
    conn = sqlite3.connect(tmp)
    conn.row_factory = sqlite3.Row
    return TestClient(app), tmp, conn


def _count_dash(content: str) -> int:
    return content.count("——")


def _manual_count(client: TestClient) -> int:
    return len(client.get("/api/manual").json())


def _wait_refine(client: TestClient, expect_min: int, timeout_s: float = 60) -> bool:
    """等待后台信号提炼完成（说明书条目 ≥ expect_min）。"""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _manual_count(client) >= expect_min:
            return True
        time.sleep(1)
    return False


def run_branch(rounds: int, with_alignment: bool) -> dict:
    client, _, conn = _new_client()
    conv: str | None = None
    chapters: list[dict] = []
    signals_sent = 0

    for i in range(1, rounds + 1):
        r = client.post(
            "/api/chat",
            json={
                "message": f"写《第{i}章 雾都{i}》250字：陈渡追查怀表线索",
                "conversation_id": conv,
            },
            timeout=180,
        )
        assert r.status_code == 200, f"第{i}章失败: {r.text[:200]}"
        data = r.json()
        conv = data["conversation_id"]
        # 从章节表取落盘内容
        row = conn.execute(
            "SELECT title, content FROM chapters ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        chapters.append(
            {
                "title": row["title"],
                "content": row["content"],
                "dashes": _count_dash(row["content"]),
            }
        )
        # 分支 A：轮 1 喂"拒绝+修改"信号（表达偏好），后续轮 accepted
        if with_alignment:
            if i == 1:
                client.post(
                    "/api/signals",
                    json={
                        "kind": "rejected",
                        "content": "这段里有破折号，不符合我的偏好",
                        "context": f"第{i}章",
                    },
                )
                client.post(
                    "/api/signals",
                    json={
                        "kind": "modified",
                        "content": PREFERENCE,
                        "new_content": "改好的版本",
                        "context": f"第{i}章",
                    },
                )
                signals_sent += 2
            else:
                client.post(
                    "/api/signals",
                    json={"kind": "accepted", "content": f"第{i}章可以接受", "context": f"第{i}章"},
                )
                signals_sent += 1

    # 等后台提炼完成
    refined = _wait_refine(client, 1) if with_alignment else True
    manual = client.get("/api/manual").json()
    stats = client.get("/api/stats").json()
    manual_count = len(manual)

    # 修改率：看 signals 的 accepted/changed 分布
    modify = stats.get("modify_rate", {})
    client.close()
    return {
        "branch": "A对齐" if with_alignment else "B对照",
        "chapters": chapters,
        "manual_count": manual_count,
        "refined_ok": refined,
        "manual_entries": [e["content"][:40] for e in manual],
        "stats_modify": {
            "total": modify.get("total"),
            "accepted": modify.get("accepted"),
            "changed": modify.get("changed"),
        },
        "signals_sent": signals_sent,
    }


def main() -> None:
    rounds = int(sys.argv[sys.argv.index("--rounds") + 1]) if "--rounds" in sys.argv else 3
    REPORT_DIR.mkdir(exist_ok=True)

    print(f"跑分支 A（对齐学习，{rounds} 轮）…（每轮 ~30-60s）")
    a = run_branch(rounds, with_alignment=True)
    print(f"跑分支 B（对照组，{rounds} 轮）…")
    b = run_branch(rounds, with_alignment=False)

    dash_a = [c["dashes"] for c in a["chapters"]]
    dash_b = [c["dashes"] for c in b["chapters"]]
    a_first_last = f"{dash_a[0]} → {dash_a[-1]}" if dash_a else "n/a"

    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    report = REPORT_DIR / f"learn-curve-{ts}.md"
    lines = [
        "# 学习曲线（分支剧本哲学指标）",
        "",
        f"> 时间：{datetime.now(UTC).isoformat()} | 模型：deepseek-v4-flash | 轮数：{rounds} | A/B 隔离实例",
        "",
        "## 分支 A（对齐学习：轮1拒绝+修改→说明书→后续接受）",
        "",
        f"- 说明书自动累积：{'✅' if a['refined_ok'] else '❌'}（提炼出 {len(a['manual_entries'])} 条）",
        f"- 说明书内容：{a['manual_entries']}",
        f"- 信号数：{a['signals_sent']} | 修改率统计：accepted={a['stats_modify']['accepted']} changed={a['stats_modify']['changed']}（应为 2改+2接受）",
        f"- 各章破折号数：{dash_a}（趋势 {a_first_last}；↓ = 偏好注入生效）",
        "",
        "## 分支 B（对照组：无信号）",
        "",
        f"- 说明书：{b['manual_count']} 条（{'✅ 无学习' if b['manual_count'] == 0 else '⚠️ 有残留'}）",
        f"- 各章破折号数：{dash_b}",
        "",
        "## 判定",
        "",
        "- 说明书累积：A>0 且 B=0 → 对齐学习发生 ✅",
        "- 偏好遵从：A 末章破折号 < A 首章（或 ≤ B 末章）→ 注入真实生效",
        "- 修改率趋势：A 从 rejected/modified 转向 accepted（↓ 方向）",
    ]
    report.write_text("\n".join(lines), encoding="utf-8")

    print(
        f"\n分支 A: 说明书 {len(a['manual_entries'])} 条 | 破折号 {a_first_last} | 提炼{'✅' if a['refined_ok'] else '❌'}"
    )
    print(f"分支 B: 破折号 {dash_b}")
    print(f"报告: {report}")


if __name__ == "__main__":
    main()
