#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

U="$REPO_ROOT/tools/util-kit/util_kit.py"
out=$(python3 "$U" now --utc)
assert_contains '"iso"' "$out"
assert_contains '"epoch"' "$out"

echo -n "abc" > "$TEST_TMPDIR/x.txt"
out=$(python3 "$U" hash "$TEST_TMPDIR/x.txt")
assert_contains 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad' "$out"

out=$(echo -n "hello" | python3 "$U" b64 encode)
assert_eq "$out" "aGVsbG8="
out=$(echo -n "aGVsbG8=" | python3 "$U" b64 decode)
assert_eq "$out" "hello"

out=$(python3 "$U" uuid)
echo "$out" | grep -qE '^[0-9a-f-]{36}$' || fail "bad uuid: $out"

out=$(echo '{"b":1,"a":2}' | python3 "$U" json keys)
assert_contains '"a"' "$out"

export SECRET_API_KEY_TEST=shouldbehidden
out=$(python3 "$U" env --prefix SECRET_API)
assert_contains '***' "$out"
assert_not_contains 'shouldbehidden' "$out"
