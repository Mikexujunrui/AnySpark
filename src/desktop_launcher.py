# SPDX-License-Identifier: AGPL-3.0-or-later
"""Cross-platform desktop shell for the packaged AnySpark application.

The React frontend is rendered inside the operating system WebView. The shell
owns the local FastAPI server, so closing the visible application also shuts
down its background process cleanly.
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, BinaryIO

# Match server.py's bootstrap so top-level core/routes imports work when frozen.
if getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(getattr(sys, "_MEIPASS", ""))))
else:
    sys.path.insert(0, str(Path(__file__).parent))

import uvicorn

from core.config import APP_VERSION, DATA_DIR, config
from core.desktop_bridge import clear_activation, wait_for_activation

logger = logging.getLogger(__name__)

APP_NAME = "火花 AnySpark"
APP_URL = f"http://127.0.0.1:{config.server.port}"
HEALTH_URL = f"{APP_URL}/api/health"
ACTIVATE_URL = f"{APP_URL}/api/desktop/activate"
LOCK_PATH = DATA_DIR.parent / ".anyspark.lock"
WEBVIEW_STORAGE = DATA_DIR.parent / "webview"

# pywebview exposes SAVE as IntEnum value 30.  Keep the trusted export bridge
# usable in headless/backend environments where the optional desktop runtime is
# deliberately not installed; packaged desktop builds still use the real enum.
_FALLBACK_SAVE_DIALOG = 30

STARTUP_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    :root { color-scheme: dark; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; display: grid; place-items: center;
      background: #090b10; color: #ecf4ff; }
    main { text-align: center; padding: 36px; }
    .spark { width: 54px; height: 54px; margin: 0 auto 22px; border-radius: 17px;
      display: grid; place-items: center; font-size: 30px; color: #67d9ff;
      border: 1px solid #1d7898; background: #082332; box-shadow: 0 0 36px #0aa4dc33; }
    h1 { margin: 0 0 10px; font-size: 22px; font-weight: 650; }
    p { margin: 0; color: #8d99a8; font-size: 14px; }
    .bar { width: 220px; height: 3px; margin: 24px auto 0; overflow: hidden;
      border-radius: 4px; background: #1b2530; }
    .bar::after { content: ""; display: block; width: 42%; height: 100%; border-radius: inherit;
      background: #21b9eb; animation: loading 1.15s ease-in-out infinite; }
    @keyframes loading { from { transform: translateX(-110%); } to { transform: translateX(350%); } }
  </style>
</head>
<body><main>
  <div class="spark">✦</div>
  <h1>火花 AnySpark</h1>
  <p>正在启动本地创作引擎…</p>
  <div class="bar"></div>
</main></body></html>"""


def _health_payload(timeout: float = 0.8) -> dict:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, urllib.error.URLError):
        return {}


def _is_anyspark_running(timeout: float = 0.8) -> bool:
    payload = _health_payload(timeout)
    return bool(payload.get("status") == "ok" and payload.get("app") == "AnySpark")


def _is_desktop_server_ready(timeout: float = 0.8) -> bool:
    payload = _health_payload(timeout)
    return bool(
        payload.get("status") == "ok"
        and payload.get("app") == "AnySpark"
        and payload.get("desktop_shell") is True
        and payload.get("version") == APP_VERSION
    )


def _activate_existing(timeout: float = 0.8) -> bool:
    request = urllib.request.Request(ACTIVATE_URL, data=b"{}", method="POST")
    request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return bool(payload.get("status") == "ok")
    except (OSError, ValueError, urllib.error.URLError):
        return False


