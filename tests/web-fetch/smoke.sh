#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"
cd "$TEST_TMPDIR"

cat > page.html <<'EOF'
<html><body><article><h1>Test Article</h1>
<p>The quick brown fox jumps over the lazy dog repeatedly to make enough
text for the extractor to identify a main content block in this page.</p>
</article></body></html>
EOF

# serve the fixture locally — deterministic, no external network
python3 -m http.server 18423 --directory "$TEST_TMPDIR" >/dev/null 2>&1 &
SRV=$!
trap "kill $SRV 2>/dev/null || true" EXIT
sleep 0.7

out=$(cd "$REPO_ROOT" && uv run --quiet tools/web-fetch/web_fetch.py http://127.0.0.1:18423/page.html)
assert_contains "quick brown fox" "$out"
assert_eq "$(echo "$out" | jqv 'd["format"]')" "markdown"

echo "web-fetch OK"
