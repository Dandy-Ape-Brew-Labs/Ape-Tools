#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

V="$REPO_ROOT/tools/serve/serve.py"

echo "artifact" > "$TEST_TMPDIR/artifact.txt"

out=$(python3 "$V" serve "$TEST_TMPDIR")
assert_contains '"url"' "$out"
pid=$(echo "$out" | jqv 'd["proc"]')
url=$(echo "$out" | jqv 'd["url"]')

# fetch it back
sleep 0.5
body=$(python3 -c "import urllib.request;print(urllib.request.urlopen('$url'+'artifact.txt',timeout=10).read().decode())")
assert_contains 'artifact' "$body"

out=$(python3 "$V" list)
assert_contains "$pid" "$out"

out=$(python3 "$V" stop "$pid")
assert_contains '"killed": true' "$out"

# missing path -> exit 2
rc=0
python3 "$V" serve "$TEST_TMPDIR/nope" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 2 ] || fail "expected exit 2 for missing path, got $rc"

echo "serve OK"
