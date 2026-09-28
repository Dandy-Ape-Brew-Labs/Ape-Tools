# file-patch

Multi-file patches in the Codex `apply_patch` envelope. Read the patch from
stdin or `--file`.

```
*** Begin Patch
*** Update File: src/app.py
@@ def greet():
-    print("Hi")
+    print("Hello")
*** Move to: src/greet.py
*** Delete File: src/old.py
*** Add File: src/new.py
+print("new")
*** End Patch
```

- `@@ <text>` anchors a hunk: search starts at the line containing text.
- Context lines: space-prefixed or bare. `-` removes, `+` adds.
- `*** End of File` anchors a hunk at the end of the file.
- Paths are relative to `--cwd`; absolute paths and `..` escapes refuse.
- `--dry-run` validates the whole patch without writing.
- For a single targeted change, `file-edit` is simpler.
