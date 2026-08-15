"""
anyspark.desktop — 桌面壳（轻量自研）。

启动本机 FastAPI 后端 + Python WebView 加载前端产物。
不引入 Electron/Tauri。PyInstaller 打包时后端在前端同进程。

S110 修复：必须加载 http://127.0.0.1:{port}/（后端同端口 serve 前端 dist，
FastAPI mount StaticFiles）——**不能**用 file:// 加载 index.html：
Vite 构建产物的 /assets/* 绝对路径在 file:// 协议下解析到磁盘根目录，
找不到 JS/CSS → 后端已起但窗口仍白屏（/assets 绝对路径在 file:// 下解析到磁盘根目录）。
"""

from __future__ import annotations

import threading


def _start_backend(port: int) -> None:
    """在子线程启动 FastAPI 后端（uvicorn）。"""
    import uvicorn

    from anyspark.server.app import app

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.run()


def _wait_backend(port: int, timeout: float = 30.0) -> bool:
    """等待后端就绪（轮询 health 端点）。

    返回 False 表示超时（端口可能被其他程序占用）——调用方仍应打开页面，
    让用户看到明确错误而非静默无响应。
    """
    import time
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main() -> None:
    import webview

    # S111：启用 WebView 下载（默认 False → 导出 txt/md/epub 被静默取消，
    # 文件不保存）。开启后点导出弹「另存为」对话框（初始目录=系统下载夹，
    # 文件名=服务端 Content-Disposition），保存位置由用户自己选。
    webview.settings["ALLOW_DOWNLOADS"] = True

    port = 8790
    t = threading.Thread(target=_start_backend, args=(port,), daemon=True)
    t.start()

    # 等后端就绪（超时也照常打开：若端口被已运行实例占用，页面仍可访问）
    _wait_backend(port)

    # 前端由后端同端口 serve（S88 生产模式 mount StaticFiles）——
    # 勿改回 file://（见模块 docstring，S110 白屏修复）。
    url = f"http://127.0.0.1:{port}/"
    webview.create_window("AnySpark v4", url, width=1280, height=800)
    webview.start()


if __name__ == "__main__":
    main()
