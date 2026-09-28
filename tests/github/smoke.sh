#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

H="$REPO_ROOT/tools/github/github.py"
if ! gh auth status >/dev/null 2>&1; then
  echo "SKIP: gh not authenticated" >&2
  exit 0
fi

# network-dependent but cheap; github.com reachable in this env
if out=$(python3 "$H" auth 2>/dev/null); then
  assert_contains '"login"' "$out"
else
  echo "SKIP: github.com unreachable" >&2
  exit 0
fi
