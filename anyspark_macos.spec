# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for the native macOS AnySpark application."""

import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(".").resolve()
ICON = ROOT / "packaging" / "macos" / "AnySpark.icns"
with (ROOT / "pyproject.toml").open("rb") as version_file:
    VERSION = tomllib.load(version_file)["project"]["version"]


def source_modules(directory):
    modules = []
    for file_path in directory.rglob("*.py"):
        if file_path.name == "__init__.py":
            module = file_path.parent.relative_to(ROOT / "src").as_posix().replace("/", ".")
        else:
            module = file_path.relative_to(ROOT / "src").with_suffix("").as_posix().replace("/", ".")
        if module:
            modules.append(module)
    return modules


hidden_imports = []
for package_dir in ("core", "routes", "tools", "data"):
    hidden_imports.extend(source_modules(ROOT / "src" / package_dir))

for package_name in ("uvicorn", "sse_starlette", "pygit2", "ebooklib"):
    hidden_imports.extend(collect_submodules(package_name))

tiktoken_datas, tiktoken_binaries, tiktoken_hidden = collect_all("tiktoken")
hidden_imports.extend(tiktoken_hidden)
hidden_imports.extend(collect_submodules("tiktoken_ext"))
hidden_imports.append("tiktoken_ext.openai_public")
hidden_imports.extend(["webview", "webview.platforms.cocoa"])

a = Analysis(
    ["src/desktop_launcher.py"],
    pathex=[str(ROOT), str(ROOT / "src")],
    binaries=tiktoken_binaries,
    datas=[
        ("frontend/dist", "frontend/dist"),
        ("styles", "styles"),
        ("reviewers", "reviewers"),
        ("skills", "skills"),
        ("src/core/prompts", "core/prompts"),
        ("pyproject.toml", "."),
        ("LICENSE", "."),
        *tiktoken_datas,
    ],
    hiddenimports=sorted(set(hidden_imports)),
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "PIL",
        "PyQt5",
        "PySide2",
        "numpy",
        "pandas",
        "scipy",
        "notebook",
        "jupyter",
        "jupyter_client",
        "ipython",
        "nbformat",
        "huggingface_hub",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AnySpark",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity="-",
    entitlements_file=None,
    icon=str(ICON),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="AnySpark",
)

app = BUNDLE(
    coll,
    name="AnySpark.app",
    icon=str(ICON),
    bundle_identifier="com.anyspark.desktop",
    info_plist={
        "CFBundleDisplayName": "火花 AnySpark",
        "CFBundleName": "AnySpark",
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSApplicationCategoryType": "public.app-category.productivity",
        "LSMinimumSystemVersion": "12.0",
        "LSUIElement": False,
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "Copyright © 2026 Junrui Xu. AGPL-3.0-or-later.",
    },
)
