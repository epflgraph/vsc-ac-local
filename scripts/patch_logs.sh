#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/shared.sh"

load_patch_config

TMP="${TARGET}.logging-patch.js"

verify_checksum "$TARGET" "$SHA256_ORIGINAL" "input"

ensure_backup

rm -f "$TMP"
cp -p "$TARGET" "$TMP"

cleanup() {
  rm -f "$TMP"
}

trap cleanup EXIT INT TERM

python3 "$PROJECT_DIR/src/patch_logs.py" "$TMP"

validate_javascript "$TMP"

verify_checksum "$TMP" "$SHA256_PATCHED_LOGS" "output"

mv "$TMP" "$TARGET"
trap - EXIT INT TERM

echo "✅ Logging patch complete: $TARGET"
