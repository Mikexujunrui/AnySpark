"""
anyspark.server.cli — 后端启动命令行入口。

    uv run anyspark-server              # 默认 127.0.0.1:8000
    uv run anyspark-server --port 9000  # 指定端口
"""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(prog="anyspark-server", description="AnySpark v4 后端")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run("anyspark.server.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
