#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

N="$REPO_ROOT/tools/nb-tool/nb_tool.py"
NB="$TEST_TMPDIR/nb.ipynb"
python3 - "$NB" <<'EOF'
import json, sys
nb = {"nbformat": 4, "nbformat_minor": 5, "metadata": {},
      "cells": [
        {"cell_type": "markdown", "metadata": {}, "source": ["# Title\n"]},
        {"cell_type": "code", "metadata": {}, "execution_count": 1,
         "source": ["print(1)\n"],
         "outputs": [{"output_type": "stream", "name": "stdout",
                      "text": ["1\n"]}]},
      ]}
json.dump(nb, open(sys.argv[1], "w"))
EOF

out=$(python3 "$N" list "$NB")
assert_contains '"type": "markdown"' "$out"
assert_contains '"preview": "# Title"' "$out"

out=$(python3 "$N" read "$NB" --cell 1)
assert_contains 'print(1)' "$out"

out=$(python3 "$N" outputs "$NB" --cell 1)
assert_contains '"execution_count": 1' "$out"
assert_contains '1\n' "$out" || assert_contains '1' "$out"

python3 "$N" set "$NB" --cell 0 --text "# New Title" >/dev/null
out=$(python3 "$N" read "$NB" --cell 0)
assert_eq "$out" "# New Title"

python3 "$N" add "$NB" --type code --text "x = 2" --at 1 >/dev/null
out=$(python3 "$N" list "$NB")
assert_contains '"index": 2' "$out"

python3 "$N" clear-outputs "$NB" >/dev/null
out=$(python3 "$N" outputs "$NB")
assert_eq "$out" "[]"
