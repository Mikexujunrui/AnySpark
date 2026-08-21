"""修复 DB 里所有会话消息的 tool_calls 配对残缺（S200）。

背景：历史版本（S170 之前的打包版）在取消/异常中断时可能给会话留下
"assistant 声明了 tool_calls 但无对应 tool 结果"的悬挂声明——再次请求
该会话历史时 OpenAI/DeepSeek 严格模式报 400
（insufficient tool messages following tool_calls message）。

**正常情况无需手动运行**：新版后端（v4.0.11+）启动时自动调用
SqliteConversationStore.repair_dangling_decls() 清理（幂等，首次启动即完成）。
本脚本仅在需要单独清理（如旧部署就地修复、手动巡检）时使用。

用法：python scripts/repair_tool_pairs.py [db_path]（缺省 data/anyspark.db）
幂等：已修剪的元数据再跑无变化。
"""

from __future__ import annotations

import sys
from pathlib import Path

from anyspark.store.sqlite import SqliteConversationStore


def main() -> None:
    db = sys.argv[1] if len(sys.argv) > 1 else "data/anyspark.db"
    if not Path(db).exists():
        print(f"[错误] 数据库不存在: {db}")
        sys.exit(1)
    store = SqliteConversationStore(db)
    try:
        fixed = store.repair_dangling_decls()
    finally:
        store.close()
    if fixed:
        print(f"[完成] 已修复 {fixed} 条消息的悬挂 tool_calls 声明 → {db}")
        print("       新版后端启动时也会自动清理，无需手动重复执行")
    else:
        print(f"[完成] 数据库无悬挂声明，无需修复 → {db}")


if __name__ == "__main__":
    main()
