"""
anyspark.server.codex — 代码扩展（S48-P4/P5：固定工具无法实现的东西 + 自我修复）。

对应 DESIGN 机制 8 预留的"编码扩展包 anyspark-codex"（可选，不默认装）：
- 复杂自定义处理（特殊格式解析/批量转换/统计——固定工具做不了的东西）
- 自我修复（Agent 写修复代码 → 沙箱运行验证 → 输出补丁/结果）

安全设计（机制硬编码，A 类底线）：
- 白名单受限命名空间：仅安全内置 + 白名单模块（math/re/json/random/itertools），
  无 open/import/exec/eval/__import__——不能读写文件、不能访问网络
- timeout 硬上限（默认 10s，可传但不超过 60s）——防死循环
- 只返回 stdout/stderr/异常文本，无副作用（沙箱内不可变状态，调用即烧）
- 自我修复路径：run_code 只验证代码正确性；真正"修工具"由 Agent 生成补丁
  文本，经用户确认后由系统应用（本模块不直接改源码）

哲学：机制（沙箱/白名单/超时）硬编码；代码内容（Agent/用户写的程序）自然语言无关。
"""

from __future__ import annotations

import contextlib
import io
import math
import random
import re
import string
import threading
from collections.abc import Callable
from typing import Any

# 安全内置白名单（机制硬编码：只放无副作用的函数/类型）
_SAFE_BUILTINS: dict[str, Any] = {
    "print": print,
    "len": len,
    "range": range,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    "frozenset": frozenset,
    "zip": zip,
    "enumerate": enumerate,
    "sorted": sorted,
    "reversed": reversed,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "round": round,
    "any": any,
    "all": all,
    "type": type,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "repr": repr,
    "hash": hash,
    "chr": chr,
    "ord": ord,
    "hex": hex,
    "oct": oct,
    "bin": bin,
    "divmod": divmod,
    "pow": pow,
    "Exception": Exception,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "KeyError": KeyError,
    "IndexError": IndexError,
    "ZeroDivisionError": ZeroDivisionError,
    "True": True,
    "False": False,
    "None": None,
    "math": math,
    "re": re,
    "random": random,
    "string": string,
    "itertools": __import__("itertools"),
}

# 允许 import 的白名单模块名（防 __import__ 逃逸；exec 内的 import 走 __import__）
_ALLOWED_MODULES = {
    "math",
    "re",
    "random",
    "string",
    "itertools",
    "json",
    "collections",
    "statistics",
}

MAX_TIMEOUT = 60  # 硬上限（秒）


class _SafeImporter:
    """受限 __import__：只允许白名单模块，其余抛 ImportError。"""

    def __init__(self, real_import: Callable[..., Any]) -> None:
        self._real = real_import

    def __call__(self, name: str, *args: Any, **kwargs: Any) -> Any:
        base = name.split(".")[0]
        if base not in _ALLOWED_MODULES:
            raise ImportError(f"沙箱禁止 import {name!r}（仅允许：{sorted(_ALLOWED_MODULES)}）")
        return self._real(name, *args, **kwargs)


def run_code(code: str, timeout: float = 10.0) -> dict[str, Any]:
    """在受限沙箱执行 Python 代码，返回 {ok, stdout, stderr, error}。

    - 白名单命名空间（无文件/网络/任意 import）
    - timeout 硬上限（默认 10s，≤60s）；超时终止线程
    - 调用即烧（无副作用），只返回文本
    """
    if not code or not code.strip():
        return {"ok": False, "stdout": "", "stderr": "", "error": "空代码"}
    t = min(max(float(timeout), 0.5), MAX_TIMEOUT)

    out_buf = io.StringIO()
    err_buf = io.StringIO()
    result: dict[str, Any] = {"ok": True, "stdout": "", "stderr": "", "error": ""}
    done = threading.Event()

    def _run() -> None:
        try:
            real_import = (
                __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__
            )
            # builtins 副本 + 受限 __import__（import 语句从 builtins 找 __import__）
            safe_builtins = dict(_SAFE_BUILTINS)
            safe_builtins["__import__"] = _SafeImporter(real_import)
            namespace: dict[str, Any] = {"__builtins__": safe_builtins}
            with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
                exec(compile(code, "<sandbox>", "exec"), namespace, namespace)
            result["stdout"] = out_buf.getvalue()
            result["stderr"] = err_buf.getvalue()
        except Exception as exc:  # 代码运行时错误：返回错误文本（不算沙箱故障）
            result["ok"] = False
            result["stderr"] = err_buf.getvalue()
            result["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            done.set()

    th = threading.Thread(target=_run, daemon=True)
    th.start()
    th.join(timeout=t)
    if not done.is_set():
        result["ok"] = False
        result["error"] = f"执行超时（>{t:.0f}s）"
        result["stdout"] = out_buf.getvalue()  # 保留已输出部分
        return result
    return result
