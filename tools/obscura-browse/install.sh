#!/usr/bin/env bash
# Downloads the Obscura release binary into vendor/obscura/ (gitignored).
# Usage: install.sh [--stealth | --no-stealth | --no-render | --no-render-stealth]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST="$REPO_ROOT/vendor/obscura"
VARIANT="-stealth"

case "${1:-}" in
  ""|--stealth)            VARIANT="-stealth" ;;
  --no-stealth)            VARIANT="" ;;
  --no-render)             VARIANT="-no-render" ;;
  --no-render-stealth)     VARIANT="-no-render-stealth" ;;
  *) echo "unknown option: $1" >&2; exit 2 ;;
esac

case "$(uname -sm)" in
  "Linux x86_64")  SUFFIX="x86_64-linux" ;;
  "Linux aarch64") SUFFIX="aarch64-linux" ;;
  "Darwin arm64")  SUFFIX="aarch64-macos" ;;
  "Darwin x86_64") SUFFIX="x86_64-macos" ;;
  *) echo "unsupported platform: $(uname -sm) — download manually from https://github.com/h4ckf0r0day/obscura/releases" >&2; exit 1 ;;
esac

ARCHIVE="obscura-${SUFFIX}${VARIANT}.tar.gz"
URL="https://github.com/h4ckf0r0day/obscura/releases/latest/download/${ARCHIVE}"

mkdir -p "$DEST"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
echo "downloading $URL"
curl -fL --progress-bar -o "$TMP" "$URL"
tar -xzf "$TMP" -C "$DEST"
chmod +x "$DEST/obscura" "$DEST/obscura-worker"
"$DEST/obscura" --version
echo "installed to $DEST"
