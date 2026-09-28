#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"
cd "$TEST_TMPDIR"
printf 'def parse_x():\n    pass\n\ndef other():\n    parse_x()\n' > m.py
printf 'nothing here\n' > n.py

out=$(python3 "$REPO_ROOT/tools/code-grep/code_grep.py" "parse_x" --mode files --path .)
assert_contains "m.py" "$out"

out=$(python3 "$REPO_ROOT/tools/code-grep/code_grep.py" "parse_x" --path .)
assert_eq "$(echo "$out" | jqv 'd["total"]')" "2"
assert_eq "$(echo "$out" | jqv 'd["matches"][0]["line"]')" "1"

# no matches -> exit 1
if python3 "$REPO_ROOT/tools/code-grep/code_grep.py" "zzz_never_zzz" --path . >/dev/null 2>&1; then
  fail "expected exit 1 on no matches"
fi

echo "code-grep OK"
