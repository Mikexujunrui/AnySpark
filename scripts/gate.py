"""
AnySpark v4 — 总闸（一次性跑全部门禁）。

运行：uv run python scripts/gate.py
覆盖：ruff check / ruff format / mypy / pytest（后端）+ tsc / eslint / build（前端，仅当
frontend/ 存在——本仓库已拆分前端，无 frontend/ 时自动跳过前端门禁）。
"""

from __future__ import annotations

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


def main() -> int:
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
        "scripts",
    ]
    failed = False

    # 后端门禁
    rc, _ = _run(["uv", "run", "ruff", "check", *py_pkgs], ROOT)
    failed |= rc != 0
    rc, _ = _run(["uv", "run", "ruff", "format", "--check", *py_pkgs], ROOT)
    failed |= rc != 0
    rc, _ = _run(["uv", "run", "mypy"], ROOT)
    failed |= rc != 0
    rc, _ = _run(["uv", "run", "pytest"], ROOT)
    failed |= rc != 0

    # 前端门禁
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
