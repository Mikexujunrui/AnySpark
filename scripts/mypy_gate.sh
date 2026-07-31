#!/usr/bin/env bash
# Incremental mypy gate: fail the build only when the mypy error count
# grows beyond the committed baseline (.mypy-baseline, a bare integer).
#
# How to refresh the baseline after intentionally fixing errors:
#   python -m mypy src/ --ignore-missing-imports --no-strict-optional \
#       --no-site-packages 2>&1 | grep -c 'error:' | tee .mypy-baseline
#
# Local note: this machine may ship a broken stub package (e.g. rdkit-stubs
# in site-packages) that mypy parses at startup and aborts on. CI environments
# don't install it; if you see `rdkit-stubs ... [syntax]` locally, run with
# --no-site-packages as done below.
set -euo pipefail

cd "$(dirname "$0")/.."

# Allow overriding the interpreter (Windows/WSL may need `PYTHON=...`)
PYTHON=${PYTHON:-python}

BASELINE=$(tr -d '[:space:]' < .mypy-baseline)

# Run the plain command first (most faithful type resolution). If a broken
# stub package in site-packages blocks startup (e.g. rdkit-stubs [syntax]
# parse error => "errors prevented further checking"), retry with
# --no-site-packages so the check still runs.
OUTPUT=$($PYTHON -m mypy src/ --ignore-missing-imports --no-strict-optional 2>&1 || true)
COUNT=$(printf '%s\n' "$OUTPUT" | grep -c 'error:' || true)
if printf '%s\n' "$OUTPUT" | grep -q 'errors prevented further checking'; then
    OUTPUT=$($PYTHON -m mypy src/ --ignore-missing-imports --no-strict-optional --no-site-packages 2>&1 || true)
    COUNT=$(printf '%s\n' "$OUTPUT" | grep -c 'error:' || true)
fi
echo "mypy errors: $COUNT (baseline: $BASELINE)"

if [ "$COUNT" -gt "$BASELINE" ]; then
    echo "::error::mypy errors increased ($COUNT > $BASELINE). Fix the new errors, or bump .mypy-baseline only when the increase is intended."
    printf '%s\n' "$OUTPUT" | grep 'error:' | head -60
    exit 1
fi

echo "OK: mypy within baseline."
