"""
anyspark.core.db — SQLite 连接默认配置（S79 连接收敛）。

背景：25+ 处 store 各自重复 "mkdir parent + sqlite3.connect + PRAGMA WAL" 五行样板，
WAL/timeout 配置散落各包、靠"每处记得写"维持（约定优于配置）。收敛为共享 helper，
配置一处定义（数据存储结构硬编码，DESIGN §1 C 类；过程控制不靠自觉）。

core 不依赖任何第三方包；sqlite3 为 Python 标准库，不违反"不依赖任何包"。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(db_path: str | Path, *, row_factory: bool = True) -> sqlite3.Connection:
    """打开配置好的 SQLite 连接（各 store 统一入口）。

    - 自动创建父目录（嵌入库文件不存在时）
    - check_same_thread=False：嵌入式 SQLite 供 FastAPI 多线程 endpoint 共用
    - timeout=30：busy_timeout，防长事务/未提交删除阻塞其他写（S75 并发锁修复）
    - PRAGMA journal_mode=WAL：读写并发（前端报告并发锁根因修复）
    - row_factory=Row：列名访问（各 store 通用；个别场景可传 row_factory=False）

    :memory: 库：父目录创建无副作用；WAL 无效果但无害（PRAGMA 返回 "memory"）。
    """
    db = str(db_path)
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    if row_factory:
        conn.row_factory = sqlite3.Row
    return conn
