#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
BUILD_VENV="${BUILD_VENV:-$ROOT/.venv-macos-build}"
PNPM_BIN="${PNPM_BIN:-}"
NODE_BIN="${NODE_BIN:-}"
SKIP_INSTALL="${SKIP_INSTALL:-0}"
ICON_ROOT=""
BUILD_ROOT=""

cleanup() {
    local status=$?
    if [[ -n "$ICON_ROOT" && "$ICON_ROOT" == /tmp/anyspark-icon.* ]]; then
        rm -rf -- "$ICON_ROOT"
    fi
    if [[ -n "$BUILD_ROOT" && "$BUILD_ROOT" == /tmp/anyspark-build.* ]]; then
        rm -rf -- "$BUILD_ROOT"
    fi
    # Building and verification must never leave a mounted installer volume.
    # We intentionally do not detach volumes that existed before this script;
    # the build itself never opens the DMG.
    local mounted_path
    while IFS= read -r mounted_path; do
        if [[ "$mounted_path" == "/Volumes/火花 AnySpark (构建验证)"* ]]; then
            hdiutil detach "$mounted_path" -quiet 2>/dev/null || true
        fi
    done < <(hdiutil info | awk -F' : ' '/mount-point/ {print $2}')
    return "$status"
}

trap cleanup EXIT

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
rm -rf -- "$ICON_ROOT"
ICON_ROOT=""

echo "[5/6] Building AnySpark.app..."
mkdir -p dist build
touch dist/.metadata_never_index build/.metadata_never_index
# Remove only legacy PyInstaller app bundles from this repository's ignored
# output directory. Installers remain; the installed /Applications app and all
# user data live elsewhere and are never touched.
find "$ROOT/dist" -maxdepth 1 -type d -name 'AnySpark*.app' -exec rm -rf -- {} +
rm -rf -- "$ROOT/build/AnySpark" "$ROOT/dist/AnySpark"

# A raw .app inside Documents is indexed by Spotlight and looks like another
# installation. Keep all intermediate apps under /tmp and publish installers
# only, so the user's Mac returns to its pre-build state after every run.
BUILD_ROOT="$(mktemp -d /tmp/anyspark-build.XXXXXX)"
WORK_DIST="$BUILD_ROOT/dist"
WORK_BUILD="$BUILD_ROOT/build"
export PYINSTALLER_CONFIG_DIR="$BUILD_ROOT/pyinstaller-config"
mkdir -p "$WORK_DIST" "$WORK_BUILD" "$PYINSTALLER_CONFIG_DIR"
"$BUILD_VENV/bin/pyinstaller" \
    --noconfirm \
    --clean \
    --distpath "$WORK_DIST" \
    --workpath "$WORK_BUILD" \
    anyspark_macos.spec
SIGNED_APP="$BUILD_ROOT/AnySpark.app"
ditto --noextattr --noqtn "$WORK_DIST/AnySpark.app" "$SIGNED_APP"
xattr -cr "$SIGNED_APP"
xattr -d com.apple.FinderInfo "$SIGNED_APP" 2>/dev/null || true
xattr -d com.apple.fileprovider.fpfs#P "$SIGNED_APP" 2>/dev/null || true
codesign --force --deep --sign - "$SIGNED_APP"
codesign --verify --deep --strict --verbose=2 "$SIGNED_APP"

echo "[6/6] Creating drag-to-install DMG..."
VERSION="${ANYSPARK_BUILD_VERSION:-$("$BUILD_VENV/bin/python" -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')}"
BUILD_LABEL="${ANYSPARK_BUILD_LABEL:-$VERSION}"
ARCH="$(uname -m)"
DMG_STAGE="$BUILD_ROOT/dmg-stage"
DMG_PATH="$ROOT/dist/AnySpark_${BUILD_LABEL}_macOS_${ARCH}.dmg"
ZIP_PATH="$ROOT/dist/AnySpark_${BUILD_LABEL}_macOS_${ARCH}.zip"
mkdir -p "$DMG_STAGE"
ditto --noextattr --noqtn "$SIGNED_APP" "$DMG_STAGE/AnySpark.app"
ln -s /Applications "$DMG_STAGE/Applications"
rm -f "$DMG_PATH"
hdiutil create -volname "火花 AnySpark" -srcfolder "$DMG_STAGE" -ov -format UDZO "$DMG_PATH"
hdiutil verify "$DMG_PATH" >/dev/null
rm -f "$ZIP_PATH"
ditto -c -k --norsrc --noextattr --keepParent "$SIGNED_APP" "$ZIP_PATH"

# Regression guard: no raw application bundle may survive under the source
# tree, otherwise Spotlight lists a broken development copy beside the real
# application in /Applications.
if find "$ROOT/dist" "$ROOT/build" -type d -name 'AnySpark*.app' -print -quit | grep -q .; then
    echo "ERROR: a raw AnySpark.app survived in the project output directories."
    exit 1
fi

echo
echo "Build complete:"
echo "  DMG: $DMG_PATH"
echo "  ZIP: $ZIP_PATH"
