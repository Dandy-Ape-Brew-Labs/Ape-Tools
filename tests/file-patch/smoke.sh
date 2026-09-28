#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"
cd "$TEST_TMPDIR"
printf 'def greet():\n    print("Hi")\n\nx = 1\n' > app.py

python3 "$REPO_ROOT/tools/file-patch/file_patch.py" --cwd "$TEST_TMPDIR" <<'EOF'
*** Begin Patch
*** Update File: app.py
@@ def greet():
-    print("Hi")
+    print("Hello")
*** Add File: new.py
+print("new")
*** End Patch
EOF

assert_contains 'print("Hello")' "$(cat app.py)"
assert_file new.py

# delete
python3 "$REPO_ROOT/tools/file-patch/file_patch.py" --cwd "$TEST_TMPDIR" <<'EOF'
*** Begin Patch
*** Delete File: new.py
*** End Patch
EOF
assert_no_file new.py

# dry-run does not modify
if python3 "$REPO_ROOT/tools/file-patch/file_patch.py" --cwd "$TEST_TMPDIR" --dry-run <<'EOF' >/dev/null
*** Begin Patch
*** Update File: app.py
-    print("Hello")
+    print("changed")
*** End Patch
EOF
then assert_contains 'print("Hello")' "$(cat app.py)"; fi

# escape attempt refused
if python3 "$REPO_ROOT/tools/file-patch/file_patch.py" --cwd "$TEST_TMPDIR" <<'EOF' 2>/dev/null
*** Begin Patch
*** Add File: ../escape.txt
+x
*** End Patch
EOF
then fail "expected path-escape refusal"; fi

echo "file-patch OK"
