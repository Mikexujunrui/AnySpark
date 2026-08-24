"""
哈利波特第一部（人文社译本 17 章）全量提取：图谱 + 伏笔。

- 从旧项目（自研高级时间线辅助写作agent/data/chapters_1781418567324.json）读取全文
- 用 AnySpark 的 GraphExtractor（真实 DeepSeek）逐章抽取实体/关系/事件 → GraphStore
- 用 PlotGenerator 对全书生成关键点图谱（伏笔）→ PlotStore
- 输出统计 + 与旧项目产物（worldbuilding/char_mentions/timeline/detailed_outline）的对比数据

用法：uv run python benchmarks/hp_compare/extract_hp.py [--skip-extract] [--skip-plot]
      --skip-extract: 图谱已抽完，只统计/对比
      --skip-plot: 伏笔已生成，只统计/对比
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

HERE = Path(__file__).resolve().parent
REPORT_DIR = HERE / "report"
OLD_DATA = Path(r"D:\总\小说\写作辅助\自研高级时间线辅助写作agent\data")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "core" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "graph" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "align" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "template" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "app" / "src"))

BOOK = "hp_test"
DB = HERE / "hp_test.db"


def load_old_chapters() -> list[dict]:
    """从旧项目读取 17 章全文。"""
    d = json.loads((OLD_DATA / "chapters_1781418567324.json").read_text(encoding="utf-8"))
    out = []
    for ch in d:
        cur = ch.get("current_version")
        ver = next(
            (v for v in ch.get("versions", []) if v.get("id") == cur),
            ch.get("versions", [{}])[0],
        )
        out.append({"title": ch["title"], "content": ver.get("content", ""), "order": len(out) + 1})
    return out


def extract_graph(chapters: list[dict]) -> None:
    """逐章图谱抽取（真实 DeepSeek）。"""
    from anyspark.graph import GraphExtractor, GraphStore
    from anyspark.models.deepseek import DeepSeekModel

    if DB.exists():
        DB.unlink()
    store = GraphStore(str(DB))
    model = DeepSeekModel()
    extractor = GraphExtractor(model)
    for i, ch in enumerate(chapters, 1):
        t0 = time.monotonic()
        existing = [e.to_dict() for e in store.list_entities(BOOK)]
        ext = extractor.extract(ch["title"], ch["content"], existing)
        store.ingest_chapter(BOOK, ch["title"], i, ext)
        print(
            f"[{i}/{len(chapters)}] 《{ch['title']}》 实体+{len(ext.entities)} "
            f"关系+{len(ext.relations)} 事件+{len(ext.events)} "
            f"({round(time.monotonic() - t0)}s)"
        )
    print("图谱抽取完成")


def extract_plot(chapters: list[dict]) -> None:
    """对全书生成关键点图谱（伏笔提取）。"""
    from anyspark.models.deepseek import DeepSeekModel
    from anyspark.template import PlotGenerator, PlotStore

    store = PlotStore(str(DB))
    model = DeepSeekModel()
    gen = PlotGenerator(model)
    # settings：全书概要 = 各章标题 + 长度（保持精简避免超 token）
    settings = "\n".join(f"{ch['title']}（{len(ch['content'])}字）" for ch in chapters)
    points = gen.generate(BOOK, store, settings)
    print(f"伏笔提取完成: {len(points)} 条关键点")
    for p in points[:30]:
        print(f"  [{p.category}] {p.content[:50]} ({p.chapter_ref})")


def stats_graph() -> dict:
    from anyspark.graph import GraphStore

    if not DB.exists():
        return {}
    g = GraphStore(str(DB))
    return {
        "entities": len(g.list_entities(BOOK, limit=2000)),
        "relations": len(g.list_relations(BOOK)),
        "events": len(g.list_events(BOOK)),
    }


def stats_plot() -> list[dict]:
    from anyspark.template import PlotStore

    if not DB.exists():
        return []
    s = PlotStore(str(DB))
    return [p.to_dict() for p in s.list(BOOK)]


def old_project_stats() -> dict:
    """旧项目哈利波特产物统计。"""
    wb = json.loads((OLD_DATA / "worldbuilding_1781418567324.json").read_text(encoding="utf-8"))
    tl = json.loads((OLD_DATA / "timeline_1781418567324.json").read_text(encoding="utf-8"))
    cm = json.loads((OLD_DATA / "char_mentions_1781418567324.json").read_text(encoding="utf-8"))
    do = json.loads((OLD_DATA / "detailed_outline_1781418567324.json").read_text(encoding="utf-8"))
    books = json.loads((OLD_DATA / "books.json").read_text(encoding="utf-8"))
    hp = next((b for b in books if b.get("id") == "1781418567324"), {})
    # worldbuilding 条目数
    entries = 0
    for cat in wb.get("categories", []):
        for child in cat.get("children", []):
            entries += len(child.get("entries", []))
    # timeline 事件数
    events = len(tl.get("events", []))
    # char_mentions 角色数
    chars = len(cm.get("matrix", []))
    # detailed_outline 伏笔/悬念提及
    do_text = json.dumps(do, ensure_ascii=False)
    return {
        "entity_count": hp.get("entityCount"),
        "worldbuilding_entries": entries,
        "timeline_events": events,
        "char_mentions_chars": chars,
        "outline_伏笔提及": do_text.count("伏笔"),
        "outline_悬念提及": do_text.count("悬念"),
    }


def main() -> None:
    skip_extract = "--skip-extract" in sys.argv
    skip_plot = "--skip-plot" in sys.argv

    REPORT_DIR.mkdir(exist_ok=True)
    chapters = load_old_chapters()
    print(
        f"旧项目哈利波特全文: {len(chapters)} 章, 总字数 {sum(len(c['content']) for c in chapters)}"
    )

    if not skip_extract:
        print("\n== 图谱抽取（真实 DeepSeek，逐章）==")
        extract_graph(chapters)
    if not skip_plot:
        print("\n== 伏笔提取（全书概要 → 关键点图谱）==")
        extract_plot(chapters)

    g = stats_graph()
    plots = stats_plot()
    old = old_project_stats()

    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    report = REPORT_DIR / f"hp-compare-{ts}.md"
    lines = [
        "# 哈利波特第一部 图谱/伏笔提取 对比报告",
        "",
        f"> 时间：{datetime.now(UTC).isoformat()} | 文本：人文社译本 17 章（{sum(len(c['content']) for c in chapters)} 字）",
        "",
        "## 数量对比",
        "",
        "| 维度 | AnySpark v4 | 旧项目 |",
        "|------|------------|--------|",
        f"| 实体 | **{g.get('entities', 0)}** | {old.get('entity_count', '—')}（books.entityCount） |",
        f"| 关系 | **{g.get('relations', 0)}** | —（旧项目无关系图谱） |",
        f"| 事件 | **{g.get('events', 0)}** | {old.get('timeline_events', '—')}（timeline） |",
        f"| 角色提及 | —（提及矩阵不在 v4 范围） | {old.get('char_mentions_chars', '—')}（char_mentions） |",
        f"| 知识条目 | — | {old.get('worldbuilding_entries', '—')}（worldbuilding） |",
        f"| 伏笔/关键点 | **{len(plots)}**（结构化 open/resolved 状态流） | {old.get('outline_伏笔提及', 0)}+{old.get('outline_悬念提及', 0)}（叙述性提及，非结构化） |",
        "",
        "## AnySpark v4 实体（节选）",
        "",
    ]
    if g.get("entities"):
        from anyspark.graph import GraphStore

        st = GraphStore(str(DB))
        for e in st.list_entities(BOOK, limit=2000)[:40]:
            lines.append(f"- {e.name}（{e.entity_type}）：{(e.description or '')[:40]}")
    lines.append("")
    lines.append("## AnySpark v4 伏笔/关键点（全文）")
    lines.append("")
    for p in plots:
        lines.append(
            f"- [{p['category']}] {p['content']}（{p.get('chapter_ref') or '全书'}｜{p.get('status')}）"
        )
    lines.append("")
    report.write_text("\n".join(lines), encoding="utf-8")
    print(
        f"\n统计: 实体 {g.get('entities')} 关系 {g.get('relations')} 事件 {g.get('events')} 伏笔 {len(plots)}"
    )
    print(
        f"对比: 旧项目 实体 {old.get('entity_count')} worldbuilding {old.get('worldbuilding_entries')} 事件 {old.get('timeline_events')}"
    )
    print(f"报告: {report}")


if __name__ == "__main__":
    main()
