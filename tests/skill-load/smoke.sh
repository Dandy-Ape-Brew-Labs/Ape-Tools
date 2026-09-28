#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

S="$REPO_ROOT/tools/skill-load/skill_load.py"
root="$TEST_TMPDIR/skills"
mkdir -p "$root/demo-skill"
cat > "$root/demo-skill/SKILL.md" <<'EOF'
---
name: demo-skill
description: A fixed demo skill for smoke testing.
---
# Demo

Body text 12345.
EOF

# list finds the fixture
out=$(python3 "$S" list --roots "$root")
assert_contains 'demo-skill' "$out"
assert_contains 'A fixed demo skill' "$out"

# get returns content + path
out=$(python3 "$S" get demo-skill --roots "$root")
assert_contains 'Body text 12345' "$out"
assert_contains 'SKILL.md' "$out"

# unknown skill -> 1, and names the available ones
rc=0
python3 "$S" get nope --roots "$root" >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 1 ] || fail "expected exit 1 for unknown skill, got $rc"

echo "skill-load OK"
