# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置：anyspark-desktop（含后端 + 前端产物）
# 用法：pyinstaller anyspark.spec
# 前端产物需先构建：cd frontend && npm run build

import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
FRONTEND_DIST = ROOT / "frontend" / "dist"

a = Analysis(
    ["packages/desktop/src/anyspark/desktop/__init__.py"],
    pathex=[str(ROOT / "packages" / "desktop" / "src")],
    datas=[
        (str(FRONTEND_DIST), "frontend/dist"),
    ],
    hiddenimports=[
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
