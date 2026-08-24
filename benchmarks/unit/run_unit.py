"""单元层入口：跑机制能力测试集，输出报告。

用法：
    uv run python -m benchmarks.unit.run_unit --spawn          # 自动起独立后端（隔离库）
    uv run python -m benchmarks.unit.run_unit --base http://127.0.0.1:9000  # 连外部后端
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx2 as httpx  # S66: httpx2（下一代，API 兼容）

ROOT = Path(__file__).resolve().parent.parent.parent
logger = logging.getLogger(__name__)


def _wait_health(base: str, timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(f"{base}/api/health", timeout=3, trust_env=False).status_code == 200:
                return True
        except httpx.HTTPError:
            logger.debug("后端尚未就绪，等待重试")
        time.sleep(2)
    return False


def _spawn_backend(port: int) -> tuple[subprocess.Popen[bytes], Path]:
    db = Path(tempfile.mkdtemp()) / "bench.db"
    # 后端是主项目的一部分：用主项目环境启动（uv run anyspark-server）
    # 注意：uv run 会再 spawn 子进程——清理时必须杀整棵进程树，否则留下孤儿占端口/db
    kwargs: dict[str, object] = {}
    if os.name != "nt":
        kwargs["start_new_session"] = True
    # 清除 VIRTUAL_ENV：benchmark 环境跑时子进程会继承 benchmarks\.venv，
    # 导致 uv 环境判定混乱（502）——让 uv 在 ROOT 自行解析主项目环境
    clean_env = dict(os.environ)
    clean_env.pop("VIRTUAL_ENV", None)
    proc = subprocess.Popen(
        ["uv", "run", "anyspark-server", "--port", str(port), "--db", str(db)],
        cwd=ROOT,
        env=clean_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs,
    )
    base = f"http://127.0.0.1:{port}"
    if not _wait_health(base):
        _stop_tree(proc)
        raise RuntimeError(f"独立后端未在 {port} 就绪")
    return proc, db


def _stop_tree(proc: subprocess.Popen[bytes]) -> None:
    """杀整棵进程树（uv run 会 spawn 后端子进程，单杀 uv 会留孤儿）。"""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            proc.kill()


def main() -> None:
    parser = argparse.ArgumentParser(description="AnySpark benchmark · 单元层")
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="后端地址")
    parser.add_argument("--spawn", action="store_true", help="自动启动隔离后端（独立 db）")
    parser.add_argument("--port", type=int, default=9000, help="--spawn 时的端口")
    parser.add_argument("--task", default=None, help="只跑指定任务（如 T1）")
    args = parser.parse_args()

    proc: subprocess.Popen[bytes] | None = None
    db_path: Path | None = None
    try:
        base = args.base
        if args.spawn:
            proc, db_path = _spawn_backend(args.port)
            base = f"http://127.0.0.1:{args.port}"
            print(f"[spawn] 隔离后端已启动: {base} (db={db_path})")
        else:
            if not _wait_health(base, timeout=10):
                print(f"[错误] 后端不可达: {base}（可用 --spawn 自动启动隔离实例）")
                sys.exit(2)

        from benchmarks.unit.core import ApiClient, Reporter
        from benchmarks.unit.registry import REGISTRY

        api = ApiClient(base)
        reporter = Reporter()

        for task_id, name, fn in REGISTRY:
            if args.task and task_id != args.task:
                continue
            print(f"▶ {task_id} {name} ...", flush=True)
            try:
                passed, metrics, detail = fn(api)
            except Exception as exc:  # noqa: BLE001  任务自身异常 = FAIL（记详情）
                reporter.record(task_id, name, False, {}, f"异常: {exc}")
                print(f"  ✗ {exc}")
                continue
            reporter.record(task_id, name, passed, metrics, detail)
            flag = "✅" if passed else "❌"
            print(f"  {flag} {metrics}")

        report_path = reporter.write("unit", env={"backend": base})
        print()
        print(f"报告: {report_path}")
        print(f"通过: {sum(1 for r in reporter.results if r.passed)}/{len(reporter.results)}")
    finally:
        if proc is not None:
            _stop_tree(proc)
            print("[spawn] 隔离后端已停止")


if __name__ == "__main__":
    main()
