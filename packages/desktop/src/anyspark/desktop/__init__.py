"""
anyspark.desktop — 桌面壳（轻量自研）。

启动本机 FastAPI 后端 + Python WebView 加载前端产物（dist/index.html）。
不引入 Electron/Tauri。PyInstaller 打包时后端在前端同进程。
"""

from __future__ import annotations

import threading
from pathlib import Path


def _start_backend(port: int) -> None:
    """在子线程启动 FastAPI 后端（uvicorn）。"""
    import uvicorn

    from anyspark.server.app import app

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.run()


def main() -> None:
    import webview

    # 前端产物：frontend/dist/index.html（相对项目根）
    project_root = Path(__file__).resolve().parents[5]
    frontend_dist = project_root / "frontend" / "dist" / "index.html"

    port = 8790
    t = threading.Thread(target=_start_backend, args=(port,), daemon=True)
    t.start()

    url = frontend_dist.as_uri() if frontend_dist.exists() else f"http://127.0.0.1:{port}/"
    webview.create_window("AnySpark v4", url, width=1280, height=800)
    webview.start()


if __name__ == "__main__":
    main()
