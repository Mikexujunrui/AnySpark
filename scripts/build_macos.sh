#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
BUILD_VENV="${BUILD_VENV:-$ROOT/.venv-macos-build}"
PNPM_BIN="${PNPM_BIN:-}"
NODE_BIN="${NODE_BIN:-}"
SKIP_INSTALL="${SKIP_INSTALL:-0}"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "ERROR: The macOS application must be built on macOS."
    exit 1
fi

echo "[1/6] Preparing Python build environment..."
if [[ ! -x "$BUILD_VENV/bin/python" ]]; then
    "$PYTHON_BIN" -m venv "$BUILD_VENV"
fi
if [[ "$SKIP_INSTALL" == "1" ]]; then
    if [[ ! -x "$BUILD_VENV/bin/pyinstaller" ]]; then
        echo "ERROR: SKIP_INSTALL=1 requires PyInstaller in $BUILD_VENV."
        exit 1
    fi
    echo "      Reusing the existing Python build environment."
else
    "$BUILD_VENV/bin/python" -m pip install --upgrade pip
    "$BUILD_VENV/bin/python" -m pip install -r requirements-macos.txt
fi

echo "[2/6] Installing frontend dependencies..."
if [[ "$SKIP_INSTALL" == "1" ]]; then
    if [[ ! -x frontend/node_modules/.bin/vite ]]; then
        echo "ERROR: SKIP_INSTALL=1 requires existing frontend dependencies."
        exit 1
    fi
    echo "      Reusing the existing frontend dependencies."
elif command -v npm >/dev/null 2>&1; then
    npm ci --prefix frontend
elif [[ -n "$PNPM_BIN" && -x "$PNPM_BIN" ]]; then
    "$PNPM_BIN" --dir frontend install --no-frozen-lockfile
elif command -v pnpm >/dev/null 2>&1; then
    pnpm --dir frontend install --no-frozen-lockfile
else
    echo "ERROR: Node.js with npm or pnpm is required to build the frontend."
    exit 1
fi

echo "[3/6] Building frontend..."
if command -v npm >/dev/null 2>&1; then
    npm run build --prefix frontend
elif [[ -n "$NODE_BIN" && -x "$NODE_BIN" ]]; then
    "$NODE_BIN" frontend/node_modules/vite/bin/vite.js build frontend --config frontend/vite.config.js
elif [[ -n "$PNPM_BIN" && -x "$PNPM_BIN" ]]; then
    "$PNPM_BIN" --dir frontend run build
else
    pnpm --dir frontend run build
fi

echo "[4/6] Generating application icon..."
mkdir -p packaging/macos
# macOS 26 iconutil can reject otherwise valid generated icon sets. Pillow's
# native ICNS writer avoids that platform regression. Build under /tmp so File
# Provider metadata from Documents cannot affect the generated icon.
ICON_ROOT="$(mktemp -d /tmp/anyspark-icon.XXXXXX)"
"$BUILD_VENV/bin/python" scripts/generate_macos_icon.py "$ICON_ROOT/AnySpark.icns"
ditto --noextattr --noqtn "$ICON_ROOT/AnySpark.icns" packaging/macos/AnySpark.icns
rm -rf "$ICON_ROOT"

echo "[5/6] Building AnySpark.app..."
rm -rf build/AnySpark dist/AnySpark dist/AnySpark.app
"$BUILD_VENV/bin/pyinstaller" --noconfirm --clean anyspark_macos.spec
# File Provider may continuously re-attach Finder metadata to .app directories
# under Documents. Copy to /tmp for a stable, clean signing environment.
SIGN_ROOT="$(mktemp -d /tmp/anyspark-sign.XXXXXX)"
trap 'rm -rf "$SIGN_ROOT"' EXIT
SIGNED_APP="$SIGN_ROOT/AnySpark.app"
ditto --noextattr --noqtn dist/AnySpark.app "$SIGNED_APP"
xattr -cr "$SIGNED_APP"
xattr -d com.apple.FinderInfo "$SIGNED_APP" 2>/dev/null || true
xattr -d com.apple.fileprovider.fpfs#P "$SIGNED_APP" 2>/dev/null || true
codesign --force --deep --sign - "$SIGNED_APP"
codesign --verify --deep --strict --verbose=2 "$SIGNED_APP"

echo "[6/6] Creating drag-to-install DMG..."
VERSION="${ANYSPARK_BUILD_VERSION:-$("$BUILD_VENV/bin/python" -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')}"
BUILD_LABEL="${ANYSPARK_BUILD_LABEL:-$VERSION}"
ARCH="$(uname -m)"
DMG_STAGE="$SIGN_ROOT/dmg-stage"
DMG_PATH="$ROOT/dist/AnySpark_${BUILD_LABEL}_macOS_${ARCH}.dmg"
ZIP_PATH="$ROOT/dist/AnySpark_${BUILD_LABEL}_macOS_${ARCH}.zip"
mkdir -p "$DMG_STAGE"
ditto --noextattr --noqtn "$SIGNED_APP" "$DMG_STAGE/AnySpark.app"
ln -s /Applications "$DMG_STAGE/Applications"
rm -f "$DMG_PATH"
hdiutil create -volname "火花 AnySpark" -srcfolder "$DMG_STAGE" -ov -format UDZO "$DMG_PATH"
rm -f "$ZIP_PATH"
ditto -c -k --norsrc --noextattr --keepParent "$SIGNED_APP" "$ZIP_PATH"

echo
echo "Build complete:"
echo "  DMG: $DMG_PATH"
echo "  ZIP: $ZIP_PATH"
