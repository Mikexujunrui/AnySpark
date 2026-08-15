#!/bin/bash
# ============================================================
# build_release.sh — AnySpark v4 发布打包（三平台通用，S165）
#
# 平台自适应（PyInstaller anyspark.spec 已平台分支）：
#   Windows → dist/AnySpark.exe          → AnySpark_Windows_x64_<v>.zip
#   macOS   → dist/AnySpark.app          → AnySpark_macOS_arm64_<v>.zip
#   Linux   → dist/AnySpark (ELF)        → AnySpark_Linux_x64_<v>.tar.gz
#
# 用法：
#   bash scripts/build_release.sh            # 默认版本 v4.0.0
#   bash scripts/build_release.sh v4.1.0     # 指定版本号
#
# 输出：<仓库上级>/AnySparkV4-发布-exe/
# 说明：正式用户下载产物挂 GitHub Release；源码分发用 scripts/package_release.py
# ============================================================
set -e

VERSION="${1:-v4.0.7}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# 输出目录：可用 BUILD_OUT_DIR 环境变量覆盖（CI 用），缺省仓库上级
OUT_BASE="${BUILD_OUT_DIR:-$(dirname "$ROOT")/AnySparkV4-发布-exe}"
STAGE="$ROOT/build/release_stage"

# ── 平台检测 ──
case "$(uname -s)" in
  MINGW*|CYGWIN*|MSYS*)  PLAT=Windows;  ART="Windows_x64";  EXT=zip ;;
  Darwin*)               PLAT=macOS;    ART="macOS_arm64";  EXT=zip ;;
  Linux*)                PLAT=Linux;    ART="Linux_x64";    EXT=tar.gz ;;
  *) echo "[错误] 未知平台: $(uname -s)"; exit 1 ;;
esac

echo "===== AnySpark v4 发布打包（$PLAT / $VERSION）====="

echo "[1/4] 构建前端产物..."
(cd "$ROOT/frontend" && npm run build)

echo "[2/4] 清理旧产物..."
rm -rf "$ROOT/dist" "$STAGE"

echo "[3/4] PyInstaller 打包（内置前后端，约 1-3 分钟）..."
(cd "$ROOT" && uv run pyinstaller anyspark.spec --noconfirm)

echo "[4/4] 组装发布包..."
mkdir -p "$STAGE/data"
case "$PLAT" in
  Windows)
    cp "$ROOT/dist/AnySpark.exe" "$STAGE/"
    BIN_NOTE="双击 AnySpark.exe 启动"
    ;;
  macOS)
    cp -R "$ROOT/dist/AnySpark.app" "$STAGE/"
    BIN_NOTE="双击 AnySpark.app 启动"
    ;;
  Linux)
    cp "$ROOT/dist/AnySpark" "$STAGE/"
    chmod +x "$STAGE/AnySpark"
    BIN_NOTE="./AnySpark 启动"
    ;;
esac

cat > "$STAGE/使用说明.txt" << EOF
AnySpark v4 创作台（$PLAT 独立版）

使用：
1. $BIN_NOTE（自动在程序同目录创建 data/ 与 .env 模板）
2. 编辑 data/.env，填入你的 DeepSeek API Key（DEEPSEEK_API_KEY=sk-...）
3. 重新启动，浏览器/窗口打开后即可使用

数据：所有作品数据（章节/图谱/书库）保存在程序同目录 data/，可整体拷贝迁移。
日志：data/logs/anyspark.log
EOF

mkdir -p "$OUT_BASE"
OUT="$OUT_BASE/AnySpark_${ART}_${VERSION}.${EXT}"
if [ "$EXT" = "zip" ]; then
  python - "$STAGE" "$OUT" << 'EOF'
import shutil, sys
stage, out = sys.argv[1], sys.argv[2]
base = out[:-4]
shutil.make_archive(base, "zip", root_dir=stage)
print(f"zip created: {out}")  # 保持 ASCII（Windows runner cp1252 编码打不了中文 stdout）
EOF
else
  tar -czf "$OUT" -C "$STAGE" .
fi
rm -rf "$STAGE"

echo ""
echo "✅ 发布包已生成：$OUT"
echo "   挂到 GitHub Release（正式用户下载即用）"
