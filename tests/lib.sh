# Shared helpers for smoke tests. Sourced by tests/<tool>/smoke.sh.
# Provides: TEST_TMPDIR (scratch dir), fail, assert_eq, assert_contains,
# assert_json_field (python eval on stdin JSON).
set -euo pipefail
TEST_TMPDIR="${TEST_TMPDIR:-$(mktemp -d)}"
mkdir -p "$TEST_TMPDIR"

fail() { echo "FAIL: $*" >&2; exit 1; }
assert_eq() { [ "$1" = "$2" ] || fail "expected '$2', got '$1'"; }
assert_neq() { [ "$1" != "$2" ] || fail "did not expect '$1'"; }
assert_contains() { case "$2" in *"$1"*) ;; *) fail "output missing '$1'";; esac; }
assert_not_contains() { case "$2" in *"$1"*) fail "output has unexpected '$1'";; *) ;; esac; }
assert_file() { [ -f "$1" ] || fail "expected file: $1"; }
assert_no_file() { [ ! -e "$1" ] || fail "unexpected file: $1"; }
# eval a python expression against JSON on stdin: jqv 'd["x"]'
jqv() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }
