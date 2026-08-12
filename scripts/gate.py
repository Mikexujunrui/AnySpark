"""
AnySpark v4 — 总闸（按改动面分层门禁，S96 升级）。

运行：
  uv run python scripts/gate.py                  # 自动判定：按 git diff 改动面选层
  uv run python scripts/gate.py --all            # 强制全量（发布/复检/大改动）
  uv run python scripts/gate.py --python         # 强制后端层（ruff+mypy+pytest）
  uv run python scripts/gate.py --frontend       # 强制前端层（tsc+lint+build）
  uv run python scripts/gate.py --pytest <路径>   # pytest 只跑子集（默认全量）

自动分层规则（S96 机械判定，替代人脑判定——S88b 打包脚本漏 format 事故的机制堵截）：
  - 命中敏感文件（pyproject.toml / uv.lock / package.json / scripts/package_release.py
    等影响面广的）→ 强制全量
  - 只改 frontend/* → 前端层；只改 *.py → 后端层；前后端都有 → 全量
  - 纯文档（docs/*.md 等）→ 无需门禁，跳过
后端门禁：ruff check / ruff format --check / mypy / pytest（--pytest 可缩子集）
前端门禁：tsc / eslint / build（仅当 frontend/ 存在）
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Windows 下 npm 是 npm.cmd
NPM = "npm.cmd" if sys.platform == "win32" else "npm"


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    print(f"\n=== {' '.join(cmd)} ===")
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    out = (proc.stdout or "") + (proc.stderr or "")
    # 只打印尾部（避免刷屏）
    lines = out.strip().splitlines()
    tail = "\n".join(lines[-6:]) if lines else ""
    if proc.returncode != 0:
        print(tail)
        print(f"❌ FAILED ({proc.returncode})")
    else:
        print(tail or "(ok)")
        print("✅ ok")
    return proc.returncode, out


# 影响面广的文件：改动命中即强制全量（S96——S88b 打包脚本漏 format 事故的机制堵截）
SENSITIVE_FILES = {
    "pyproject.toml",
    "uv.lock",
    "frontend/package.json",
    "frontend/package-lock.json",
    ".gitattributes",
    "scripts/package_release.py",
}


def _changed_files() -> list[str]:
    """工作区相对 HEAD 的全部改动文件（已跟踪 diff + 未跟踪文件）。"""
    out = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    tracked = [line for line in out.stdout.splitlines() if line.strip()]
    out2 = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    untracked = [line for line in out2.stdout.splitlines() if line.strip()]
    # 临时/工具目录不计入改动面（评审残留 .review_tmp/、remote-pi 配置 .pi/ 等）
    ignored_prefix = (".review_tmp/", ".pi/")
    return [f for f in tracked + untracked if not f.startswith(ignored_prefix)]


def _classify(changed: list[str]) -> str:
    """按改动文件自动判定门禁层：all / python / frontend / none（纯文档）。"""
    if any(
        f in SENSITIVE_FILES or (f.startswith("packages/") and f.endswith("/pyproject.toml"))
        for f in changed
    ):
        return "all"
    has_py = any(f.endswith(".py") for f in changed)
    has_fe = any(f.startswith("frontend/") for f in changed)
    if has_py and has_fe:
        return "all"
    if has_py:
        return "python"
    if has_fe:
        return "frontend"
    return "none"


def _print_preflight() -> None:
    """提交前状态核查（S70 加固 + S96 diff 归属）：输出最近提交 + 改动归属清单。

    多会话共享工作区：跑 gate 前先看对方动态（撞号/撞文件立即让位），再逐文件
    核对「该文件的未提交改动是否全部属于本次任务」——只显式 add 本任务文件，
    不带走并行会话的未提交改动（S81/S89 裹挟事故的机制性提醒）。
    """
    print("\n" + "=" * 50)
    print("【提交前核查】最近提交（看并行会话动态，撞阶段号立即让位）：")
    subprocess.run(["git", "log", "--oneline", "-3"], cwd=ROOT)
    print("\n【提交前核查】改动归属（逐文件确认：该文件未提交改动是否全部属于本次任务？）")
    print("  含并行会话改动的文件，禁止 git add 该文件（S81/S89 裹挟教训）：")
    subprocess.run(["git", "status", "--short"], cwd=ROOT)
    print("\n【提交前核查】改动文件清单（diff vs HEAD + 未跟踪）：")
    for f in _changed_files():
        print(f"  {f}")
    print("=" * 50 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="AnySpark v4 总闸（分层门禁）")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true", help="强制全量（发布/复检/大改动）")
    group.add_argument("--python", action="store_true", help="强制后端层（ruff+mypy+pytest）")
    group.add_argument("--frontend", action="store_true", help="强制前端层（tsc+lint+build）")
    parser.add_argument(
        "--pytest", nargs="+", default=None, metavar="PATH", help="pytest 只跑指定路径（默认全量）"
    )
    args = parser.parse_args()

    # S70：提交前核查（强制输出，逼确认并行边界后再跑门禁）
    _print_preflight()

    # S96：分层判定（显式参数优先；缺省按改动面机械判定）
    if args.all or args.python or args.frontend:
        mode = "all" if args.all else ("python" if args.python else "frontend")
    else:
        mode = _classify(_changed_files())
    mode_names = {"all": "全量", "python": "后端层", "frontend": "前端层", "none": "纯文档（跳过）"}
    print(
        f"\n【分层门禁】本次判定：{mode_names.get(mode, mode)}"
        + (f"（--pytest 子集: {' '.join(args.pytest)}）" if args.pytest else "")
    )
    if mode == "none":
        print("纯文档/非代码改动，无需跑门禁。")
        return 0

    py_pkgs = [
        "packages/core",
        "packages/app",
        "packages/align",
        "packages/explore",
        "packages/check",
        "packages/template",
        "packages/graph",
        "packages/workflow",
        "packages/review",
        "packages/play",
        "packages/library",
        "scripts",
    ]
    failed = False

    # 后端门禁（python 层或全量）
    if mode in ("python", "all"):
        rc, _ = _run(["uv", "run", "ruff", "check", *py_pkgs], ROOT)
        failed |= rc != 0
        rc, _ = _run(["uv", "run", "ruff", "format", "--check", *py_pkgs], ROOT)
        failed |= rc != 0
        rc, _ = _run(["uv", "run", "mypy"], ROOT)
        failed |= rc != 0
        pytest_cmd = (
            ["uv", "run", "pytest", *args.pytest] if args.pytest else ["uv", "run", "pytest"]
        )
        rc, _ = _run(pytest_cmd, ROOT)
        failed |= rc != 0

    # 前端门禁（frontend 层或全量）
    if mode in ("frontend", "all"):
        fe = ROOT / "frontend"
        if fe.exists():
            rc, _ = _run([NPM, "run", "typecheck"], fe)
            failed |= rc != 0
            rc, _ = _run([NPM, "run", "lint"], fe)
            failed |= rc != 0
            rc, _ = _run([NPM, "run", "build"], fe)
            failed |= rc != 0

    print("\n" + "=" * 40)
    if failed:
        print("总闸：❌ 有失败项")
        return 1
    print("总闸：✅ 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
