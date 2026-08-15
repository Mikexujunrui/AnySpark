"""
anyspark.server.codex — 代码扩展（S48-P4/P5 + S116 进程级隔离重写）。

对应 DESIGN 机制 8 预留的"编码扩展包 anyspark-codex"（可选，不默认装）：
- 复杂自定义处理（特殊格式解析/批量转换/统计——固定工具做不了的东西）
- 自我修复（Agent 写修复代码 → 沙箱运行验证 → 输出补丁/结果）

安全设计（S116 重写，A 类底线）：
- **进程级隔离**：用户代码在独立 Python 子进程执行（subprocess），非线程——
  超时直接杀进程（Python 无法杀线程）；GIL 饿死/死循环不挂主进程；
  stdout/stderr 经 pipe 回收，无进程级全局污染
- **数据快照传入**：ws_* 数据环境 = 主进程构造的可序列化快照（JSON 传入子进程），
  子进程无 store 引用；ws_read/src_read 在子进程内严格校验（is_relative_to +
  大小上限），防路径前缀绕过（S116 修复 startswith 无尾分隔符缺陷）
- **环境变量最小集**：子进程仅继承 PATH/SYSTEMROOT/TEMP 等必需项，
  剥离 DEEPSEEK_* 等敏感密钥
- **白名单命名空间（第二层防线）**：受限内置 + 白名单模块 import；
  即使逃逸（属性遍历链），也只能在子进程内、环境干净、可被超时杀掉
- **frozen 禁用**：打包版（PyInstaller）无独立解释器可起子进程，且无法保证
  隔离——直接拒绝（失败关闭：无法确认隔离 → 不执行）
- timeout 硬上限（默认 10s，可传但不超过 60s）

已知残余风险（文档明示）：子进程内逃逸后可按本机用户权限读文件（写主进程
状态/环境被隔离）——codex 面向本机可信用户（用户/Agent 自写代码），非对抗
多租户场景；对抗级安全需容器级隔离（YAGNI）。
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import string
import subprocess
import sys
from pathlib import Path
from typing import Any

# 安全内置白名单（机制硬编码：只放无副作用的函数/类型；子进程内第二层防线）
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

# 文件读取上限（ws_read：防沙箱代码读超大文件）
_WS_READ_MAX = 200_000
# 源码只读根（S49：修 bug 辅助——沙箱可只读 packages/ 源码定位问题）
SRC_ROOT = Path(__file__).resolve().parents[5] / "packages"
_SRC_READ_MAX = 100_000


def _is_frozen() -> bool:
    """PyInstaller 打包态：无独立解释器起子进程 → run_code 拒绝（失败关闭）。"""
    return bool(getattr(sys, "frozen", False))


# ---------------------------------------------------------------------------
# 子进程 runner（内嵌常量：自包含，PyInstaller 无需额外收集文件）
# 主进程 subprocess 调 [python, -c, _RUNNER_SRC]，stdin 传 {code, snapshot, read_roots}，
# stdout 回传 {ok, stdout, stderr, error} JSON。
# ---------------------------------------------------------------------------
_RUNNER_SRC = r'''
import contextlib
import io
import json
import math
import random
import re
import string
import sys
from pathlib import Path

_SAFE_BUILTINS = {
    "print": print, "len": len, "range": range, "str": str, "int": int,
    "float": float, "bool": bool, "list": list, "dict": dict, "set": set,
    "tuple": tuple, "frozenset": frozenset, "zip": zip, "enumerate": enumerate,
    "sorted": sorted, "reversed": reversed, "min": min, "max": max, "sum": sum,
    "abs": abs, "round": round, "any": any, "all": all, "type": type,
    "isinstance": isinstance, "issubclass": issubclass, "repr": repr, "hash": hash,
    "chr": chr, "ord": ord, "hex": hex, "oct": oct, "bin": bin, "divmod": divmod,
    "pow": pow, "Exception": Exception, "ValueError": ValueError,
    "TypeError": TypeError, "KeyError": KeyError, "IndexError": IndexError,
    "ZeroDivisionError": ZeroDivisionError,
    "True": True, "False": False, "None": None,
    "math": math, "re": re, "random": random, "string": string,
    "itertools": __import__("itertools"),
}
_ALLOWED_MODULES = {
    "math", "re", "random", "string", "itertools", "json", "collections", "statistics",
}


class _SafeImporter:
    def __init__(self, real_import):
        self._real = real_import

    def __call__(self, name, *args, **kwargs):
        base = name.split(".")[0]
        if base not in _ALLOWED_MODULES:
            raise ImportError(
                "sandbox blocks import " + repr(name) + " (allowed: "
                + str(sorted(_ALLOWED_MODULES)) + ")"
            )
        return self._real(name, *args, **kwargs)


def _read_relative(rel_path, base, max_size):
    """Strict path check with is_relative_to (blocks prefix-sibling bypass)."""
    base_p = Path(base).resolve()
    p = (base_p / rel_path).resolve()
    if not p.is_relative_to(base_p):
        raise ValueError("out of bounds: " + rel_path)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(rel_path)
    if p.stat().st_size > max_size:
        raise ValueError("file too large (>" + str(max_size) + " bytes)")
    return p.read_text(encoding="utf-8", errors="ignore")


def _make_namespace(snap, roots):
    """Restricted namespace + ws_* read-only data functions (from snapshot)."""
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__
    safe_builtins = dict(_SAFE_BUILTINS)
    safe_builtins["__import__"] = _SafeImporter(real_import)
    namespace = {"__builtins__": safe_builtins}

    def ws_chapters():
        return snap.get("chapters", [])

    def ws_entities():
        return snap.get("entities", [])

    def ws_relations():
        return snap.get("relations", [])

    def ws_events():
        return snap.get("events", [])

    def ws_read(rel_path):
        return _read_relative(rel_path, roots.get("project", ""), 200000)

    def ws_uploads():
        return snap.get("uploads", [])

    def src_read(rel_path):
        return _read_relative(rel_path, roots.get("src", ""), 100000)

    namespace.update({
        "ws_chapters": ws_chapters, "ws_entities": ws_entities,
        "ws_relations": ws_relations, "ws_events": ws_events,
        "ws_read": ws_read, "ws_uploads": ws_uploads, "src_read": src_read,
    })
    return namespace


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    code = data.get("code", "")
    snap = data.get("snapshot") or {}
    roots = data.get("read_roots") or {}
    out = {"ok": True, "stdout": "", "stderr": "", "error": ""}
    ob = io.StringIO()
    eb = io.StringIO()
    try:
        namespace = _make_namespace(snap, roots)
        with contextlib.redirect_stdout(ob), contextlib.redirect_stderr(eb):
            exec(compile(code, "<sandbox>", "exec"), namespace, namespace)
    except Exception as exc:
        out["ok"] = False
        out["error"] = type(exc).__name__ + ": " + str(exc)
    out["stdout"] = ob.getvalue()
    out["stderr"] = eb.getvalue()
    sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    main()
'''


def make_data_env(
    workspace: Any, chapters: Any, graph: Any, book_id: str = "main"
) -> dict[str, Any]:
    """构建沙箱只读数据**快照**（S116：进程隔离后改快照传入，不再注入闭包）。

    返回 {snapshot: {...可序列化数据}, read_roots: {...只读根路径}}——
    子进程从快照读数据（章节/图谱/上传），ws_read/src_read 经严格校验读文件。
    数据进子进程内存（不占模型 token——模型只看到代码与输出）。
    """

    def _chapters() -> list[dict[str, Any]]:
        return [{"title": c.title, "content": c.content} for c in chapters.list_by_book(book_id)]

    def _uploads() -> list[dict[str, Any]]:
        return [{"name": u["name"], "size": u["size"]} for u in workspace.list_uploads(book_id)]

    snapshot = {
        "chapters": _chapters(),
        "entities": [e.to_dict() for e in graph.list_entities(book_id, limit=10000)],
        "relations": [r.to_dict() for r in graph.list_relations(book_id, limit=10000)],
        "events": [ev.to_dict() for ev in graph.list_events(book_id, limit=10000)],
        "uploads": _uploads(),
    }
    return {
        "snapshot": snapshot,
        "read_roots": {
            "project": str(workspace.project_dir(book_id).resolve()),
            "src": str(SRC_ROOT.resolve()),
        },
    }


def _minimal_env() -> dict[str, str]:
    """子进程环境最小集：仅必需项，剥离 DEEPSEEK_*/OPENAI_*/ANYSPARK_* 等敏感密钥。"""
    keep = {
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "COMSPEC",
        "PATHEXT",
        "PYTHONIOENCODING",
        "PYTHONUTF8",
        "NUMBER_OF_PROCESSORS",
    }
    env = {k: v for k, v in os.environ.items() if k in keep}
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    return env


def run_code(
    code: str, timeout: float = 10.0, data_env: dict[str, Any] | None = None
) -> dict[str, Any]:
    """在**独立子进程**执行 Python 代码，返回 {ok, stdout, stderr, error}。

    - 进程级隔离：超时杀进程、GIL 饿死不挂主进程、stdout 经 pipe 无全局污染
    - data_env（可选）：make_data_env 返回的快照 dict（{snapshot, read_roots}）
    - 白名单命名空间（第二层防线）+ 环境变量最小集
    - timeout 硬上限（默认 10s，≤60s）
    - frozen（打包版）拒绝执行：无法起独立解释器进程 → 失败关闭
    """
    if not code or not code.strip():
        return {"ok": False, "stdout": "", "stderr": "", "error": "空代码"}
    if _is_frozen():
        return {
            "ok": False,
            "stdout": "",
            "stderr": "",
            "error": "打包版禁用代码沙箱（无法进程级隔离，失败关闭）",
        }
    t = min(max(float(timeout), 0.5), MAX_TIMEOUT)

    payload = {
        "code": code,
        "snapshot": (data_env or {}).get("snapshot") or {},
        "read_roots": (data_env or {}).get("read_roots") or {},
    }
    # UTF-8 bytes 全链路（Windows 终端编码 cp936 会毁中文）：stdin 传 bytes、
    # stdout 按 utf-8 解码（子进程端 PYTHONUTF8=1 已强制）
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _RUNNER_SRC],
            input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            capture_output=True,
            timeout=t,
            env=_minimal_env(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "", "error": f"执行超时（>{t:.0f}s）"}
    except Exception as exc:
        return {"ok": False, "stdout": "", "stderr": "", "error": f"沙箱启动失败：{exc}"}

    if proc.returncode != 0:
        return {
            "ok": False,
            "stdout": "",
            "stderr": (proc.stderr or b"").decode("utf-8", errors="replace")[:500],
            "error": f"沙箱进程异常退出（code={proc.returncode}）",
        }
    try:
        result: dict[str, Any] = json.loads((proc.stdout or b"").decode("utf-8", errors="replace"))
    except Exception:
        return {
            "ok": False,
            "stdout": "",
            "stderr": (proc.stderr or b"").decode("utf-8", errors="replace")[:500],
            "error": "沙箱输出解析失败",
        }
    return result
