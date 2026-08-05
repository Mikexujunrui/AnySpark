"""批量灌入：《猎手准则》第一卷（164 章）→ 图谱（真实 LLM 抽取，并行加速）。

用法：uv run python scripts/batch_ingest_hunter.py [--start 1] [--end 164] [--workers 6] [--db 路径]

产物：隔离库 data/dev/bench_hunter_vol1.db（不入库）；进度 data/dev/runs/batch_ingest/。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = (
    r"E:/Desktop/新建文件夹/soushu2023.com@《猎手准则》（校对版全本） "
    r"作者：你是不是笨蛋[搜书吧].txt"
)


def load_chapters() -> list[tuple[str, str]]:
    """第一卷 164 章：(章题, 正文)。"""
    with open(SRC, encoding="gb18030") as fh:
        text = fh.read()
    start = text.find("第一卷 倒吊人")
    vol2 = text.find("第二卷 世界", start)
    seg = text[start:vol2] if vol2 > start else text[start:]
    titles = [
        (m.start(), m.group().strip())
        for m in re.finditer(r"第[一二三四五六七八九十百]+章\s+\S+", seg)
    ]
    chapters: list[tuple[str, str]] = []
    for i, (pos, title) in enumerate(titles):
        end = titles[i + 1][0] if i + 1 < len(titles) else len(seg)
        body = seg[pos:end]
        body = re.sub(r"^第[一二三四五六七八九十百]+章.*?\n", "", body)
        body = "\n".join(x.rstrip() for x in body.split("\n") if x.strip())
        chapters.append((title, body))
    return chapters


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=164)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--db", default="data/dev/bench_hunter_vol1.db")
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT))
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from anyspark.graph import GraphExtractor, GraphStore
    from anyspark.models import DeepSeekModel

    chapters = load_chapters()
    print(f"第一卷共 {len(chapters)} 章；本次灌 {args.start}-{min(args.end, len(chapters))} 章")

    model = DeepSeekModel(temperature=0.2)
    graph = GraphStore(ROOT / args.db)
    extractor = GraphExtractor(model)

    out_dir = ROOT / "data/dev/runs/batch_ingest"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / f"vol1_{args.start}-{args.end}.jsonl"
    log = open(log_path, "w", encoding="utf-8")  # noqa: SIM115

    def ingest_one(idx: int) -> dict[str, object]:
        """灌一章：existing → extract（失败重试 2 次）→ ingest。"""
        title, body = chapters[idx - 1]
        t0 = time.time()
        for attempt in range(3):
            try:
                existing = [e.to_dict() for e in graph.list_entities("main")]
                ext = extractor.extract(title, body, existing)
                graph.ingest_chapter("main", title, idx, ext, "main")
                return {
                    "order": idx,
                    "title": title,
                    "ok": True,
                    "entities": len(ext.entities),
                    "relations": len(ext.relations),
                    "events": len(ext.events),
                    "secs": round(time.time() - t0, 1),
                }
            except Exception as exc:
                if attempt == 2:
                    return {
                        "order": idx,
                        "title": title,
                        "ok": False,
                        "error": str(exc)[:200],
                        "secs": round(time.time() - t0, 1),
                    }
                time.sleep(2 * (attempt + 1))
        return {"order": idx, "title": title, "ok": False, "error": "unreachable"}

    ok = fail = 0
    total_entities = total_relations = total_events = 0
    t_start = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {
            pool.submit(ingest_one, i): i
            for i in range(args.start, min(args.end, len(chapters)) + 1)
        }
        for done, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            log.write(json.dumps(r, ensure_ascii=False) + "\n")
            log.flush()
            done += 1
            if r["ok"]:
                ok += 1
                total_entities += int(str(r["entities"]))
                total_relations += int(str(r["relations"]))
                total_events += int(str(r["events"]))
            else:
                fail += 1
            if done % 10 == 0 or done == len(futs):
                el = time.time() - t_start
                print(
                    f"[{done}/{len(futs)}] ok={ok} fail={fail} 实体累计={total_entities} "
                    f"({el / 60:.1f}min, {el / max(done, 1):.1f}s/章)",
                    flush=True,
                )
    log.close()
    print(f"\n完成: ok={ok} fail={fail} 总耗时 {(time.time() - t_start) / 60:.1f}min")
    print(f"累计: 实体{total_entities} 关系{total_relations} 事件{total_events}")
    print(f"日志: {log_path}")


if __name__ == "__main__":
    main()
