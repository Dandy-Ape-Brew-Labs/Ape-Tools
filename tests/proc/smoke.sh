#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"
cd "$TEST_TMPDIR"

id=$(python3 "$REPO_ROOT/tools/proc/proc.py" start "echo started; sleep 60" --cwd "$TEST_TMPDIR" | jqv 'd["id"]')
sleep 0.5

out=$(python3 "$REPO_ROOT/tools/proc/proc.py" read "$id" --tail 10)
assert_contains "started" "$out"
assert_contains '"status": "running"' "$out"

out=$(python3 "$REPO_ROOT/tools/proc/proc.py" list)
assert_contains "$id" "$out"

# stdin write reaches the process
id2=$(python3 "$REPO_ROOT/tools/proc/proc.py" start "read line; echo got:\$line" --cwd "$TEST_TMPDIR" | jqv 'd["id"]')
sleep 0.3
python3 "$REPO_ROOT/tools/proc/proc.py" write "$id2" --text $'hello\n' >/dev/null
sleep 0.5
out=$(python3 "$REPO_ROOT/tools/proc/proc.py" read "$id2" --tail 10)
assert_contains "got:hello" "$out"

python3 "$REPO_ROOT/tools/proc/proc.py" kill "$id" >/dev/null
out=$(python3 "$REPO_ROOT/tools/proc/proc.py" read "$id" --tail 5)
case "$out" in *'"status": "exited"'*'"exit": 143'*|*'"status": "gone"'*) ;; *) fail "expected exited/gone, got: $out";; esac

echo "proc OK"
