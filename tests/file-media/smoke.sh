#!/usr/bin/env bash
source "$(dirname "$0")/../lib.sh"
cd "$TEST_TMPDIR"
# 2x3 PNG (hand-built minimal)
python3 - <<'PY'
import struct, zlib
def chunk(t, d): return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
ihdr = struct.pack(">IIBBBBB", 2, 3, 8, 2, 0, 0, 0)
raw = b"".join(b"\x00" + b"\x00\x00\x00" * 2 for _ in range(3))
png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
open("img.png", "wb").write(png)
PY
out=$(python3 "$REPO_ROOT/tools/file-media/file_media.py" img.png)
assert_eq "$(echo "$out" | jqv 'd["width"]')" "2"
assert_eq "$(echo "$out" | jqv 'd["height"]')" "3"
assert_eq "$(echo "$out" | jqv 'd["mime"]')" "image/png"
echo "file-media OK"
