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

# tiktoken：编码表（cl100k_base 等）是数据文件，PyInstaller 默认不收集——
# 缺了会 ValueError: Unknown encoding cl100k_base
_TIKTOKEN_DATAS = collect_data_files("tiktoken")
_TIKTOKEN_HIDDEN = collect_submodules("tiktoken_ext")

a = Analysis(
    ["packages/desktop/src/anyspark/desktop/__init__.py"],
    pathex=[str(ROOT / "packages" / "desktop" / "src")],
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
