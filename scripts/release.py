#!/usr/bin/env python
# One-command release: bump version → update CHANGELOG → run check → tag.
#
#   python scripts/release.py --dry-run          # 演练：只输出计划，不改任何文件
#   python scripts/release.py patch              # bump patch (3.2.1 → 3.2.2)
#   python scripts/release.py minor              # bump minor (3.2.1 → 3.3.0)
#   python scripts/release.py major              # bump major (3.2.1 → 4.0.0)
#
# After tagging, CI (release.yml, tag-triggered) builds and publishes.
# Local build is NOT part of this script — run `_build.ps1` separately if
# you need a local artifact.

import re
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"


def read_version() -> str:
    with open(PYPROJECT, "rb") as f:
        return tomllib.load(f)["project"]["version"]


def bump(version: str, part: str) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def write_version(new_version: str) -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    text = re.sub(r'^version = ".*"$', f'version = "{new_version}"', text, count=1, flags=re.M)
    PYPROJECT.write_text(text, encoding="utf-8")


def prepend_changelog(new_version: str) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = (
        f"\n## {new_version} - {today}\n\n"
        f"- 版本发布（由 scripts/release.py 生成，详细信息见 git log）。\n"
    )
    text = CHANGELOG.read_text(encoding="utf-8")
    # 插到第一个 "## " 之前（保留文件头说明）
    m = re.search(r"^## ", text, flags=re.M)
    if m:
        text = text[: m.start()] + entry + "\n" + text[m.start():]
    else:
        text = text + entry
    CHANGELOG.write_text(text, encoding="utf-8")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv[1:]
    if not args:
        print("用法: python scripts/release.py [--dry-run] <patch|minor|major>")
        return 2

    part = args[0]
    if part not in ("patch", "minor", "major"):
        print(f"未知版本类型: {part}")
        return 2

    current = read_version()
    new_version = bump(current, part)
    tag = f"v{new_version}"

    print(f"当前版本: {current}")
    print(f"新版本:   {new_version}")
    print(f"tag:      {tag}")
    print(f"dry-run:  {dry_run}")
    print()

    if dry_run:
        print("[dry-run] 将执行:")
        print(f"  1. pyproject.toml version → {new_version}")
        print(f"  2. CHANGELOG.md 插入 {new_version} 条目")
        print(f"  3. 运行 scripts/check.py")
        print(f"  4. git tag {tag}")
        return 0

    write_version(new_version)
    prepend_changelog(new_version)
    print(f"✓ 版本已 bump 至 {new_version}")

    print("→ 运行 check gate...")
    r = subprocess.run([sys.executable, "scripts/check.py", "--py-only", "--fast"], cwd=ROOT)
    if r.returncode != 0:
        print("✗ check gate 失败，中止发布。请先修复问题。")
        return 1

    subprocess.run(["git", "add", "pyproject.toml", "CHANGELOG.md"], cwd=ROOT, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"chore: release {new_version} (via scripts/release.py)"],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(["git", "tag", tag], cwd=ROOT, check=True)
    print(f"✓ 已提交并打 tag {tag}")
    print("→ 推送: git push && git push --tags（触发 release.yml CI 发布）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
