from pathlib import Path
import json
import shlex
import sys

import yaml


if len(sys.argv) != 2:
    raise SystemExit(f"Usage: {sys.argv[0]} patch_settings.yaml")


config_path = Path(sys.argv[1]).expanduser().resolve()

with config_path.open("r", encoding="utf-8") as f:
    config = yaml.safe_load(f)


supported_version = str(config["supported_version"])
target = Path(config["extension_path"]).expanduser().resolve()
verify_sha256 = bool(config.get("verify_SHA256", True))

expected = config["expected_SHA256"]


# ===========================================================================
# Find Continue extension version
#
# extension.js:
#
#   continue.continue-2.0.0-darwin-arm64/
#       package.json
#       out/
#           extension.js
# ===========================================================================

package_json = target.parent.parent / "package.json"

if not package_json.is_file():
    raise RuntimeError(
        f"Could not find Continue package.json: {package_json}"
    )

with package_json.open("r", encoding="utf-8") as f:
    package = json.load(f)

installed_version = str(package.get("version", ""))

if not installed_version:
    raise RuntimeError(
        f"Could not determine Continue version from {package_json}"
    )


# ===========================================================================
# Emit shell-safe assignments
# ===========================================================================

values = {
    "TARGET": str(target),
    "SUPPORTED_VERSION": supported_version,
    "INSTALLED_VERSION": installed_version,
    "VERIFY_SHA256": "1" if verify_sha256 else "0",
    "SHA256_ORIGINAL": str(expected["original"]),
    "SHA256_PATCHED_LOGS": str(expected["patched_logs"]),
    "SHA256_PATCHED_FULL": str(expected["patched_full"]),
}

for key, value in values.items():
    print(f"{key}={shlex.quote(value)}")
