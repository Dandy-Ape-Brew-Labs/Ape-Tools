#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"
cd "$TEST_TMPDIR"
printf 'a = 1\nb = 2\na = 1 again\nc = 3\n' > f.py

# single unique edit
python3 "$REPO_ROOT/tools/file-edit/file_edit.py" f.py --old "b = 2" --new "b = 9" >/dev/null
assert_eq "$(sed -n 2p f.py)" "b = 9"

# ambiguous match refused
if python3 "$REPO_ROOT/tools/file-edit/file_edit.py" f.py --old "a = 1" --new "x" 2>/dev/null; then
  fail "expected ambiguous-match refusal"
fi

# replace-all
python3 "$REPO_ROOT/tools/file-edit/file_edit.py" f.py --old "a = 1" --new "a = 7" --replace-all >/dev/null
assert_eq "$(grep -c '^a = 7' f.py)" "2"

# dry-run changes nothing
before=$(cat f.py)
python3 "$REPO_ROOT/tools/file-edit/file_edit.py" f.py --old "c = 3" --new "c = 4" --dry-run >/dev/null
assert_eq "$before" "$(cat f.py)"

# multi-edit atomic
cat > edits.json <<'EOF'
[{"old": "c = 3", "new": "c = 4"}, {"old": "b = 9", "new": "b = 0"}]
EOF
python3 "$REPO_ROOT/tools/file-edit/file_edit.py" f.py --edits edits.json >/dev/null
assert_contains "c = 4" "$(cat f.py)"
assert_contains "b = 0" "$(cat f.py)"

echo "file-edit OK"
