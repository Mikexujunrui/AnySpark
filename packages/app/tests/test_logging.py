"""anyspark.server.logging — 日志机制测试。"""

import logging

from anyspark.server.logging import log_path, logger, setup_logging


def test_setup_logging_idempotent() -> None:
    """重复调用 setup_logging 不重复加 handler（幂等）。"""
    setup_logging()
    setup_logging()
    handlers = [h for h in logger.handlers if isinstance(h, logging.Handler)]
    # 文件 + 控制台，各一个
    assert sum(1 for h in handlers if "RotatingFile" in type(h).__name__) == 1
    assert sum(1 for h in handlers if "Stream" in type(h).__name__) == 1


def test_log_path_points_to_file() -> None:
    path = log_path()
    assert path.endswith("anyspark.log")
    assert "data" in path and "logs" in path


def test_logger_writes() -> None:
    """logger 能发出 info 日志（不抛错）。"""
    logger.info("test message %s", "ok")
    assert True
