#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

S="$REPO_ROOT/tools/privacy-scan/privacy_scan.py"
BAD="$TEST_TMPDIR/dirty"
CLEAN="$TEST_TMPDIR/clean"
mkdir -p "$BAD" "$CLEAN"

# Plant leaks — composed via printf so this script itself stays clean
# under a repo-wide scan.
n=99
printf 'LLM_BASE_URL="http://192.168.%s.7/v1"\n' "$n" > "$BAD/config.txt"
printf 'workspace=/home/%s/x\n' "$n" >> "$BAD/config.txt"
printf 'key=sk-%s\n' "abcdefghij1234" >> "$BAD/config.txt"
printf 'contact=bob@%s\n' "corp.example.io" >> "$BAD/config.txt"
printf 'notes=ok\n' > "$CLEAN/readme.txt"

# dirty dir -> exit 1 with hits on stdout
rc=0
out=$(python3 "$S" "$BAD") || rc=$?
assert_eq "$rc" "1"
assert_contains 'private-ip' "$out"
assert_contains 'home-path' "$out"
assert_contains 'token' "$out"
assert_contains 'email' "$out"
assert_contains 'config.txt' "$out"

# clean dir -> exit 0, ok:true
out=$(python3 "$S" "$CLEAN")
assert_contains '"ok": true' "$out"

# extra patterns via env var
printf 'team=totally-secret-project\n' >> "$BAD/config.txt"
rc=0
out=$(PRIVACY_EXTRA_PATTERNS="totally-secret-project" python3 "$S" "$BAD") || rc=$?
assert_eq "$rc" "1"
assert_contains 'totally-secret-project' "$out"

# nonexistent dir -> exit 2
rc=0
python3 "$S" "$TEST_TMPDIR/nope" >/dev/null 2>&1 || rc=$?
assert_eq "$rc" "2"

# the repo itself must be clean (regression gate)
python3 "$S" "$REPO_ROOT" >/dev/null || fail "repo scan reported hits"

echo "privacy-scan OK"
