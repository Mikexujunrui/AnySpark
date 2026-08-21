# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置：anyspark-desktop（含后端 + 前端产物）
# 用法：pyinstaller anyspark.spec（同一 spec 三平台通用——S165）
# 前端产物需先构建：cd frontend && npm run build
# 平台分支：Windows/Linux → 单文件 EXE；macOS → .app BUNDLE（COLLECT 目录结构）

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve()
FRONTEND_DIST = ROOT / "frontend" / "dist"
IS_DARWIN = sys.platform == "darwin"

# S203d：Windows Anaconda/conda 布局的 DLL 兜底收集。
# 坑：_ctypes.pyd/_sqlite3.pyd 等 pyd 在 <prefix>/DLLs，但依赖的 ffi-8.dll /
# sqlite3.dll / liblzma.dll / libbz2.dll / libexpat.dll 分散在 conda 的
# Library/bin 或 envs/<env>/Library/bin——PyInstaller 默认搜索不到，打包后的
# exe 启动即崩（ImportError: DLL load failed while importing _ctypes）。
# 解法：从多个候选目录收集缺失 DLL 进 binaries（只收存在的，跨机器不报错）。


def _conda_dll_binaries() -> list[tuple[str, str]]:
    """返回 (dll源路径, exe内目标目录) 列表；找不到的 DLL 跳过。"""
    import os

    wanted = [
        "ffi-8.dll",
        "libffi-8.dll",
        "sqlite3.dll",
        "liblzma.dll",
        "LIBBZ2.dll",
        "libbz2.dll",
        "libexpat.dll",
        # _ssl.pyd/_hashlib.pyd 依赖（OpenSSL 3 命名）
        "libcrypto-3-x64.dll",
        "libssl-3-x64.dll",
    ]
    # 候选目录：当前 conda env 的 Library/bin、根 env 的 Library/bin、
    # python 安装目录 DLLs（标准 python.org 布局）
    candidates: list[Path] = []
    if os.environ.get("CONDA_PREFIX"):
        candidates.append(Path(os.environ["CONDA_PREFIX"]) / "Library" / "bin")
    base_prefix = Path(sys.base_prefix)
    if (base_prefix / "conda-meta" / "history").exists():  # 根 conda env
        candidates.append(base_prefix / "Library" / "bin")
    candidates.append(Path(sys.executable).resolve().parent.parent / "DLLs")
    candidates.append(Path(sys.base_prefix) / "DLLs")
    # envs 子目录（多个 env 时 ffi 可能只在某个 env 里）
    for sub in sorted((base_prefix / "envs").glob("*/Library/bin")) if (base_prefix / "envs").exists() else []:
        candidates.append(sub)

    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name in wanted:
        if name.lower() in seen:
            continue
        for d in candidates:
            p = d / name
            if p.exists():
                out.append((str(p), "."))
                seen.add(name.lower())
                break
    # _ctypes.pyd 的导入名是 ffi.dll（非 ffi-8.dll）——conda 只有 ffi-8.dll，
    # 需要按 ffi.dll 名义收集。PyInstaller 的 binaries (src, dest) 中 dest 是**目标目录**
    # 不是文件名（实测 (src, "ffi.dll") 生成 ffi.dll/ffi-8.dll 嵌套，_ctypes 仍找不到）——
    # 正确做法：复制一份名为 ffi.dll 的临时文件再收集（解压后同名在根级）。
    for d in candidates:
        src = d / "ffi-8.dll"
        if src.exists():
            import shutil

            tmp_ffi = Path(SPECPATH) / "build" / "_ffi_rename" / "ffi.dll"
            tmp_ffi.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, tmp_ffi)
            out.append((str(tmp_ffi), "."))
            break
    return out


# tiktoken：编码表（cl100k_base 等）是数据文件，PyInstaller 默认不收集——
# 缺了会 ValueError: Unknown encoding cl100k_base
_TIKTOKEN_DATAS = collect_data_files("tiktoken")
_TIKTOKEN_HIDDEN = collect_submodules("tiktoken_ext")
_WIN_DLL_BINARIES = _conda_dll_binaries()

a = Analysis(
    ["packages/desktop/src/anyspark/desktop/__init__.py"],
    pathex=[str(ROOT / "packages" / "desktop" / "src")],
    binaries=_WIN_DLL_BINARIES,
    datas=[
        (str(FRONTEND_DIST), "frontend/dist"),
        # S109：.env 模板（frozen 启动时复制到 exe 同目录 data/）+ 系统评审员
        (str(ROOT / ".env.example"), "."),
        # S164：frozen 时版本检测读本地版本（pyproject.toml 打进 exe 资源）
        (str(ROOT / "pyproject.toml"), "."),
        (str(ROOT / "packages" / "review" / "reviewers"), "reviewers"),
        *_TIKTOKEN_DATAS,
    ],
    hiddenimports=[
        *_TIKTOKEN_HIDDEN,
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "dotenv",
        "webview",
    ],
)

pyz = PYZ(a.pure)

if IS_DARWIN:
    # macOS：.app（BUNDLE 需要 COLLECT 目录结构；图标用 anyspark.icns，无则默认）
    _ICNS = ROOT / "anyspark.icns"
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="AnySpark",
        console=False,
    )
    coll = COLLECT(exe, a.binaries, a.datas, name="AnySpark")
    app = BUNDLE(
        coll,
        name="AnySpark.app",
        icon=str(_ICNS) if _ICNS.exists() else None,
        bundle_identifier="ai.anyspark.desktop",
    )
else:
    # Windows/Linux：单文件 EXE（现状保持；Linux 无 console 属性差异，upx 均关）
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="AnySpark",
        console=False,
        upx=False,
    )
