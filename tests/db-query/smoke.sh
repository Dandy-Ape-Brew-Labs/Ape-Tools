#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"

D="$REPO_ROOT/tools/db-query/db_query.py"
DB="$TEST_TMPDIR/test.db"
sqlite3 "$DB" "CREATE TABLE t(id INTEGER PRIMARY KEY, name TEXT);
              INSERT INTO t(name) VALUES('alice'),('bob');"

out=$(python3 "$D" --db "$DB" --tables)
assert_contains '"name": "t"' "$out"

out=$(python3 "$D" --db "$DB" --sql "SELECT name FROM t ORDER BY id")
assert_contains '"name": "alice"' "$out"
assert_contains '"name": "bob"' "$out"

out=$(python3 "$D" --db "$DB" --sql "SELECT * FROM t" --limit 1)
assert_contains 'alice' "$out"
assert_not_contains 'bob' "$out"

out=$(python3 "$D" --db "$DB" --schema t)
assert_contains 'CREATE TABLE t' "$out"

if python3 "$D" --db "$DB" --sql "SELECT * FROM missing" 2>/dev/null; then
  fail "expected failure for bad query"
fi
