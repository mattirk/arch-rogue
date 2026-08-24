#!/usr/bin/env bash
# Resolve, download, and inject the licensed runtime SFX bundle without retaining
# the private transport artifact. Intended for authorized public release runners.

set -euo pipefail
set +x

: "${ARCH_ROGUE_SFX_RELEASE_API_URL:?ARCH_ROGUE_SFX_RELEASE_API_URL is required}"
: "${ARCH_ROGUE_SFX_BUNDLE_AUTHORIZATION:?ARCH_ROGUE_SFX_BUNDLE_AUTHORIZATION is required}"
ARCH_ROGUE_SFX_BUNDLE_NAME="${ARCH_ROGUE_SFX_BUNDLE_NAME:-arch-rogue-sfx-runtime.tar.gz}"

if [[ ! "$ARCH_ROGUE_SFX_RELEASE_API_URL" =~ ^https:// ]]; then
  echo "licensed SFX release API URL must use HTTPS" >&2
  exit 1
fi
if [[ -n "${ARCH_ROGUE_SFX_BUNDLE_SHA256:-}" && ! "$ARCH_ROGUE_SFX_BUNDLE_SHA256" =~ ^[0-9a-fA-F]{64}$ ]]; then
  echo "optional licensed SFX bundle SHA-256 must be exactly 64 hexadecimal characters" >&2
  exit 1
fi
if [[ "$ARCH_ROGUE_SFX_BUNDLE_NAME" == */* || "$ARCH_ROGUE_SFX_BUNDLE_NAME" != *.tar.gz ]]; then
  echo "licensed SFX bundle name must be a plain .tar.gz filename" >&2
  exit 1
fi

work="$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/arch-rogue-sfx.XXXXXX")"
trap 'rm -rf "$work"' EXIT
metadata="$work/release.json"
bundle="$work/runtime-sfx.tar.gz"

curl \
  --fail --silent --show-error --location \
  --proto '=https' --proto-redir '=https' --tlsv1.2 \
  --retry 3 --retry-all-errors \
  --header 'Accept: application/vnd.github+json' \
  --header "Authorization: $ARCH_ROGUE_SFX_BUNDLE_AUTHORIZATION" \
  --output "$metadata" \
  "$ARCH_ROGUE_SFX_RELEASE_API_URL"

asset_url="$(python3 - "$metadata" "$ARCH_ROGUE_SFX_BUNDLE_NAME" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    release = json.load(source)
name = sys.argv[2]
matches = [asset for asset in release.get("assets", []) if asset.get("name") == name]
if len(matches) != 1 or not isinstance(matches[0].get("url"), str):
    raise SystemExit(f"private SFX release must contain exactly one asset named {name!r}")
print(matches[0]["url"])
PY
)"
if [[ ! "$asset_url" =~ ^https:// ]]; then
  echo "private release returned a non-HTTPS SFX asset URL" >&2
  exit 1
fi

curl \
  --fail --silent --show-error --location \
  --proto '=https' --proto-redir '=https' --tlsv1.2 \
  --retry 3 --retry-all-errors \
  --header 'Accept: application/octet-stream' \
  --header "Authorization: $ARCH_ROGUE_SFX_BUNDLE_AUTHORIZATION" \
  --output "$bundle" \
  "$asset_url"

if [[ -n "${ARCH_ROGUE_SFX_BUNDLE_SHA256:-}" ]]; then
  printf '%s  %s\n' "${ARCH_ROGUE_SFX_BUNDLE_SHA256,,}" "$bundle" \
    | sha256sum --check --strict
fi
python3 tools/sfx_bundle.py inject --bundle "$bundle"
python3 tools/sfx_bundle.py verify
