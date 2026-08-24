"""
长书压力测试：真实 DeepSeek + 小窗口（模拟长书）连续写 N 章，
验证压缩触发 + 持久化回写 + 消息数有界 + 章节完整性。

预算 = context_window × 0.7：窗口 4000 → 预算 ~2800 token，写 2-3 章必触发压缩。

用法：uv run python benchmarks/parity/stress_longbook.py [--chapters 6] [--real]
      --real 用真实 DeepSeek（默认：脚本化模型，快且确定）
"""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT_DIR = HERE / "report"

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "app" / "src"))


def run_real(chapters: int) -> dict:
    """真实 DeepSeek 链路（TestClient + 小窗口模型）。"""
    import tempfile

    from anyspark.models.deepseek import DeepSeekModel
    from anyspark.server.app import build_app
    from anyspark.store import SqliteConversationStore
    from fastapi.testclient import TestClient

    tmp = Path(tempfile.mkdtemp()) / "stress.db"
    model = DeepSeekModel(context_window=4000)  # 小窗口 → 预算 ~2800 → 快速触发压缩
    app = build_app(model=model, db_path=tmp)
    client = TestClient(app)
    store = SqliteConversationStore(tmp)

    conv_id: str | None = None
    history: list[dict] = []
    for i in range(1, chapters + 1):
        t0 = time.monotonic()
        r = client.post(
            "/api/chat",
            json={
                "message": f"写《第{i}章 章节{i}》150字：雾都侦探陈渡的进展",
                "conversation_id": conv_id,
            },
            timeout=180,
        )
        elapsed = time.monotonic() - t0
        assert r.status_code == 200, f"第{i}章失败: {r.status_code} {r.text[:200]}"
        conv_id = r.json()["conversation_id"]
        msgs = store.messages(conv_id)
        chars = sum(len(m.content) for m in msgs)
        has_summary = any("历史对话摘要" in m.content for m in msgs)
        history.append(
            {
                "ch": i,
                "msgs": len(msgs),
                "chars": chars,
                "summary": has_summary,
                "elapsed_s": round(elapsed, 1),
            }
        )

    chapters_db = store._conn.execute("SELECT COUNT(*) AS n FROM chapters").fetchone()["n"]  # type: ignore[attr-defined]
    return {"history": history, "chapters_written": chapters_db, "db": str(tmp)}


def run_scripted(chapters: int) -> dict:
    """脚本化快速压力（确定性）：Agent + TokenBudget 小预算 + persist_compression。"""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "core" / "src"))

    from anyspark.core import Agent, ModelOutput, ToolRegistry
    from anyspark.server.context import TokenBudget, make_summarizer

    class FakeModel:
        def __init__(self) -> None:
            self.n = 0

        def respond(self, messages, tools):  # type: ignore[no-untyped-def]
            self.n += 1
            return ModelOutput(text=f"第{self.n}轮回答（长度约占空间）" + "续" * 60)

    model = FakeModel()
    budget = TokenBudget(budget=400, summarize=make_summarizer(model))  # 小预算必压缩
    store_impl = _InMemoryStore()
    agent = Agent(
        model=model,  # type: ignore[arg-type]
        registry=ToolRegistry(),
        store=store_impl,
        context_compressor=budget.compress,
        persist_compression=True,
    )
    conv = store_impl.create()
    history: list[dict] = []
    for i in range(1, chapters + 1):
        agent.run(f"继续写作第{i}轮", conv.id)
        msgs = store_impl.messages(conv.id)
        chars = sum(len(m.content) for m in msgs)
        has_summary = any("历史对话摘要" in m.content for m in msgs)
        history.append({"ch": i, "msgs": len(msgs), "chars": chars, "summary": has_summary})
    return {"history": history, "chapters_written": -1, "db": "memory"}


class _InMemoryStore:
    """最小内存 store（避免依赖 app 包）。"""

    from anyspark.core.storage import InMemoryConversationStore

    def __init__(self) -> None:
        from anyspark.core.storage import InMemoryConversationStore

        self._s = InMemoryConversationStore()

    def __getattr__(self, name: str):
        return getattr(self._s, name)


def main() -> None:
    chapters = int(sys.argv[sys.argv.index("--chapters") + 1]) if "--chapters" in sys.argv else 6
    real = "--real" in sys.argv

    result = run_real(chapters) if real else run_scripted(chapters)
    hist = result["history"]
    REPORT_DIR.mkdir(exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    report = REPORT_DIR / f"stress-longbook-{ts}.md"

    # 断言：消息数有界（不随轮次线性爆炸——压缩回写生效）
    msgs_last = hist[-1]["msgs"]
    msgs_any_compressed = any(h["summary"] for h in hist)
    bounded = (
        msgs_last <= max(h["msgs"] for h in hist[: max(1, len(hist) // 2)]) * 3 or len(hist) < 4
    )

    lines = [
        "# 长书压力测试",
        "",
        f"> 时间：{datetime.now(UTC).isoformat()} | 模式：{'真实 DeepSeek（窗口4000）' if real else '脚本化（预算400）'} | 章节数：{chapters}",
        "",
        "| 轮次 | 消息数 | 累计字符 | 已压缩(含摘要) |",
        "|------|--------|----------|----------------|",
    ]
    for h in hist:
        lines.append(
            f"| {h['ch']} | {h['msgs']} | {h['chars']} | {'✅' if h['summary'] else '—'} |"
        )
    lines.append("")
    lines.append(f"- 末轮消息数：{msgs_last}（有界断言：{'✅' if bounded else '❌'}）")
    lines.append(
        f"- 压缩触发过：{'✅' if msgs_any_compressed else '❌'}（小预算下应至少触发 1 次）"
    )
    if real:
        lines.append(f"- 实际落盘章节数：{result['chapters_written']}（应为 {chapters}）")
    lines.append("")
    report.write_text("\n".join(lines), encoding="utf-8")

    print(f"{'轮':<4} {'消息数':<8} {'累计字符':<10} {'压缩':<6}")
    for h in hist:
        print(f"{h['ch']:<4} {h['msgs']:<8} {h['chars']:<10} {'✅' if h['summary'] else '—'}")
    print(f"\n末轮消息数: {msgs_last} | 压缩触发: {msgs_any_compressed}")
    if real:
        print(f"落盘章节: {result['chapters_written']}/{chapters}")
    print(f"报告: {report}")
    ok = msgs_any_compressed and bounded and (not real or result["chapters_written"] == chapters)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
