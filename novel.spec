# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for packaging the Novel Agent as a single EXE.

Usage:
    pip install pyinstaller
    pyinstaller novel.spec

The resulting EXE will be in dist/NovelAgent/NovelAgent.exe
"""

import sys
from pathlib import Path

# Locate tiktoken_ext namespace package for bundling
# (namespace packages are not auto-detected by PyInstaller)
try:
    import tiktoken_ext
    _TIKTOKEN_EXT_SRC = tiktoken_ext.__path__[0]
except (ImportError, AttributeError, IndexError):
    _TIKTOKEN_EXT_SRC = None

block_cipher = None

# Collect all core and routes modules (they use dynamic imports)
core_pkg = Path("src/core")
routes_pkg = Path("src/routes")
tools_pkg = Path("src/tools")
data_pkg = Path("src/data")

# Collect all Python files recursively
core_modules = []
if core_pkg.is_dir():
    for f in core_pkg.rglob("*.py"):
        rel = f.relative_to("src").with_suffix("").as_posix().replace("/", ".")
        core_modules.append(rel)

if routes_pkg.is_dir():
    for f in routes_pkg.rglob("*.py"):
        rel = f.relative_to("src").with_suffix("").as_posix().replace("/", ".")
        core_modules.append(rel)

if tools_pkg.is_dir():
    for f in tools_pkg.rglob("*.py"):
        rel = f.relative_to("src").with_suffix("").as_posix().replace("/", ".")
        core_modules.append(rel)

if data_pkg.is_dir():
    for f in data_pkg.rglob("*.py"):
        rel = f.relative_to("src").with_suffix("").as_posix().replace("/", ".")
        core_modules.append(rel)

a = Analysis(
    ['src/server.py'],
    pathex=[
        str(Path(".").resolve()),
        str(Path("src").resolve()),  # <-- so core.*, routes.*, tools.* can be found
    ],
    binaries=[],
    datas=[
        # Include the production-built frontend
        ('frontend/dist', 'frontend/dist'),
        # System default styles and reviewers (read-only, shipped with product)
        ('styles', 'styles'),
        ('reviewers', 'reviewers'),
        ('skills', 'skills'),
        # tiktoken encoding plugins (namespace package, not auto-detected)
        *([(_TIKTOKEN_EXT_SRC, 'tiktoken_ext')] if _TIKTOKEN_EXT_SRC else []),
        # NOTE: data/ is NOT included — SQLiteStore creates novel.db at runtime
        # next to the executable (_resolve_db_dir handles this for frozen mode).
    ],
    hiddenimports=[
        # FastAPI + ASGI server
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan.on',
        'sse_starlette',
        'sse_starlette.sse',
        # OpenAI / LLM client
        'openai',
        'openai._base_client',
        'httpx',
        'httpx._config',
        'httpcore',
        'httpcore._async.connection_pool',
        # Pydantic / validation
        'pydantic',
        'pydantic.generics',
        'pydantic.dataclasses',
        # YAML
        'yaml',
        # Rich terminal output
        'rich',
        'rich.console',
        'rich.table',
        'rich.box',
        # tiktoken encoding plugins (namespace package, not auto-detected)
        'tiktoken_ext',
        'tiktoken_ext.openai_public',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'PIL',
        'PyQt5',
        'PySide2',
        'numpy',
        'pandas',
        'scipy',
        'notebook',
        'jupyter',
        'jupyter_client',
        'ipython',
        'nbformat',
        'huggingface_hub',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='NovelAgent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep console for server logs; set False for GUI-only mode
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# Also create a one-folder bundle (easier to debug)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NovelAgent',
)
