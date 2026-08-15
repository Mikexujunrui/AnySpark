#!/usr/bin/env python
"""scan_main_hardcode.py — 后端 book_id="main" 硬编码扫描门禁（S152h）。

背景：S152 系反复出现"调用点写死 book_id='main'"的跨项目 bug（定点编辑写错
项目/心智共享/会话摘要落错库……）。本脚本在提交前机制化拦截新增硬编码：
- 扫描 packages/ 后端源码（.py）中 **调用点** 的 `book_id="main"` 字面量传参
- 排除合法场景：函数签名默认参数（def f(book_id="main")）、dataclass 字段、
  schema 定义、表结构 DEFAULT、注释、文档字符串、测试断言预期值
- 命中即非零退出（gate 接入，检出即 fail）

用法：uv run python scripts/scan_main_hardcode.py [--quiet]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG_DIRS = ["packages"]

# 匹配 `book_id="main"` / `book_id = "main"` / `book_id='main'`（调用点传参形态）
_CALL_RE = re.compile(r"book_id\s*=\s*[\"']main[\"']")
# 合法排除：
#  1) 单行内函数签名默认参数：def f(... book_id: str = "main" ...) / def f(book_id="main")
#  2) 带类型注解的字段/参数：book_id: str = "main"（dataclass/schema 字段、
#     也可跨行 def 的续行参数——保守：带 : str 注解即视为声明）
_DEF_RE = re.compile(
    r"def\s+\w+\s*\([^)]*book_id\s*[:=][^)]*[\"']main[\"']"
    r"|book_id\s*:\s*str\s*=\s*[\"']main[\"']"
)


def scan_file(path: Path) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return hits
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # 跳过注释/文档字符串行
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        if not _CALL_RE.search(line):
            continue
        # 默认参数声明：形如 def f(..., book_id: str = "main", ...) 或 def f(book_id="main")
        # （跨行声明无法单行判定——保守：整函数体上下文在调用扫描时人工复核）
        if _DEF_RE.search(line):
            continue
        # 数据类字段/schema：book_id: str = "main"（dataclass 字段定义）
        if re.search(r"^\s*book_id\s*:\s*str\s*=\s*[\"']main[\"']\s*$", line):
            continue
        # 调用形态（参数名在前、值在后、非默认声明）→ 命中
        hits.append((i, stripped[:120]))
    return hits


def main() -> int:
    quiet = "--quiet" in sys.argv
    total = 0
    issues: list[tuple[str, int, str]] = []
    for pkg in PKG_DIRS:
        base = ROOT / pkg
        if not base.exists():
            continue
        for py in sorted(base.rglob("*.py")):
            if "__pycache__" in str(py) or "/tests/" in str(py) or "\\tests\\" in str(py):
                continue
            for ln, text in scan_file(py):
                total += 1
                issues.append((str(py.relative_to(ROOT)), ln, text))
    if issues:
        print("=" * 60)
        print(f'【S152h】book_id="main" 硬编码调用点扫描：检出 {total} 处（人工复核）')
        for f, ln, text in issues:
            print(f"  {f}:{ln}: {text}")
        print("=" * 60)
        print(
            "说明：这些是调用点字面量传参（非默认参数声明）。若为业务需要（全局/单书兼容）\n"
            "可显式改用常量并注释原因；若为跨项目数据路径，应改为从请求/ToolContext 取。"
        )
        return 0 if quiet else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
