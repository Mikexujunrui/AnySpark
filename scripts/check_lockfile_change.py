#!/usr/bin/env python
# pre-commit hook: lockfile changes require explicit approval.
#
# Supply-chain guard (pi philosophy): dependency lockfiles are ground
# truth. A changed lockfile is a real dependency decision and must be
# reviewed - pass ALLOW_LOCKFILE_CHANGE=1 in the environment to allow it
# through (e.g. after an intentional dependency bump).
#
# Usage (pre-commit local hook):
#   entry: python scripts/check_lockfile_change.py
#   files: ^(requirements.lock|frontend/package-lock.json)$

import os
import sys

LOCKFILES = {"requirements.lock", "package-lock.json"}


def main() -> int:
    changed = [f for f in sys.argv[1:] if os.path.basename(f) in LOCKFILES]
    if not changed:
        return 0
    if os.environ.get("ALLOW_LOCKFILE_CHANGE") == "1":
        print(f"[lockfile-guard] ALLOW_LOCKFILE_CHANGE=1 放行: {', '.join(changed)}")
        return 0
    print(
        f"[lockfile-guard] 锁文件变更被拦截: {', '.join(changed)}\n"
        "锁文件是依赖 ground truth，变更需要审查。\n"
        "如果是故意的依赖升级，请设置 ALLOW_LOCKFILE_CHANGE=1 提交，\n"
        "并同时在 commit message 中说明变更原因。"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
