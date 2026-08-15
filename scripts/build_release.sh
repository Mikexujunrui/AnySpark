#!/bin/bash
# ============================================================
# build_release.sh — AnySpark v4 exe 发布打包
#
# 产物：单文件 AnySpark.exe（PyInstaller，内置前后端）+ 使用说明 + 空 data 模板 → zip
# 用途：挂到 GitHub Release，给正式用户（双击即用，无需 Python/Node）
#
# 用法：
#   bash scripts/build_release.sh              # 默认版本 v4.0.0
#   bash scripts/build_release.sh v4.1.0       # 指定版本号
#
# 输出：<仓库上级>/AnySparkV4-发布-exe/AnySpark_Windows_x64_<版本>.zip
# 说明：源码分发形态用 scripts/package_release.py（群内测/预览），本脚本只出 exe。
# ============================================================
set -e

VERSION="${1:-v4.0.0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_BASE="$(dirname "$ROOT")/AnySparkV4-发布-exe"
STAGE="$ROOT/build/release_stage"

echo "===== AnySpark v4 exe 发布打包（$VERSION）====="

echo "[1/4] 构建前端产物..."
(cd "$ROOT/frontend" && npm run build)

echo "[2/4] 清理旧 exe..."
rm -f "$ROOT/dist/AnySpark.exe"

echo "[3/4] PyInstaller 打包（内置前后端，约 1-3 分钟）..."
(cd "$ROOT" && uv run pyinstaller anyspark.spec --noconfirm)

echo "[4/4] 组装发布包..."
rm -rf "$STAGE" && mkdir -p "$STAGE/data"
cp "$ROOT/dist/AnySpark.exe" "$STAGE/"
cat > "$STAGE/使用说明.txt" << 'EOF'
AnySpark v4 创作台（独立版）

使用：
1. 双击 AnySpark.exe 启动（自动在 exe 同目录创建 data/ 与 .env 模板）
2. 编辑 data/.env，填入你的 DeepSeek API Key（DEEPSEEK_API_KEY=sk-...）
3. 重新启动 exe，浏览器/窗口打开后即可使用

数据：所有作品数据（章节/图谱/书库）保存在 exe 同目录 data/，可整体拷贝迁移。
日志：data/logs/anyspark.log
EOF

mkdir -p "$OUT_BASE"
OUT="$OUT_BASE/AnySpark_Windows_x64_${VERSION}.zip"
python - "$STAGE" "$OUT" << 'EOF'
import shutil, sys
stage, out = sys.argv[1], sys.argv[2]
# make_archive 的 base 不能带扩展名，生成后改名
base = out[:-4]
shutil.make_archive(base, "zip", root_dir=stage)
print(f"zip 已生成: {out}")
EOF
rm -rf "$STAGE"

echo ""
echo "✅ 发布包已生成：$OUT"
echo "   挂到 GitHub Release 即可（正式用户下载解压 → 双击 AnySpark.exe）"
