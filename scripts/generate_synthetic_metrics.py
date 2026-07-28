"""
Generate synthetic metrics.jsonl data for analysis script testing.

Usage:
    python scripts/generate_synthetic_metrics.py [--count N]

Produces realistic-looking metrics for common task patterns:
- Simple write tasks (5-8 rounds)
- Complex extract tasks (15-25 rounds with hallucination)
- Plan tasks (10-20 rounds, some with early plan_complete)
- KB mutation tasks (many rounds with doom loops)
"""
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "metrics.jsonl"


def gen_task(ttype: str):
    ts = datetime(2025, 1, 1) + timedelta(hours=random.randint(0, 720))
    book_id = random.choice(["1781165301900", "1781418567324", "1781680421140"])
    user_msgs = {
        "write": ["写第1章", "续写第3章", "按计划写第5章", "用古风风格写下一章"],
        "extract": ["提取第2章的设定", "提取全文角色", "从参考书提取设定"],
        "plan": ["规划后续剧情", "分析当前伏笔", "列出待完成任务"],
        "edit": ["修改第1章的开篇", "润色第3章", "调整战斗场景"],
        "consistency": ["检查知识库一致性", "对比大纲与已完成章节"],
        "general": ["帮我查一下角色A的关系", "总结一下当前进度"],
    }
    msg = random.choice(user_msgs.get(ttype, ["..."]))

    if ttype == "write":
        rounds = random.randint(5, 10)
        llm_calls = rounds + random.randint(0, 2)  # rarely a retry
        tool_calls = random.randint(3, 8)
        hall_retries = 0
        doom_skips = 0
        finish = "done"
    elif ttype == "extract":
        rounds = random.randint(12, 25)
        llm_calls = rounds + random.randint(0, 4)
        tool_calls = random.randint(8, 20)
        hall_retries = random.choice([0, 0, 1, 2])  # sometimes hallucination
        doom_skips = random.choice([0, 0, 0, 1])
        finish = random.choice(["done"] * 7 + ["hallucination_limit"])
    elif ttype == "plan":
        rounds = random.randint(8, 20)
        llm_calls = rounds + random.randint(0, 2)
        tool_calls = random.randint(3, 10)
        hall_retries = 0
        doom_skips = 0
        # Sometimes plan completes early with Stage 5.5
        plan_early = random.choice([False, False, True])
        finish = "plan_complete" if plan_early else "done"
        # Subagent usage: plan mode can only spawn read-only types
        subagent_spawned = random.choice([0, 0, 0, 1, 2]) if random.random() < 0.3 else 0
        subagent_types = {}
        if subagent_spawned > 0:
            types_pool = ["research", "plan", "consistency", "reviewer"]
            for _ in range(subagent_spawned):
                picked = random.choice(types_pool)
                subagent_types[picked] = subagent_types.get(picked, 0) + 1
        subagent_blocked = random.choice([0, 0, 1]) if subagent_spawned > 0 else 0
        return {
            "timestamp": ts.isoformat(),
            "agent_type": ttype,
            "book_id": book_id,
            "user_message": msg,
            "rounds": rounds,
            "llm_calls": llm_calls,
            "llm_retries": random.randint(0, 1),
            "tool_calls": tool_calls,
            "hallucination_hits": {},
            "hallucination_retry_rounds": hall_retries,
            "doom_loop_skips": doom_skips,
            "read_only_rounds": random.randint(0, rounds // 3),
            "text_and_tool_rounds": random.randint(0, 2),
            "plan_complete_early": plan_early,
            "subagent_spawned": subagent_spawned,
            "subagent_types": subagent_types,
            "subagent_blocked": subagent_blocked,
            "compactions": 0,
            "sitreps": 0,
            "drift_corrections": 0,
            "kb_mutation_stops": 0,
            "cancellations": 0,
            "finish_reason": finish,
        }
    elif ttype == "edit":
        rounds = random.randint(6, 15)
        llm_calls = rounds + random.randint(0, 2)
        tool_calls = random.randint(2, 8)
        hall_retries = random.choice([0, 0, 1])
        doom_skips = 0
        finish = "done"
    else:
        rounds = random.randint(3, 12)
        llm_calls = rounds + random.randint(0, 2)
        tool_calls = random.randint(1, 5)
        hall_retries = 0
        doom_skips = 0
        finish = "done"

    # Subagent usage: write/general can spawn all types; extract/edit only read-only when in plan mode
    subagent_spawned = 0
    subagent_types = {}
    subagent_blocked = 0
    if ttype == "write" and random.random() < 0.15:  # 15% of write tasks use subagents
        subagent_spawned = random.randint(1, 3)
        types_pool = ["research", "plan", "consistency", "reviewer", "general", "extract", "edit"]
        for _ in range(subagent_spawned):
            picked = random.choice(types_pool)
            subagent_types[picked] = subagent_types.get(picked, 0) + 1
    elif ttype == "general" and random.random() < 0.4:  # 40% of general tasks use subagents
        subagent_spawned = random.randint(1, 2)
        types_pool = ["research", "general"]
        for _ in range(subagent_spawned):
            picked = random.choice(types_pool)
            subagent_types[picked] = subagent_types.get(picked, 0) + 1

    return {
        "timestamp": ts.isoformat(),
        "agent_type": ttype,
        "book_id": book_id,
        "user_message": msg,
        "rounds": rounds,
        "llm_calls": llm_calls,
        "llm_retries": random.randint(0, 1),
        "tool_calls": tool_calls,
        "hallucination_hits": {"past": 1} if hall_retries else {},
        "hallucination_retry_rounds": hall_retries,
        "doom_loop_skips": doom_skips,
        "read_only_rounds": random.randint(0, rounds // 4),
        "text_and_tool_rounds": random.randint(0, 1),
        "plan_complete_early": False,
        "subagent_spawned": subagent_spawned,
        "subagent_types": subagent_types,
        "subagent_blocked": subagent_blocked,
        "compactions": 1 if rounds > 15 else 0,
        "sitreps": 1 if rounds > 20 else 0,
        "drift_corrections": 1 if hall_retries else 0,
        "kb_mutation_stops": 1 if ttype == "extract" and rounds > 20 else 0,
        "cancellations": 0,
        "finish_reason": finish,
    }


def main():
    import sys
    count = 200
    if len(sys.argv) > 2 and sys.argv[1] == "--count":
        count = int(sys.argv[2])

    print(f"Generating {count} synthetic metrics records to {DATA_FILE}")
    types = (
        ["write"] * 40 +
        ["extract"] * 25 +
        ["plan"] * 20 +
        ["edit"] * 10 +
        ["general"] * 5
    )
    random.shuffle(types)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        for _i in range(count):
            ttype = random.choice(types)
            rec = gen_task(ttype)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("Done.")


if __name__ == "__main__":
    main()
