"""Inspect binary media: image dimensions/type, PDF page text, or base64.

Images (PNG/JPEG/GIF/WebP): reports mime + dimensions parsed from headers.
--base64 embeds the file for downstream vision use.
PDF: extracts text with pdftotext when available.
"""

import base64
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import agentlib


def png_size(data: bytes):
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return struct.unpack(">II", data[16:24])
    return None


def gif_size(data: bytes):
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", data[6:10])
    return None


def jpeg_size(data: bytes):
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            return data[i + 7] << 8 | data[i + 8], data[i + 5] << 8 | data[i + 6]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
        i += 2 + seg_len
    return None


def webp_size(data: bytes):
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        if data[12:16] == b"VP8 ":
            w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
            h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
            return w, h
        if data[12:16] == b"VP8X":
            w = int.from_bytes(data[24:27], "little") + 1
            h = int.from_bytes(data[27:30], "little") + 1
            return w, h
    return None


def pdf_info(path: Path, args) -> dict:
    pdfinfo = agentlib.which("pdfinfo")
    info = {"mime": "application/pdf"}
    if pdfinfo:
        res = agentlib.run_cmd([pdfinfo, str(path)])
        for line in res["stdout"].splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                info[k.strip().lower().replace(" ", "_")] = v.strip()
    if args.pages or args.text:
        pdftotext = agentlib.which("pdftotext")
        if not pdftotext:
            agentlib.die("pdftotext not found — install poppler-utils for PDF text extraction")
        argv = [pdftotext]
        if args.pages:
            first, _, last = args.pages.partition("-")
            argv += ["-f", first, "-l", last or first]
        argv += [str(path), "-"]
        res = agentlib.run_cmd(argv)
        if res["exit"] != 0:
            agentlib.die(f"pdftotext failed: {res['stderr'].strip()}")
        info["text"] = res["stdout"]
    return info


def main() -> int:
    p = agentlib.arg_parser(__doc__)
    p.add_argument("path")
    p.add_argument("--base64", action="store_true", help="embed file as base64")
    p.add_argument("--pages", help="PDF page range, e.g. '1-5' (requires pdftotext)")
    p.add_argument("--text", action="store_true", help="extract all PDF text")
    args = p.parse_args()

    path = Path(args.path)
    if not path.is_file():
        agentlib.die(f"not a file: {path}", 2)

    mime = agentlib.guess_mime(path)
    info = {"path": str(path.resolve()), "size_bytes": path.stat().st_size}

    if mime == "application/pdf" or path.suffix.lower() == ".pdf":
        info.update(pdf_info(path, args))
        agentlib.emit(info)
        return 0

    head = path.read_bytes()[:64]
    dims = None
    for fn in (png_size, gif_size, jpeg_size, webp_size):
        dims = fn(head if fn is not jpeg_size else path.read_bytes()[: 1 << 16])
        if dims:
            break
    info["mime"] = mime
    if dims:
        info["width"], info["height"] = dims
    else:
        info["note"] = "unrecognized media type; metadata only"

    if args.base64:
        data = path.read_bytes()
        if len(data) > 10 * 1024 * 1024:
            agentlib.die("file too large to base64 (>10MB)", 2)
        info["base64"] = base64.b64encode(data).decode()

    agentlib.emit(info)
    return 0


if __name__ == "__main__":
    sys.exit(main())
