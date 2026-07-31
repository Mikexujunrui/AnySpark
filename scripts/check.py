#!/usr/bin/env python
# Unified check gate — one command, CI-equivalent.
#
#   python scripts/check.py            # full: ruff + mypy gate + pytest + tsc + eslint
#   python scripts/check.py --fast     # skip pytest (lint + types only)
#   python scripts/check.py --py-only  # python side only (no frontend)
#
# Exit code 0 = all green. Matches .github/workflows/ci.yml step-for-step
# so the local gate and CI cannot drift apart.

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cmd: list[str], cwd: Path, label: str, env: dict | None = None) -> bool:
    print(f"\n── {label} ──")
    try:
        r = subprocess.run(cmd, cwd=cwd, env=env)
    except FileNotFoundError as e:
        print(f"  ✗ 命令不可用: {e}")
        return False
    if r.returncode != 0:
        print(f"  ✗ {label} 失败 (exit={r.returncode})")
        return False
    print(f"  ✓ {label}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="统一 check gate")
    ap.add_argument("--fast", action="store_true", help="跳过 pytest")
    ap.add_argument("--py-only", action="store_true", help="只跑 Python 侧")
    args = ap.parse_args()

    ok = True
    ok &= run([sys.executable, "-m", "ruff", "check", "src/", "tests/"], ROOT, "ruff lint")
    # mypy gate needs a working interpreter with mypy installed; on WSL pass
    # the same interpreter that's running this script.
    env = dict(os.environ)
    env.setdefault("PYTHON", sys.executable)
    ok &= run(["bash", "scripts/mypy_gate.sh"], ROOT, "mypy gate", env=env)
    if not args.fast:
        ok &= run([sys.executable, "-m", "pytest", "tests/", "-q"], ROOT, "pytest")
    if not args.py_only:
        ok &= run(["npx", "tsc", "--noEmit"], ROOT / "frontend", "tsc")
        ok &= run(["npm", "run", "lint"], ROOT / "frontend", "eslint")

    print("\n" + ("✅ check gate 全绿" if ok else "❌ check gate 有失败项"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
