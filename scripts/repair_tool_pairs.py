"""修复 DB 里所有会话消息的 tool_calls 配对残缺（S200）。

背景：历史版本（S170 之前的打包版）在取消/异常中断时可能给会话留下
"assistant 声明了 tool_calls 但无对应 tool 结果"的悬挂声明——再次请求
该会话历史时 OpenAI/DeepSeek 严格模式报 400
（insufficient tool messages following tool_calls message）。

当前代码（v4.0.10+）在读取时做内存级自愈（_heal_tool_pairs），请求本身
不会再 400；但 DB 里的旧数据仍残留残缺，任何绕过自愈的读取路径都可能踩雷。
本脚本把修剪结果**落库**，一次性根治。

用法：python scripts/repair_tool_pairs.py [db_path]（缺省 data/anyspark.db）
幂等：已修剪的元数据再跑无变化。
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path


def repair(db_path: str | Path) -> int:
    """扫描全部会话消息，把未配对的 assistant tool_calls 声明从元数据中移除。

    返回修复的消息条数（0 表示 DB 本来就干净）。
    """
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT conversation_id, seq, role, metadata FROM messages ORDER BY conversation_id, seq"
        ).fetchall()
        conv_msgs: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            conv_msgs[r["conversation_id"]].append(dict(r))

        fixed = 0
        for conv_id, msgs in conv_msgs.items():
            declared: list[str] = []
            for m in msgs:
                md = json.loads(m["metadata"] or "{}")
                if m["role"] == "assistant" and md.get("tool_calls"):
                    for tc in md["tool_calls"]:
                        if isinstance(tc, dict) and tc.get("id"):
                            declared.append(str(tc["id"]))
                elif m["role"] == "tool":
                    tid = str(md.get("tool_call_id") or "")
                    if tid in declared:
                        declared.remove(tid)
            if not declared:
                continue
            dangling = set(declared)
            for m in msgs:
                md = json.loads(m["metadata"] or "{}")
                if m["role"] != "assistant" or not md.get("tool_calls"):
                    continue
                calls = [
                    tc
                    for tc in md["tool_calls"]
                    if not (isinstance(tc, dict) and str(tc.get("id") or "") in dangling)
                ]
                if len(calls) == len(md["tool_calls"]):
                    continue
                new_md = dict(md)
                if calls:
                    new_md["tool_calls"] = calls
                else:
                    new_md.pop("tool_calls", None)
                conn.execute(
                    "UPDATE messages SET metadata=? WHERE conversation_id=? AND seq=?",
                    (json.dumps(new_md, ensure_ascii=False), conv_id, m["seq"]),
                )
                fixed += 1
            conn.commit()
        return fixed
    finally:
        conn.close()


def main() -> None:
    db = sys.argv[1] if len(sys.argv) > 1 else "data/anyspark.db"
    if not Path(db).exists():
        print(f"[错误] 数据库不存在: {db}")
        sys.exit(1)
    fixed = repair(db)
    if fixed:
        print(f"[完成] 已修复 {fixed} 条消息的悬挂 tool_calls 声明 → {db}")
        print("       建议同时升级到 v4.0.10+（新版本取消收尾会自动补回填，不再产生悬挂）")
    else:
        print(f"[完成] 数据库无悬挂声明，无需修复 → {db}")


if __name__ == "__main__":
    main()