def _show_process_conflict() -> None:
    """Give legacy users a visible way to understand why startup stopped."""
    import webview

    conflict_html = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
    <style>body{{font:15px -apple-system,sans-serif;background:#0b0d12;color:#e8edf3;
    padding:48px;line-height:1.7}}main{{max-width:620px;margin:auto}}h1{{font-size:22px;color:#ffd28c}}
    code{{color:#8fdcff}}</style><main><h1>旧版 AnySpark 仍在运行</h1>
    <p>请先从旧版菜单栏图标退出，或在“活动监视器/任务管理器”中结束 AnySpark，
    然后重新打开 {APP_VERSION} 独立窗口版。</p>
    <p>当前本地端口：<code>{config.server.port}</code></p></main></html>"""
    webview.create_window(
        f"{APP_NAME} — 需要退出旧版",
        html=conflict_html,
        width=680,
        height=390,
        min_size=(560, 320),
        background_color="#0b0d12",
    )
    webview.start(gui="edgechromium" if os.name == "nt" else "cocoa", private_mode=True)


class InstanceLock:
    """One process per AnySpark user-data directory on macOS and Windows."""

    def __init__(self, path: Path = LOCK_PATH) -> None:
        self.path = path
        self._file: BinaryIO | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_file = self.path.open("a+b")
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"0")
            lock_file.flush()
        lock_file.seek(0)

        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
        except (OSError, BlockingIOError):
            lock_file.close()
            return False

        self._file = lock_file
        return True

    def release(self) -> None:
        if self._file is None:
            return
        try:
            self._file.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
            else:
                import fcntl

                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
        except OSError:
            pass
        self._file.close()
        self._file = None


class DesktopApi:
    """Small trusted bridge for native desktop-only operations."""

    def __init__(self, controller: DesktopController) -> None:
        self.controller = controller

    def export_book(self, book_id: str, export_format: str) -> dict:
        """Show the OS save panel, write the export, and return its exact path."""

        from core.archive import export_spark
        from core.exporter import export_docx, export_epub, export_txt
        from data.json_store import json_store

        save_dialog: Any
        try:
            import webview

            save_dialog = webview.FileDialog.SAVE
        except ModuleNotFoundError:
            save_dialog = _FALLBACK_SAVE_DIALOG

        allowed = {"txt", "docx", "epub", "spark"}
        if export_format not in allowed:
            return {"saved": False, "error": "不支持的导出格式"}
        try:
            book = json_store.get_book(book_id)
            chapters = [json_store._chapter_view(ch) for ch in json_store.load_chapters(book_id)]
            if not chapters:
                return {"saved": False, "error": "暂无章节可导出"}
            title = str(book.get("title", "未命名"))
            safe_title = re.sub(r'[\\/:*?"<>|]+', "_", title).strip(" .") or "未命名"
            filename = f"{safe_title}.{export_format}"
            selected = self.controller.window.create_file_dialog(
                save_dialog,
                save_filename=filename,
            )
            if not selected:
                return {"saved": False, "cancelled": True}
            raw_path = selected[0] if isinstance(selected, (list, tuple)) else selected
            path = Path(str(raw_path)).expanduser().resolve()

            if export_format == "spark":
                export_spark(book_id, output_path=str(path))
            elif export_format == "docx":
                path.write_bytes(export_docx(title, chapters))
            elif export_format == "epub":
                path.write_bytes(export_epub(title, chapters))
            else:
                path.write_bytes(export_txt(title, chapters))
            return {"saved": True, "path": str(path), "filename": path.name}
        except Exception as exc:
            logger.exception("Native export failed")
            return {"saved": False, "error": str(exc)[:300]}


class DesktopController:
    """Own the FastAPI thread and the single visible desktop window."""

    def __init__(self) -> None:
        self.server: uvicorn.Server | None = None
        self.server_thread: threading.Thread | None = None
        self.window: Any = None
        self._shutdown_started = threading.Event()
        self._server_error = ""
        self.desktop_api = DesktopApi(self)

    def start_server(self) -> None:
        self.server_thread = threading.Thread(target=self._run_server, name="AnySparkServer", daemon=True)
        self.server_thread.start()

    def _run_server(self) -> None:
        try:
            from server import app

            server_config = uvicorn.Config(
                app,
                host="127.0.0.1",
                port=config.server.port,
                timeout_keep_alive=300,
                log_level="info",
            )
            self.server = uvicorn.Server(server_config)
            self.server.run()
        except Exception as exc:  # pragma: no cover - defensive frozen-app boundary
            self._server_error = f"{type(exc).__name__}: {exc}"
            logger.exception("Desktop server failed")

    def _error_html(self) -> str:
        detail = html.escape(self._server_error or f"端口 {config.server.port} 被占用或服务启动失败。")
        log_path = html.escape(str(DATA_DIR / "logs" / "server.log"))
        return f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8">
        <style>body{{font:15px -apple-system,sans-serif;background:#0b0d12;color:#e8edf3;
        padding:60px;line-height:1.7}}main{{max-width:720px;margin:auto}}h1{{color:#ff8d8d}}
        code{{word-break:break-all;color:#8fdcff}}</style>
        <main><h1>AnySpark 启动失败</h1><p>{detail}</p>
        <p>请完全退出旧版 AnySpark 后重试。</p><p>日志：<code>{log_path}</code></p></main></html>"""

    def bootstrap_window(self) -> None:
        for _ in range(160):
            if _is_desktop_server_ready():
                self.window.load_url(APP_URL)
                threading.Thread(target=self._activation_loop, name="AnySparkActivation", daemon=True).start()
                return
            if self.server_thread is not None and not self.server_thread.is_alive():
                break
            time.sleep(0.05)
        self.window.load_html(self._error_html())

    def _activation_loop(self) -> None:
        clear_activation()
        while not self._shutdown_started.is_set():
            if not wait_for_activation(0.5):
                continue
            try:
                self.window.show()
                self.window.restore()
            except Exception:
                logger.debug("Unable to focus desktop window", exc_info=True)

    def shutdown(self) -> None:
        if self._shutdown_started.is_set():
            return
        self._shutdown_started.set()
        if self.server is not None:
            self.server.should_exit = True
        if self.server_thread is not None and self.server_thread.is_alive():
            self.server_thread.join(timeout=8)

    def run(self) -> None:
        import webview

        self.start_server()
        self.window = webview.create_window(
            f"{APP_NAME} {APP_VERSION}",
            html=STARTUP_HTML,
            width=1440,
            height=900,
            min_size=(1050, 680),
            background_color="#090b10",
            text_select=True,
            zoomable=True,
            js_api=self.desktop_api,
        )
        self.window.events.closed += self.shutdown
        WEBVIEW_STORAGE.mkdir(parents=True, exist_ok=True)
        try:
            webview.start(
                self.bootstrap_window,
                gui="edgechromium" if os.name == "nt" else "cocoa",
                private_mode=False,
                storage_path=str(WEBVIEW_STORAGE),
            )
        finally:
            self.shutdown()


def _run_headless() -> int:
    from server import app as server_app

    uvicorn.run(
        server_app,
        host="127.0.0.1",
        port=config.server.port,
        timeout_keep_alive=300,
        log_level="info",
    )
    return 0


def main() -> int:
    if "--headless" in sys.argv:
        return _run_headless()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    instance_lock = InstanceLock()
    if not instance_lock.acquire():
        for _ in range(20):
            if _activate_existing():
                return 0
            time.sleep(0.1)
        _show_process_conflict()
        return 0

    try:
        # A legacy browser-based build may be using the same server port but a
        # different lock. Activate it instead of starting a conflicting server.
        if _is_anyspark_running():
            if not _activate_existing():
                _show_process_conflict()
            return 0
        DesktopController().run()
        return 0
    finally:
        instance_lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
