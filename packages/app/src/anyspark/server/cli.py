"""
anyspark.server.cli — 后端启动命令行入口。

    uv run anyspark-server                # 默认 127.0.0.1:8000
    uv run anyspark-server --port 9000    # 指定端口
    uv run anyspark-server --db /tmp/bench.db  # 独立数据文件（benchmark 隔离用）
"""

from __future__ import annotations

import argparse

import uvicorn

from anyspark.server.app import build_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="anyspark-server", description="AnySpark v4 后端")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--db", default=None, help="独立 SQLite 数据文件（默认 data/anyspark.db）")
    args = parser.parse_args()

    if args.db:
        # 独立数据实例：benchmark 等隔离场景（不污染主库）
        uvicorn.run(build_app(db_path=args.db), host=args.host, port=args.port)
    else:
        uvicorn.run("anyspark.server.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
