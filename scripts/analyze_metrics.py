"""
Analyse the metrics.jsonl file produced by ``_persist_metrics``.

Usage:
    python scripts/analyze_metrics.py                       # analyse full file
    python scripts/analyze_metrics.py --since 2025-01-01    # filter by date
    python scripts/analyze_metrics.py --book-id <ID>        # filter by book

Produces summary statistics about wheel-consumption patterns and flags
common inefficiencies (hallucination retries, doom loops, etc.).
"""
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "metrics.jsonl"


def load_records(path: Path, since: str = "", book_id: str = ""):
    if not path.exists():
        return []
    out = []
    for line in path.open(encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if since:
            ts = datetime.fromisoformat(rec["timestamp"])
            if ts < datetime.fromisoformat(since):
                continue
        if book_id and rec.get("book_id") != book_id:
            continue
        out.append(rec)
    return out


def bucket_by_type(records):
    by_type = defaultdict(list)
    for r in records:
        by_type[r.get("agent_type", "unknown")].append(r)
    return dict(by_type)


def summarize_type(tname, recs):
    n = len(recs)
    if n == 0:
        return

    rounds = [r["rounds"] for r in recs]
    tool_calls = [r["tool_calls"] for r in recs]
    llm_calls = [r["llm_calls"] for r in recs]
    hall_retries = [r.get("hallucination_retry_rounds", 0) for r in recs]
    doom_skips = [r.get("doom_loop_skips", 0) for r in recs]
    reads = [r.get("read_only_rounds", 0) for r in recs]
    mixed = [r.get("text_and_tool_rounds", 0) for r in recs]
    subagent_spawns = [r.get("subagent_spawned", 0) for r in recs]
    subagent_blockeds = [r.get("subagent_blocked", 0) for r in recs]

    # Aggregate subagent types across all runs
    subagent_type_totals = Counter()
    for r in recs:
        for stype, count in r.get("subagent_types", {}).items():
            subagent_type_totals[stype] += count

    def avg(xs):
        return sum(xs) / len(xs) if xs else 0
    def p50(xs):
        return sorted(xs)[len(xs) // 2] if xs else 0
    def p90(xs):
        return sorted(xs)[int(len(xs) * 0.9)] if xs else 0
    def p99(xs):
        return sorted(xs)[min(int(len(xs) * 0.99), len(xs) - 1)] if xs else 0

    finish_reasons = Counter(r.get("finish_reason", "?") for r in recs)

    # Efficiency ratio: how many LLM calls were "productive" (not retries)?
    total_llm = sum(llm_calls)
    total_retry_extra = sum(llm_calls) - sum(rounds)  # retries beyond one round each
    retry_rate = total_retry_extra / total_llm if total_llm else 0

    print(f"\n{'=' * 70}")
    print(f"Agent type: {tname}  (n={n})")
    print(f"{'=' * 70}")
    print(f"  Rounds per task:     mean={avg(rounds):.1f}  p50={p50(rounds)}  p90={p90(rounds)}  p99={p99(rounds)}")
    print(f"  Tool calls per task: mean={avg(tool_calls):.1f}  p50={p50(tool_calls)}  max={max(tool_calls) if tool_calls else 0}")
    print(f"  LLM call count:     mean={avg(llm_calls):.1f}  (rounds + retries)")
    print(f"  Retry overhead:      {retry_rate:.1%} of LLM calls were retries over round count")
    print(f"  Hallucination retries: mean={avg(hall_retries):.2f}  (wasted rounds)")
    print(f"  Doom loop skips:    mean={avg(doom_skips):.2f}  (blocked doom calls)")
    print(f"  Read-only rounds:   mean={avg(reads):.2f}")
    print(f"  Mixed (text+tool) rounds: mean={avg(mixed):.2f}")
    print(f"  Subagent spawns:    mean={avg(subagent_spawns):.2f}  blocked={avg(subagent_blockeds):.2f}")
    if subagent_type_totals:
        sa_breakdown = ", ".join(f"{k}:{v}" for k, v in sorted(subagent_type_totals.items()))
        print(f"  Subagent types:     {sa_breakdown}")
    print("  Finish reasons:")
    for reason, count in finish_reasons.most_common(10):
        print(f"    {reason:<25} {count:>4}  ({count / n:.1%})")

    # Flag common waste patterns
    waste_high = sum(1 for r in recs if round_waste(r) > 0.3)
    print(f"  High-waste tasks (>30% rounds wasted): {waste_high}/{n} ({waste_high / n:.1%})")


def round_waste(r):
    """Estimated fraction of rounds that were wasted.

    Heuristic: (hallucination retries + doom loop skips + read-only) / rounds.
    This isn't perfect but gives a rough signal.
    """
    rounds = r["rounds"]
    if rounds == 0:
        return 0.0
    wasted = (
        r.get("hallucination_retry_rounds", 0)
        + r.get("doom_loop_skips", 0)
        + r.get("read_only_rounds", 0)
    )
    return wasted / rounds


def find_outliers(records, field="rounds", threshold=40):
    return [
        (r["timestamp"], r.get("agent_type"), r[field],
         r["user_message"][:80], r.get("finish_reason"))
        for r in records if r.get(field, 0) >= threshold
    ]


def main():
    since = ""
    book_id = ""
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--since" and i + 1 < len(args):
            since = args[i + 1]
            i += 2
        elif args[i] == "--book-id" and i + 1 < len(args):
            book_id = args[i + 1]
            i += 2
        else:
            print(f"Usage: {sys.argv[0]} [--since YYYY-MM-DD] [--book-id ID]")
            return
        continue

    records = load_records(DATA_FILE, since=since, book_id=book_id)
    if not records:
        print(f"No records in {DATA_FILE}" + (f" since {since}" if since else ""))
        return

    total = len(records)
    print(f"Loaded {total} records from {DATA_FILE}")
    by_type = bucket_by_type(records)
    print(f"Agent types: {list(by_type.keys())}")

    # Grand totals
    rounds_all = [r["rounds"] for r in records]
    print(f"\nOverall round stats (n={total}):")
    print(f"  mean={sum(rounds_all) / total:.1f}  median={sorted(rounds_all)[total // 2]}  "
          f"max={max(rounds_all)}  total={sum(rounds_all)}")

    # Subagent stats
    total_spawns = sum(r.get("subagent_spawned", 0) for r in records)
    total_blocked = sum(r.get("subagent_blocked", 0) for r in records)
    if total_spawns > 0 or total_blocked > 0:
        print("\nSubagent stats:")
        print(f"  Total spawns: {total_spawns}")
        print(f"  Total blocked (plan-mode guard): {total_blocked}")
        type_totals = Counter()
        for r in records:
            for stype, count in r.get("subagent_types", {}).items():
                type_totals[stype] += count
        if type_totals:
            breakdown = ", ".join(f"{k}:{v}" for k, v in sorted(type_totals.items()))
            print(f"  Type breakdown: {breakdown}")

    for tname, recs in sorted(by_type.items()):
        summarize_type(tname, recs)

    # Outliers
    print(f"\n{'=' * 70}")
    print("Outliers (>= 40 rounds):")
    outliers = find_outliers(records, "rounds", 40)
    for ts, atype, rounds, msg, reason in outliers[:20]:
        print(f"  {ts[:19]}  {atype:<12} rounds={rounds:>3}  {reason:<25} {msg}")


if __name__ == "__main__":
    main()
