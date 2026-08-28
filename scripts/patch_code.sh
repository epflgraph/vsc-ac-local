#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/shared.sh"

load_patch_config

TMP="${TARGET}.behavior-patch.js"

verify_checksum "$TARGET" "$SHA256_PATCHED_LOGS" "input"

require_backup

rm -f "$TMP"
cp -p "$TARGET" "$TMP"

cleanup() {
  rm -f "$TMP"
}

trap cleanup EXIT INT TERM

python3 "$PROJECT_DIR/src/patch_code.py" "$TMP"

validate_javascript "$TMP"

verify_checksum "$TMP" "$SHA256_PATCHED_FULL" "output"

mv "$TMP" "$TARGET"
trap - EXIT INT TERM

verify_checksum "$TARGET" "$SHA256_PATCHED_FULL" "final"

echo "✅ Code patch complete: $TARGET"
