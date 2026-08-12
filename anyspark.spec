# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置：anyspark-desktop（含后端 + 前端产物）
# 用法：pyinstaller anyspark.spec
# 前端产物需先构建：cd frontend && npm run build

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve()
FRONTEND_DIST = ROOT / "frontend" / "dist"

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
