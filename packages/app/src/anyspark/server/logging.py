"""
anyspark.server.logging — 日志机制（最小可用版）。

- 标准库 logging + RotatingFileHandler：写入 data/logs/anyspark.log（已 gitignore）
- 同时保留控制台输出（黑窗口可见）
- 覆盖：请求访问 / 工具调用 / 事件 / 错误
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_configured = False
# S109：frozen → exe 同目录 data/logs（与 app 数据根一致）；开发 → 项目 data/logs
if getattr(sys, "frozen", False):
    _LOG_DIR = Path(sys.executable).resolve().parent / "data" / "logs"
else:
    _LOG_DIR = Path(__file__).resolve().parents[5] / "data" / "logs"
LOG_DIR = _LOG_DIR
LOG_FILE = LOG_DIR / "anyspark.log"

# 应用 logger（统一出口）
logger = logging.getLogger("anyspark")


def setup_logging(level: int = logging.INFO) -> None:
    """初始化日志：文件（轮转）+ 控制台。幂等，重复调用无害。"""
    global _configured
    if _configured:
        return
    _configured = True

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger.setLevel(level)

    # 文件 handler（5MB 轮转，保留 3 份）
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    # 控制台 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    # uvicorn 访问日志也进文件（便于事后排查请求）
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uv = logging.getLogger(name)
        uv.setLevel(logging.INFO)
        uv.addHandler(file_handler)


def log_path() -> str:
    """返回日志文件路径（供 UI/提示展示）。"""
    return str(LOG_FILE)
