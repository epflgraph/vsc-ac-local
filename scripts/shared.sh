#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

CONFIG_FILE="$PROJECT_DIR/config/patch_settings.yaml"


# ===========================================================================
# Load configuration
# ===========================================================================

load_patch_config() {
  if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ Config not found: $CONFIG_FILE" >&2
    exit 1
  fi

  eval "$(python3 "$PROJECT_DIR/src/read_config.py" "$CONFIG_FILE")"

  BACKUP="${TARGET}.bak"

  if [ ! -f "$TARGET" ]; then
    echo "❌ Target not found: $TARGET" >&2
    exit 1
  fi

  echo "📦 Continue version:"
  echo "   Supported: $SUPPORTED_VERSION"
  echo "   Installed: $INSTALLED_VERSION"

  if [ "$INSTALLED_VERSION" != "$SUPPORTED_VERSION" ]; then
    echo "❌ Unsupported Continue version." >&2
    exit 1
  fi

  echo "✅ Continue version supported."
  echo "📄 Target: $TARGET"

  if [ "$VERIFY_SHA256" -eq 1 ]; then
    echo "🔐 SHA-256 verification enabled."
  else
    echo "⚠️ SHA-256 verification disabled."
  fi
}


# ===========================================================================
# SHA-256 helper
# ===========================================================================

checksum_file() {
  python3 "$PROJECT_DIR/src/checksum_file.py" "$1"
}


# ===========================================================================
# Verify checksum
# ===========================================================================

verify_checksum() {
  VERIFY_FILE=$1
  VERIFY_EXPECTED=$2
  VERIFY_LABEL=$3

  if [ "$VERIFY_SHA256" -ne 1 ]; then
    return 0
  fi

  VERIFY_ACTUAL=$(checksum_file "$VERIFY_FILE")

  echo "🔐 Expected $VERIFY_LABEL SHA-256: $VERIFY_EXPECTED"
  echo "🔐 Actual $VERIFY_LABEL SHA-256:   $VERIFY_ACTUAL"

  if [ "$VERIFY_ACTUAL" != "$VERIFY_EXPECTED" ]; then
    echo "❌ FAIL: $VERIFY_LABEL checksum does not match." >&2
    exit 1
  fi

  echo "✅ PASS: $VERIFY_LABEL checksum matches."
}


# ===========================================================================
# Validate generated JavaScript
# ===========================================================================

validate_javascript() {
  JS_FILE=$1

  echo ""
  echo "🔎 Validating JavaScript syntax..."

  if command -v node >/dev/null 2>&1; then
    if ! node --check "$JS_FILE"; then
      echo "❌ JavaScript syntax validation failed." >&2
      exit 1
    fi

    echo "✅ JavaScript syntax valid."
  else
    echo "⚠️ node not found; skipping JavaScript syntax validation."
  fi
}


# ===========================================================================
# Create pristine backup if needed
# ===========================================================================

ensure_backup() {
  if [ ! -f "$BACKUP" ]; then
    cp -p "$TARGET" "$BACKUP"
    echo "💾 Created backup: $BACKUP"
  else
    echo "💾 Keeping existing backup: $BACKUP"
  fi
}


# ===========================================================================
# Require existing pristine backup
# ===========================================================================

require_backup() {
  if [ ! -f "$BACKUP" ]; then
    echo "❌ Backup not found: $BACKUP" >&2
    exit 1
  fi

  echo "💾 Existing backup: $BACKUP"
}
