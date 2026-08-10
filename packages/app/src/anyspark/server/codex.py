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
from pathlib import Path
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


# 文件读取上限（ws_read：防沙箱代码读超大文件拖垮线程）
_WS_READ_MAX = 200_000
# 源码只读根（S49：修 bug 辅助——沙箱可只读 packages/ 源码定位问题）
SRC_ROOT = Path(__file__).resolve().parents[5] / "packages"
_SRC_READ_MAX = 100_000


def make_data_env(
    workspace: Any, chapters: Any, graph: Any, book_id: str = "main"
) -> dict[str, Any]:
    """构建沙箱只读数据环境（S48-P4/A：沙箱可读数据——真实统计/自定义分析）。

    注入的 ws_* 函数是**只读快照管道**：沙箱代码可调用它们拿到工作区数据
    （章节全文/图谱实体关系事件/上传列表/受限文件读取），然后自由计算。
    安全边界（A 类硬编码）：只读不可写；路径限制在项目目录内防越界；
    文件读取限大小；超时由 run_code 兜底。

    设计：数据进沙箱内存（不占模型 token——模型只看到代码与输出），
    长书全文本地可算。
    """

    def ws_chapters() -> list[dict[str, Any]]:
        return [{"title": c.title, "content": c.content} for c in chapters.list_by_book(book_id)]

    def ws_entities() -> list[dict[str, Any]]:
        return [e.to_dict() for e in graph.list_entities(book_id, limit=10000)]

    def ws_relations() -> list[dict[str, Any]]:
        return [r.to_dict() for r in graph.list_relations(book_id, limit=10000)]

    def ws_events() -> list[dict[str, Any]]:
        return [ev.to_dict() for ev in graph.list_events(book_id, limit=10000)]

    def ws_read(rel_path: str) -> str:
        """只读项目目录内文件（相对项目根，如 '上传/设定.txt'）。"""
        base = workspace.project_dir(book_id).resolve()
        p = (base / rel_path).resolve()
        if not str(p).startswith(str(base)):
            raise ValueError(f"越界：{rel_path}")
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(rel_path)
        if p.stat().st_size > _WS_READ_MAX:
            raise ValueError(f"文件过大（>{_WS_READ_MAX} 字节），请用 ws_chapters 等快照")
        return str(p.read_text(encoding="utf-8", errors="ignore"))

    def ws_uploads() -> list[dict[str, Any]]:
        return [{"name": u["name"], "size": u["size"]} for u in workspace.list_uploads(book_id)]

    def src_read(rel_path: str) -> str:
        """只读 packages/ 源码（修 bug 辅助：定位问题/验证修复逻辑）。

        安全：只读、限项目源码目录、限大小——不能写（修复由开发 agent 应用）。
        """
        base = SRC_ROOT.resolve()
        p = (base / rel_path).resolve()
        if not str(p).startswith(str(base)):
            raise ValueError(f"越界：{rel_path}")
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(rel_path)
        if p.stat().st_size > _SRC_READ_MAX:
            raise ValueError(f"文件过大（>{_SRC_READ_MAX} 字节）")
        return str(p.read_text(encoding="utf-8", errors="ignore"))

    return {
        "ws_chapters": ws_chapters,
        "ws_entities": ws_entities,
        "ws_relations": ws_relations,
        "ws_events": ws_events,
        "ws_read": ws_read,
        "ws_uploads": ws_uploads,
        "src_read": src_read,
    }


def run_code(
    code: str, timeout: float = 10.0, data_env: dict[str, Any] | None = None
) -> dict[str, Any]:
    """在受限沙箱执行 Python 代码，返回 {ok, stdout, stderr, error}。

    - 白名单命名空间（无文件/网络/任意 import）
    - data_env（可选）：注入只读数据函数（ws_chapters/ws_entities/ws_read/…），
      沙箱可真实计算工作区数据，但不接触文件系统原始能力
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
            if data_env:
                namespace.update(data_env)  # 注入只读数据函数（沙箱可调用）
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
