#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/shared.sh"

load_patch_config

require_backup

echo "♻️ Restoring:"
echo "   $BACKUP"
echo "→  $TARGET"

cp -p "$BACKUP" "$TARGET"

verify_checksum "$TARGET" "$SHA256_ORIGINAL" "restored"

echo "✅ Original extension.js restored."
