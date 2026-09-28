#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

A="$REPO_ROOT/tools/ast-search/ast_search.py"
SRC="$TEST_TMPDIR/src"
mkdir -p "$SRC"
cat > "$SRC/mod.py" <<'EOF'
import os
import requests as r

# calls find_me() in a comment — must NOT match
def find_me():
    pass

def caller():
    db = r.Session()
    find_me()          # real call
    db.get("http://x")
EOF
cat > "$SRC/other.py" <<'EOF'
class Widget:
    def render(self):
        pass
EOF

out=$(python3 "$A" symbols "$SRC")
assert_contains '"name": "find_me"' "$out"
assert_contains '"name": "Widget"' "$out"

out=$(python3 "$A" calls "$SRC" --name "^find_me$")
assert_eq "$(echo "$out" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')" "1"

out=$(python3 "$A" calls "$SRC" --name "r\.Session")
assert_contains '"name": "r.Session"' "$out"

out=$(python3 "$A" imports "$SRC" --name requests)
assert_contains 'requests' "$out"

out=$(python3 "$A" refs "$SRC" --name "^find_me$")
# def site + call site both are Name refs? find_me: FunctionDef name is
# not a Name node — refs finds the call's Name only.
assert_eq "$(echo "$out" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')" "1"
