"""AnySpark v4 发布打包脚本（S88）。

组装一个可分发目录：完整前后端（后端源码 + 前端构建产物 + 一键启动），
**不含技术文件**：docs/ tests/ benchmarks/ data/ scripts/ *.md .git node_modules .venv 等。

用法：
    uv run python scripts/package_release.py [输出目录]
缺省输出：<项目上级>/AnySparkV4-发布/
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 后端要打包的包（依赖 core 的全部领域包 + app + desktop）
BACKEND_PACKAGES = [
    "core",
    "app",
    "align",
    "explore",
    "check",
    "template",
    "graph",
    "workflow",
    "play",
    "review",
    "library",
]

# 复制时排除的目录/文件
EXCLUDE_DIRS = {
    "tests",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "node_modules",
}
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".pyd")


def copy_tree(src: Path, dst: Path) -> None:
    """复制目录树，排除技术文件。"""
    for item in src.rglob("*"):
        if not item.is_file():
            continue
        if any(part in EXCLUDE_DIRS for part in item.relative_to(src).parts):
            continue
        if item.suffix in EXCLUDE_SUFFIXES:
            continue
        rel = item.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def build_frontend() -> None:
    """构建前端产物（frontend/dist）。"""
    print("  [1/4] 构建前端...")
    r = subprocess.run(
        ["npm", "run", "build"], cwd=str(ROOT / "frontend"), shell=True
    )
    if r.returncode != 0:
        print("  [错误] 前端构建失败")
        sys.exit(1)


def assemble(out_root: Path) -> None:
    """组装发布目录。"""
    # 1. 后端包源码
    print("  [2/4] 复制后端包源码...")
    pkgs_dst = out_root / "packages"
    for name in BACKEND_PACKAGES:
        src = ROOT / "packages" / name
        if not src.exists():
            continue
        copy_tree(src, pkgs_dst / name)
        # 保留 pyproject.toml / py.typed
        for meta in ("pyproject.toml",):
            m = src / meta
            if m.exists():
                t = pkgs_dst / name / meta
                t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(m, t)

    # 2. 前端产物
    print("  [3/4] 复制前端产物...")
    dist = ROOT / "frontend" / "dist"
    if (dist / "index.html").exists():
        copy_tree(dist, out_root / "frontend" / "dist")
    else:
        print("  [警告] 未找到 frontend/dist——跳过前端")

    # 3. 根级配置文件 + 启动脚本
    for f in ("pyproject.toml", "uv.lock", ".env.example"):
        s = ROOT / f
        if s.exists():
            shutil.copy2(s, out_root / f)
    _write_start_bat(out_root)


def _write_start_bat(out_root: Path) -> None:
    """生产模式一键启动（后端 serve 前端 dist，单端口 8000）。"""
    start = r'''@echo off
rem ============================================
rem  AnySpark v4 - 发布版一键启动（双击即用）
rem  后端 serve 前端 dist（单端口 8000）
rem  编码：UTF-8 无 BOM + CRLF
rem ============================================
setlocal
cd /d "%~dp0"

echo.
echo  ============================================
echo    AnySpark v4  创作台启动中...
echo  ============================================
echo.

rem ---- 0. 释放残留端口 ----
echo  [0/4] 清理残留进程...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%p >nul 2>&1
)

rem ---- 1. 检查 .env ----
if not exist ".env" (
    echo  [提示] 未找到 .env，已从模板生成——请填入 DeepSeek API Key 后重新运行
    copy ".env.example" ".env" >nul
    echo.
)

rem ---- 2. 后端环境（首次才安装）----
echo  [1/4] 检查 Python 环境...
if not exist ".venv" (
    echo       首次安装依赖（需要联网 + 已装 uv）...
    uv sync
    if errorlevel 1 (
        echo  [错误] 依赖安装失败，请确认已安装 uv 且网络通畅
        pause
        exit /b 1
    )
) else (
    echo       环境已就绪
)

rem ---- 3. 启动后端（serve 前端 + API）----
echo  [2/4] 启动服务 127.0.0.1:8000 ...
if exist ".venv\Scripts\anyspark-server.exe" (
    start "AnySpark" cmd /k "cd /d %~dp0 && .venv\Scripts\anyspark-server.exe --port 8000"
) else (
    echo  [错误] 未找到 .venv\Scripts\anyspark-server.exe，请删除 .venv 后重新运行
    pause
    exit /b 1
)

echo  [3/4] 等待服务就绪...
"%SystemRoot%\System32\timeout.exe" /t 8 /nobreak >nul

rem ---- 4. 打开浏览器 ----
echo  [4/4] 打开浏览器...
start "" "http://localhost:8000"

echo.
echo  创作台已启动：http://localhost:8000
echo  退出时请关闭所有黑色窗口
echo.
pause
exit /b 0
'''
    (out_root / "start.bat").write_text(start, encoding="utf-8", newline="\r\n")


def copy_venv(out_root: Path) -> None:
    """在发布目录重建干净 .venv（便携版：解压即用，用户无需装 Python/uv）。

    关键：根 .venv 是 uv workspace **editable 安装**（.pth 指向根源码路径，
    跨机复制会断）——必须重建为非 editable 真实安装：
      1. uv venv 新建
      2. uv pip install 第三方依赖（uv export --no-emit-workspace 导出，不含 workspace 成员）
      3. uv pip install --no-deps 各包路径（真实复制进 site-packages，无路径依赖）
    """
    venv = out_root / ".venv"
    print("  [重建] 发布目录 .venv（非 editable 真实安装，约 1-2 分钟）...")
    import subprocess as sp

    # 1. 建 venv
    r = sp.run(["uv", "venv", str(venv)], cwd=str(out_root), capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  [错误] uv venv 失败: {r.stderr[-300:]}")
        return
    py = venv / "Scripts" / "python.exe"
    if not py.exists():
        print(f"  [错误] venv python 未创建: {py}")
        return

    # 2. 第三方依赖（从根 uv.lock 导出，不含 workspace 成员）
    reqs = ROOT.parent / "pkg_reqs_tmp.txt"
    sp.run(
        ["uv", "export", "--format", "requirements.txt", "--no-emit-workspace",
         "--no-hashes", "-o", str(reqs)],
        cwd=str(ROOT), check=True, capture_output=True,
    )
    r = sp.run(
        ["uv", "pip", "install", "--python", str(py), "-r", str(reqs)],
        cwd=str(out_root), capture_output=True, text=True,
    )
    reqs.unlink(missing_ok=True)
    if r.returncode != 0:
        print(f"  [错误] 第三方依赖安装失败: {r.stderr[-300:]}")
        return

    # 3. 各包（--no-deps 真实安装；core 先，其余依赖 core 的随后，app 最后）
    order = [
        "core", "align", "explore", "check", "template", "graph",
        "workflow", "review", "play", "library", "app",
    ]
    for name in order:
        pkg = out_root / "packages" / name
        if not pkg.exists():
            continue
        r = sp.run(
            ["uv", "pip", "install", "--python", str(py), "--no-deps", str(pkg)],
            cwd=str(out_root), capture_output=True, text=True,
        )
        if r.returncode != 0:
            print(f"  [警告] {name} 安装失败: {r.stderr[-200:]}")

    exe = venv / "Scripts" / "anyspark-server.exe"
    if not exe.exists():
        print(f"  [警告] anyspark-server.exe 未生成: {exe}")




def make_zip(out_dir: Path) -> Path:
    """把发布目录打成 zip（排除 data 运行时数据；便携版含 .venv）。"""
    import zipfile

    out = out_dir.parent / (out_dir.name + ".zip")
    if out.exists():
        out.unlink()
    n = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in out_dir.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(out_dir)
            parts = rel.parts
            if "data" in parts:  # 运行时数据不进包
                continue
            if ".venv" in parts and ("__pycache__" in parts or f.suffix == ".pyc"):
                continue
            zf.write(f, f"{out_dir.name}/{rel}")
            n += 1
    print(f"  [zip] {out.name}：{n} 文件，{out.stat().st_size/1024/1024:.1f} MB")
    return out


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    with_venv = "--with-venv" in sys.argv
    do_zip = "--zip" in sys.argv
    out_dir = Path(args[0]) if args else ROOT.parent / "AnySparkV4-发布"
    print(f"打包到: {out_dir}（{'便携版：含 .venv' if with_venv else '源码版：需 uv sync'}）")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    build_frontend()
    assemble(out_dir)
    if with_venv:
        copy_venv(out_dir)

    # 统计
    size = sum(f.stat().st_size for f in out_dir.rglob("*") if f.is_file())
    n_files = sum(1 for f in out_dir.rglob("*") if f.is_file())
    print(f"  [4/4] 完成：{n_files} 文件，{size/1024/1024:.1f} MB")
    print(f"  → {out_dir}")
    if do_zip:
        make_zip(out_dir)
    if with_venv:
        print("  [便携版] 解压即用：填 .env API Key → 双击 start.bat（无需 Python/uv）")
    else:
        print("  [源码版] 双击 start.bat（首次需装 uv + uv sync + 填 .env API Key）")


if __name__ == "__main__":
    main()
