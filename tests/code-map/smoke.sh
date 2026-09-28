#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"
cd "$TEST_TMPDIR"
printf 'class Foo:\n    def m(self):\n        pass\n\ndef bar():\n    pass\n' > m.py

out=$(python3 "$REPO_ROOT/tools/code-map/code_map.py" m.py)
assert_contains "class Foo" "$out"
assert_contains "def bar" "$out"

echo "code-map OK"
